$ErrorActionPreference = "Stop"

docker compose down

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not stop the environment."
}