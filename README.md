# DataLakehouse

A modern local-first lakehouse stack with Docker Compose, medallion-style data flow, ETL orchestration, and analytics dashboards.

## Documentation

- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Variables Reference](docs/VARIABLES_REFERENCE.md)
- [Pipeline Guide](docs/PIPELINE_GUIDE.md)
- [Lakehouse Architecture](docs/LAKEHOUSE_ARCHITECTURE.md)
- [Refactoring Summary](docs/LAKEHOUSE_REFACTORING_SUMMARY.md)

## Quick Start

### Prerequisites

- Docker Engine + Docker Compose plugin
- uv (for host-side Python scripts)
- Linux/macOS host recommended

Check tools:

```bash
docker --version
docker compose version
uv --version
```

### 1. Clone and install host dependencies

```bash
git clone https://github.com/HoangThinh2024/DataLakehouse.git
cd DataLakehouse
uv sync --all-groups
```

### 2. Run guided setup (recommended)

```bash
bash scripts/setup.sh
```

What setup does:

1. Prompts for all key configuration values.
2. Generates `.env`.
3. Creates `web_network` if missing.
4. Deploys all services.

### 3. Verify stack health

```bash
bash scripts/stackctl.sh check-system
```

## Access URLs (default ports)

- RustFS Console: http://localhost:29101
- Mage: http://localhost:26789
- NocoDB: http://localhost:28082
- Superset: http://localhost:28088
- Grafana: http://localhost:23001
- PostgreSQL: localhost:25432
- ClickHouse HTTP: http://localhost:28123

## Lifecycle Management

Use `scripts/stackctl.sh` as the main operational command.

### Core commands

```bash
bash scripts/stackctl.sh up
bash scripts/stackctl.sh down
bash scripts/stackctl.sh redeploy
bash scripts/stackctl.sh redeploy --with-etl
```

### Diagnostics and logs

```bash
bash scripts/stackctl.sh status
bash scripts/stackctl.sh health
bash scripts/stackctl.sh logs all
bash scripts/stackctl.sh logs dlh-mage
bash scripts/stackctl.sh inspect dlh-postgres
```

### Environment management

```bash
bash scripts/stackctl.sh check-env
bash scripts/stackctl.sh validate-env
bash scripts/stackctl.sh sync-env
```

### Reset options

```bash
# Keep volumes
bash scripts/stackctl.sh reset

# Remove volumes (destructive)
bash scripts/stackctl.sh reset --hard
```

## Firewall and LAN Access

Configure Docker-aware firewall rules with:

```bash
bash scripts/setup_ufw_docker.sh
```

Notes:

- Uses `ufw-docker` style management.
- Adds descriptive comments to rules.
- Supports cleanup commands:

```bash
bash scripts/setup_ufw_docker.sh --remove
bash scripts/setup_ufw_docker.sh --down
```

## Architecture

![DataLakehouse architecture](docs/assets/datalakehouse-architecture.svg)

Data path:

```text
PostgreSQL / CSV -> RustFS Bronze -> RustFS Silver -> RustFS Gold -> ClickHouse -> Superset/Grafana
```

## ETL and Dashboard Automation

Run ETL and dashboard provisioning:

```bash
uv run python scripts/run_etl_and_dashboard.py
```

Or include ETL in lifecycle redeploy:

```bash
bash scripts/stackctl.sh redeploy --with-etl
```

## Project Structure

```text
DataLakehouse/
├── docker-compose.yaml
├── .env.example
├── pyproject.toml
├── uv.lock
├── clickhouse/
├── grafana/
├── mage/
├── postgres/
├── superset/
├── scripts/
│   ├── setup.sh
│   ├── stackctl.sh
│   ├── setup_ufw_docker.sh
│   ├── run_etl_and_dashboard.py
│   ├── create_superset_demo_dashboard.py
│   ├── demo_to_lakehouse.py
│   └── verify_lakehouse_architecture.py
└── docs/
    ├── DEPLOYMENT_GUIDE.md
    ├── VARIABLES_REFERENCE.md
    ├── PIPELINE_GUIDE.md
    ├── LAKEHOUSE_ARCHITECTURE.md
    ├── LAKEHOUSE_REFACTORING_SUMMARY.md
    └── assets/datalakehouse-architecture.svg
```

## Troubleshooting

### Services not healthy

```bash
bash scripts/stackctl.sh health
bash scripts/stackctl.sh logs all
```

### Port conflicts

```bash
bash scripts/stackctl.sh validate-env
bash scripts/stackctl.sh sync-env
bash scripts/stackctl.sh redeploy
```

### Full rebuild

```bash
bash scripts/stackctl.sh reset --hard
bash scripts/setup.sh
```

## Security Notes

- Change all default passwords before production use.
- Restrict `DLH_BIND_IP` and `DLH_LAN_CIDR` appropriately.
- Use TLS/reverse proxy for internet-exposed deployments.

## License

MIT
