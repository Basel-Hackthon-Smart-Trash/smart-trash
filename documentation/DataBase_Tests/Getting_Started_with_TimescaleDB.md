# Step 2: Add TimescaleDB

## Target architecture for this step

```text
Docker Compose
├── Mosquitto
│   └── MQTT works as established in Step 1
│
└── TimescaleDB
    ├── PostgreSQL database
    ├── TimescaleDB extension
    ├── automatically initialized schema
    ├── persistent Docker volume
    └── health check
```

The result should be reproducible with:

```bash
git clone ...
cp .env.example .env
docker compose up -d
```

---

## 1. Implementation plan

Complete Step 2 in this order:

1. Create the database directory structure.
2. Extend `.env.example`.
3. Add TimescaleDB to `compose.yaml`.
4. Add database initialization scripts.
5. Start the environment.
6. Verify the TimescaleDB extension.
7. Verify the tables and hypertable.
8. Insert and query a test measurement.
9. Verify persistence after a container restart.
10. Update the repository documentation.
11. Commit the completed milestone.

Do not add the processor, dashboard or sensor simulator yet.

---

# 2. Select the TimescaleDB image

As of October 31, 2026, TimescaleDB 2.31.0 is the latest published release, and images are available for PostgreSQL 18, 17 and 16. [[github.com]](https://github.com/timescale/timescaledb/releases), https://hub.docker.com/r/timescale/timescaledb/tags/

For a reproducible team environment, use a fixed version:

```text
timescale/timescaledb:2.31.0-pg18
```

Avoid this in the shared repository:

```text
timescale/timescaledb:latest-pg18
```

The TimescaleDB image deliberately has no generic `latest` tag because an automatic update could also change the PostgreSQL major version, which would require a database upgrade procedure. The image documentation recommends pinning an explicit version for production-style environments. https://hub.docker.com/r/timescale/timescaledb/

For your PoC, I recommend:

```dotenv
TIMESCALEDB_IMAGE=timescale/timescaledb:2.31.0-pg18
```

Keeping the image name in `.env.example` makes future upgrades explicit and reviewable.

---

# 3. Create the database directory structure

Your repository should now look like this:

```text
smart-trash/
├── .env
├── .env.example
├── .gitignore
├── compose.yaml
├── README.md
├── docs/
│   ├── Getting_Started.md
│   └── Proof of Concept for the system architecture.md
└── code/
    ├── mosquitto/
    │   └── config/
    │       └── mosquitto.conf
    ├── database/
    │   └── init/
    │       ├── 001-create-extension.sql
    │       ├── 002-create-schema.sql
    │       └── 003-create-hypertable.sql
    ├── processor/
    ├── simulator/
    ├── dashboard/
    └── scripts/
```

You do not need a `code/database/data` directory because we will use a named Docker volume for the database files.

The SQL files will be mounted into:

```text
/docker-entrypoint-initdb.d/
```

The TimescaleDB image is based on the official PostgreSQL image, so it supports the normal PostgreSQL environment variables and initialization behavior. [[github.com]](https://github.com/timescale/timescaledb-docker)

---

# 4. Extend .env.example

Update `.env.example`:

```dotenv
COMPOSE_PROJECT_NAME=smart-trash

MQTT_PORT=1883
MQTT_TLS_PORT=8883

TIMESCALEDB_IMAGE=timescale/timescaledb:2.31.0-pg18
POSTGRES_HOST_PORT=5432
POSTGRES_DB=smart_trash
POSTGRES_USER=smart_trash_app
POSTGRES_PASSWORD=change-me-locally

DASHBOARD_PORT=3000
```

Then update your local `.env` file with the same variables.

If your `.env` already contains the MQTT settings, add only the database section:

```dotenv
TIMESCALEDB_IMAGE=timescale/timescaledb:2.31.0-pg18
POSTGRES_HOST_PORT=5432
POSTGRES_DB=smart_trash
POSTGRES_USER=smart_trash_app
POSTGRES_PASSWORD=your-local-development-password
```

Do not commit `.env`.

Commit only:

```text
.env.example
```

## Naming distinction

Use these names consistently:

| Purpose            | Value                          |
|--------------------|--------------------------------|
| Compose project    | `smart-trash`                  |
| Docker network     | `smart-trash-network`          |
| Database name      | `smart_trash`                  |
| Database user      | `smart_trash_app`              |
| Database service   | `timescaledb`                  |
| Database container | `smart-trash-timescaledb`      |
| Database volume    | `smart-trash-timescaledb-data` |

Docker resource names can use hyphens. PostgreSQL identifiers are easier to handle with underscores.

---

# 5. Add TimescaleDB to compose.yaml

Your existing Mosquitto configuration may differ slightly. Keep the working configuration from Step 1 and add the `timescaledb` service and database volume.

A complete initial version could look like this:

```yaml
name: smart-trash

services:
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: smart-trash-mosquitto
    restart: unless-stopped

    ports:
      - "${MQTT_PORT:-1883}:1883"

    volumes:
      - ./code/mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log

    networks:
      - smart-trash-network

  timescaledb:
    image: "${TIMESCALEDB_IMAGE}"
    container_name: smart-trash-timescaledb
    restart: unless-stopped

    environment:
      POSTGRES_DB: "${POSTGRES_DB}"
      POSTGRES_USER: "${POSTGRES_USER}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
      TIMESCALEDB_TELEMETRY: "off"

    ports:
      - "127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"

    volumes:
      - timescaledb-data:/var/lib/postgresql/data
      - ./code/database/init:/docker-entrypoint-initdb.d:ro

    networks:
      - smart-trash-network

    healthcheck:
      test:
        [
          "CMD-SHELL",
          "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"
        ]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

networks:
  smart-trash-network:
    name: smart-trash-network

volumes:
  mosquitto-data:
    name: smart-trash-mosquitto-data

  mosquitto-log:
    name: smart-trash-mosquitto-log

  timescaledb-data:
    name: smart-trash-timescaledb-data
```

## Important configuration details

### Bind the database port to localhost

This mapping:

```yaml
ports:
  - "127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432"
```

means the database is reachable from your development machine but is not intentionally exposed on every network interface.

Your local database client connects to:

```text
Host: localhost
Port: 5432
```

Other containers connect through the internal Docker network:

```text
Host: timescaledb
Port: 5432
```

The future processing service must therefore use:

```text
Host=timescaledb;Port=5432;...
```

and not:

```text
Host=localhost;Port=5432;...
```

Inside a container, `localhost` refers to that container itself.

### Use a named volume

This mapping:

```yaml
- timescaledb-data:/var/lib/postgresql/data
```

keeps the database files outside the lifecycle of the container. Recreating the container will therefore not delete the data.

### Use a health check

A running database container is not necessarily ready to accept connections. The `pg_isready` health check determines whether PostgreSQL is ready. Docker Compose can later use `condition: service_healthy` to delay the processing service until the database is operational. https://docs.docker.com/compose/how-tos/startup-order/, https://docs.docker.com/compose/how-tos/startup-order.md

### Disable telemetry for the PoC

The TimescaleDB Docker image supports:

```yaml
TIMESCALEDB_TELEMETRY: "off"
```

This setting is applied during initial database creation. The image documentation notes that changing this environment variable later does not reconfigure an already initialized database volume. [[github.com]](https://github.com/timescale/timescaledb-docker)

---

# 6. Create the initialization scripts

The files are executed alphabetically, so use numeric prefixes.

## 001-create-extension.sql

Create:

```text
code/database/init/001-create-extension.sql
```

with:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

This ensures the TimescaleDB extension is enabled in the `smart_trash` database.

---

## 002-create-schema.sql

Create:

```text
code/database/init/002-create-schema.sql
```

with:

```sql
CREATE SCHEMA IF NOT EXISTS smart_trash;

CREATE TABLE IF NOT EXISTS smart_trash.devices
(
    device_id          text                     PRIMARY KEY,
    area_id            text                     NOT NULL,
    description        text,
    firmware_version   text,
    registered_at      timestamp with time zone NOT NULL DEFAULT now(),
    last_seen_at       timestamp with time zone,
    status             text                     NOT NULL DEFAULT 'registered',

    CONSTRAINT ck_devices_status
        CHECK (status IN ('registered', 'online', 'offline', 'disabled'))
);

CREATE TABLE IF NOT EXISTS smart_trash.measurement_batches
(
    batch_id           text                     PRIMARY KEY,
    message_id         text                     NOT NULL UNIQUE,
    device_id          text                     NOT NULL,
    sequence_number    bigint                   NOT NULL,
    sent_at            timestamp with time zone NOT NULL,
    received_at        timestamp with time zone NOT NULL DEFAULT now(),
    sample_count       integer                  NOT NULL,
    processing_status  text                     NOT NULL DEFAULT 'received',
    payload_hash       text,

    CONSTRAINT fk_measurement_batches_device
        FOREIGN KEY (device_id)
        REFERENCES smart_trash.devices (device_id),

    CONSTRAINT ck_measurement_batches_sample_count
        CHECK (sample_count >= 0),

    CONSTRAINT ck_measurement_batches_status
        CHECK
        (
            processing_status IN
            (
                'received',
                'processing',
                'completed',
                'rejected'
            )
        )
);

CREATE TABLE IF NOT EXISTS smart_trash.measurements
(
    recorded_at         timestamp with time zone NOT NULL,
    device_id           text                     NOT NULL,
    batch_id            text                     NOT NULL,
    fulfilment_percent  double precision,
    weight_percent      double precision,
    battery_voltage     double precision,
    quality_code        integer                  NOT NULL DEFAULT 0,
    received_at         timestamp with time zone NOT NULL DEFAULT now(),

    CONSTRAINT fk_measurements_device
        FOREIGN KEY (device_id)
        REFERENCES smart_trash.devices (device_id),

    CONSTRAINT fk_measurements_batch
        FOREIGN KEY (batch_id)
        REFERENCES smart_trash.measurement_batches (batch_id),

    CONSTRAINT uq_measurements_device_time
        UNIQUE (device_id, recorded_at),

    CONSTRAINT ck_measurements_weight
        CHECK
        (
            weight_percent IS NULL
            OR weight_percent BETWEEN 0 AND 100
        ),

    CONSTRAINT ck_measurements_battery
        CHECK
        (
            battery_voltage IS NULL
            OR battery_voltage >= 0
        )
);

CREATE TABLE IF NOT EXISTS smart_trash.ingestion_errors
(
    error_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at        timestamp with time zone NOT NULL DEFAULT now(),
    mqtt_topic         text                     NOT NULL,
    message_id         text,
    error_code         text                     NOT NULL,
    error_description  text                     NOT NULL,
    original_payload   jsonb
);
```

## Why start with a wide measurement table?

Your current sensor message contains:

- fulfilment level;
- weight; and
- battery voltage.

Because these measurements appear to be consistent across the sensor fleet, the wide-table model is easier to query and visualize.

If future sensors report substantially different measurements, we can later introduce a more generic measurement model.

---

# 7. Convert the measurement table into a hypertable

Create:

```text
code/database/init/003-create-hypertable.sql
```

with:

```sql
SELECT create_hypertable(
    'smart_trash.measurements',
    by_range('recorded_at'),
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS ix_measurements_device_recorded_at
    ON smart_trash.measurements
    (device_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS ix_measurement_batches_device_sent_at
    ON smart_trash.measurement_batches
    (device_id, sent_at DESC);

CREATE INDEX IF NOT EXISTS ix_measurement_batches_received_at
    ON smart_trash.measurement_batches
    (received_at DESC);
```

The hypertable partitions the measurement table according to `recorded_at`.

That is more appropriate than partitioning by `received_at`, because your primary analytical dimension is when the sensor measured the condition, not when the hourly batch happened to reach the server.

---

# 8. Validate the Compose configuration

Before starting the environment, run:

```bash
docker compose config
```

For a shorter validation without printing the complete resolved configuration:

```bash
docker compose config --quiet
```

Check that the environment variables are available:

```bash
docker compose config --environment
```

Be careful when sharing output from this command because it may display the local database password.

---

# 9. Start TimescaleDB

Start only the database first:

```bash
docker compose up -d timescaledb
```

Check its state:

```bash
docker compose ps
```

Initially, it may show:

```text
health: starting
```

After initialization, it should show:

```text
healthy
```

Follow the initialization logs:

```bash
docker compose logs -f timescaledb
```

On the first startup, the logs should show:

1. PostgreSQL database initialization;
2. creation of the configured database;
3. execution of `001-create-extension.sql`;
4. execution of `002-create-schema.sql`;
5. execution of `003-create-hypertable.sql`;
6. PostgreSQL becoming ready for connections.

Press `Ctrl+C` to stop following the logs. This does not stop the database.

Then start the complete current environment:

```bash
docker compose up -d
```

---

# 10. Important initialization behavior

The SQL initialization files are executed only when PostgreSQL initializes an **empty data directory**.

That means this sequence:

```bash
docker compose down
docker compose up -d
```

does not execute the SQL initialization files again because the named volume still contains the initialized database.

This is intentional and prevents your schema from being recreated on every restart.

If you make changes to the SQL files during this early PoC phase and want to recreate the database completely, use:

```bash
docker compose down
docker volume rm smart-trash-timescaledb-data
docker compose up -d timescaledb
```

Alternatively:

```bash
docker compose down --volumes
docker compose up -d
```

However, `docker compose down --volumes` removes **all named volumes belonging to the Compose project**, including Mosquitto persistence.

Use it only when you intentionally want to remove all persistent PoC data.

A safer database-only reset is:

```bash
docker compose down
docker volume rm smart-trash-timescaledb-data
docker compose up -d timescaledb
```

---

# 11. Verify database connectivity

You do not need to install PostgreSQL tools locally. Use `psql` inside the TimescaleDB container.

Open an interactive database session:

```bash
docker compose exec timescaledb \
  psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB"
```

If your shell does not load the `.env` variables as shell environment variables, use the explicit PoC values:

```bash
docker compose exec timescaledb \
  psql \
  --username smart_trash_app \
  --dbname smart_trash
```

You should see a prompt similar to:

```text
smart_trash=#
```

Leave `psql` with:

```text
\q
```

---

# 12. Verify the TimescaleDB extension

Inside `psql`, run:

```sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname = 'timescaledb';
```

You should receive one row containing:

```text
timescaledb
```

You can also run the query directly from your terminal:

```bash
docker compose exec timescaledb \
  psql \
  --username smart_trash_app \
  --dbname smart_trash \
  --command "SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';"
```

---

# 13. Verify the created tables

Inside `psql`:

```text
\dt smart_trash.*
```

Expected tables:

```text
smart_trash.devices
smart_trash.ingestion_errors
smart_trash.measurement_batches
smart_trash.measurements
```

Inspect the measurement table:

```text
\d smart_trash.measurements
```

---

# 14. Verify the hypertable

Run:

```sql
SELECT
    hypertable_schema,
    hypertable_name,
    num_dimensions,
    num_chunks
FROM timescaledb_information.hypertables
WHERE hypertable_schema = 'smart_trash'
  AND hypertable_name = 'measurements';
```

You should receive one row for:

```text
smart_trash.measurements
```

At this point, `num_chunks` might be zero because no measurements have been inserted yet.

---

# 15. Insert test data

The foreign keys require the records to be inserted in this order:

1. device;
2. measurement batch;
3. measurements.

## Insert a test device

```sql
INSERT INTO smart_trash.devices
(
    device_id,
    area_id,
    description,
    firmware_version,
    status
)
VALUES
(
    'sensor-00001',
    'area-01',
    'PoC fulfilment and weight sensor',
    '0.1.0',
    'online'
)
ON CONFLICT (device_id) DO NOTHING;
```

## Insert a test batch

```sql
INSERT INTO smart_trash.measurement_batches
(
    batch_id,
    message_id,
    device_id,
    sequence_number,
    sent_at,
    sample_count,
    processing_status,
    payload_hash
)
VALUES
(
    'sensor-00001-20261031T150000Z',
    'test-message-001',
    'sensor-00001',
    1,
    '2026-10-31T15:00:00Z',
    2,
    'completed',
    'development-test'
)
ON CONFLICT (batch_id) DO NOTHING;
```

## Insert two measurements

```sql
INSERT INTO smart_trash.measurements
(
    recorded_at,
    device_id,
    batch_id,
    fulfilment_percent,
    weight_percent,
    battery_voltage,
    quality_code
)
VALUES
(
    '2026-10-31T14:50:00Z',
    'sensor-00001',
    'sensor-00001-20261031T150000Z',
    18.7,
    63.1,
    3.62,
    0
),
(
    '2026-10-31T14:55:00Z',
    'sensor-00001',
    'sensor-00001-20261031T150000Z',
    18.8,
    62.9,
    3.62,
    0
)
ON CONFLICT (device_id, recorded_at) DO NOTHING;
```

---

# 16. Query the test data

Run:

```sql
SELECT
    recorded_at,
    device_id,
    fulfilment_percent,
    weight_percent,
    battery_voltage,
    quality_code
FROM smart_trash.measurements
ORDER BY recorded_at;
```

Expected result:

```text
2026-10-31 14:50:00+00 | sensor-00001 | 18.7 | 63.1 | 3.62 | 0
2026-10-31 14:55:00+00 | sensor-00001 | 18.8 | 62.9 | 3.62 | 0
```

Test a time-series aggregation:

```sql
SELECT
    time_bucket('1 hour', recorded_at) AS measurement_hour,
    device_id,
    avg(fulfilment_percent) AS average_fulfilment,
    avg(weight_percent) AS average_weight,
    min(battery_voltage) AS minimum_battery_voltage
FROM smart_trash.measurements
GROUP BY
    measurement_hour,
    device_id
ORDER BY
    measurement_hour,
    device_id;
```

This verifies that TimescaleDB-specific functions are working, rather than only ordinary PostgreSQL.

---

# 17. Verify database persistence

Stop the containers:

```bash
docker compose down
```

Start them again:

```bash
docker compose up -d
```

Wait until TimescaleDB is healthy:

```bash
docker compose ps
```

Query the measurements again:

```bash
docker compose exec timescaledb \
  psql \
  --username smart_trash_app \
  --dbname smart_trash \
  --command "SELECT device_id, recorded_at, fulfilment_percent FROM smart_trash.measurements ORDER BY recorded_at;"
```

The two measurements should still exist.

This verifies that:

- the container can be recreated;
- the database volume persists;
- the schema remains available; and
- database data survives normal Compose shutdown and startup.

---

# 18. Optional: Connect from Rider or DBeaver

Use these connection settings:

```text
Database type: PostgreSQL
Host: localhost
Port: 5432
Database: smart_trash
User: smart_trash_app
Password: value from your local .env
SSL mode: Disable for this local PoC step
```

Do not use `timescaledb` as the host name from Rider or DBeaver running directly on your machine. That name is only resolved inside the Docker network.

Use:

```text
localhost
```

from the host machine.

Use:

```text
timescaledb
```

from another container.

---

# 19. Add a database verification script

Create:

```text
code/scripts/test-database.sh
```

```bash
#!/usr/bin/env bash

set -euo pipefail

echo "Checking TimescaleDB container status..."
docker compose ps timescaledb

echo "Checking TimescaleDB extension..."
docker compose exec -T timescaledb \
    psql \
    --username smart_trash_app \
    --dbname smart_trash \
    --set ON_ERROR_STOP=1 \
    --command "
        SELECT extname, extversion
        FROM pg_extension
        WHERE extname = 'timescaledb';
    "

echo "Checking smart-trash tables..."
docker compose exec -T timescaledb \
    psql \
    --username smart_trash_app \
    --dbname smart_trash \
    --set ON_ERROR_STOP=1 \
    --command "
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema = 'smart_trash'
        ORDER BY table_name;
    "

echo "Checking measurements hypertable..."
docker compose exec -T timescaledb \
    psql \
    --username smart_trash_app \
    --dbname smart_trash \
    --set ON_ERROR_STOP=1 \
    --command "
        SELECT hypertable_schema, hypertable_name
        FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'smart_trash'
          AND hypertable_name = 'measurements';
    "

echo "TimescaleDB verification completed successfully."
```

Make it executable:

```bash
chmod +x code/scripts/test-database.sh
```

For PowerShell, create:

```text
code/scripts/Test-Database.ps1
```

```powershell
$ErrorActionPreference = "Stop"

Write-Host "Checking TimescaleDB container status..."
docker compose ps timescaledb

if ($LASTEXITCODE -ne 0) {
    throw "Could not retrieve the TimescaleDB container status."
}

Write-Host "Checking TimescaleDB extension..."
docker compose exec -T timescaledb `
    psql `
    --username smart_trash_app `
    --dbname smart_trash `
    --set ON_ERROR_STOP=1 `
    --command "SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';"

if ($LASTEXITCODE -ne 0) {
    throw "The TimescaleDB extension verification failed."
}

Write-Host "Checking smart-trash tables..."
docker compose exec -T timescaledb `
    psql `
    --username smart_trash_app `
    --dbname smart_trash `
    --set ON_ERROR_STOP=1 `
    --command "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'smart_trash' ORDER BY table_name;"

if ($LASTEXITCODE -ne 0) {
    throw "The database table verification failed."
}

Write-Host "Checking measurements hypertable..."
docker compose exec -T timescaledb `
    psql `
    --username smart_trash_app `
    --dbname smart_trash `
    --set ON_ERROR_STOP=1 `
    --command "SELECT hypertable_schema, hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_schema = 'smart_trash' AND hypertable_name = 'measurements';"

if ($LASTEXITCODE -ne 0) {
    throw "The hypertable verification failed."
}

Write-Host "TimescaleDB verification completed successfully."
```

These first scripts use the known PoC database names. When the environment is stable, we can pass values from `.env` more generically.

---

# 20. Update .gitignore

Ensure that these entries are present:

```gitignore
# Local environment configuration
.env
.env.local
.env.*.local

# Database runtime data
code/database/data/
*.sql.bak
*.dump

# PostgreSQL client password files
.pgpass
pgpass.conf

# Logs
*.log
```

Because the actual PostgreSQL data uses a named Docker volume, it does not appear inside the Git repository. Nevertheless, ignoring `code/database/data/` protects the repository if someone later switches to a bind-mounted database directory.

---

# 21. Definition of done for Step 2

Step 2 is complete when all of these statements are true:

- TimescaleDB is defined in `compose.yaml`.
- A fixed TimescaleDB image version is used.
- Database credentials are read from `.env`.
- `.env` is excluded from Git.
- `.env.example` documents every required variable.
- The database uses a named Docker volume.
- The database has a working health check.
- The TimescaleDB extension is enabled.
- The `smart_trash` schema is created automatically.
- The `devices` table exists.
- The `measurement_batches` table exists.
- The `measurements` table is a hypertable.
- The `ingestion_errors` table exists.
- A test device, batch and measurement can be inserted.
- A TimescaleDB `time_bucket` query works.
- Data remains after `docker compose down` and `docker compose up -d`.
- A team member can repeat the setup from the repository documentation.

---

# 22. Suggested Git commit

After all verification steps pass:

```bash
git status
git add .
git commit -m "Add TimescaleDB persistence and initial schema"
git push
```

The commit should contain:

```text
compose.yaml
.env.example
.gitignore
code/database/init/001-create-extension.sql
code/database/init/002-create-schema.sql
code/database/init/003-create-hypertable.sql
code/scripts/test-database.sh
code/scripts/Test-Database.ps1
README.md
```

It must not contain:

```text
.env
passwords
database files
database dumps
runtime logs
```

## What Step 3 will add

After this milestone is stable, Step 3 should be:

```text
Mosquitto
    ↓ MQTT subscription
.NET ingestion worker
    ↓ PostgreSQL connection
TimescaleDB
```

The C# worker will subscribe to:

```text
poc/v1/+/+/measurements
```

It will validate each JSON batch and insert records into the tables created during this step.