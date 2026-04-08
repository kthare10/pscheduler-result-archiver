# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

REST-based service for ingesting, storing, and visualizing pScheduler test results (latency, throughput, RTT, MTU, trace, clock data). Part of the FABRIC Testbed Ship-to-Shore Monitoring Stack. Built with Connexion (OpenAPI 3.0), SQLAlchemy ORM, TimescaleDB, and Grafana.

## Common Commands

### Run locally (no Docker)
```bash
pip install -r requirements.txt
python -m archiver          # Starts on http://localhost:3500/ps/
                            # Swagger UI: http://localhost:3500/ps/ui
```

### Run tests
```bash
pip install -r test-requirements.txt
pytest archiver/openapi_server/test/
pytest --cov=archiver archiver/    # with coverage
```

### Docker build and deploy
```bash
docker build -t kthare10/archiver:1.0.0 .
docker-compose up -d               # Full stack: timescaledb, grafana, archiver, nginx
```

## Architecture

### API-First Design
The OpenAPI 3.0 spec at `archiver/openapi_server/openapi/openapi.yaml` drives routing via Connexion. Controller functions are auto-routed to endpoints. Swagger UI is served at `/ps/ui`.

### Request Flow
```
NGINX (TLS on :8443) → /ps/* → Archiver (Waitress WSGI on :3500)
                      → /*   → Grafana (:3000)
```

### Key Layers
- **`archiver/response/`** — HTTP controllers. `measurements_controller.py` handles all ingestion (parses pScheduler JSON → Measurement objects). `archives_controller.py` handles retrieval. `security_controller.py` validates Bearer token / API key.
- **`archiver/db/`** — `models.py` defines three SQLAlchemy ORM tables: `ps_test_results` (PK: run_id, metric_name, ts), `ps_trace_hops` (PK: run_id, hop_idx), and `nav_data` (PK: ts, vessel_id — stores NMEA 0183 GPS/heading/roll/pitch/heave, COALESCE-based upsert merges partial sentences). `database_manager.py` performs idempotent upserts.
- **`archiver/common/`** — `config.py` loads YAML config into typed dataclasses with env var overrides (ARCHIVER_DSN, ARCHIVER_DB_PASSWORD). `globals.py` provides a cached singleton via `get_globals()`.
- **`archiver_client/`** — Standalone Python client library with retry logic and typed dataclasses.

### Data Model
Each measurement test produces N rows in `ps_test_results` (one per metric). The JSONB `aux` column stores raw tool output for drilldown. The composite PK `(run_id, metric_name, ts)` enables idempotent re-ingestion. `nav_data` stores NMEA 0183 navigation data with composite PK `(ts, vessel_id)`; COALESCE-based upsert merges partial sentences. TimescaleDB hypertable support provides compression and retention policies.

### Configuration
YAML config at `archiver/config.yml`. Environment variables take precedence:
1. `ARCHIVER_DSN` / `DATABASE_DSN` / `POSTGRES_DSN` for database connection
2. `ARCHIVER_DB_PASSWORD` overrides config file password

### Docker Compose Stack
Four services: `timescaledb` (PostgreSQL 16 + TimescaleDB), `grafana` (with provisioned datasources and 3 dashboards: Pairs, Navigation Correlation, Time-Aligned Environmental Correlation), `archiver` (this app), `nginx` (TLS termination). Health checks enforce startup ordering.

### Nav API Endpoints
- `POST /ps/measurements/nav` — Ingest NMEA navigation data (batch of GPS/heading/motion points)
- `GET /ps/nav` — Retrieve navigation data by time range, vessel ID

### Supported Metrics
throughput_mbps, retransmits, delay_ms, jitter_ms, loss_pct, rtt_ms (mean/min/max), mtu_bytes, hop_count, clock_diff_ms, clock_offset_s.
