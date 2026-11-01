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