"""Operational workflows test.

Tests retry, acknowledgement, recovery, duplicate-run protection,
and historical-alert suppression.

Requires: DataPulse API running (docker compose up -d)
"""

import os

import httpx

API_URL = os.environ.get("DATAPULSE_URL", "http://localhost:8000")
API_KEY = os.environ.get("DATAPULSE_API_KEY", "")

checks = []


if __name__ == "__main__":

    def ok(label, condition):
        checks.append((label, bool(condition)))

    def api_post(path, json=None):
        headers = {}
        if API_KEY:
            headers["X-API-Key"] = API_KEY
        return httpx.post(f"{API_URL}{path}", json=json, headers=headers, timeout=30)

    def api_get(path):
        headers = {}
        if API_KEY:
            headers["X-API-Key"] = API_KEY
        return httpx.get(f"{API_URL}{path}", headers=headers, timeout=10)

    FIXTURES = "/app/examples/fixtures"

    # Register pipeline
    api_post("/pipelines", json={"name": "ops_test_pipeline", "owner": "ops-team"})
    api_post(
        "/datasets",
        json={
            "pipeline_name": "ops_test_pipeline",
            "dataset_name": "ops_source",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {
                "order_id": {"type": "string", "nullable": False},
                "amount": {"type": "decimal", "nullable": False},
                "status": {"type": "string", "nullable": False},
            },
            "freshness": {"max_age_hours": 24, "timestamp_column": "order_id"},
            "quality_rules": {"unique_keys": ["order_id"], "min_row_count": 50, "max_row_count": 10000},
        },
    )

    # ── Test 1: Idempotent run submission ────────────────────────

    print("=== Test 1: Idempotent run submission ===")
    r1 = api_post(
        "/runs",
        json={
            "pipeline_name": "ops_test_pipeline",
            "run_id": "ops-idempotent-1",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "dataset_name": "ops_source",
        },
    )
    ok("First submission returns 201", r1.status_code == 201)

    r2 = api_post(
        "/runs",
        json={
            "pipeline_name": "ops_test_pipeline",
            "run_id": "ops-idempotent-1",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "dataset_name": "ops_source",
        },
    )
    ok("Duplicate submission returns 201 (idempotent)", r2.status_code == 201)
    if r1.status_code == 201 and r2.status_code == 201:
        ok("Same run_id returns same result", r1.json()["run_id"] == r2.json()["run_id"])
        ok("Same status", r1.json()["status"] == r2.json()["status"])

    # ── Test 2: Run history shows both runs ──────────────────────

    print("\n=== Test 2: Run history ===")
    r = api_get("/pipelines/ops_test_pipeline/runs")
    ok("Run history returns 200", r.status_code == 200)
    if r.status_code == 200:
        runs = r.json()
        ok("Has runs", len(runs) >= 1)
        ok("Run has duration_ms", "duration_ms" in runs[0])

    # ── Test 3: Incident acknowledgement ────────────────────────

    print("\n=== Test 3: Incident acknowledgement ===")
    # Submit a failing run to create an incident
    r_fail = api_post(
        "/runs",
        json={
            "pipeline_name": "ops_test_pipeline",
            "run_id": "ops-fail-28269c",
            "source_path": f"{FIXTURES}/inventory_schema_drift.csv",
            "dataset_name": "ops_source",
        },
    )
    ok("Failing run returns 201", r_fail.status_code == 201)

    # Check incidents
    r_inc = api_get("/pipelines/ops_test_pipeline/incidents")
    ok("Incidents endpoint returns 200", r_inc.status_code == 200)
    if r_inc.status_code == 200:
        incidents = r_inc.json()
        ok("Has open incidents", len(incidents) >= 1)
        if incidents:
            ok("Incident is open", incidents[0]["status"] == "open")

    # Acknowledge the run
    r_ack = api_post("/runs/ops-fail-28269c/acknowledge")
    ok("Acknowledge returns 200", r_ack.status_code == 200)
    if r_ack.status_code == 200:
        ack_data = r_ack.json()
        ok("Acknowledged at least 1 incident", ack_data.get("acknowledged", 0) >= 1)

    # Verify the specific run's incidents are acknowledged
    # (other runs may still have open incidents)
    r_ack_run = api_get("/pipelines/ops_test_pipeline/runs/ops-fail-28269c")
    if r_ack_run.status_code == 200:
        acked_incidents = r_ack_run.json().get("incidents", [])
        acked_count = sum(1 for i in acked_incidents if i["status"] == "acknowledged")
        ok("ops-fail-1 incidents acknowledged", acked_count >= 1)

    # ── Test 4: Retry (new run_id = backfill) ────────────────────

    print("\n=== Test 4: Retry and backfill ===")
    # Original run
    r_orig = api_post(
        "/runs",
        json={
            "pipeline_name": "ops_test_pipeline",
            "run_id": "ops-retry-original",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "dataset_name": "ops_source",
        },
    )
    ok("Original run returns 201", r_orig.status_code == 201)

    # Backfill (different run_id)
    r_backfill = api_post(
        "/runs",
        json={
            "pipeline_name": "ops_test_pipeline",
            "run_id": "ops-retry-backfill",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "dataset_name": "ops_source",
        },
    )
    ok("Backfill run returns 201", r_backfill.status_code == 201)

    # Both should exist
    r_hist = api_get("/pipelines/ops_test_pipeline/runs")
    if r_hist.status_code == 200:
        run_ids = [r["run_id"] for r in r_hist.json()]
        ok("Original in history", "ops-retry-original" in run_ids)
        ok("Backfill in history", "ops-retry-backfill" in run_ids)

    # ── Test 5: Metrics endpoint ─────────────────────────────────

    print("\n=== Test 5: Metrics ===")
    r_metrics = api_get("/metrics")
    ok("Metrics returns 200", r_metrics.status_code == 200)
    if r_metrics.status_code == 200:
        m = r_metrics.json()
        ok("Has pipelines count", "pipelines" in m)
        ok("Has runs_24h", "runs_24h" in m)
        ok("Has incidents", "incidents" in m)
        ok("Has notifications_24h", "notifications_24h" in m)
        ok("Pipeline count >= 1", m["pipelines"]["total"] >= 1)

    # ── Results ──────────────────────────────────────────────────

    print("\n" + "=" * 50)
    passed = sum(1 for _, ok_val in checks if ok_val)
    total = len(checks)
    for label, ok_val in checks:
        print(f"  [{'OK' if ok_val else 'FAIL'}] {label}")
    print(f"\n{passed}/{total} checks passed")

    if passed < total:
        exit(1)
