"""Integration tests — API endpoints and run lifecycle."""

from pathlib import Path

import pytest

FIXTURES = str(Path(__file__).resolve().parent.parent.parent / "examples" / "fixtures")


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestPipelineRegistration:
    def test_register_pipeline(self, client):
        r = client.post("/pipelines", json={"name": "test_pipe", "owner": "test_owner"})
        assert r.status_code == 201
        assert r.json()["name"] == "test_pipe"
        assert r.json()["enabled"] is True

    def test_register_same_pipeline_is_idempotent(self, client):
        r1 = client.post("/pipelines", json={"name": "p", "owner": "o"})
        r2 = client.post("/pipelines", json={"name": "p", "owner": "o"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"]


class TestDatasetRegistration:
    def test_register_dataset(self, client, registered_pipeline):
        r = client.post("/datasets", json={
            "pipeline_name": "ecommerce_inventory",
            "dataset_name": "test_ds",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {"id": {"type": "integer", "nullable": False}},
            "freshness": {"max_age_hours": 24, "timestamp_column": "id"},
            "quality_rules": {"unique_keys": ["id"], "min_row_count": 1, "max_row_count": 100},
        })
        assert r.status_code == 201
        assert r.json()["contract_version"] == 1

    def test_dataset_without_pipeline_returns_404(self, client):
        r = client.post("/datasets", json={
            "pipeline_name": "nonexistent",
            "dataset_name": "ds",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {},
            "freshness": {},
            "quality_rules": {},
        })
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_dataset_is_idempotent(self, client, registered_pipeline):
        payload = {
            "pipeline_name": "ecommerce_inventory",
            "dataset_name": "inv",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {"id": {"type": "integer", "nullable": False}},
            "freshness": {"max_age_hours": 24, "timestamp_column": "id"},
            "quality_rules": {},
        }
        r1 = client.post("/datasets", json=payload)
        r2 = client.post("/datasets", json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["contract_id"] == r2.json()["contract_id"]


class TestRunLifecycle:
    def test_valid_run_passes(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-valid",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        d = r.json()
        assert r.status_code == 201
        assert len(d["checks"]) == 5
        # All checks except freshness pass (fixtures have old dates)
        readability = next(c for c in d["checks"] if c["type"] == "source_readability")
        assert readability["status"] == "passed"

    def test_schema_drift_creates_incident(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-drift",
            "source_path": f"{FIXTURES}/inventory_schema_drift.csv",
        })
        d = r.json()
        assert r.status_code == 201
        # Schema check should fail
        schema_check = next(c for c in d["checks"] if c["type"] == "schema_compatibility")
        assert schema_check["status"] == "failed"
        assert "loyalty_points" in str(schema_check["observed"])
        # Incident created
        assert len(d["incidents"]) >= 1
        inc = d["incidents"][0]
        assert inc["owner"] == "data-platform"
        assert inc["retryable"] is True

    def test_missing_file_fails_clearly(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-missing",
            "source_path": "nonexistent.csv",
        })
        d = r.json()
        assert r.status_code == 201
        assert d["status"] == "failed"
        # Only readability check runs (short-circuit on failure)
        assert len(d["checks"]) == 1
        readability = d["checks"][0]
        assert readability["type"] == "source_readability"
        assert readability["status"] == "failed"
        assert "not found" in readability["message"].lower()

    def test_run_without_pipeline_returns_400(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "nonexistent",
            "run_id": "run-x",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        assert r.status_code == 400

    def test_duplicate_run_is_idempotent(self, client, registered_dataset):
        payload = {
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-dup",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        }
        r1 = client.post("/runs", json=payload)
        r2 = client.post("/runs", json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["run_id"] == r2.json()["run_id"]
        assert r1.json()["status"] == r2.json()["status"]


class TestGetRunHealth:
    def test_get_existing_run(self, client, registered_dataset):
        # Submit a run first
        client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-get",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        r = client.get("/pipelines/ecommerce_inventory/runs/run-get")
        assert r.status_code == 200
        assert r.json()["run_id"] == "run-get"

    def test_get_nonexistent_run_returns_404(self, client, registered_pipeline):
        r = client.get("/pipelines/ecommerce_inventory/runs/nope")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_get_nonexistent_pipeline_returns_404(self, client):
        r = client.get("/pipelines/nope/runs/nope")
        assert r.status_code == 404


class TestPipelineHealth:
    def test_latest_health(self, client, registered_dataset):
        client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-h1",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        r = client.get("/pipelines/ecommerce_inventory/health")
        assert r.status_code == 200
        assert r.json()["run_id"] == "run-h1"

    def test_no_runs_returns_404(self, client, registered_pipeline):
        r = client.get("/pipelines/ecommerce_inventory/health")
        assert r.status_code == 404


class TestIncidentFields:
    def test_incident_has_all_required_fields(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-inc",
            "source_path": f"{FIXTURES}/inventory_schema_drift.csv",
        })
        d = r.json()
        assert len(d["incidents"]) >= 1
        inc = d["incidents"][0]
        for field in ("type", "severity", "owner", "status", "retryable", "failure_summary"):
            assert field in inc, f"incident missing {field}"


class TestCheckResultFields:
    def test_check_results_have_expected_and_observed(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-chk",
            "source_path": f"{FIXTURES}/inventory_schema_drift.csv",
        })
        d = r.json()
        for check in d["checks"]:
            if check["status"] == "failed":
                assert check["expected"] is not None, f"{check['type']} missing expected"
                assert check["observed"] is not None, f"{check['type']} missing observed"
                assert check["message"], f"{check['type']} missing message"


class TestTimestampsUTC:
    def test_started_at_and_ended_at_present(self, client, registered_dataset):
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-ts",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        d = r.json()
        assert d["started_at"] is not None
        assert d["ended_at"] is not None
        # ISO format with timezone or at least valid format
        assert "T" in d["started_at"]
        assert "T" in d["ended_at"]


class TestContractVersionEnforcement:
    def test_specific_version_is_loaded(self, client, registered_dataset):
        """Version 1 allows 50 rows, version 2 allows only 2.
        Same 5-row file: v1 passes, v2 fails on row count.
        """
        # Register version 2 with a very tight row count limit
        r = client.post("/datasets", json={
            "pipeline_name": "ecommerce_inventory",
            "dataset_name": "inventory_snapshot",
            "role": "source",
            "contract_version": 2,
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
            "freshness": {"max_age_hours": 99999, "timestamp_column": "snapshot_date"},
            "quality_rules": {"unique_keys": ["product_id"], "min_row_count": 1, "max_row_count": 2},
        })
        assert r.status_code == 201

        # Version 1 (max_row_count=50) should pass with 5-row fixture
        r1 = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-v1",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "contract_version": 1,
        })
        assert r1.status_code == 201
        assert r1.json()["contract_version"] == 1
        row_check_v1 = next(c for c in r1.json()["checks"] if c["type"] == "row_count")
        assert row_check_v1["status"] == "passed"

        # Version 2 (max_row_count=2) should fail with same 5-row fixture
        r2 = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-v2",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "contract_version": 2,
        })
        assert r2.status_code == 201
        assert r2.json()["contract_version"] == 2
        row_check_v2 = next(c for c in r2.json()["checks"] if c["type"] == "row_count")
        assert row_check_v2["status"] == "failed"

    def test_nonexistent_version_returns_400(self, client, registered_dataset):
        """Requesting a version that doesn't exist should fail."""
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-ver-99",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "contract_version": 99,
        })
        assert r.status_code == 400
        assert "version 99 not found" in r.json()["detail"].lower()


class TestDuplicateKeyValidation:
    def test_no_duplicates_passes(self, client, registered_dataset):
        """Valid fixture has unique product_ids — should pass."""
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-nodup",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        d = r.json()
        row_check = next(c for c in d["checks"] if c["type"] == "row_count")
        assert row_check["status"] == "passed"

    def test_duplicates_detected(self, client, registered_dataset, tmp_path):
        """CSV with duplicate product_ids should fail row_count check."""
        # Create a CSV with duplicate product_id
        rows = [
            "snapshot_date,product_id,sku,warehouse_id,stock_on_hand,reserved_quantity,reorder_point,reorder_quantity,restock_lead_time_days,unit_cost,supplier_id,supplier_name,last_restock_date",
            "2026-08-18,1,FS-0001,WH-NYC,33,6,20,60,7,72.50,SUP-001,Northline Supply,2026-08-18",
            "2026-08-18,1,FS-0001,WH-NYC,33,6,20,60,7,72.50,SUP-001,Northline Supply,2026-08-18",
            "2026-08-18,2,FS-0002,WH-NYC,5,3,15,50,10,14.25,SUP-002,Urban Goods Co,2026-08-18",
        ]
        dup_file = tmp_path / "duplicates.csv"
        dup_file.write_text("\n".join(rows), encoding="utf-8")

        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-dup",
            "source_path": str(dup_file),
        })
        d = r.json()
        row_check = next(c for c in d["checks"] if c["type"] == "row_count")
        assert row_check["status"] == "failed"
        assert "duplicate" in row_check["message"].lower()


class TestTargetSchemaSkipped:
    """Regression: target_schema_compat must be SKIPPED when no target supplied."""

    def test_no_target_returns_skipped(self, client, registered_dataset):
        """When no target_path is given, target_schema_compatibility should be skipped."""
        # Register a target dataset so the check type is active
        r = client.post("/datasets", json={
            "pipeline_name": "ecommerce_inventory",
            "dataset_name": "inventory_target",
            "role": "target",
            "contract_version": 1,
            "schema_definition": {
                "snapshot_date": {"type": "date", "nullable": False},
                "product_id": {"type": "integer", "nullable": False},
                "sku": {"type": "string", "nullable": False},
                "warehouse_id": {"type": "string", "nullable": False},
                "stock_on_hand": {"type": "integer", "nullable": False},
            },
            "freshness": {"max_age_hours": 24, "timestamp_column": "snapshot_date"},
            "quality_rules": {"unique_keys": ["product_id"], "min_row_count": 1, "max_row_count": 100},
        })
        assert r.status_code == 201

        # Run with source only — no target_path
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-tgt-skip",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
        })
        d = r.json()
        assert r.status_code == 201

        target_check = next(c for c in d["checks"] if c["type"] == "target_schema_compatibility")
        assert target_check["status"] == "skipped"
        assert "no target" in target_check["message"].lower()


class TestSourceToTargetReconciliation:
    def test_matching_counts_pass(self, client, registered_dataset, tmp_path):
        """Source and target with same row count should pass."""
        header = "snapshot_date,product_id,sku,warehouse_id,stock_on_hand,reserved_quantity,reorder_point,reorder_quantity,restock_lead_time_days,unit_cost,supplier_id,supplier_name,last_restock_date"
        row = "2026-08-18,1,FS-0001,WH-NYC,33,6,20,60,7,72.50,SUP-001,Northline Supply,2026-08-18"
        src = tmp_path / "src.csv"
        tgt = tmp_path / "tgt.csv"
        content = f"{header}\n{row}\n"
        src.write_text(content, encoding="utf-8")
        tgt.write_text(content, encoding="utf-8")

        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-recon-ok",
            "source_path": str(src),
            "target_path": str(tgt),
        })
        d = r.json()
        row_check = next(c for c in d["checks"] if c["type"] == "row_count")
        assert row_check["status"] == "passed"

    def test_mismatched_counts_fail(self, client, registered_dataset, tmp_path):
        """Source with 2 rows, target with 1 row should fail reconciliation."""
        header = "snapshot_date,product_id,sku,warehouse_id,stock_on_hand,reserved_quantity,reorder_point,reorder_quantity,restock_lead_time_days,unit_cost,supplier_id,supplier_name,last_restock_date"
        row1 = "2026-08-18,1,FS-0001,WH-NYC,33,6,20,60,7,72.50,SUP-001,Northline Supply,2026-08-18"
        row2 = "2026-08-18,2,FS-0002,WH-NYC,5,3,15,50,10,14.25,SUP-002,Urban Goods Co,2026-08-18"
        src = tmp_path / "src.csv"
        tgt = tmp_path / "tgt.csv"
        src.write_text(f"{header}\n{row1}\n{row2}\n", encoding="utf-8")
        tgt.write_text(f"{header}\n{row1}\n", encoding="utf-8")

        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-recon-fail",
            "source_path": str(src),
            "target_path": str(tgt),
        })
        d = r.json()
        row_check = next(c for c in d["checks"] if c["type"] == "row_count")
        assert row_check["status"] == "failed"
        assert "mismatch" in row_check["message"].lower()

    def test_missing_target_file_fails(self, client, registered_dataset):
        """Providing a target_path that doesn't exist should fail clearly."""
        r = client.post("/runs", json={
            "pipeline_name": "ecommerce_inventory",
            "run_id": "run-no-tgt",
            "source_path": f"{FIXTURES}/inventory_valid.csv",
            "target_path": "nonexistent_target.csv",
        })
        d = r.json()
        row_check = next(c for c in d["checks"] if c["type"] == "row_count")
        assert row_check["status"] == "failed"
        assert "target" in row_check["message"].lower()
        assert "not found" in row_check["message"].lower()
