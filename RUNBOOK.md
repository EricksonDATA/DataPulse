# DataPulse Operational Runbook

This runbook covers day-to-day operations, incident recovery, and maintenance procedures for DataPulse.

## Table of Contents

1. [Identifying Failures](#1-identifying-failures)
2. [Inspecting Check Results](#2-inspecting-check-results)
3. [Pipeline Ownership](#3-pipeline-ownership)
4. [Retrying a Run](#4-retrying-a-run)
5. [Backfilling Historical Data](#5-backfilling-historical-data)
6. [Resolving Incidents](#6-resolving-incidents)
7. [Contract Changes](#7-contract-changes)
8. [Secret Rotation](#8-secret-rotation)
9. [Database Backup and Restore](#9-database-backup-and-restore)
10. [Monitoring DataPulse Itself](#10-monitoring-datapulse-itself)

---

## 1. Identifying Failures

### From Grafana

1. Open `http://localhost:3000/d/datapulse-health`
2. The **Pipeline Status** panel shows the latest run for each pipeline
3. Red rows = FAILED, yellow = LATE
4. The **Open Incidents** panel shows unresolved failures

### From the API

```bash
# List recent runs for a pipeline
curl http://localhost:8000/pipelines/{name}/runs?status=failed

# Get the latest health for a pipeline
curl http://localhost:8000/pipelines/{name}/health

# List open incidents
curl http://localhost:8000/pipelines/{name}/incidents
```

### From the CLI

```bash
# Run the adapter to submit a new run
python -m datapulse.adapters.healthcare_analytics \
  --source /path/to/source.csv \
  --target /path/to/target.csv \
  --api-url http://localhost:8000
```

### From webhook alerts

Alerts fire to `http://api:8000/webhook/receiver` and are logged at:

```bash
curl http://localhost:8000/webhook/log
```

---

## 2. Inspecting Check Results

Each run produces 5 checks. To inspect why a check failed:

```bash
# Get full run details including check results
curl http://localhost:8000/pipelines/{name}/runs/{run_id} | python -m json.tool
```

The response includes:

```json
{
  "checks": [
    {
      "type": "schema_compatibility",
      "status": "failed",
      "expected": {"columns": ["id", "name"], "column_count": 2},
      "observed": {"columns": ["id", "name", "extra"], "column_count": 3},
      "message": "Unexpected columns: ['extra']"
    }
  ]
}
```

### Check types and what they validate

| Check | Validates | Common failure |
|---|---|---|
| `source_readability` | File exists and is parseable | Missing file, corrupt CSV |
| `schema_compatibility` | Columns match contract | Extra/missing columns, type mismatches |
| `target_schema_compatibility` | Target columns match contract | dbt output schema changed |
| `row_count` | Row count within min/max range | Too few or too many rows |
| `freshness` | Latest timestamp within max_age | Stale data, broken pipeline schedule |

---

## 3. Pipeline Ownership

Each pipeline has an `owner` field set at registration time. The owner is responsible for:

- Investigating failures
- Fixing the upstream pipeline
- Acknowledging incidents
- Updating contracts when the schema intentionally changes

### Current ownership

| Pipeline | Owner | Contact |
|---|---|---|
| healthcare_analytics | data-platform | #data-platform Slack channel |
| ecommerce_inventory | data-platform | #data-platform Slack channel |

To update ownership:

```bash
# Re-register with new owner (idempotent)
curl -X POST http://localhost:8000/pipelines \
  -H "Content-Type: application/json" \
  -d '{"name": "healthcare_analytics", "owner": "new-owner"}'
```

---

## 4. Retrying a Run

### When is a retry safe?

A retry is safe when:
- The underlying pipeline is idempotent (re-running produces the same output)
- The target write behavior is understood (append vs overwrite)
- The source data hasn't changed since the original run

A retry is **NOT** safe when:
- The pipeline appends data (would create duplicates)
- The source data has been updated (would produce different results)
- The target table is being used by downstream consumers

### How to retry

```bash
# Option 1: Same run_id (idempotent — returns cached result)
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "healthcare_analytics",
    "run_id": "2026-08-18-61cfb3",
    "source_path": "/app/examples/fixtures/healthcare_admissions.csv"
  }'

# Option 2: New run_id (creates a new auditable run)
python -m datapulse.adapters.healthcare_analytics \
  --source /app/examples/fixtures/healthcare_admissions.csv \
  --api-url http://localhost:8000
```

### Run ID convention

Run IDs follow the pattern: `YYYY-MM-DD-{6-char-hex}`

For retries, use the same run_id. For backfills, generate a new run_id.

---

## 5. Backfilling Historical Data

Backfills are new runs with different run_ids for historical data periods.

### Process

1. Identify the data period to backfill
2. Generate a new run_id for each period
3. Submit each run via the SDK or API
4. Monitor the run history for failures

```bash
# Example: backfill July 2026 data
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "healthcare_analytics",
    "run_id": "backfill-2026-07",
    "source_path": "/data/healthcare/admissions_2026-07.csv"
  }'
```

### Important

- Each backfill run creates a separate auditable entry
- Backfills do NOT overwrite previous runs
- The `GET /pipelines/{name}/runs` endpoint shows all runs including backfills

---

## 6. Resolving Incidents

### From the API

```bash
# Acknowledge an incident (marks it as acknowledged)
curl -X POST http://localhost:8000/runs/{run_id}/acknowledge
```

### Incident lifecycle

```
OPEN → ACKNOWLEDGED → RESOLVED
```

- **OPEN**: Alert has fired, no action taken yet
- **ACKNOWLEDGED**: Owner is aware and investigating
- **RESOLVED**: Root cause fixed, pipeline healthy again

### When to resolve

Resolve an incident when:
- The root cause has been fixed
- The pipeline has completed a successful run
- The data is fresh and within contract limits

---

## 7. Contract Changes

When the upstream data schema changes intentionally:

### Update the contract

```bash
# Register a new contract version (v2)
curl -X POST http://localhost:8000/datasets \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "healthcare_analytics",
    "dataset_name": "admissions_source",
    "role": "source",
    "contract_version": 2,
    "schema_definition": {
      "admission_id": {"type": "string", "nullable": false},
      "patient_id": {"type": "string", "nullable": false},
      "new_field": {"type": "integer", "nullable": true}
    },
    "freshness": {"max_age_hours": 72, "timestamp_column": "admission_date"},
    "quality_rules": {"unique_keys": ["admission_id"], "min_row_count": 1000, "max_row_count": 200000}
  }'
```

### Contract versioning

- Contracts are immutable once created
- Each dataset can have multiple contract versions
- Runs can specify a contract version: `"contract_version": 2`
- If no version is specified, the latest version is used
- Old contract versions are preserved for audit trail

### What to do

1. Create the new contract version
2. Update the adapter to use the new version (if needed)
3. Run the pipeline and verify checks pass
4. Update the Grafana dashboard if new columns need visualization

---

## 8. Secret Rotation

### Local development

Secrets are in environment variables. To rotate:

1. Update `DATAPULSE_DATABASE_URL` in `.env` or shell
2. Restart the API: `docker compose restart api`

### Docker Compose

Update `docker-compose.yml`:

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: new-password-here
  api:
    environment:
      DATAPULSE_DATABASE_URL: postgresql+psycopg://datapulse:new-password-here@postgres:5432/datapulse
```

Then:

```bash
docker compose down
docker compose up -d
```

### Production

- Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Never commit secrets to git
- The `.env.example` file contains placeholder values only

---

## 9. Database Backup and Restore

### Backup

```bash
# Backup from Docker PostgreSQL
docker compose exec postgres pg_dump -U datapulse datapulse > backup_$(date +%Y%m%d).sql

# Backup with compression
docker compose exec postgres pg_dump -U datapulse datapulse | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore

```bash
# Restore from backup
cat backup_20260818.sql | docker compose exec -T postgres psql -U datapulse datapulse

# Restore from compressed backup
gunzip -c backup_20260818.sql.gz | docker compose exec -T postgres psql -U datapulse datapulse
```

### Fresh start (destroy all data)

```bash
docker compose down -v  # -v removes the pgdata volume
docker compose up -d
python -m alembic upgrade head
```

### Migration management

```bash
# Check current migration version
python -m alembic current

# Upgrade to latest
python -m alembic upgrade head

# Downgrade one version
python -m alembic downgrade -1
```

---

## 10. Monitoring DataPulse Itself

### Health checks

```bash
# API health
curl http://localhost:8000/health

# Readiness (API + database)
curl http://localhost:8000/ready

# Grafana health
curl http://localhost:3000/api/health
```

### Docker status

```bash
# Check all services
docker compose ps

# View logs
docker compose logs api --tail=50
docker compose logs grafana --tail=50
docker compose logs postgres --tail=50
```

### What to watch for

| Signal | Action |
|---|---|
| API returns 500 | Check `docker compose logs api` |
| Grafana shows "No data" | Check PostgreSQL connectivity |
| Alerts not firing | Check Grafana alert rules and webhook contact point |
| Migrations fail | Check `alembic current` and database connectivity |
| Tests fail in CI | Check GitHub Actions logs |

---

## Quick Reference

### Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API availability |
| GET | `/ready` | API + database readiness |
| POST | `/pipelines` | Register pipeline |
| POST | `/datasets` | Register dataset + contract |
| POST | `/runs` | Submit a run |
| GET | `/pipelines/{name}/runs` | List runs |
| GET | `/pipelines/{name}/runs/{run_id}` | Get run details |
| GET | `/pipelines/{name}/health` | Latest run health |
| GET | `/pipelines/{name}/incidents` | List open incidents |
| GET | `/datasets/{name}/contract` | Get contract summary |
| POST | `/runs/{run_id}/acknowledge` | Acknowledge incidents |
| POST | `/webhook/receiver` | Receive alert webhooks |
| GET | `/webhook/log` | View webhook history |

### Grafana

| URL | Purpose |
|---|---|
| `http://localhost:3000` | Grafana UI (admin/admin) |
| `http://localhost:3000/d/datapulse-health` | Pipeline Health dashboard |
| `http://localhost:3000/alerting/list` | Alert rules |

### Docker

```bash
docker compose up -d          # Start all services
docker compose down            # Stop all services
docker compose down -v         # Stop and delete data
docker compose restart api     # Restart API only
docker compose logs -f api     # Follow API logs
```
