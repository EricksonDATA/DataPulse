"""Ecommerce orders pipeline adapter.

Demonstrates DataPulse reusability with a different integration pattern:
- S3-style path references (simulated with local files)
- Daily partitioned order data
- Shorter freshness window (12h vs 72h)
- Source-to-target row count reconciliation

Usage:
    python -m datapulse.adapters.ecommerce_orders \
        --source /path/to/orders.csv \
        --target /path/to/order_facts.csv \
        --api-url http://localhost:8000
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone

from datapulse.contracts.ecommerce_orders import (
    ORDER_FACTS_TARGET_FRESHNESS,
    ORDER_FACTS_TARGET_QUALITY,
    ORDER_FACTS_TARGET_SCHEMA,
    ORDERS_SOURCE_FRESHNESS,
    ORDERS_SOURCE_QUALITY,
    ORDERS_SOURCE_SCHEMA,
    PIPELINE_NAME,
    PIPELINE_OWNER,
)
from datapulse.sdk import DataPulseClient


def setup(client: DataPulseClient, source_path: str, target_path: str | None = None) -> dict:
    """Register the ecommerce_orders pipeline, datasets, and contracts."""
    # Register pipeline
    pipeline = client.register_pipeline(PIPELINE_NAME, PIPELINE_OWNER)
    print(f"[DataPulse] Pipeline registered: {PIPELINE_NAME} (id={pipeline['id']})")

    # Register source dataset
    source_dataset = client.register_dataset(
        pipeline_name=PIPELINE_NAME,
        dataset_name="orders_source",
        role="source",
        contract_version=1,
        schema_definition=ORDERS_SOURCE_SCHEMA,
        freshness=ORDERS_SOURCE_FRESHNESS,
        quality_rules=ORDERS_SOURCE_QUALITY,
    )
    print("[DataPulse] Source dataset registered: orders_source (contract v1)")

    # Register target dataset
    target_dataset = client.register_dataset(
        pipeline_name=PIPELINE_NAME,
        dataset_name="order_facts_target",
        role="target",
        contract_version=1,
        schema_definition=ORDER_FACTS_TARGET_SCHEMA,
        freshness=ORDER_FACTS_TARGET_FRESHNESS,
        quality_rules=ORDER_FACTS_TARGET_QUALITY,
    )
    print("[DataPulse] Target dataset registered: order_facts_target (contract v1)")

    return {"pipeline": pipeline, "source": source_dataset, "target": target_dataset}


def run(
    client: DataPulseClient,
    source_path: str,
    target_path: str | None = None,
) -> dict:
    """Submit a run for the ecommerce_orders pipeline."""
    run_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"
    print(f"[DataPulse] Submitting run: {run_id}")
    print(f"[DataPulse]   Source: {source_path}")
    if target_path:
        print(f"[DataPulse]   Target: {target_path}")

    result = client.submit_run(
        pipeline_name=PIPELINE_NAME,
        run_id=run_id,
        source_path=source_path,
        target_path=target_path,
        target_dataset_name="order_facts_target" if target_path else None,
    )

    # Display results
    status_icon = "OK" if result["status"] == "passed" else "FAIL"
    print(f"\n[DataPulse] Run {run_id}: [{status_icon}] {result['status']}")

    # Show checks
    checks = result.get("checks", [])
    print(f"[DataPulse] Checks ({len(checks)}):")
    for check in checks:
        if check["status"] == "passed":
            print(f"  [OK] {check['type']}: {check['status']} - {check.get('message', '')}")
        elif check["status"] == "skipped":
            print(f"  [--] {check['type']}: {check['status']} - {check.get('message', '')}")
        else:
            print(f"  [!!] {check['type']}: {check['status']} - {check.get('message', '')}")

    # Show incidents
    incidents = result.get("incidents", [])
    if incidents:
        print(f"[DataPulse] Incidents ({len(incidents)}):")
        for inc in incidents:
            print(f"  [!] {inc['type']} ({inc['severity']}) - {inc.get('failure_summary', '')}")
            print(f"      Owner: {inc['owner']}, Retryable: {inc['retryable']}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Ecommerce orders pipeline adapter")
    parser.add_argument("--source", required=True, help="Path to source orders CSV")
    parser.add_argument("--target", help="Path to target order facts CSV (optional)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="DataPulse API URL")
    args = parser.parse_args()

    client = DataPulseClient(args.api_url)

    # Register pipeline and contracts
    setup(client, args.source, args.target)

    # Submit run
    result = run(client, args.source, args.target)

    # Exit with appropriate code
    if result["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
