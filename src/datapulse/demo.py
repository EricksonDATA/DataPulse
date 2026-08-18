"""
DataPulse Phase 1 Demo

Run from the project root:
    python -m datapulse.demo

Or via CLI:
    datapulse demo

This script demonstrates the full monitoring loop:
    1. Start API with fresh database
    2. Register pipeline and dataset
    3. Submit a valid run -> show PASSED checks
    4. Submit a schema-drift run -> show FAILED + incident
    5. Re-submit same run -> show idempotency
    6. Run the test suite
"""

import json
import tempfile
import uuid
from pathlib import Path

# -- Setup -------------------------------------------------------

def _setup_test_db():
    """Create a fresh database for the demo (doesn't touch production)."""
    import datapulse.db.engine as eng
    import datapulse.api.deps as deps
    import datapulse.config as config

    db_path = Path(tempfile.gettempdir()) / f"datapulse_demo_{uuid.uuid4().hex[:6]}.db"
    deps._engine = None
    deps._session_factory = None
    config.DATABASE_URL = f"sqlite:///{db_path}"
    return db_path


def _print_header(title: str):
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}\n")


def _print_json(data: dict, indent: int = 2):
    print(json.dumps(data, indent=indent, default=str))


# -- Demo Steps --------------------------------------------------

def run_demo():
    """Run the full Phase 1 demo."""
    db_path = _setup_test_db()

    import datapulse.db.engine as eng
    from datapulse.logging_config import setup_logging
    import logging

    from datapulse.api.app import app  # import app FIRST (triggers setup_logging)
    from fastapi.testclient import TestClient

    # Suppress structured logs AFTER app import for cleaner demo output
    logging.getLogger("datapulse").setLevel(logging.CRITICAL)

    eng.init_db(eng.get_engine())
    client = TestClient(app)

    print("\n" + "=" * 60)
    print("  DataPulse - Phase 1 Demo")
    print("  Data Contract and Pipeline Observability Platform")
    print("=" * 60)

    # -- Step 1: Health check ------------------------------------
    _print_header("Step 1: API Health Check")
    r = client.get("/health")
    print(f"GET /health -> {r.status_code}")
    _print_json(r.json())

    # -- Step 2: Register pipeline -------------------------------
    _print_header("Step 2: Register Pipeline")
    r = client.post("/pipelines", json={
        "name": "ecommerce_inventory",
        "owner": "data-platform",
    })
    print(f"POST /pipelines -> {r.status_code}")
    _print_json(r.json())

    # -- Step 3: Register dataset + contract ---------------------
    _print_header("Step 3: Register Dataset + Contract")
    r = client.post("/datasets", json={
        "pipeline_name": "ecommerce_inventory",
        "dataset_name": "inventory_snapshot",
        "role": "source",
        "location": "data/inventory/",
        "contract_version": 1,
        "schema_definition": {
            "snapshot_date": {"type": "date", "nullable": False},
            "product_id": {"type": "integer", "nullable": False},
            "sku": {"type": "string", "nullable": False},
            "warehouse_id": {"type": "string", "nullable": False},
            "stock_on_hand": {"type": "integer", "nullable": False},
            "reserved_quantity": {"type": "integer", "nullable": False},
            "reorder_point": {"type": "integer", "nullable": False},
            "reorder_quantity": {"type": "integer", "nullable": False},
            "restock_lead_time_days": {"type": "integer", "nullable": False},
            "unit_cost": {"type": "decimal", "nullable": False},
            "supplier_id": {"type": "string", "nullable": False},
            "supplier_name": {"type": "string", "nullable": False},
            "last_restock_date": {"type": "date", "nullable": False},
        },
        "freshness": {"max_age_hours": 24, "timestamp_column": "snapshot_date"},
        "quality_rules": {"unique_keys": ["product_id"], "min_row_count": 1, "max_row_count": 50},
    })
    print(f"POST /datasets -> {r.status_code}")
    _print_json(r.json())

    # -- Step 4: Submit valid run --------------------------------
    _print_header("Step 4: Submit Valid Run")

    # Generate a fresh fixture with today's date
    from datetime import date
    today = date.today().isoformat()
    template = Path("examples/fixtures/inventory_fresh_template.csv")
    fresh_fixture = Path(tempfile.gettempdir()) / f"inventory_fresh_{uuid.uuid4().hex[:6]}.csv"
    fresh_fixture.write_text(template.read_text().replace("TODAY", today), encoding="utf-8")

    r = client.post("/runs", json={
        "pipeline_name": "ecommerce_inventory",
        "run_id": "2026-07-27-001",
        "source_path": str(fresh_fixture),
    })
    d = r.json()
    print(f"POST /runs -> {r.status_code}")
    print(f"Run ID:     {d['run_id']}")
    print(f"Status:     {d['status']}")
    print(f"Checks:     {len(d['checks'])}")
    for c in d["checks"]:
        symbol = "[OK]" if c["status"] == "passed" else "[!!]"
        print(f"  {symbol} {c['type']}: {c['status']}")
    if d["incidents"]:
        print(f"Incidents:  {len(d['incidents'])}")
        for inc in d["incidents"]:
            print(f"  [!] {inc['type']} ({inc['severity']}) - {inc['failure_summary'][:60]}")

    # -- Step 5: Submit schema-drift run -------------------------
    _print_header("Step 5: Submit Run with Schema Drift")
    r = client.post("/runs", json={
        "pipeline_name": "ecommerce_inventory",
        "run_id": "2026-07-27-002",
        "source_path": "examples/fixtures/inventory_schema_drift.csv",
    })
    d = r.json()
    print(f"POST /runs -> {r.status_code}")
    print(f"Run ID:     {d['run_id']}")
    print(f"Status:     {d['status']}")
    print(f"Checks:     {len(d['checks'])}")
    for c in d["checks"]:
        symbol = "[OK]" if c["status"] == "passed" else "[!!]"
        detail = ""
        if c["status"] == "failed" and c.get("message"):
            detail = f" - {c['message'][:60]}"
        print(f"  {symbol} {c['type']}: {c['status']}{detail}")
    if d["incidents"]:
        print(f"Incidents:  {len(d['incidents'])}")
        for inc in d["incidents"]:
            print(f"  [!] Type:     {inc['type']}")
            print(f"    Severity: {inc['severity']}")
            print(f"    Owner:    {inc['owner']}")
            print(f"    Retryable: {inc['retryable']}")
            print(f"    Summary:  {inc['failure_summary'][:80]}")

    # -- Step 6: Idempotency ------------------------------------
    _print_header("Step 6: Re-submit Same Run (Idempotency)")
    r = client.post("/runs", json={
        "pipeline_name": "ecommerce_inventory",
        "run_id": "2026-07-27-001",
        "source_path": str(fresh_fixture),
    })
    d = r.json()
    print(f"POST /runs (same run_id) -> {r.status_code}")
    print(f"Run ID:     {d['run_id']}")
    print(f"Status:     {d['status']}")
    print(f"No duplicate created - same run returned.")

    # -- Step 7: Query health ------------------------------------
    _print_header("Step 7: Query Pipeline Health")
    r = client.get("/pipelines/ecommerce_inventory/health")
    d = r.json()
    print(f"GET /pipelines/ecommerce_inventory/health -> {r.status_code}")
    print(f"Latest run: {d['run_id']}")
    print(f"Status:     {d['status']}")

    # -- Step 8: Run tests ---------------------------------------
    _print_header("Step 8: Run Automated Tests")
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        capture_output=True, text=True,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print(f"\n[!] Some tests failed!")
    else:
        print(f"\nAll tests passed.")

    # -- Summary -------------------------------------------------
    _print_header("Demo Complete")
    print("What you just saw:")
    print("  1. Pipeline and dataset registration")
    print("  2. A valid run passing all checks")
    print("  3. A schema-drift run failing with an incident")
    print("  4. Idempotent run submission (no duplicates)")
    print("  5. Pipeline health query")
    print("  6. Automated test suite")
    print()
    print("Next steps:")
    print("  - Start the API server:  datapulse serve")
    print("  - Run tests:             datapulse test")
    print("  - Explore the API docs:  http://127.0.0.1:8000/docs")
    print()

    # Cleanup
    if hasattr(client, 'close'):
        client.close()
    import datapulse.api.deps as deps
    if deps._engine:
        deps._engine.dispose()
    if db_path.exists():
        db_path.unlink()
    if fresh_fixture.exists():
        fresh_fixture.unlink()


if __name__ == "__main__":
    run_demo()
