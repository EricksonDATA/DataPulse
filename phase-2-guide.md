# DataPulse Phase 2 Guide

Phase 2 turns the successful Phase 1 vertical slice into a production-shaped platform foundation. The focus is reliability, real pipeline integration, and operational visibility.

> **Phase 2 outcome:** one real existing pipeline reports source, target, contract, quality, freshness, ownership, and incident metadata into DataPulse running on PostgreSQL, with a dashboard and at least one working alert.

## 1. Phase 2 definition of done

Phase 2 is complete when all of the following are true:

- Source-to-target reconciliation works through the API and run service, not only inside a helper function.
- A target dataset and target path or table are represented explicitly in a run request.
- A mismatch between source and target row counts produces a failed check and incident.
- PostgreSQL runs through Docker Compose for local development.
- Database schema changes are managed by migrations rather than only `create_all()`.
- Configuration is loaded from environment variables with safe local defaults.
- One real, non-sensitive existing pipeline reports a run to DataPulse.
- Pipeline runs are still idempotent under normal retries and safe under concurrent submissions.
- At least one history endpoint supports dashboard queries.
- Grafana shows current pipeline health, check failures, freshness, and open incidents.
- At least one alert is delivered through a webhook or another explicitly chosen channel.
- CI runs tests and validates the migration path on every change.
- Recovery, retry, backfill, ownership, and secret-handling procedures are documented.

Phase 2 is complete when the platform can be trusted for one real pipeline. It does not need to monitor every existing project yet.

## 2. Scope and non-goals

### In scope

- PostgreSQL control database.
- Docker Compose local environment.
- Initial and incremental database migrations.
- End-to-end source and target metadata.
- One reusable pipeline adapter or SDK integration.
- More scalable validation execution.
- Run history and incident query endpoints.
- Grafana dashboard and one alert path.
- CI checks for application, database, and contract behavior.

### Out of scope

- Multi-tenant authentication and authorization.
- A custom frontend application.
- A general-purpose workflow scheduler.
- Automatic execution of arbitrary retries.
- Streaming ingestion.
- Machine-learning anomaly detection.
- Full OpenLineage platform deployment.
- Monitoring all portfolio projects at once.

Keep orchestration ownership with the existing pipeline. DataPulse should observe, validate, explain, and signal recovery needs before it tries to schedule or restart workloads.

## 3. Phase 2 architecture

```text
Existing pipeline or DataPulse SDK adapter
                    |
                    v
             FastAPI metadata API
                    |
                    v
       PostgreSQL control database + migrations
                    |
          +---------+----------+
          |                    |
          v                    v
   Quality and contract      Run history and
       evaluations             incidents
          |                    |
          +---------+----------+
                    v
        Grafana dashboards and alerts
```

Use SQLite for fast unit tests if it remains useful, but treat PostgreSQL as the integration and local deployment database. The repository layer should keep database-specific SQL isolated.

## 4. Step 0: freeze the Phase 1 baseline

Before changing architecture, record a clean baseline:

```powershell
.\\.venv\\Scripts\\datapulse.exe test
.\\.venv\\Scripts\\datapulse.exe demo
```

Capture:

- test count and result;
- demo output and exit code;
- current API endpoints;
- current contract version behavior;
- current fixture names;
- current database tables and constraints.

Do not start Phase 2 by deleting the working SQLite path. Keep it available until the PostgreSQL path passes the same tests.

## 5. Step 1: complete source-to-target reconciliation

This is the first implementation priority because it closes the remaining Phase 1 product gap.

### 5.1 Define the run contract

Extend the run request and service contract with explicit source and target information. A minimal first version may use paths:

```yaml
pipeline_name: ecommerce_inventory
run_id: 2026-08-18-001
source_dataset_name: inventory_source
target_dataset_name: inventory_target
source_path: examples/fixtures/inventory_source.csv
target_path: examples/fixtures/inventory_target.csv
contract_version: 1
```

For a real pipeline, paths may become table names, object-store URIs, or query references. Keep the field names domain-oriented so the API can evolve without tying the model permanently to CSV files.

### 5.2 Decide the reconciliation rule

Document the rule in the contract:

- exact equality when every source row must arrive at the target;
- an absolute difference threshold when small losses are expected;
- a percentage threshold for proportional data movement;
- a separate accepted rejection count when the target intentionally filters records.

Do not hide the rule in code. Store expected values, observed source and target counts, difference, difference percentage, and the configured tolerance in the check result.

### 5.3 Wire the full path

Update these boundaries together:

1. Pydantic run request model.
2. FastAPI `POST /runs` handler.
3. `RunService.submit_run()`.
4. Check execution and result persistence.
5. CLI or SDK integration.
6. Demo fixture and output.
7. Integration tests.

The test that matters is an API-level test: submit a source and target with a known mismatch, then assert the run is failed, the observed counts are persisted, and the incident explains the difference.

## 6. Step 2: move the control plane to PostgreSQL

### 6.1 Add local services

Create a Docker Compose environment containing:

- PostgreSQL;
- the DataPulse API;
- Grafana after the database and API are stable.

Keep credentials in local environment variables or an ignored `.env` file. Commit a `.env.example` with placeholder values only.

Recommended configuration values:

```text
DATAPULSE_DATABASE_URL=postgresql+psycopg://datapulse:change-me@postgres:5432/datapulse
DATAPULSE_LOG_LEVEL=INFO
DATAPULSE_ENVIRONMENT=development
```

Never commit the real password or connection string used outside local development.

### 6.2 Add migrations

Use Alembic or an equivalent migration tool. Create an initial migration for the existing control model, then apply it to an empty PostgreSQL database.

The migration path must support:

- a clean database from zero;
- upgrading an existing Phase 1 database if migration is supported;
- repeated application without destructive recreation;
- rollback or a documented forward-only recovery strategy.

Keep `Base.metadata.create_all()` for isolated test setup only. Production-shaped environments should fail clearly when migrations have not been applied.

### 6.3 Make the database model operational

Review and add indexes for expected access patterns:

| Query | Suggested index |
| --- | --- |
| Pipeline lookup | unique pipeline name |
| Dataset lookup | pipeline ID plus dataset name |
| Contract lookup | dataset ID plus version |
| Latest run | pipeline ID plus started time |
| Run lookup | pipeline ID plus run ID |
| Checks for a run | pipeline run ID plus check type |
| Open incidents | status plus owner or pipeline run ID |

Use PostgreSQL timestamp types that preserve UTC. The API should return timezone-aware ISO 8601 timestamps.

## 7. Step 3: harden configuration and database boundaries

Replace module-level assumptions with explicit configuration:

- database URL;
- environment name;
- log level;
- API host and port;
- maximum accepted file size or scan size if relevant;
- default retryable incident policy.

Use a typed settings object. Make it possible for tests to inject a database URL without mutating global module state.

Define error categories at the service boundary:

- invalid request or contract: client error;
- missing pipeline, dataset, or contract: not found or validation error;
- transient database or infrastructure failure: server error and safe retry guidance;
- data-quality failure: successful request with a failed run result, if that matches the chosen API semantics.

Handle concurrent duplicate run submissions explicitly. A pre-check followed by an insert is not sufficient by itself; the unique database constraint must be caught and resolved as an idempotent replay.

## 8. Step 4: make validation scalable and deterministic

Phase 1 materializes CSV rows with `list(reader)`. Before connecting a real pipeline, replace that behavior where volume requires it.

### 8.1 Stream simple metrics

Use one-pass or bounded-memory processing for:

- row counts;
- latest timestamp;
- null counts;
- rejected counts;
- basic schema observations.

Do not load an entire source file into memory just to count rows.

### 8.2 Choose an exact uniqueness strategy

For duplicate keys, choose deliberately:

- a bounded in-memory set for small inputs;
- DuckDB or database-side SQL for larger local files;
- a staged table with a unique constraint for warehouse-backed data;
- an external sort or partitioned key check when inputs exceed memory.

Record the chosen strategy and its volume limit in the project documentation.

### 8.3 Make time behavior testable

Inject a clock or evaluation timestamp into freshness checks. Tests and demos should not become stale because the calendar changes.

Define behavior for:

- future timestamps;
- missing timestamps;
- mixed time zones;
- daylight-saving transitions;
- empty inputs;
- late-arriving records;
- backfills with an older event date but a recent ingestion date.

Distinguish event time from ingestion or extraction time in the contract when both exist.

### 8.4 Enforce contract registration rules

Validate contracts before persisting them:

- pipeline and dataset names are non-empty;
- dataset role is one of the supported values;
- contract versions are positive integers;
- required schema fields have valid types;
- freshness thresholds are non-negative;
- unique-key columns exist in the schema;
- reconciliation thresholds are within a valid range.

Breaking changes should require a new contract version. Existing runs must retain the exact version they evaluated.

## 9. Step 5: connect one real existing pipeline

Choose one existing project that can run with synthetic or approved non-sensitive data. Prefer a batch pipeline with a clear start and finish.

### 9.1 Use an observer integration first

The existing pipeline should call DataPulse at three points:

1. `run_started` with pipeline, run ID, contract version, source, and target metadata.
2. `run_completed` with output location, counts, and execution metadata.
3. `run_failed` with safe error context when the pipeline fails before validation.

Keep the adapter thin. It should translate the pipeline's native metadata into DataPulse's request model rather than duplicate transformation logic.

### 9.2 Define a reusable adapter interface

The adapter should provide:

- stable pipeline name;
- deterministic run ID;
- source and target references;
- execution interval;
- optional orchestration job ID;
- contract version;
- owner;
- safe retry or backfill context.

Do not expose credentials or full data payloads through the adapter.

### 9.3 Prove reruns and backfills

Run the same pipeline twice with the same run ID and confirm idempotency. Run a new backfill with a different run ID and confirm it creates a separate auditable run.

Document whether a retry reuses the same run ID or creates an attempt ID beneath one logical run. Choose one model before adding automated retry behavior.

## 10. Step 6: expand the API for operations

Keep the existing endpoints compatible and add only the queries needed by operators and Grafana:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/pipelines/{name}/runs` | List recent runs with status filters |
| `GET` | `/pipelines/{name}/incidents` | List open and historical incidents |
| `GET` | `/datasets/{name}/contract` | Retrieve the active contract summary |
| `GET` | `/ready` | Confirm the API and database are ready |
| `POST` | `/runs/{run_id}/acknowledge` | Optional incident or run acknowledgement |

Add pagination and time filters before the history endpoints are used by dashboards. Do not return unbounded run or check histories.

Use stable response models and document the endpoints through FastAPI's generated OpenAPI schema.

## 11. Step 7: add Grafana dashboards and alerts

Connect Grafana to PostgreSQL or a stable metrics endpoint. Start with one dashboard containing:

- current status by pipeline;
- latest run time and duration;
- freshness age versus threshold;
- source and target row counts;
- failed checks by type;
- open incidents by owner and severity;
- recent schema drift events.

Start with alert rules that are actionable:

- pipeline run failed;
- pipeline is late beyond its freshness threshold;
- source-target reconciliation failed;
- repeated failures for the same pipeline;
- incident remains open beyond a chosen duration.

Every alert needs an owner, severity, condition, notification route, and runbook link. Avoid alerting on every individual check if one run-level alert is more useful.

## 12. Step 8: add the first notification path

Choose one channel for Phase 2, preferably a generic webhook so local testing does not depend on a personal Slack or email account.

The notification payload should include:

- pipeline name;
- run ID;
- status;
- failed check;
- expected and observed values;
- incident owner;
- retryable flag;
- link to Grafana or the API run endpoint.

Use bounded retries with backoff for transient notification failures. Do not make a pipeline run fail solely because an alert notification is temporarily unavailable; record the notification failure separately.

## 13. Step 9: add CI and integration validation

Update GitHub Actions to run:

- unit tests for checks and contract parsing;
- API integration tests;
- PostgreSQL-backed integration tests;
- migration upgrade tests;
- CLI demo smoke test;
- formatting and lint checks;
- dependency and secret checks where available.

The CI database should be isolated per job. Tests must not depend on a developer's local SQLite file, environment variables, or current date.

Add regression tests for the Phase 2 risks:

- source-target count mismatch;
- missing target path or target dataset;
- duplicate unique keys;
- requested contract version not found;
- concurrent duplicate run submission;
- timezone-aware run timestamps;
- pagination bounds;
- failed notification delivery;
- migration from an empty PostgreSQL database.

## 14. Step 10: document recovery and ownership

Create a short operational runbook covering:

- how to identify a failed run;
- how to inspect expected versus observed values;
- who owns each pipeline;
- how to retry a safe run;
- how to backfill historical data;
- how to resolve an incident;
- what to do when a contract changes;
- how to rotate local or deployment secrets;
- how to restore the control database.

The runbook should make clear that a retry is safe only when the underlying pipeline is idempotent or the target write behavior is understood.

## 15. Phase 2 milestones

Use these gates to keep the work measurable:

### Milestone A: reconciliation complete

- Target metadata is represented in the API.
- Source-target mismatch is detected end to end.
- The result is persisted and visible in the run response.
- Regression tests pass.

### Milestone B: PostgreSQL ready

- Docker Compose starts PostgreSQL.
- Migrations create all tables and constraints.
- The API connects through environment configuration.
- PostgreSQL integration tests pass.

### Milestone C: real pipeline connected

- One approved existing pipeline reports runs.
- Reruns and backfills are documented and tested.
- No secrets or sensitive records enter logs or fixtures.

### Milestone D: operational visibility

- Grafana dashboard is available.
- At least one alert reaches the chosen webhook.
- The alert links to a run, owner, and recovery procedure.

## 16. Phase 2 exit criteria checklist

Before moving to Phase 3, confirm:

- [ ] Source-to-target reconciliation is wired through API, service, CLI or SDK, and tests.
- [ ] Source and target counts, differences, and tolerance are persisted.
- [ ] PostgreSQL runs locally through Docker Compose.
- [ ] Initial database migrations are committed and repeatable.
- [ ] Environment configuration and `.env.example` contain no real secrets.
- [ ] UTC timestamps are timezone-aware at the API boundary.
- [ ] Contract versions are immutable and enforced during validation.
- [ ] Validation no longer requires loading large files entirely into memory.
- [ ] One real existing pipeline sends run metadata successfully.
- [ ] Reruns, backfills, and concurrent duplicate submissions have defined behavior.
- [ ] Run history and incident query endpoints are bounded and documented.
- [ ] Grafana shows pipeline health and open incidents.
- [ ] At least one alert is delivered and tested.
- [ ] CI validates unit tests, API behavior, migrations, and the demo.
- [ ] A recovery and ownership runbook exists.

## 17. Senior data-engineering takeaway

Phase 2 is where DataPulse becomes operationally credible. The important transition is from a correct local demo to a repeatable control plane that can observe one real pipeline, preserve the exact contract and evidence for every run, and help an owner recover without guessing.

