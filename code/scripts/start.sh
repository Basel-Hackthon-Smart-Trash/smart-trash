#!/usr/bin/env bash

set -euo pipefail

docker compose config --quiet
docker compose up -d
docker compose ps