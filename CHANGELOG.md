# Changelog

All notable changes to DataPulse are documented in this file.

## [1.0.0] — 2026-08-20

### Added

**Core Platform**
- FastAPI metadata API with 14 endpoints (health, readiness, pipelines, datasets, runs, incidents, contracts, metrics, webhooks)
- 5 quality checks: source readability, schema compatibility, target schema compatibility, row count, freshness
- Versioned data contracts with schema, freshness, and quality rules
- Idempotent run submission with duplicate-run detection
- Incident creation with ownership tracking and retryable flags
- Operational metrics endpoint (GET /metrics)

**Database**
- PostgreSQL control database with 8 tables (pipelines, datasets, contracts, pipeline_runs, check_results, incidents, notifications, alembic_version)
- Alembic migrations (3 migrations: initial schema, target_schema_compatibility, notifications)
- SQLite support for local development and unit tests

**S3 Integration**
- DatasetReference abstraction supporting 5 reference types: local, s3, table, query, partition
- Injectable S3 client factory with explicit credential configuration
- S3 mock mode for development (DATAPULSE_S3_MOCK=true)
- LocalStack integration tests (8 tests)
- Streaming CSV reader for large datasets

**Grafana**
- Provisioned dashboard with 7 panels (pipeline status, run history, freshness, row counts, failed checks, incidents, schema drift)
- 4 alert rules (pipeline failed, freshness exceeded, open incidents, schema drift)
- Webhook notification delivery with shared secret validation

**Authentication & Security**
- API key authentication via X-API-Key header
- Webhook secret validation via X-Webhook-Secret header
- Production-like docker-compose with non-default Grafana credentials

**Testing**
- 92 tests passing (unit + integration)
- PostgreSQL integration tests (8 tests)
- S3 integration tests with LocalStack (8 tests)
- Realistic pipeline tests with 1000-row datasets (6 tests)
- Operational workflow tests (24 tests)
- Deployment verification tests (15 tests)
- Backup and recovery tests (16 tests)

**CI/CD**
- GitHub Actions CI with 5 jobs (lint, test-sqlite, test-postgresql, test-migrations, test-cli)
- Branch protection requiring CI before merge
- Ruff linting and formatting

**Documentation**
- Integration guide (3 steps: contract, adapter, run)
- Operational runbook (RUNBOOK.md)
- AWS deployment guidance with IAM permissions
- Authentication and webhook security documentation

### Pipelines Monitored

| Pipeline | Data Type | Freshness | Source |
|---|---|---|---|
| healthcare_analytics | Hospital admissions (CSV) | 72h | Local fixtures |
| ecommerce_orders | Daily orders (CSV) | 12h | Local fixtures / S3 |

### Known Limitations

- S3 integration verified with LocalStack only (not yet tested with AWS)
- Grafana alert labels don't include pipeline name (Grafana limitation)
- Notification history is in-memory in development (database-backed in production)
- No OpenLineage integration yet

---

## [0.2.0] — 2026-08-19

### Added
- Target schema compatibility check
- Freshness alert using structured check_result data
- SDK dataset_name made required (removed dangerous default)
- Operational runbook (RUNBOOK.md)

## [0.1.0] — 2026-08-18

### Added
- Initial release
- Core API with 6 endpoints
- 4 quality checks (source readability, schema, row count, freshness)
- SQLite support
- PostgreSQL support with Docker Compose
- Healthcare analytics pipeline integration
- Grafana dashboard with 7 panels
- 4 alert rules
- Webhook notification delivery
