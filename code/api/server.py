"""Small read-only API for the latest prediction and routing snapshot.

The daily prediction job creates ``code/web/data/bins.json``. This server does
not run prediction or routing; it only exposes that already-generated file.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "web" / "data" / "bins.json"


def load_snapshot(path: Path) -> dict[str, Any]:
    """Load and minimally validate the shared frontend snapshot."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("bins"), list):
        raise ValueError("snapshot must be an object containing a bins list")
    if not isinstance(data.get("routes"), list):
        raise ValueError("snapshot must contain a routes list")
    return data


def make_handler(data_path: Path):
    class ApiHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            self._send_json(204, {})

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/api/health":
                try:
                    snapshot = load_snapshot(data_path)
                    self._send_json(200, {
                        "status": "ok",
                        "generated_at": snapshot.get("generated_at"),
                        "simulated": snapshot.get("simulated", True),
                    })
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    self._send_json(503, {"status": "unavailable", "error": str(error)})
                return

            if self.path == "/api/bins":
                try:
                    self._send_json(200, load_snapshot(data_path))
                except FileNotFoundError:
                    self._send_json(404, {"error": "snapshot not found"})
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    self._send_json(500, {"error": str(error)})
                return

            self._send_json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:
            print(f"API: {format % args}")

    return ApiHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.data))
    print(f"Smart Trash API listening on http://{args.host}:{args.port}")
    print(f"Serving snapshot: {args.data}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
