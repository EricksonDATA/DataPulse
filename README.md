# DataPulse

**A data contract and pipeline observability platform**

DataPulse monitors existing data pipelines and makes their health visible. It answers the operational questions that are easy to miss when a pipeline appears to have completed successfully:

- Did the pipeline run?
- Was the source file or API response valid?
- Did the schema change?
- Is the data late?
- Did row counts change unexpectedly?
- Which tables failed quality checks?
- Who owns the failure?
- Can the run be retried?

## Architecture

```text
Existing data pipelines (healthcare, ecommerce, ...)
          |
          v
DataPulse Python SDK / CLI adapter
          |
          v
FastAPI metadata API (13 endpoints)
          |
          v
PostgreSQL control database (7 tables, Alembic migrations)
          |
          v
Grafana dashboards + 4 alert rules → webhook notifications
```

## Quick start

```bash
# Clone and install
git clone https://github.com/EricksonDATA/DataPulse.git
cd DataPulse
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -q

# Start the stack (Docker required)
docker compose up -d

# Run the healthcare adapter
python -m datapulse.adapters.healthcare_analytics \
    --source /app/examples/fixtures/healthcare_admissions.csv \
    --target /app/examples/fixtures/healthcare_fact_admission.csv \
    --api-url http://localhost:8000

# Run the ecommerce orders adapter
python -m datapulse.adapters.ecommerce_orders \
    --source /app/examples/fixtures/ecommerce_orders.csv \
    --target /app/examples/fixtures/ecommerce_order_facts.csv \
    --api-url http://localhost:8000

# Open Grafana dashboard
# http://localhost:3000 (admin/admin)
```

## Core capabilities

| Capability | Status |
|---|---|
| Pipeline and dataset registration | ✅ |
| Versioned data contracts (schema, freshness, quality) | ✅ |
| 5 quality checks (readability, schema, target schema, row count, freshness) | ✅ |
| Run lifecycle with idempotent submissions | ✅ |
| Incident creation and ownership tracking | ✅ |
| Grafana dashboard with 7 panels | ✅ |
| 4 alert rules (pipeline failed, freshness, incidents, schema drift) | ✅ |
| Webhook notification delivery | ✅ |
| PostgreSQL + SQLite dual-database support | ✅ |
| Alembic migrations | ✅ |
| GitHub Actions CI (5 jobs) | ✅ |
| Branch protection | ✅ |
| Operational runbook | ✅ |

## Integrating a new pipeline

DataPulse is pipeline-agnostic. To monitor a new pipeline, create two things:

### 1. Contract definition

Create `src/datapulse/contracts/your_pipeline.py`:

```python
PIPELINE_NAME = "your_pipeline"
PIPELINE_OWNER = "your-team"

SOURCE_SCHEMA = {
    "id": {"type": "string", "nullable": False},
    "value": {"type": "decimal", "nullable": False},
    "created_at": {"type": "timestamp", "nullable": False},
}

SOURCE_FRESHNESS = {
    "max_age_hours": 24,
    "timestamp_column": "created_at",
}

SOURCE_QUALITY = {
    "unique_keys": ["id"],
    "min_row_count": 100,
    "max_row_count": 1000000,
}

# Optional: target contract for source-to-target reconciliation
TARGET_SCHEMA = {
    "id": {"type": "string", "nullable": False},
    "value": {"type": "decimal", "nullable": False},
}
```

### 2. Adapter

Create `src/datapulse/adapters/your_pipeline.py`:

```python
import sys
import uuid
from datetime import datetime, timezone

from datapulse.contracts.your_pipeline import (
    PIPELINE_NAME, PIPELINE_OWNER,
    SOURCE_SCHEMA, SOURCE_FRESHNESS, SOURCE_QUALITY,
)
from datapulse.sdk import DataPulseClient


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()

    client = DataPulseClient(args.api_url)

    # Register
    client.register_pipeline(PIPELINE_NAME, PIPELINE_OWNER)
    client.register_dataset(
        pipeline_name=PIPELINE_NAME,
        dataset_name="your_source",
        role="source",
        contract_version=1,
        schema_definition=SOURCE_SCHEMA,
        freshness=SOURCE_FRESHNESS,
        quality_rules=SOURCE_QUALITY,
    )

    # Run
    run_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"
    result = client.submit_run(
        pipeline_name=PIPELINE_NAME,
        run_id=run_id,
        source_path=args.source,
    )

    if result["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
```

### 3. Run it

```bash
python -m datapulse.adapters.your_pipeline --source /path/to/data.csv
```

That's it. DataPulse handles:
- Pipeline and dataset registration (idempotent)
- Contract storage and versioning
- All 5 quality checks
- Incident creation and ownership
- Dashboard and alert integration

No changes to the core are needed.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | API availability |
| GET | `/ready` | API + database readiness |
| POST | `/pipelines` | Register pipeline |
| POST | `/datasets` | Register dataset + contract |
| POST | `/runs` | Submit a run |
| GET | `/pipelines/{name}/runs` | List runs (paginated, filterable) |
| GET | `/pipelines/{name}/runs/{run_id}` | Get run details |
| GET | `/pipelines/{name}/health` | Latest run health |
| GET | `/pipelines/{name}/incidents` | List open incidents |
| GET | `/datasets/{name}/contract` | Get contract summary |
| POST | `/runs/{run_id}/acknowledge` | Acknowledge incidents |
| POST | `/webhook/receiver` | Receive alert webhooks |
| GET | `/webhook/log` | View webhook history |
| GET | `/metrics` | Operational metrics |

## Authentication

API key authentication is optional. Set `DATAPULSE_API_KEY` to enable:

```bash
# Enable authentication
export DATAPULSE_API_KEY="your-secret-key"

# All requests must include X-API-Key header
curl -H "X-API-Key: your-secret-key" http://localhost:8000/pipelines

# /health and /ready are always public
curl http://localhost:8000/health  # No key needed
```

SDK usage with API key:

```python
client = DataPulseClient("http://localhost:8000", api_key="your-secret-key")
```

## Webhook security

The webhook endpoint (`POST /webhook/receiver`) accepts Grafana alerts.

Set `DATAPULSE_WEBHOOK_SECRET` to require a shared secret:

```bash
# In docker-compose.yml or .env
DATAPULSE_WEBHOOK_SECRET=my-webhook-secret
```

When set, Grafana must send the secret in the `X-Webhook-Secret` header.
Configure this in the Grafana webhook contact point settings.

When not set (development mode), the webhook is open.

## Grafana dashboard

Provisioned at `http://localhost:3000/d/datapulse-health` with 7 panels:

1. **Pipeline Status** — latest run per pipeline
2. **Run History** — timeline of all runs
3. **Freshness: Age vs Threshold** — data age vs contract limit
4. **Row Counts: Source vs Target** — reconciliation bar chart
5. **Failed Checks by Type** — pie chart of check failures
6. **Open Incidents** — unresolved incidents by owner
7. **Recent Schema Drift Events** — schema failures in last 30 days

4 alert rules fire to the webhook at `http://api:8000/webhook/receiver`.

## Monitored pipelines

| Pipeline | Adapter | Data type | Freshness |
|---|---|---|---|
| healthcare_analytics | `adapters/healthcare_analytics.py` | CSV (hospital admissions) | 72h |
| ecommerce_orders | `adapters/ecommerce_orders.py` | CSV (daily orders) | 12h |

## Project structure

```
DataPulse/
├── src/datapulse/
│   ├── api/            # FastAPI endpoints
│   ├── adapters/       # Pipeline adapters
│   ├── checks/         # Quality check implementations
│   ├── contracts/      # Contract definitions
│   ├── db/             # Repositories
│   ├── models/         # SQLAlchemy models
│   ├── services/       # Business logic
│   ├── sdk.py          # Python SDK
│   └── cli.py          # CLI entry point
├── tests/
│   ├── unit/           # Check tests
│   └── integration/    # API + PostgreSQL tests
├── grafana/            # Dashboard + alert provisioning
├── migrations/         # Alembic migrations
├── examples/fixtures/  # Test data (synthetic only)
├── docker-compose.yml  # PostgreSQL + API + Grafana
├── Dockerfile          # API container
├── RUNBOOK.md          # Operational runbook
└── pyproject.toml      # Project config
```

## Status

**v0.1.0** — Phase 2 complete, Phase 3 in progress.

- 53 tests passing, 7 SQLite-specific skipped
- CI pipeline: 5 jobs (lint, sqlite, postgresql, migrations, cli)
- Branch protection: requires CI before merge

## Guides

- [Phase 1 guide](phase-1-guide.md)
- [Phase 2 guide](phase-2-guide.md)
- [Operational runbook](RUNBOOK.md)
