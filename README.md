# pscheduler-result-archiver

The **Result Archiver** is a REST-based service for ingesting, storing, and visualizing [pScheduler](https://docs.perfsonar.net/pscheduler_intro.html) test results such as latency, throughput, RTT, MTU, and trace data.
It performs idempotent upserts (by `run_id` and `metric_name`) into a TimescaleDB backend and exposes endpoints for archival and retrieval, along with built-in OpenAPI/Swagger documentation.

The stack also includes **Grafana** for visualization and **NGINX** for TLS termination and routing.

---

## Architecture Overview

```
    ┌──────────────┐
    │  Test Nodes  │  (pScheduler JSON uploads)
    └──────┬───────┘
           │  HTTPS /ps/measurements/*
           ▼
    ┌──────────────────────────┐
    │   Archiver (Python)      │
    │ Connexion + Waitress API │
    │ - /ps/measurements/*    │
    │ - /ps/archives/{run_id} │
    │ - /ps/ui (Swagger UI)   │
    └──────────┬───────────────┘
               │ SQL
               ▼
    ┌──────────────────────────┐
    │   TimescaleDB (Postgres) │
    │   Database: perfsonar    │
    │   Tables: measurements   │
    └──────────┬───────────────┘
               │ Grafana datasource (readonly)
               ▼
    ┌──────────────────────────┐
    │   Grafana Dashboards     │
    │   Pre-provisioned views  │
    │   http(s)://<host>:3000  │
    └──────────┬───────────────┘
               │
               ▼
    ┌──────────────────────────┐
    │   NGINX Reverse Proxy    │
    │   TLS (port 8443)        │
    │   /ps → archiver:3500   │
    │   /    → grafana:3000    │
    └──────────────────────────┘
```

---

## Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/kthare10/pscheduler-result-archiver.git
cd pscheduler-result-archiver
```

### 2. Prepare directories

```bash
mkdir -p tsdb_data grafana_data provisioning/datasources provisioning/dashboards logs certs
```

### 3. Generate or copy certificates

Place your valid certificate and key files under:

```
certs/fullchain.pem
certs/privkey.pem
```

> **Note:** The `certs/` directory is git-ignored. Never commit TLS certificates to version control.

### 4. Configure environment

Copy the example environment file and fill in your secrets:

```bash
cp .env.example .env
```

Required variables in `.env`:

| Variable                | Description                              |
| ----------------------- | ---------------------------------------- |
| `ARCHIVER_DB_PASSWORD`  | PostgreSQL password for `grafana_writer`  |
| `ARCHIVER_BEARER_TOKEN` | Bearer token for API authentication       |
| `GRAFANA_ADMIN_PASSWORD`| Grafana admin UI password                 |
| `GRAFANA_ADMIN_USER`    | Grafana admin username (default: `admin`) |

Docker Compose will refuse to start if required variables are missing.

Optionally review `archiver/config.yml` for pool tuning, logging, and SSL settings. Environment variables always take precedence over config file values.

---

## Docker Compose Deployment

### Compose file overview

```yaml
services:
  timescaledb:
    image: timescale/timescaledb:latest-pg16
    environment:
      - POSTGRES_DB=perfsonar
      - POSTGRES_USER=grafana_writer
      - POSTGRES_PASSWORD=${ARCHIVER_DB_PASSWORD}
    volumes:
      - ./tsdb_data:/var/lib/postgresql/data

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
    volumes:
      - ./grafana_data:/var/lib/grafana
      - ./provisioning/datasources:/etc/grafana/provisioning/datasources
      - ./provisioning/dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      timescaledb:
        condition: service_healthy

  archiver:
    build:
      context: .
      dockerfile: Dockerfile
    image: kthare10/archiver:1.0.0
    environment:
      - APP_CONFIG_PATH=/etc/archiver/config/config.yml
      - ARCHIVER_DB_PASSWORD=${ARCHIVER_DB_PASSWORD}
      - ARCHIVER_BEARER_TOKEN=${ARCHIVER_BEARER_TOKEN}
    volumes:
      - ./archiver/config.yml:/etc/archiver/config/config.yml
      - ./logs:/var/log/archiver
    depends_on:
      - grafana

  nginx:
    image: nginx:1
    ports: ["8443:443"]
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf
      - ./certs/fullchain.pem:/etc/ssl/public.pem
      - ./certs/privkey.pem:/etc/ssl/private.pem
    depends_on:
      - archiver
```

---

### Start all services

```bash
docker-compose up -d
```

### Check running containers

```bash
docker ps
```

### Logs

```bash
docker-compose logs -f archiver
docker-compose logs -f archiver-nginx
```

---

## Access Points

| Service          | URL (default)                   | Notes                             |
| ---------------- |---------------------------------| --------------------------------- |
| **Archiver API** | `https://localhost:8443/ps`     | Base path for ingestion endpoints |
| **Swagger UI**   | `https://localhost:8443/ps/ui`  | OpenAPI documentation             |
| **Grafana**      | `https://localhost:8443/`       | Dashboards / visualization        |
| **TimescaleDB**  | `timescaledb:5432`              | Internal DB connection            |

---

## Authentication

* API supports `Bearer` and `X-API-Key` auth schemes.
* The bearer token is set via the `ARCHIVER_BEARER_TOKEN` environment variable.
* The service will refuse to start if the token is missing or set to a known insecure default.

---

## Example Ingestion Request

```bash
curl -sk -X POST https://localhost:8443/ps/measurements/throughput \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <your-token>' \
  -d '{
        "run_id": "test-123",
        "src": {"ip": "192.168.1.10", "name": "ship-a"},
        "dst": {"ip": "23.134.232.50", "name": "shore"},
        "direction": "forward",
        "raw": {"tool": "iperf3", "result": {"bits_per_second": 50000000}}
      }'
```

Expected response:

```json
{
  "status": 200,
  "type": "no_content"
}
```

---

## Grafana Integration

Grafana is pre-provisioned with:

* a **TimescaleDB datasource** (user: `grafana_writer`)
* optional prebuilt dashboards under `provisioning/dashboards`

Login credentials are controlled by `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` environment variables.

To reset password:

```bash
docker exec -it grafana grafana-cli admin reset-admin-password newpass
docker restart grafana
```

---

## HTTPS and Reverse Proxy

`nginx/default.conf` routes:

* `/ps/*` → Archiver (`http://archiver:3500`)
* `/` → Grafana (`http://grafana:3000`)

TLS is enabled via `/etc/ssl/public.pem` and `/etc/ssl/private.pem`.

NGINX is configured with:
* Security headers (HSTS, X-Frame-Options, X-Content-Type-Options, etc.)
* Rate limiting (10 req/s per IP on `/ps` endpoints)
* Request body size limit (10 MB)

---

## Development

Run the API standalone (no Docker):

```bash
pip install -r requirements.txt
python -m archiver
```

Default listens on port `3500`.
Swagger UI: `http://localhost:3500/ps/ui`

### Run tests

```bash
pip install -r test-requirements.txt
pytest archiver/openapi_server/test/
```

---

## Maintenance

### Backup TimescaleDB

```bash
docker exec -t timescaledb pg_dump -U grafana_writer perfsonar > backup.sql
```

### Upgrade containers

```bash
docker-compose pull
docker-compose up -d --build
```

---

## License

MIT License - 2025 Komal Thareja
Part of the FABRIC Testbed Ship-to-Shore Monitoring Stack.

---

## References

* [pScheduler Documentation](https://docs.perfsonar.net/pscheduler_intro.html)
* [TimescaleDB](https://www.timescale.com/)
* [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
* [Connexion Framework](https://connexion.readthedocs.io/en/latest/)
