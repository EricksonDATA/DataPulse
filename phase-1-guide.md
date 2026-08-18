# DataPulse Phase 1 Guide

Phase 1 is the foundation milestone for DataPulse. The goal is to prove one complete monitoring loop from a pipeline run to a visible, actionable result.

> **Phase 1 outcome:** submit one pipeline run, validate its data contract, persist the results, create an incident when necessary, and retrieve the run health through an API.

## 1. Phase 1 definition of done

Phase 1 is complete when all of the following are true:

- A pipeline and its datasets can be registered.
- A versioned contract can be stored for a dataset.
- A pipeline run can be started, completed, and queried.
- The run records a stable run ID, timestamps, status, counts, and failure context.
- The system validates:
  - source readability and required columns;
  - schema compatibility;
  - row-count expectations;
  - freshness of the source data.
- Every check produces a persisted result with expected and observed values.
- A failed or late run creates an incident with an owner and severity.
- Re-submitting the same run ID does not create duplicate run records.
- API and validation behavior are covered by automated tests.
- A small demo can show both a passing run and a failing run.

The first implementation should use synthetic or non-sensitive data. Do not use patient data, credentials, API tokens, or production connection strings in the repository.

## 2. Keep the scope deliberately small

### In scope

- Python service and CLI or SDK entry point.
- FastAPI metadata endpoints.
- SQLite for local development, behind a repository interface that can later support PostgreSQL.
- One monitored pipeline, such as `healthcare_analytics`.
- One source dataset and one target dataset.
- A small contract model and validation result model.
- Structured logs, tests, and a repeatable local demo.

### Out of scope for Phase 1

- Monitoring every existing project.
- Full authentication and multi-tenant authorization.
- Production deployment.
- Automatic execution of arbitrary retries.
- Slack or email integrations.
- Full OpenLineage integration.
- Advanced anomaly detection or machine learning.
- A polished Grafana dashboard.
- Great Expectations integration if custom checks are sufficient for the first slice.

These are follow-up capabilities, not reasons to delay the first working path.

## 3. The Phase 1 architecture

```text
Synthetic fixture or existing pipeline adapter
                    |
                    v
             DataPulse CLI / SDK
                    |
                    v
             FastAPI metadata API
                    |
                    v
        SQLite control database locally
                    |
                    v
       Contracts, runs, checks, incidents
                    |
                    v
       JSON health response and structured logs
```

Use SQLite first to remove setup friction. Keep SQL and persistence behind a small repository layer so the application does not depend on SQLite-specific behavior. Move to PostgreSQL after the data model and run lifecycle are proven.

## 4. Step 1: establish the project foundation

Create a small, predictable structure before adding features:

```text
DataPulse/
├── src/
│   └── datapulse/
│       ├── api/
│       ├── checks/
│       ├── contracts/
│       ├── db/
│       ├── models/
│       └── cli.py
├── tests/
│   ├── unit/
│   └── integration/
├── examples/
│   └── fixtures/
├── migrations/
├── pyproject.toml
├── README.md
└── phase-1-guide.md
```

Use a virtual environment and pin dependencies. Start with only the dependencies needed for the first slice:

- FastAPI
- Uvicorn
- Pydantic
- SQLAlchemy or another lightweight persistence layer
- a SQLite driver if required by the chosen database library
- pytest
- an HTTP test client

Add dependencies only when a concrete Phase 1 requirement needs them.

## 5. Step 2: write the first data contract

Choose one synthetic dataset and define its contract before implementing checks. The contract should state:

- dataset name and owner;
- grain, such as one row per claim or one row per event;
- required columns and types;
- nullable versus non-nullable fields;
- business or natural key;
- expected freshness window and time zone;
- acceptable row-count range or reconciliation rule;
- retention and sensitivity classification;
- expected behavior for empty, late, malformed, and duplicate input.

Example contract shape:

```yaml
pipeline_name: healthcare_analytics
dataset_name: claims_source
contract_version: 1
owner: data-platform
grain: one row per claim
freshness:
  max_age_minutes: 90
schema:
  claim_id: {type: string, nullable: false}
  member_id: {type: string, nullable: false}
  claim_amount: {type: decimal, nullable: false}
  claim_status: {type: string, nullable: false}
  event_timestamp: {type: timestamp, nullable: false}
quality:
  max_null_rate: 0.0
  unique_keys: [claim_id]
```

Treat the contract as versioned configuration, not as an informal comment. A breaking schema change should fail the run and create an incident. A compatible change should be deliberate, versioned, and observable.

## 6. Step 3: design the minimum control model

Start with five logical entities:

| Entity | Purpose | Important fields |
| --- | --- | --- |
| `pipelines` | Registered pipeline and owner | name, owner, enabled |
| `datasets` | Source and target datasets | pipeline, name, role, location |
| `contracts` | Expected schema and thresholds | dataset, version, schema, freshness, rules |
| `pipeline_runs` | One execution attempt | run ID, status, timestamps, counts, error |
| `check_results` | Outcome of each validation | run, check type, status, expected, observed |
| `incidents` | Actionable failure record | run, type, severity, owner, status |

Recommended constraints:

- `pipelines.name` is unique.
- A dataset name is unique within a pipeline.
- A contract version is unique per dataset.
- A run ID is unique per pipeline.
- A check result belongs to exactly one run.
- An incident can reference the failing run and check results.

Store frequently filtered values as typed columns. Use JSON only for flexible details such as schema snapshots, rule configuration, and diagnostic context.

## 7. Step 4: implement the run lifecycle

Use an explicit state machine:

```text
registered -> running -> passed
                    \-> failed
                    \-> late
```

Suggested lifecycle:

1. Create or retrieve the pipeline and dataset metadata.
2. Start a run with a caller-provided `run_id`.
3. Capture `started_at`, source identifier, and contract version.
4. Execute checks in a deterministic order.
5. Persist each check result immediately or within a transaction boundary that is safe to retry.
6. Calculate the final run status from the check results.
7. Persist counts, duration, failure reason, and `ended_at`.
8. Create or update an incident for a failed or late result.
9. Return a health summary through the API.

The operation must be idempotent. If a caller retries the same request after a network timeout, DataPulse must not create a second logical run or duplicate incident. Use the pipeline plus caller-provided run ID as the idempotency key.

## 8. Step 5: build the first checks

Implement checks in this order:

### 8.1 Source readability

Confirm that the fixture or source can be opened and parsed. Record the source identifier, file or response type, and any parsing error. Fail fast for malformed input.

### 8.2 Schema compatibility

Compare the observed schema with the contract:

- missing required column: failure;
- unexpected column: failure by default;
- incompatible type: failure;
- nullable field containing nulls: failure when the contract forbids nulls;
- additional compatible column: only allowed if the contract explicitly permits it.

Do not silently coerce or drop columns in the monitoring layer. The pipeline owner should make schema evolution explicit.

### 8.3 Row-count validation

Record source and target counts separately. Start with a simple configured rule, such as an absolute difference or percentage threshold. Make the rule explicit so a count mismatch is explainable.

### 8.4 Freshness validation

Compare the latest source event timestamp or extraction timestamp with the contract's maximum age. Store the evaluated timestamp, time zone, observed age, and threshold. Avoid local-time ambiguity by storing timestamps in UTC.

After these checks work, add null-rate, duplicate-key, accepted-values, and source-to-target reconciliation checks as the next increment.

## 9. Step 6: expose a small API

The first API should be intentionally narrow:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/pipelines` | Register a pipeline |
| `POST` | `/datasets` | Register a dataset and contract |
| `POST` | `/runs` | Submit or start a pipeline run |
| `GET` | `/pipelines/{name}/runs/{run_id}` | Retrieve one run health summary |
| `GET` | `/pipelines/{name}/health` | Retrieve the latest pipeline health |
| `GET` | `/health` | Confirm the API is available |

Use Pydantic request and response models. Return stable error shapes for validation failures. Keep API handlers thin: validation orchestration belongs in application services, while persistence belongs in the repository layer.

## 10. Step 7: add observability and incidents

Every run should produce structured logs containing at least:

- `run_id`;
- pipeline and dataset;
- contract version;
- check type;
- status;
- start and end time;
- duration;
- input and output row counts;
- rejected count when applicable;
- error type and safe diagnostic context.

Never log credentials, tokens, full source payloads, or sensitive records. Log identifiers and counts instead.

Create an incident when a run fails, is late, or violates a contract. The incident should include:

- incident type;
- severity;
- owning team or role;
- linked run ID;
- failing check;
- first observed time;
- current status;
- retryable flag;
- safe failure summary.

For Phase 1, a JSON response and logs are enough for visibility. A Grafana dashboard can consume the API or database after the lifecycle is stable.

## 11. Step 8: test the failure paths first

Write tests for the behavior that makes an observability platform trustworthy:

- a valid run passes;
- an unreadable source fails clearly;
- a required column is missing;
- an unexpected column is detected;
- a type mismatch fails;
- row-count thresholds behave at, below, and above the boundary;
- a late source creates the correct incident;
- duplicate run submission is idempotent;
- a retry after a transient persistence or API failure does not duplicate results;
- empty input is handled according to the contract;
- timestamps are stored and compared in UTC;
- API responses expose useful, stable error details.

Use small fixtures with synthetic values. Add an integration test that submits a run through the API and reads the persisted result back from the database.

## 12. Demo script for the phase review

The Phase 1 review should be repeatable from a clean local environment:

1. Start the API and initialize the local database.
2. Register the `healthcare_analytics` pipeline.
3. Register the source and target datasets.
4. Load a valid fixture and submit a run.
5. Show the run as `passed`.
6. Load a fixture with an unexpected column and submit another run.
7. Show the run as `failed` with the schema check failure.
8. Show the created incident, owner, and retryable flag.
9. Re-submit the same run ID and show that no duplicate run is created.
10. Run the automated test suite.

The demo should explain what happened and how an operator would recover, not just show that an endpoint returns JSON.

## 13. Phase 1 risks and decisions

| Risk or decision | Phase 1 approach | Revisit when |
| --- | --- | --- |
| SQLite versus PostgreSQL | Use SQLite behind a repository interface | Multiple users, concurrent writes, or deployment begins |
| Custom checks versus Great Expectations | Start with small custom checks | Check library reuse or rule complexity justifies adoption |
| SDK versus CLI first | Expose one simple CLI path and keep a callable Python service | A second monitored pipeline needs reusable integration |
| Run retry behavior | Record whether a run is retryable; do not execute retries automatically | Orchestration ownership and retry policy are defined |
| Grafana integration | Stabilize run and check data first | API or database metrics are stable enough to dashboard |
| OpenLineage | Keep lineage fields extensible but minimal | A real orchestrator integration is selected |

Document decisions that change the data model or run semantics. Do not add platform complexity before the first vertical slice demonstrates a real operational need.

## 14. Exit criteria checklist

Before moving to Phase 2, confirm:

- [ ] The repository has a reproducible local setup.
- [ ] The first contract is written and versioned.
- [ ] The control model has uniqueness and foreign-key constraints.
- [ ] Run submission is idempotent.
- [ ] Required checks persist expected and observed values.
- [ ] Failed and late runs create incidents.
- [ ] Structured logs include run context and safe diagnostics.
- [ ] Unit and integration tests cover success and failure paths.
- [ ] A clean-environment demo can be run by someone else.
- [ ] The README links to this guide and clearly labels the project as early-stage.
- [ ] Open questions and follow-up decisions are documented.

## Senior data-engineering takeaway

Build the smallest useful control plane around one real pipeline. The most important Phase 1 property is not the number of checks or endpoints; it is that a run can be observed, explained, retried safely, and tied to an owner without creating duplicate or misleading operational state.
