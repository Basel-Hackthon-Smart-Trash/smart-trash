$ErrorActionPreference = "Stop"

docker compose config --quiet

if ($LASTEXITCODE -ne 0) {
    throw "The Docker Compose configuration is invalid."
}

docker compose up -d

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not start the environment."
}

docker compose ps