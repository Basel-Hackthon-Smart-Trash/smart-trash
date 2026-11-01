import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from api.server import make_handler


def start_server(tmp_path: Path):
    snapshot = tmp_path / "bins.json"
    snapshot.write_text(json.dumps({
        "generated_at": "2026-11-01T06:00:00",
        "simulated": True,
        "bins": [],
        "routes": [],
    }), encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(snapshot))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def request(server, path):
    connection = HTTPConnection(*server.server_address)
    connection.request("GET", path)
    response = connection.getresponse()
    body = json.loads(response.read())
    headers = dict(response.getheaders())
    connection.close()
    return response.status, body, headers


def test_bins_endpoint_returns_snapshot(tmp_path):
    server, thread = start_server(tmp_path)
    try:
        status, body, headers = request(server, "/api/bins")
    finally:
        server.shutdown()
        thread.join()

    assert status == 200
    assert body["generated_at"] == "2026-11-01T06:00:00"
    assert "bins" in body and "routes" in body
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_health_endpoint_reports_snapshot(tmp_path):
    server, thread = start_server(tmp_path)
    try:
        status, body, _ = request(server, "/api/health")
    finally:
        server.shutdown()
        thread.join()

    assert status == 200
    assert body == {
        "status": "ok",
        "generated_at": "2026-11-01T06:00:00",
        "simulated": True,
    }


def test_missing_endpoint_returns_404(tmp_path):
    server, thread = start_server(tmp_path)
    try:
        status, body, _ = request(server, "/wrong")
    finally:
        server.shutdown()
        thread.join()

    assert status == 404
    assert body == {"error": "not found"}
