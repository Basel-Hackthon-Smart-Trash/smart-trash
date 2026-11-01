"""Reproducibly seed simulated bin telemetry into the live TimescaleDB.

The simulation functions in this module do not require PostgreSQL.  The CLI
connects only after loading the repository-root ``.env`` file and validates the
live schema before it can write anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GEOJSON = ROOT / "assets" / "geojson" / "bin-locations.geojson"
DEFAULT_START = "2025-11-01T00:00:00"
DEFAULT_END = "2026-11-01T00:00:00"
LOCAL_ZONE = ZoneInfo("Europe/Zurich")
SAMPLE_INTERVAL = timedelta(minutes=5)
GROUP_CYCLES = {
    "hotspot": timedelta(hours=24),
    "very_hot_hotspot": timedelta(hours=12),
    "regular": timedelta(hours=72),
    "low_traffic": timedelta(days=14),
}
GROUP_ORDER = tuple(GROUP_CYCLES)
BASE_GROUP_COUNTS = {"hotspot": 10, "very_hot_hotspot": 5, "regular": 50, "low_traffic": 35}
DEFAULT_SEED = 20261101
DEFAULT_AREA = "basel-demo"


class SeedError(ValueError):
    """A validation or simulation-plan error."""


@dataclass(frozen=True, slots=True)
class Bin:
    device_id: str


@dataclass(frozen=True, slots=True)
class BinPlan:
    bin: Bin
    group: str
    cycle: timedelta
    start_offset: timedelta
    fill_phase: timedelta
    initial_battery_age: timedelta
    initial_battery_lifetime: timedelta


@dataclass(frozen=True, slots=True)
class SimulationPlan:
    start: datetime
    end: datetime
    bins: tuple[BinPlan, ...]
    expected_rows: int
    battery_parameters: tuple[float, float, float, float]


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    """Load simple dotenv assignments without exposing their values."""
    if not path.is_file():
        raise SeedError(f"environment file not found: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def parse_boundary(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise SeedError(f"invalid {name}: {value!r}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_ZONE)
    return parsed.astimezone(UTC)


def load_bins(path: Path, expected_count: int) -> tuple[Bin, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SeedError(f"unable to read GeoJSON: {path}") from error
    features = payload.get("features") if isinstance(payload, dict) else None
    if payload.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise SeedError("GeoJSON must be a FeatureCollection with a features array")
    if len(features) != expected_count:
        raise SeedError(f"expected exactly {expected_count} GeoJSON features, found {len(features)}")
    identifiers: list[str] = []
    for number, feature in enumerate(features, 1):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise SeedError(f"feature {number} is not a GeoJSON Feature")
        identifier = feature.get("id")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(identifier, str) or not identifier.strip():
            raise SeedError(f"feature {number} has no non-empty id")
        if not isinstance(properties, dict) or properties.get("@id") != identifier:
            raise SeedError(f"feature {number} id and properties.@id do not match")
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise SeedError(f"feature {number} geometry must be a Point")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise SeedError(f"feature {number} geometry must have two coordinates")
        identifiers.append(identifier)
    if len(set(identifiers)) != len(identifiers):
        raise SeedError("GeoJSON feature IDs must be unique")
    return tuple(Bin(identifier) for identifier in sorted(identifiers))


def stable_rng(seed: int, device_id: str, component: str) -> random.Random:
    material = f"smart-trash-seed\0{seed}\0{component}\0{device_id}".encode()
    derived = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
    return random.Random(derived)


def group_counts(bin_count: int) -> dict[str, int]:
    raw = {group: bin_count * share / 100 for group, share in BASE_GROUP_COUNTS.items()}
    counts = {group: math.floor(value) for group, value in raw.items()}
    remainder = bin_count - sum(counts.values())
    for group in sorted(
        raw, key=lambda item: (-(raw[item] - counts[item]), GROUP_ORDER.index(item))
    )[:remainder]:
        counts[group] += 1
    return counts


def truncated_gaussian(rng: random.Random, mean: float, standard_deviation: float, lower: float, upper: float) -> float:
    if not lower <= mean <= upper or standard_deviation <= 0 or lower >= upper:
        raise SeedError("invalid truncated Gaussian parameters")
    while True:
        value = rng.gauss(mean, standard_deviation)
        if lower <= value <= upper:
            return value


def make_plan(
    bins: tuple[Bin, ...],
    start: datetime,
    end: datetime,
    seed: int,
    *,
    battery_mean_days: float = 90.0,
    battery_std_days: float = 22.5,
    battery_min_days: float = 30.0,
    battery_max_days: float = 150.0,
) -> SimulationPlan:
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise SeedError("simulation boundaries must be timezone-aware and end after start")
    if (end - start) % SAMPLE_INTERVAL:
        raise SeedError("simulation duration must be aligned to five minutes")
    counts = group_counts(len(bins))
    shuffled = list(bins)
    random.Random(seed).shuffle(shuffled)
    groups: dict[str, str] = {}
    cursor = 0
    for group in GROUP_ORDER:
        for item in shuffled[cursor : cursor + counts[group]]:
            groups[item.device_id] = group
        cursor += counts[group]
    plans: list[BinPlan] = []
    for item in bins:
        fill_rng = stable_rng(seed, item.device_id, "fill")
        battery_rng = stable_rng(seed, item.device_id, "battery")
        cycle = GROUP_CYCLES[groups[item.device_id]]
        cycle_slots = int(cycle / SAMPLE_INTERVAL)
        lifetime_days = truncated_gaussian(
            battery_rng, battery_mean_days, battery_std_days, battery_min_days, battery_max_days
        )
        lifetime = timedelta(days=lifetime_days)
        age_slots = battery_rng.randrange(int(lifetime / SAMPLE_INTERVAL) + 1)
        plans.append(
            BinPlan(
                bin=item,
                group=groups[item.device_id],
                cycle=cycle,
                start_offset=timedelta(minutes=5 * stable_rng(seed, item.device_id, "offset").randrange(576)),
                fill_phase=timedelta(minutes=5 * fill_rng.randrange(cycle_slots)),
                initial_battery_age=age_slots * SAMPLE_INTERVAL,
                initial_battery_lifetime=lifetime,
            )
        )
    expected = sum(row_count(item, start, end) for item in plans)
    return SimulationPlan(
        start, end, tuple(plans), expected,
        (battery_mean_days, battery_std_days, battery_min_days, battery_max_days),
    )


def row_count(item: BinPlan, start: datetime, end: datetime) -> int:
    first = start + item.start_offset
    if first >= end:
        return 0
    return int((end - first - timedelta(microseconds=1)) / SAMPLE_INTERVAL) + 1


def fill_value(item: BinPlan, timestamp: datetime, start: datetime) -> float:
    first_full = start + item.fill_phase
    elapsed = (timestamp - first_full).total_seconds()
    cycle_seconds = item.cycle.total_seconds()
    since_full = elapsed % cycle_seconds
    if since_full == 0:
        return 100.0
    if since_full <= SAMPLE_INTERVAL.total_seconds():
        return 0.0
    return min(100.0, max(0.0, since_full / cycle_seconds * 100.0))


def telemetry_rows(item: BinPlan, plan: SimulationPlan, seed: int) -> Iterator[tuple[datetime, str, float, float]]:
    timestamp = plan.start + item.start_offset
    lifetime_rng = stable_rng(seed, item.bin.device_id, "battery")
    # Consume the initial battery draws in the same order as make_plan.
    mean, standard_deviation, lower, upper = plan.battery_parameters
    truncated_gaussian(lifetime_rng, mean, standard_deviation, lower, upper)
    lifetime_rng.randrange(int(item.initial_battery_lifetime / SAMPLE_INTERVAL) + 1)
    battery_start = plan.start - item.initial_battery_age
    lifetime = item.initial_battery_lifetime
    depletion = battery_start + lifetime
    replacement_pending = False
    while timestamp < plan.end:
        if replacement_pending:
            battery_start = timestamp
            lifetime = timedelta(
                days=truncated_gaussian(lifetime_rng, mean, standard_deviation, lower, upper)
            )
            depletion = battery_start + lifetime
            replacement_pending = False
            battery = 100.0
        elif timestamp >= depletion:
            battery = 0.0
            replacement_pending = True
        else:
            battery = max(0.0, 100.0 * (1 - (timestamp - battery_start) / lifetime))
        yield timestamp, item.bin.device_id, round(fill_value(item, timestamp, plan.start), 6), round(battery, 6)
        timestamp += SAMPLE_INTERVAL


def batch_id(item: BinPlan, plan: SimulationPlan, seed: int) -> str:
    raw = f"{seed}|{item.bin.device_id}|{plan.start.isoformat()}|{plan.end.isoformat()}"
    return "seed-" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def db_connection():
    try:
        import psycopg
    except ImportError as error:
        raise SeedError("psycopg is required; run with `uv run --with psycopg[binary] ...`") from error
    env = load_env()
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise SeedError(f"missing database settings in .env: {', '.join(missing)}")
    return psycopg.connect(
        host="127.0.0.1",
        port=int(env.get("POSTGRES_HOST_PORT", "5432")),
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )


def validate_live_schema(connection) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name, column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'smart_trash'
              AND table_name IN ('devices', 'measurement_batches', 'measurements')
            ORDER BY table_name, ordinal_position
        """)
        columns = {(row[0], row[1]): row[2] for row in cursor.fetchall()}
        required = {
            ("devices", "device_id"), ("devices", "area_id"),
            ("measurement_batches", "batch_id"), ("measurement_batches", "message_id"),
            ("measurement_batches", "device_id"), ("measurement_batches", "sequence_number"),
            ("measurement_batches", "sent_at"), ("measurement_batches", "sample_count"),
            ("measurements", "recorded_at"), ("measurements", "device_id"),
            ("measurements", "batch_id"), ("measurements", "fulfilment_percent"),
            ("measurements", "weight_percent"), ("measurements", "battery_voltage"),
        }
        missing = sorted(required - columns.keys())
        if missing:
            raise SeedError(f"live schema is missing required columns: {missing}")
        cursor.execute("""
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'smart_trash.measurements'::regclass
              AND contype = 'u' AND pg_get_constraintdef(oid) LIKE '%(device_id, recorded_at)%'
        """)
        if cursor.fetchone() is None:
            raise SeedError("safe reruns require unique (device_id, recorded_at) on measurements")
        cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        extension = cursor.fetchone()
        cursor.execute("""
            SELECT hypertable_schema, hypertable_name, column_name, time_interval
            FROM timescaledb_information.dimensions
            WHERE hypertable_schema = 'smart_trash' AND hypertable_name = 'measurements'
        """)
        dimension = cursor.fetchone()
        cursor.execute("""
            SELECT count(*) FROM timescaledb_information.jobs
            WHERE hypertable_schema = 'smart_trash' AND hypertable_name = 'measurements'
        """)
        policies = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM smart_trash.devices")
        device_count = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM smart_trash.measurements")
        measurement_count = cursor.fetchone()[0]
    if extension is None or dimension is None:
        raise SeedError("smart_trash.measurements is not a TimescaleDB hypertable")
    return {
        "columns": columns,
        "timescaledb": extension[0],
        "dimension": dimension,
        "policies": policies,
        "device_count": device_count,
        "measurement_count": measurement_count,
    }


def print_summary(plan: SimulationPlan, schema: dict[str, object], args: argparse.Namespace) -> None:
    counts = {group: sum(item.group == group for item in plan.bins) for group in GROUP_ORDER}
    offsets = [item.start_offset for item in plan.bins]
    print(f"Source bins: {len(plan.bins)}; mapping: direct GeoJSON id -> devices.device_id")
    print("Destination: smart_trash.devices, measurement_batches, measurements")
    print(f"Time range UTC: {plan.start.isoformat()} inclusive to {plan.end.isoformat()} exclusive")
    print(f"Groups: {counts}; cycles: {GROUP_CYCLES}")
    print(f"Sampling: 5 minutes elapsed; start offsets: {min(offsets)}..{max(offsets)}")
    print("Battery: truncated Gaussian 90 +/- 22.5 days, bounds 30..150 days; stored 0..100 in battery_voltage")
    print(f"Seed: {args.seed}; expected generated telemetry rows: {plan.expected_rows}")
    print(f"Existing devices: {schema['device_count']}; existing measurements: {schema['measurement_count']}")
    print("Conflicts: never overwrite; skip existing (device_id, recorded_at); weight remains NULL")
    print(f"TimescaleDB: {schema['timescaledb']}; chunk interval: {schema['dimension'][3]}; policies: {schema['policies']}")
    if schema["policies"]:
        print("WARNING: retention/compression policies exist and may affect historical data")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")


def write_seed(connection, plan: SimulationPlan, seed: int, batch_size: int, area: str) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(
            """INSERT INTO smart_trash.devices (device_id, area_id, description, status)
               VALUES (%s, %s, %s, 'registered') ON CONFLICT (device_id) DO NOTHING""",
            [(item.bin.device_id, area, "Simulated Basel bin telemetry") for item in plan.bins],
        )
        cursor.executemany(
            """INSERT INTO smart_trash.measurement_batches
               (batch_id, message_id, device_id, sequence_number, sent_at, received_at,
                sample_count, processing_status, payload_hash)
               VALUES (%s, %s, %s, 1, %s, %s, %s, 'completed', %s)
               ON CONFLICT (batch_id) DO NOTHING""",
            [
                (batch_id(item, plan, seed), batch_id(item, plan, seed), item.bin.device_id,
                 plan.end, plan.end, row_count(item, plan.start, plan.end), "smart-trash-seed")
                for item in plan.bins
            ],
        )
    connection.commit()
    with connection.cursor() as cursor:
        cursor.execute("""CREATE TEMP TABLE seed_measurements (
            recorded_at timestamptz NOT NULL, device_id text NOT NULL, batch_id text NOT NULL,
            fulfilment_percent double precision, battery_voltage double precision
        ) ON COMMIT PRESERVE ROWS""")
    connection.commit()
    generated = inserted = 0
    started = time.monotonic()
    rows: list[tuple[datetime, str, str, float, float]] = []
    for number, item in enumerate(plan.bins, 1):
        bid = batch_id(item, plan, seed)
        for recorded_at, device_id, fill, battery in telemetry_rows(item, plan, seed):
            rows.append((recorded_at, device_id, bid, fill, battery))
            if len(rows) >= batch_size:
                inserted += _insert_rows(connection, rows)
                generated += len(rows)
                rows.clear()
        if number % 10 == 0 or number == len(plan.bins):
            elapsed = max(time.monotonic() - started, 0.001)
            print(f"bins={number}/{len(plan.bins)} generated={generated + len(rows)} inserted={inserted} "
                  f"skipped={generated - inserted} throughput={inserted / elapsed:.0f}/s")
    if rows:
        inserted += _insert_rows(connection, rows)
        generated += len(rows)
    print(f"Completed: generated={generated}, inserted={inserted}, skipped={generated - inserted}")


def _insert_rows(connection, rows: list[tuple[datetime, str, str, float, float]]) -> int:
    with connection.cursor() as cursor:
        with cursor.copy("COPY seed_measurements (recorded_at, device_id, batch_id, fulfilment_percent, battery_voltage) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        cursor.execute("""INSERT INTO smart_trash.measurements
            (recorded_at, device_id, batch_id, fulfilment_percent, battery_voltage, weight_percent)
            SELECT recorded_at, device_id, batch_id, fulfilment_percent, battery_voltage, NULL
            FROM seed_measurements ON CONFLICT (device_id, recorded_at) DO NOTHING""")
        inserted = cursor.rowcount
        cursor.execute("TRUNCATE seed_measurements")
    connection.commit()
    return inserted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geojson", type=Path, default=DEFAULT_GEOJSON)
    parser.add_argument("--expected-bin-count", type=int, default=342)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--area", default=DEFAULT_AREA)
    parser.add_argument("--battery-mean-days", type=float, default=90.0)
    parser.add_argument("--battery-std-days", type=float, default=22.5)
    parser.add_argument("--battery-min-days", type=float, default=30.0)
    parser.add_argument("--battery-max-days", type=float, default=150.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size <= 0:
        raise SeedError("--batch-size must be positive")
    bins = load_bins(args.geojson, args.expected_bin_count)
    plan = make_plan(
        bins, parse_boundary(args.start, "start"), parse_boundary(args.end, "end"), args.seed,
        battery_mean_days=args.battery_mean_days, battery_std_days=args.battery_std_days,
        battery_min_days=args.battery_min_days, battery_max_days=args.battery_max_days,
    )
    connection = db_connection()
    try:
        schema = validate_live_schema(connection)
        print_summary(plan, schema, args)
        if not args.dry_run:
            write_seed(connection, plan, args.seed, args.batch_size, args.area)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SeedError, OSError) as error:
        print(f"seed error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
