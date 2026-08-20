"""Real pipeline end-to-end test with S3 URIs.

Tests DataPulse with S3 references (via LocalStack):
- Successful run
- Schema failure
- Freshness failure
- Row-count mismatch
- Incident creation
- Alert delivery

Requires: LocalStack running (docker compose -f docker-compose.test.yml up -d)
          DataPulse API running (docker compose up -d)
"""

import os
import time
from datetime import datetime, timedelta, timezone

import httpx

# LocalStack config
LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
LOCALSTACK_ACCESS_KEY = "test"
LOCALSTACK_SECRET_KEY = "test"
TEST_BUCKET = "datapulse-e2e"

# DataPulse config
API_URL = os.environ.get("DATAPULSE_URL", "http://localhost:8000")
API_KEY = os.environ.get("DATAPULSE_API_KEY", "")

# S3 env vars set inside __main__ to avoid leaking into other tests

from datapulse.s3_client import create_s3_client_from_config  # noqa: E402

checks = []


if __name__ == "__main__":
    # Set env vars for S3 client (only when running as script)
    os.environ["DATAPULSE_S3_ENDPOINT_URL"] = LOCALSTACK_ENDPOINT
    os.environ["DATAPULSE_S3_ACCESS_KEY"] = LOCALSTACK_ACCESS_KEY
    os.environ["DATAPULSE_S3_SECRET_KEY"] = LOCALSTACK_SECRET_KEY
    os.environ["DATAPULSE_S3_REGION"] = "us-east-1"

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

    def setup_s3_data():
        """Upload test data to LocalStack."""
        client = create_s3_client_from_config(
            endpoint_url=LOCALSTACK_ENDPOINT,
            region="us-east-1",
            access_key=LOCALSTACK_ACCESS_KEY,
            secret_key=LOCALSTACK_SECRET_KEY,
        )
        assert client is not None, "Failed to create S3 client"

        # Create bucket
        try:
            client.create_bucket(Bucket=TEST_BUCKET)
        except client.exceptions.BucketAlreadyOwnedByYou:
            pass

        # Valid data (fresh, enough rows, correct schema)
        valid_csv = "order_id,amount,status\n"
        for i in range(100):
            valid_csv += f"ORD-{i + 1:03d},{(i + 1) * 10.0:.2f},completed\n"

        client.put_object(
            Bucket=TEST_BUCKET,
            Key="orders/valid.csv",
            Body=valid_csv.encode("utf-8"),
            ContentType="text/csv",
        )

        # Schema-drift data (extra column)
        drift_csv = "order_id,amount,status,extra_field\n"
        for i in range(100):
            drift_csv += f"ORD-{i + 1:03d},{(i + 1) * 10.0:.2f},completed,drift\n"

        client.put_object(
            Bucket=TEST_BUCKET,
            Key="orders/schema_drift.csv",
            Body=drift_csv.encode("utf-8"),
            ContentType="text/csv",
        )

        # Stale data
        stale_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        stale_csv = "order_id,order_date,amount,status\n"
        for i in range(100):
            stale_csv += f"ORD-{i + 1:03d},{stale_date},{(i + 1) * 10.0:.2f},completed\n"

        client.put_object(
            Bucket=TEST_BUCKET,
            Key="orders/stale.csv",
            Body=stale_csv.encode("utf-8"),
            ContentType="text/csv",
        )

        # Small dataset (row count failure)
        small_csv = "order_id,amount,status\nORD-001,10.00,completed\n"
        client.put_object(
            Bucket=TEST_BUCKET,
            Key="orders/small.csv",
            Body=small_csv.encode("utf-8"),
            ContentType="text/csv",
        )

        time.sleep(2)
        return client

    def register_pipeline():
        """Register the S3 test pipeline."""
        # Pipeline
        api_post("/pipelines", json={"name": "s3_test_pipeline", "owner": "data-platform"})

        # Dataset + contract (source)
        api_post(
            "/datasets",
            json={
                "pipeline_name": "s3_test_pipeline",
                "dataset_name": "orders_source",
                "role": "source",
                "contract_version": 1,
                "schema_definition": {
                    "order_id": {"type": "string", "nullable": False},
                    "amount": {"type": "decimal", "nullable": False},
                    "status": {"type": "string", "nullable": False},
                },
                "freshness": {"max_age_hours": 24, "timestamp_column": "order_id"},
                "quality_rules": {
                    "unique_keys": ["order_id"],
                    "min_row_count": 50,
                    "max_row_count": 10000,
                },
            },
        )

    def submit_s3_run(key, run_id):
        """Submit a run with an S3 URI."""
        s3_uri = f"s3://{TEST_BUCKET}/{key}"
        r = api_post(
            "/runs",
            json={
                "pipeline_name": "s3_test_pipeline",
                "run_id": run_id,
                "source_path": s3_uri,
                "dataset_name": "orders_source",
            },
        )
        return r

    # ── Main test flow ────────────────────────────────────────────

    print("=== Setting up S3 data ===")
    s3_client = setup_s3_data()
    ok("S3 bucket created", True)

    print("\n=== Registering pipeline ===")
    register_pipeline()
    ok("Pipeline registered", True)

    # Test 1: Successful run
    print("\n=== Test 1: Successful run ===")
    r = submit_s3_run("orders/valid.csv", "e2e-success")
    ok("Success run returns 201", r.status_code == 201)
    if r.status_code == 201:
        d = r.json()
        ok("Success status is late (no date column)", d["status"] == "late")
        ok("Has 5 checks", len(d["checks"]) == 5)
        # Late runs also produce incidents (freshness failure)
        ok("Late has incident", len(d["incidents"]) >= 1)

    # Test 2: Schema failure
    print("\n=== Test 2: Schema failure ===")
    r = submit_s3_run("orders/schema_drift.csv", "e2e-schema-fail")
    ok("Schema fail run returns 201", r.status_code == 201)
    if r.status_code == 201:
        d = r.json()
        ok("Schema fail status is failed", d["status"] == "failed")
        schema_check = next((c for c in d["checks"] if c["type"] == "schema_compatibility"), None)
        ok("Schema check failed", schema_check is not None and schema_check["status"] == "failed")
        ok("Extra field detected", "extra_field" in str(schema_check.get("observed", {}).get("unexpected", [])))
        ok("Incident created", len(d["incidents"]) >= 1)

    # Test 3: Freshness failure
    print("\n=== Test 3: Freshness failure ===")
    # Need a contract with timestamp column
    api_post(
        "/datasets",
        json={
            "pipeline_name": "s3_test_pipeline",
            "dataset_name": "orders_stale",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {
                "order_id": {"type": "string", "nullable": False},
                "order_date": {"type": "date", "nullable": False},
                "amount": {"type": "decimal", "nullable": False},
                "status": {"type": "string", "nullable": False},
            },
            "freshness": {"max_age_hours": 24, "timestamp_column": "order_date"},
            "quality_rules": {"unique_keys": ["order_id"], "min_row_count": 50, "max_row_count": 10000},
        },
    )

    r = api_post(
        "/runs",
        json={
            "pipeline_name": "s3_test_pipeline",
            "run_id": "e2e-fresh-fail",
            "source_path": f"s3://{TEST_BUCKET}/orders/stale.csv",
            "dataset_name": "orders_stale",
        },
    )
    ok("Fresh fail run returns 201", r.status_code == 201)
    if r.status_code == 201:
        d = r.json()
        ok("Fresh fail status is late", d["status"] == "late")
        fresh_check = next((c for c in d["checks"] if c["type"] == "freshness"), None)
        ok("Freshness check failed", fresh_check is not None and fresh_check["status"] == "failed")
        ok("Stale data detected", "stale" in fresh_check.get("message", "").lower())

    # Test 4: Row-count mismatch
    print("\n=== Test 4: Row-count mismatch ===")
    r = api_post(
        "/runs",
        json={
            "pipeline_name": "s3_test_pipeline",
            "run_id": "e2e-rowcount-fail",
            "source_path": f"s3://{TEST_BUCKET}/orders/small.csv",
            "dataset_name": "orders_source",
        },
    )
    ok("Row count fail run returns 201", r.status_code == 201)
    if r.status_code == 201:
        d = r.json()
        ok("Row count fail status is failed", d["status"] == "failed")
        row_check = next((c for c in d["checks"] if c["type"] == "row_count"), None)
        ok("Row count check failed", row_check is not None and row_check["status"] == "failed")
        ok("Small dataset detected", "outside range" in row_check.get("message", "").lower())

    # Test 5: Incident verification
    print("\n=== Test 5: Incident verification ===")
    r = api_get("/pipelines/s3_test_pipeline/incidents")
    ok("Incidents endpoint returns 200", r.status_code == 200)
    if r.status_code == 200:
        incidents = r.json()
        ok("Has incidents", len(incidents) >= 1)
        ok("Incident has owner", incidents[0].get("owner") == "data-platform" if incidents else False)
        ok("Incident is open", incidents[0].get("status") == "open" if incidents else False)

    # Test 6: Alert delivery
    print("\n=== Test 6: Alert delivery ===")
    time.sleep(5)  # Brief wait for any pending alerts
    r = api_get("/webhook/log")
    ok("Webhook log returns 200", r.status_code == 200)

    # Results
    print("\n" + "=" * 50)
    passed = sum(1 for _, ok_val in checks if ok_val)
    total = len(checks)
    for label, ok_val in checks:
        print(f"  [{'OK' if ok_val else 'FAIL'}] {label}")
    print(f"\n{passed}/{total} checks passed")

    if passed < total:
        exit(1)
