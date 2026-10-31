# Getting Started

Yes, you are at the right point to begin implementation, but **do not set up all components at once**. Start with a small, reproducible vertical slice:

```text
Test publisher → Mosquitto → Test subscriber
```

After that works, add the database and processing service.

## 1. Which operating system should you choose?

### My recommendation: Ubuntu Linux

Use a dedicated **Ubuntu 24.04 LTS** machine or VM as the primary PoC development environment.

Why:

- Your containers will be Linux containers.
- Docker Engine runs directly on Linux without an additional virtualization layer.
- Linux shell scripts work well in local development and CI/CD.
- File permissions and volume mounts are generally simpler.
- Your GitHub repository remains portable to Windows users running Docker Desktop.
- Docker officially supports Ubuntu 24.04 LTS and provides installation instructions for the Docker Engine and Compose plugin. https://docs.docker.com/engine/install/ubuntu/, https://docs.docker.com/engine/install/

### Windows is also possible

If Windows is your primary workstation, use:

```text
Windows
└── WSL 2
    └── Ubuntu
        └── Docker Desktop WSL 2 integration
```

Docker recommends the WSL 2 backend for most Windows users. It provides a Linux environment and allows the same Linux-oriented project to run from Windows. Docker also recommends storing source code inside the WSL Linux filesystem for better performance. https://docs.docker.com/desktop/features/wsl.md, https://docs.docker.com/desktop/features/wsl/use-wsl/

One important company-related consideration: commercial use of Docker Desktop in an organization with more than 250 employees or more than USD 10 million in annual revenue requires a paid subscription. Check your company's existing Docker licensing before using Docker Desktop. https://docs.docker.com/engine/, https://docs.docker.com/desktop/setup/install/windows-install/

### Practical decision

| Situation | Recommendation |
|---|---|
| Dedicated machine or VM is available | Ubuntu 24.04 LTS with Docker Engine |
| Windows is your daily workstation | Windows + WSL 2 + Docker Desktop |
| Company has no Docker Desktop license | Ubuntu with Docker Engine |
| Team uses mixed operating systems | Linux-container-based Compose project |
| Future target is a Linux server | Develop and validate primarily on Ubuntu |

For your PoC, I would choose:

> **Ubuntu 24.04 LTS + Docker Engine + Docker Compose plugin**

Team members can still run the same repository on Windows through Docker Desktop and WSL 2.

---

## 2. Do not start with all services

Your eventual architecture contains:

```text
Sensor simulator
→ Mosquitto
→ Processing service
→ TimescaleDB
→ Grafana
```

Trying to configure everything at once makes troubleshooting difficult. Instead, build the system incrementally.

### Recommended implementation order

#### Milestone 1: Docker and Mosquitto

```text
MQTT publisher → Mosquitto → MQTT subscriber
```

Goal: verify that Docker Compose, networking and MQTT work.

#### Milestone 2: Database

```text
TimescaleDB
```

Goal: verify persistent database storage and schema initialization.

#### Milestone 3: Processing service

```text
MQTT publisher
→ Mosquitto
→ Processing service
→ TimescaleDB
```

Goal: complete the first end-to-end data path.

#### Milestone 4: Sensor simulator

Replace the manual publisher with a C# application.

#### Milestone 5: Grafana

Add dashboards only after data is correctly stored.

#### Milestone 6: Security and scaling

Add:

- MQTT authentication
- TLS
- access-control lists
- 1,000 simulated sensors
- randomized transmission windows
- retries and duplicate handling

This order keeps every change small and testable.

---

## 3. Install the prerequisites

### Option A: Ubuntu Linux

Install these tools:

- Git
- Docker Engine
- Docker Compose plugin
- An editor or IDE
- Optional MQTT test tool

Follow Docker's official Ubuntu installation procedure rather than installing older distribution packages such as `docker.io` or the legacy `docker-compose` package. Docker warns that distribution-provided or conflicting packages may differ from or conflict with the official Docker packages. https://docs.docker.com/engine/install/ubuntu/, https://docs.docker.com/engine/install/ubuntu.md

After installation, verify:

```bash
docker --version
docker compose version
git --version
```

Test Docker:

```bash
docker run --rm hello-world
```

Docker Compose V2 uses:

```bash
docker compose
```

Do not use the old command:

```bash
docker-compose
```

The standalone Compose installation is considered legacy; Docker recommends Docker Desktop or the Compose plugin. https://docs.docker.com/compose/install/

### Option B: Windows with WSL 2

1. Install or enable WSL 2.
2. Install an Ubuntu WSL distribution.
3. Install Docker Desktop.
4. Select the WSL 2 backend.
5. Enable integration for your Ubuntu distribution.
6. Clone the repository inside the Linux filesystem.

For example:

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/your-organization/smart-trash.git
```

Avoid locating the working repository under:

```text
/mnt/c/...
```

Prefer:

```text
~/projects/smart-trash
```

Docker recommends keeping the project inside the default WSL Linux distribution for the best development experience. https://docs.docker.com/desktop/features/wsl/use-wsl.md, https://docs.docker.com/desktop/features/wsl/use-wsl/

---

## 4. Create the GitHub repository first

Create one repository before creating the implementation files.

A suitable name would be:

```text
smart-trash
```

Initially, the repository should contain:

```text
smart-trash/
├── .editorconfig
├── .env.example
├── .gitattributes
├── .gitignore
├── compose.yaml
├── LICENSE
├── README.md
├── docs/
│   └── Proof of Concept for the system architecture.md
└── code/
    ├── mosquitto/
    │   ├── config/
    │   │   └── mosquitto.conf
    │   ├── data/
    │   │   └── .gitkeep
    │   └── log/
    │       └── .gitkeep
    ├── database/
    │   └── init/
    ├── processor/
    ├── simulator/
    ├── dashboard/
    │   └── provisioning/
    └── scripts/
        ├── start.sh
        ├── stop.sh
        ├── start.ps1
        └── stop.ps1
```

Use both PowerShell and shell scripts only for simple convenience commands. The actual environment definition must remain in `compose.yaml`, so the same infrastructure behaves consistently on Linux and Windows.

---

## 5. Decide what belongs in Git

### Commit these files

Commit:

- `compose.yaml`
- Dockerfiles
- Mosquitto configuration
- database initialization scripts
- dashboard (Grafana) provisioning files
- source code
- test scripts
- `.env.example`
- `.gitignore`
- documentation
- startup and cleanup scripts

### Do not commit these files

Do not commit:

- `.env`
- passwords
- database contents
- broker persistence data
- broker logs
- private keys
- private certificates
- IDE-specific user settings
- build output
- generated test data

GitHub recommends committing `.gitignore` so that everyone cloning the repository receives the same ignore rules. https://docs.github.com/en/get-started/git-basics/ignoring-files

GitHub also recommends never hardcoding credentials. Secrets should be supplied through environment variables or a secret-management mechanism. https://docs.github.com/en/get-started/learning-to-code/storing-your-secrets-safely, https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning

---

## 6. Create the initial .gitignore

Create `.gitignore` in the repository root:

```gitignore
# Local environment configuration
.env
.env.local
.env.*.local

# Secrets and certificates
*.key
*.pfx
*.p12
*.pem
!*.example.pem

# Mosquitto runtime data
code/mosquitto/data/*
!code/mosquitto/data/.gitkeep
code/mosquitto/log/*
!code/mosquitto/log/.gitkeep

# PostgreSQL runtime data
code/database/data/

# Dashboard (Grafana) runtime data
code/dashboard/data/

# Node-RED runtime and credential data
node-red/data/
node-red/.config.runtime.json

# .NET build output
**/bin/
**/obj/
*.user
*.suo

# JetBrains Rider
.idea/
*.sln.iml

# Visual Studio Code
.vscode/
!.vscode/extensions.json
!.vscode/settings.example.json

# Operating-system files
.DS_Store
Thumbs.db

# Logs and temporary data
*.log
tmp/
temp/
```

The negative rules keep placeholder files such as `.gitkeep` while excluding generated runtime data.

---

## 7. Create .env.example

The repository should contain an example file showing which variables are required.

Create `.env.example`:

```dotenv
COMPOSE_PROJECT_NAME=smart-trash

MQTT_PORT=1883
MQTT_TLS_PORT=8883

POSTGRES_DB=iot_measurements
POSTGRES_USER=iot_user
POSTGRES_PASSWORD=change-me-locally

GRAFANA_PORT=3000
NODE_RED_PORT=1880
```

Each developer creates a local copy:

```bash
cp .env.example .env
```

On PowerShell:

```powershell
Copy-Item .env.example .env
```

The `.env` file is ignored by Git. Only `.env.example` is committed.

For the earliest PoC, placeholder development passwords are acceptable, but they must never be reused in a shared or production environment.

---

## 8. First implementation: Mosquitto only

Do not add TimescaleDB or Grafana yet.

Create:

```text
code/mosquitto/config/mosquitto.conf
```

with this initial configuration:

```conf
listener 1883
protocol mqtt

allow_anonymous true

persistence true
persistence_location /mosquitto/data/

log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
```

This intentionally allows anonymous access because the first objective is to verify connectivity. It must be replaced with authentication in a later milestone.

---

## 9. Create the first compose.yaml

Create `compose.yaml` in the repository root:

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

    healthcheck:
      test:
        [
          "CMD-SHELL",
          "mosquitto_sub -h localhost -p 1883 -t '$$SYS/broker/version' -C 1 -W 5"
        ]
      interval: 10s
      timeout: 6s
      retries: 5
      start_period: 10s

networks:
  smart-trash-network:
    name: smart-trash-network

volumes:
  mosquitto-data:
    name: smart-trash-mosquitto-data

  mosquitto-log:
    name: smart-trash-mosquitto-log
```

Docker Compose defines multiple services, networks and volumes in a YAML file and manages their lifecycle with commands such as `up`, `down`, `logs` and `ps`. https://docs.docker.com/compose/, [github.com](https://github.com/docker/compose/blob/main/README.md)

Although this file currently contains only one service, it creates the foundation to which the other services will be added.

---

## 10. Validate the Compose file

Before starting anything, run:

```bash
docker compose config
```

This command parses the configuration, resolves variables and displays the resulting Compose model.

If it succeeds, start the environment:

```bash
docker compose up -d
```

Check the container:

```bash
docker compose ps
```

Expected result:

```text
smart-trash-mosquitto    running
```

View the broker logs:

```bash
docker compose logs -f mosquitto
```

Press `Ctrl+C` to stop following the logs. This does not stop the container.

---

## 11. Test MQTT without installing local MQTT tools

You can use temporary Mosquitto containers as test clients.

### Terminal 1: start a subscriber

```bash
docker run --rm -it \
  --network smart-trash-network \
  eclipse-mosquitto:2 \
  mosquitto_sub \
  -h mosquitto \
  -p 1883 \
  -t "poc/v1/+/+/measurements" \
  -q 1 \
  -v
```

### Terminal 2: publish a test batch

```bash
docker run --rm \
  --network smart-trash-network \
  eclipse-mosquitto:2 \
  mosquitto_pub \
  -h mosquitto \
  -p 1883 \
  -t "poc/v1/area-01/sensor-00001/measurements" \
  -q 1 \
  -m '{"schemaVersion":1,"messageId":"test-message-001","batchId":"test-batch-001","deviceId":"sensor-00001","areaId":"area-01","sentAt":"2026-10-31T10:00:00Z","sequenceNumber":1,"samples":[{"recordedAt":"2026-10-31T09:55:00Z","temperature":18.7,"humidity":63.1,"batteryVoltage":3.62}]}'
```

Terminal 1 should receive:

```text
poc/v1/area-01/sensor-00001/measurements {"schemaVersion":1,...}
```

If this works, you have proven:

- Docker installation;
- Docker Compose;
- the Compose network;
- Mosquitto startup;
- MQTT publication;
- MQTT wildcard subscription;
- QoS 1 messaging; and
- JSON payload transport.

That is your **first meaningful milestone**.

---

## 12. Add convenience scripts

### code/scripts/start.sh

```bash
#!/usr/bin/env bash

set -euo pipefail

docker compose config --quiet
docker compose up -d
docker compose ps
```

Make it executable:

```bash
chmod +x code/scripts/start.sh
```

### code/scripts/stop.sh

```bash
#!/usr/bin/env bash

set -euo pipefail

docker compose down
```

Make it executable:

```bash
chmod +x code/scripts/stop.sh
```

### code/scripts/start.ps1

```powershell
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
```

### code/scripts/stop.ps1

```powershell
$ErrorActionPreference = "Stop"

docker compose down

if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not stop the environment."
}
```

The scripts should remain small. Do not duplicate the infrastructure configuration in the scripts.

---

## 13. Add a useful README.md

The initial README should describe:

1. the purpose of the PoC;
2. prerequisites;
3. supported operating systems;
4. how to create `.env`;
5. how to start the environment;
6. how to test MQTT;
7. how to inspect logs;
8. how to stop the environment;
9. how to remove persistent data;
10. the current and next milestones.

The most important onboarding section should be short:

````markdown
## Quick start

1. Clone the repository.
2. Create the local environment file:

   ```bash
   cp .env.example .env
   ```

3. Start the environment:

   ```bash
   ./code/scripts/start.sh
   ```

4. Check the services:

   ```bash
   docker compose ps
   ```

5. Follow the broker logs:

   ```bash
   docker compose logs -f mosquitto
   ```

6. Stop the environment:

   ```bash
   ./code/scripts/stop.sh
   ```
````

Also document the difference between:

```bash
docker compose down
```

and:

```bash
docker compose down --volumes
```

The second command deletes named volumes and therefore removes persisted PoC data.

---

## 14. Make the first Git commit

After the Mosquitto test works:

```bash
git status
git add .
git commit -m "Initialize Docker Compose environment with Mosquitto"
git push
```

A clean first commit should contain only the reproducible environment setup, not generated runtime data.

A suitable first pull request description would state:

```text
- Add the initial Docker Compose project
- Add Eclipse Mosquitto
- Add persistent broker volumes
- Add MQTT health check
- Add Linux and Windows startup scripts
- Add local environment template
- Document the MQTT connectivity test
```

---

## 15. What comes next?

After Mosquitto works, add components one at a time:

```text
Step 1: Mosquitto
Step 2: TimescaleDB
Step 3: Database initialization scripts
Step 4: Manual MQTT-to-database processing
Step 5: C# ingestion worker
Step 6: C# sensor simulator
Step 7: Grafana
Step 8: MQTT authentication and TLS
Step 9: Fleet simulation and load tests
```

I recommend **not using Node-RED initially** if your final processing service will be written in C#. For your learning and architecture goals, a small .NET Worker Service will give you a more representative PoC and can be unit- and integration-tested from the beginning.

The first target should therefore be:

```text
This week's first milestone
───────────────────────────
GitHub repository
+ Docker Compose
+ Mosquitto
+ manual publisher
+ manual subscriber
+ documented repeatable test
```

Once this works identically on your Linux and Windows test machines, add TimescaleDB.