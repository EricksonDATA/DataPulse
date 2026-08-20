#!/usr/bin/env python3
"""
DataPulse Demo — one-command demonstration of pipeline observability.

Shows:
1. A passing pipeline run (valid data)
2. A failing pipeline run (schema drift)
3. The resulting incident
4. Grafana alert delivery

Usage:
    python demo.py                    # Run with defaults
    python demo.py --api-url http://localhost:8000  # Custom API URL

Requires:
    - Docker services running: docker compose up -d
    - Grafana accessible at http://localhost:3000
"""

import argparse
import time
import uuid

import httpx


def header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def step(text: str):
    print(f"  → {text}")


def result(label: str, data: dict):
    status = data.get("status", data.get("detail", "unknown"))
    icon = "✅" if status == "passed" else "❌" if status in ("failed", "late") else "⏰"
    print(f"  {icon} {label}: {status}")

    checks = data.get("checks", [])
    for check in checks:
        check_icon = "✅" if check["status"] == "passed" else "❌" if check["status"] == "failed" else "⏭️"
        print(f"     {check_icon} {check['type']}: {check['status']}")
        if check.get("message"):
            print(f"        {check['message']}")

    incidents = data.get("incidents", [])
    if incidents:
        print(f"\n  🚨 Incidents ({len(incidents)}):")
        for inc in incidents:
            if isinstance(inc, dict):
                print(
                    f"     • {inc.get('type', inc.get('incident_type', '?'))} ({inc.get('severity', '?')}) — {str(inc.get('failure_summary', ''))[:80]}"
                )
                print(f"       Owner: {inc.get('owner', '?')}, Retryable: {inc.get('retryable', '?')}")
            else:
                print(f"     • {inc}")


def main():
    parser = argparse.ArgumentParser(description="DataPulse Demo")
    parser.add_argument("--api-url", default="http://localhost:8000", help="DataPulse API URL")
    args = parser.parse_args()

    api = args.api_url
    fixtures = "/app/examples/fixtures"

    header("DataPulse Demo — Pipeline Observability Platform")

    # Step 1: Health check
    step("Checking API health...")
    r = httpx.get(f"{api}/health", timeout=10)
    assert r.status_code == 200, f"API not healthy: {r.status_code}"
    print(f"  ✅ API healthy: {r.json()}")

    # Step 2: Register pipeline
    step("Registering demo pipeline...")
    httpx.post(f"{api}/pipelines", json={"name": "demo_pipeline", "owner": "demo-team"}, timeout=10)

    # Register source dataset
    httpx.post(
        f"{api}/datasets",
        json={
            "pipeline_name": "demo_pipeline",
            "dataset_name": "demo_source",
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
                "min_row_count": 5,
                "max_row_count": 10000,
            },
        },
        timeout=10,
    )
    print("  ✅ Pipeline and contract registered")

    # Step 3: Successful run
    header("Run 1: Valid Data (Expected: PASSED)")
    step("Submitting run with valid data...")
    r = httpx.post(
        f"{api}/runs",
        json={
            "pipeline_name": "demo_pipeline",
            "run_id": f"demo-pass-{uuid.uuid4().hex[:6]}",
            "source_path": f"{fixtures}/ecommerce_orders_fresh.csv",
            "dataset_name": "demo_source",
        },
        timeout=30,
    )
    result("Valid Data Run", r.json())

    # Step 4: Failing run (schema drift)
    header("Run 2: Schema Drift (Expected: FAILED)")
    step("Submitting run with schema drift...")
    r = httpx.post(
        f"{api}/runs",
        json={
            "pipeline_name": "demo_pipeline",
            "run_id": f"demo-fail-{uuid.uuid4().hex[:6]}",
            "source_path": f"{fixtures}/inventory_schema_drift.csv",
            "dataset_name": "demo_source",
        },
        timeout=30,
    )
    result("Schema Drift Run", r.json())

    # Step 5: Check incidents
    header("Open Incidents")
    r = httpx.get(f"{api}/pipelines/demo_pipeline/incidents", timeout=10)
    if r.status_code == 404:
        print("  (pipeline not found — API may have restarted)")
    else:
        incidents = r.json()
        if isinstance(incidents, list) and incidents:
            for inc in incidents:
                if isinstance(inc, dict):
                    print(f"  🚨 {inc.get('incident_type', '?')} ({inc.get('severity', '?')})")
                    print(f"     Owner: {inc.get('owner', '?')}")
                    print(f"     Status: {inc.get('status', '?')}")
                    print(f"     Summary: {str(inc.get('failure_summary', ''))[:100]}")
        else:
            print("  ✅ No open incidents")

    # Step 6: Check webhook log
    header("Webhook Alerts")
    step("Waiting for Grafana to evaluate alerts (30s)...")
    time.sleep(35)
    r = httpx.get(f"{api}/webhook/log", timeout=10)
    logs = r.json()
    if logs:
        print(f"  📨 {len(logs)} webhook entries:")
        for entry in logs[-5:]:
            alerts = entry.get("alerts", [])
            for a in alerts:
                name = a.get("labels", {}).get("alertname", "?")
                status = a.get("status", "?")
                print(f"     • {status}: {name}")
    else:
        print("  ⏳ No webhook entries yet (Grafana may need more time)")

    # Step 7: Metrics
    header("Operational Metrics")
    r = httpx.get(f"{api}/metrics", timeout=10)
    m = r.json()
    print(f"  Pipelines: {m['pipelines']['total']}")
    print(f"  Runs (24h): {m['runs_24h']['total']}")
    print(f"  Open incidents: {m['incidents']['open']}")
    print(f"  Notifications (24h): {m['notifications_24h']['total']}")

    header("Demo Complete")
    print("  Dashboard: http://localhost:3000/d/datapulse-health")
    print("  API docs:  http://localhost:8000/docs")
    print("  Metrics:   http://localhost:8000/metrics")
    print()


if __name__ == "__main__":
    main()
