# Security

Security hardening guide for the DataLakehouse stack.
Follow all items in the [Production Checklist](#production-checklist) before exposing the stack to any non-local network.

---

## Secrets and Credentials

All credentials are stored in `.env` — never in `docker-compose.yaml` or source code.

### Rotate all default passwords

The `.env.example` file contains placeholder values (`change-*`, `replace-*`).
**Replace every one** before going to production:

```ini
# Critical credentials to change
POSTGRES_PASSWORD=<strong-random-password>
CLICKHOUSE_PASSWORD=<strong-random-password>
REDIS_PASSWORD=<strong-random-password>
RUSTFS_ACCESS_KEY=<your-access-key>
RUSTFS_SECRET_KEY=<strong-random-secret>
MAGE_DEFAULT_OWNER_PASSWORD=<strong-random-password>
SUPERSET_ADMIN_PASSWORD=<strong-random-password>
SUPERSET_SECRET_KEY=<64-char-random-string>
GRAFANA_ADMIN_PASSWORD=<strong-random-password>
AUTHENTIK_BOOTSTRAP_PASSWORD=<strong-random-password>
AUTHENTIK_SECRET_KEY=<64-char-random-string>
```

Generate strong random values:

```bash
openssl rand -base64 32    # for passwords
openssl rand -hex 32       # for secret keys
```

### Service isolation

Each stack service has its own isolated PostgreSQL database and user role. No service shares the admin account. This is enforced by the `postgres-bootstrap` init container.

---

## Network Exposure

### Bind IP strategy

Control which interfaces each port group listens on:

```ini
# UI/app ports — behind reverse proxy, local only
DLH_APP_BIND_IP=127.0.0.1

# Data/DB ports — accessible from LAN if needed for direct client tools
DLH_DATA_BIND_IP=127.0.0.1   # or 0.0.0.0 for LAN access

# Restrict Redis to localhost — never expose Redis to the internet
REDIS_BIND_IP=127.0.0.1
```

### LAN access

To allow LAN clients (e.g., DBeaver, BI tools) to connect directly to PostgreSQL and ClickHouse:

```ini
DLH_DATA_BIND_IP=0.0.0.0
UFW_ALLOW_DATA_PORTS=true
DLH_LAN_CIDR=192.168.1.0/24   # replace with your LAN subnet
```

Then apply firewall rules:

```bash
bash scripts/setup_ufw_docker.sh
```

### Firewall management

`scripts/setup_ufw_docker.sh` uses the Docker-aware UFW workflow:

- Opens data ports to `DLH_LAN_CIDR` only
- **Does not touch SSH rules** — safe on remote servers
- Each rule has an explicit audit comment
- `--remove` cleans up only the rules added by this script

```bash
# Apply rules
bash scripts/setup_ufw_docker.sh

# Remove managed rules
bash scripts/setup_ufw_docker.sh --remove

# Remove rules and stop the stack
bash scripts/setup_ufw_docker.sh --down
```

---

## TLS / HTTPS

For any internet-facing deployment, all traffic should go through TLS.

### Using Nginx Proxy Manager (included in the stack)

1. Access the NPM admin UI at http://localhost:28081.
2. Create **Proxy Hosts** for each service.
3. Enable SSL with Let's Encrypt (requires a public domain and ports 80/443 open).
4. Set `DLH_APP_BIND_IP=127.0.0.1` so services only accept connections through NPM.

### Internal service names for NPM upstreams

| Service | Internal upstream |
|---------|-------------------|
| Mage | `dlh-mage:6789` |
| Superset | `dlh-superset:8088` |
| Grafana | `dlh-grafana:3000` |
| Authentik | `dlh-authentik-server:9000` |
| RustFS Console | `dlh-rustfs:9001` |
| CloudBeaver | `dlh-cloudbeaver:8978` |

---

## Identity and Access Control

### Authentik (SSO / RBAC)

Authentik is included as the centralised identity provider. It can protect any UI service via OAuth2/OIDC or a forward-auth proxy flow.

- First-run setup: http://localhost:29090/if/flow/initial-setup/
- Change the default bootstrap password immediately after first login.

### Guacamole

Guacamole's default credentials are `guacadmin` / `guacadmin`. Change them on first login.

---

## Image Pinning

Avoid using `latest` image tags in production. Pinned versions ensure reproducible deployments and avoid unexpected breaking changes.

```ini
POSTGRES_IMAGE_VERSION=17-alpine
CLICKHOUSE_IMAGE_VERSION=25.4-alpine
MAGE_IMAGE_VERSION=0.9.76
SUPERSET_IMAGE_VERSION=4.1.2
GRAFANA_IMAGE_VERSION=12.0.0
REDIS_STACK_IMAGE_VERSION=7.4.2-v3
AUTHENTIK_IMAGE_VERSION=2026.2.1
MINIO_MC_IMAGE_VERSION=RELEASE.2025-04-16T18-13-26Z
```

---

## Backup Security

ClickHouse backups are stored in RustFS (`s3://backups/`). Ensure:

- `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` are strong random values.
- The RustFS Console (`DLH_RUSTFS_CONSOLE_PORT`) is not publicly accessible.
- For production, consider replicating RustFS data offsite using `mc mirror`.

---

## Production Checklist

Before promoting to a production or internet-facing environment, verify every item below:

- [ ] **Rotate all default passwords** — every `change-*` and `replace-*` value in `.env`.
- [ ] **Pin all image tags** — no `latest` in `.env`.
- [ ] **Restrict bind IPs** — `DLH_APP_BIND_IP=127.0.0.1`; expose only through the reverse proxy.
- [ ] **Enable TLS** — configure Nginx Proxy Manager with valid certificates.
- [ ] **Configure firewall** — run `setup_ufw_docker.sh` with your trusted `DLH_LAN_CIDR`.
- [ ] **Change Guacamole default password** — `guacadmin` / `guacadmin` must be rotated on first login.
- [ ] **Complete Authentik first-run setup** — set up SSO flows and change bootstrap password.
- [ ] **Set up automated backups** — add a cron job for `maintenance_tasks.py`.
- [ ] **Test restore procedure** — verify backup files in RustFS and practice the RESTORE SQL.
- [ ] **Monitor with Grafana** — confirm the `pipeline_runs` dashboard shows recent data.
- [ ] **Validate stack** — `bash scripts/stackctl.sh check-system` returns no errors.
- [ ] **Back up Docker volumes** — PostgreSQL, ClickHouse, RustFS, Redis.

---

## Security Notes Summary

| Topic | Recommendation |
|-------|----------------|
| Secrets | Rotate all default credentials; store only in `.env` |
| Network | Use `127.0.0.1` bind for UI ports; restrict DB ports to LAN CIDR |
| TLS | Terminate TLS at Nginx Proxy Manager for all internet-facing services |
| Images | Pin all image versions; avoid `latest` |
| Identity | Use Authentik SSO + RBAC for all UI services |
| Databases | Each service uses an isolated PostgreSQL role — no shared admin accounts |
| Redis | Always password-protect Redis; never expose to the internet |
| Backups | Schedule daily ClickHouse backups; replicate RustFS data offsite |
| Firewall | Use `setup_ufw_docker.sh` with explicit CIDR rules; preserve SSH rules |
