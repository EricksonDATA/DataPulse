"""
DataPulse adapter for the healthcare_analytics pipeline.

This script demonstrates how to integrate an existing pipeline with DataPulse.
It registers the pipeline, datasets, contracts, and submits runs.

Usage:
    python -m datapulse.adapters.healthcare_analytics --source datasets/admissions.csv

    # Or with a target for source-to-target reconciliation:
    python -m datapulse.adapters.healthcare_analytics \\
        --source datasets/admissions.csv \\
        --target path/to/fact_admission.csv

The adapter does NOT modify the pipeline. It observes externally.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone

from datapulse.contracts.healthcare_analytics import (
    ADMISSIONS_SOURCE_FRESHNESS,
    ADMISSIONS_SOURCE_QUALITY,
    ADMISSIONS_SOURCE_SCHEMA,
    FACT_ADMISSION_TARGET_FRESHNESS,
    FACT_ADMISSION_TARGET_QUALITY,
    FACT_ADMISSION_TARGET_SCHEMA,
    PIPELINE_NAME,
    PIPELINE_OWNER,
)
from datapulse.sdk import DataPulseClient


def generate_run_id() -> str:
    """Generate a deterministic run ID from current timestamp."""
    now = datetime.now(timezone.utc)
    return f"{now.strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6]}"


def setup(client: DataPulseClient) -> None:
    """Register the healthcare pipeline, datasets, and contracts."""
    # 1. Register pipeline
    result = client.register_pipeline(PIPELINE_NAME, PIPELINE_OWNER)
    print(f"[DataPulse] Pipeline registered: {result['name']} (id={result['id']})")

    # 2. Register source dataset (bronze admissions)
    result = client.register_dataset(
        pipeline_name=PIPELINE_NAME,
        dataset_name="admissions_source",
        role="source",
        contract_version=1,
        schema_definition=ADMISSIONS_SOURCE_SCHEMA,
        freshness=ADMISSIONS_SOURCE_FRESHNESS,
        quality_rules=ADMISSIONS_SOURCE_QUALITY,
        location="datasets/admissions.csv",
    )
    print(f"[DataPulse] Source dataset registered: {result['dataset_name']} (contract v{result['contract_version']})")

    # 3. Register target dataset (gold fact_admission)
    result = client.register_dataset(
        pipeline_name=PIPELINE_NAME,
        dataset_name="fact_admission_target",
        role="target",
        contract_version=1,
        schema_definition=FACT_ADMISSION_TARGET_SCHEMA,
        freshness=FACT_ADMISSION_TARGET_FRESHNESS,
        quality_rules=FACT_ADMISSION_TARGET_QUALITY,
        location="gold/fact_admission",
    )
    print(f"[DataPulse] Target dataset registered: {result['dataset_name']} (contract v{result['contract_version']})")


def run(client: DataPulseClient, source_path: str, target_path: str | None = None) -> dict:
    """Submit a pipeline run with source and optional target paths."""
    run_id = generate_run_id()

    print(f"[DataPulse] Submitting run: {run_id}")
    print(f"[DataPulse]   Source: {source_path}")
    if target_path:
        print(f"[DataPulse]   Target: {target_path}")

    result = client.submit_run(
        pipeline_name=PIPELINE_NAME,
        run_id=run_id,
        source_path=source_path,
        target_path=target_path,
        dataset_name="admissions_source",
        target_dataset_name="fact_admission_target",
        contract_version=1,
    )

    # Print summary
    status = result["status"]
    checks = result.get("checks", [])
    incidents = result.get("incidents", [])

    status_symbol = {"passed": "[OK]", "failed": "[FAIL]", "late": "[LATE]"}.get(status, "[??]")
    print(f"\n[DataPulse] Run {run_id}: {status_symbol} {status}")
    print(f"[DataPulse] Checks ({len(checks)}):")
    for c in checks:
        sym = "[OK]" if c["status"] == "passed" else "[!!]"
        msg = f" - {c['message'][:60]}" if c.get("message") else ""
        print(f"  {sym} {c['type']}: {c['status']}{msg}")

    if incidents:
        print(f"[DataPulse] Incidents ({len(incidents)}):")
        for inc in incidents:
            print(f"  [!] {inc['type']} ({inc['severity']}) - {inc.get('failure_summary', '')[:60]}")
            print(f"      Owner: {inc['owner']}, Retryable: {inc['retryable']}")

    return result


def main():
    parser = argparse.ArgumentParser(description="DataPulse adapter for healthcare_analytics")
    parser.add_argument("--api-url", default="http://localhost:8000", help="DataPulse API URL")
    parser.add_argument("--source", required=True, help="Path to source CSV (admissions)")
    parser.add_argument("--target", default=None, help="Path to target CSV (fact_admission)")
    parser.add_argument("--setup-only", action="store_true", help="Only register pipeline/datasets, don't run")
    args = parser.parse_args()

    client = DataPulseClient(args.api_url)

    # Verify API is available
    try:
        client.health()
    except Exception as e:
        print(f"[DataPulse] ERROR: Cannot reach API at {args.api_url}: {e}")
        sys.exit(1)

    # Register pipeline, datasets, contracts
    setup(client)

    if args.setup_only:
        print("[DataPulse] Setup complete. Use --source to submit a run.")
        return

    # Submit run
    source_path = args.source
    target_path = args.target

    result = run(client, source_path, target_path)

    # Exit with non-zero if run failed
    if result["status"] in ("failed", "late"):
        sys.exit(1)


if __name__ == "__main__":
    main()
