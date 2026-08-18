# DataPulse

**A data contract and pipeline observability platform**

DataPulse is a small platform for monitoring existing data pipelines and making their health visible. It answers the operational questions that are easy to miss when a pipeline appears to have completed successfully:

- Did the pipeline run?
- Was the source file or API response valid?
- Did the schema change?
- Is the data late?
- Did row counts change unexpectedly?
- Which tables failed quality checks?
- Who owns the failure?
- Can the run be retried?

DataPulse is designed as a platform product rather than another Bronze/Silver/Gold analytics project. It can monitor existing pipelines and connect them through shared metadata, data contracts, quality checks, lineage, incidents, and alerts.

## Architecture

```text
Existing data pipelines
          |
          v
DataPulse Python SDK / CLI
          |
          v
FastAPI metadata API
          |
          v
PostgreSQL control database
          |
          v
Quality checks + lineage metadata
          |
          v
Grafana dashboards and alerts
```

## Core capabilities

DataPulse will provide a central place to:

1. Register pipelines and their datasets.
2. Store expected schemas and freshness requirements.
3. Record every pipeline run and its outcome.
4. Validate row counts, null rates, duplicates, freshness, and accepted values.
5. Detect schema drift and unexpected source changes.
6. Create incidents for failed or late data.
7. Track ownership and retryability for failures.
8. Display pipeline health in dashboards.
9. Send alerts through email, Slack, or webhooks.
10. Connect existing projects as monitored pipelines.

## Recommended stack

| Area | Technology | Purpose |
| --- | --- | --- |
| Language | Python | SDK, CLI, validation, and platform services |
| Metadata API | FastAPI | Documented endpoints for pipeline and dataset metadata |
| Control database | PostgreSQL | Pipeline runs, datasets, contracts, incidents, and ownership |
| Data quality | Great Expectations or custom SQL checks | Reusable validation rules |
| Lineage | OpenLineage | Job, run, input, and output metadata |
| Observability | Grafana | Dashboards, alert rules, and operational visibility |
| Local development | Docker Compose | Reproducible local services |
| CI/CD | GitHub Actions | Automated tests and delivery workflows |

SQLite can be used initially if PostgreSQL setup becomes a distraction during early development. PostgreSQL is the intended control database for the platform.

Useful references:

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Great Expectations validation](https://docs.greatexpectations.io/docs/core/run_validations/)
- [OpenLineage specification](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md)
- [Grafana alerting](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/link-alert-rules-to-panels/)

## MVP scope

The first version should focus on a complete monitoring loop for one existing pipeline:

- Register a pipeline and its datasets.
- Define expected schemas and freshness requirements.
- Capture pipeline run metadata.
- Run basic data quality checks.
- Detect schema drift.
- Persist failures and incidents.
- Show pipeline health in Grafana.
- Send an alert when a run fails, arrives late, or violates a contract.
- Connect one existing project as the first monitored pipeline.

## Example run record

```yaml
pipeline_name: healthcare_analytics
run_id: 2026-08-18-001
status: failed
source_row_count: 680000
target_row_count: 679842
freshness_status: passed
schema_status: failed
quality_status: failed
failure_reason: unexpected column added
```

This record makes the run outcome actionable: freshness passed, while schema and quality checks failed because the source contained an unexpected column.

## Why DataPulse?

Existing projects already demonstrate experience with:

- Databricks and S3
- Medallion architecture
- Batch and incremental processing
- dbt and Spark
- Dimensional modeling
- BI dashboards

DataPulse adds the platform capabilities that are often missing from individual analytics projects:

- API development
- Metadata modeling
- Platform engineering
- Data contracts
- Observability and alerting
- Incident management
- Reusable tooling
- CI/CD and containerization

The result is a platform that ties existing projects together instead of creating another disconnected pipeline.

## Project direction

**DataPulse: A Data Contract and Pipeline Observability Platform**

The long-term goal is to make pipeline health, data validity, ownership, and recovery visible from one operational interface.

## Status

Phase 1 complete. Core monitoring loop implemented: pipeline registration, data contracts, run lifecycle with 4 validation checks, incident creation, structured logging, and 35 automated tests. Demo available via `datapulse demo`.

## Guides

- [Phase 1 guide](phase-1-guide.md)
- [Phase 2 guide](phase-2-guide.md)
