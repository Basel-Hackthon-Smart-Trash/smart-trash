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