# Simulated Telemetry Seeding

`code/database/seed.py` generates reproducible simulated telemetry and writes it
to the existing PostgreSQL + TimescaleDB database. It does not run migrations,
create permanent tables, truncate data, or overwrite telemetry.

## Live mapping

The inspected live database is PostgreSQL 18.6 with TimescaleDB 2.31.0. The
relevant tables are:

- `smart_trash.devices`: GeoJSON `id` and `properties.@id` become `device_id`.
- `smart_trash.measurement_batches`: one deterministic batch per device.
- `smart_trash.measurements`: five-minute telemetry, hypertabled by `recorded_at`.

The live table has a unique `(device_id, recorded_at)` constraint. The GeoJSON
currently contains 342 unique `node/...` features, so the default seed assigns
all 342 bins. Group counts are scaled proportionally to 34 hotspot, 17 very hot
hotspot, 171 regular, and 120 low traffic bins. These are simulated categories.

`fulfilment_percent` is stored from 0 to 100. The existing battery column is
named `battery_voltage`, but the approved simulation stores the requested 0 to
100 battery percentage there. `weight_percent` is explicitly `NULL` and is
never generated.

## Defaults and configuration

- Time zone: `Europe/Zurich` for CLI boundaries; timestamps are written as UTC `timestamptz`.
- Start: `2025-11-01T00:00:00 Europe/Zurich`, inclusive.
- End: `2026-11-01T00:00:00 Europe/Zurich`, exclusive.
- Sampling: five elapsed minutes.
- Seed: `20261101`.
- Battery: truncated Gaussian, mean 90 days, standard deviation 22.5 days, bounds 30 to 150 days.
- Default batch size: 10,000 rows.

The script loads `.env` relative to the repository root and uses
`POSTGRES_HOST_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
Secrets are not printed.

## Commands

Non-writing live validation and plan summary:

```bash
uv run --with 'psycopg[binary]' python code/database/seed.py --dry-run
```

Small-scope writing example (explicitly writes data; use a temporary short
range and a separate seed if desired):

```bash
uv run --with 'psycopg[binary]' python code/database/seed.py \
  --start 2025-11-01T00:00:00 --end 2025-11-01T02:00:00
```

Full-year population command:

```bash
uv run --with 'psycopg[binary]' python code/database/seed.py
```

The full-year command is the population operation. It was not run while
developing this change.

## Reruns and recovery

Devices and batches use `ON CONFLICT DO NOTHING`. Existing measurement rows are
skipped through the live unique `(device_id, recorded_at)` constraint. Rows are
staged in a temporary table and committed in bounded batches; a failed batch is
rolled back, while earlier committed batches remain safe to rerun. Progress
reports distinguish generated, inserted, and skipped rows.

The dry-run performs schema and input validation and does not create temporary
tables or write any database object. The live database had no retention,
compression, or continuous-aggregate policies at discovery time.

## Tests

Run the pure simulation tests without database access:

```bash
pytest code/database/tests/test_seed.py
```

Known limitation: `battery_voltage` is a legacy column name. The approved
simulation decision is to store the requested percentage representation there;
real sensor ingestion should define a separate conversion contract before
mixing real voltage readings with this simulated dataset.
