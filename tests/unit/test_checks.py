"""Unit tests for the four data quality checks."""

from pathlib import Path

from datapulse.checks.freshness import check_freshness
from datapulse.checks.row_count import check_row_count
from datapulse.checks.schema_compatibility import check_schema_compatibility
from datapulse.checks.source_readability import check_source_readability
from datapulse.models.check_result import CheckStatus

FIXTURES = Path(__file__).resolve().parent.parent.parent / "examples" / "fixtures"

SCHEMA_13 = {
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
}
QUALITY = {"unique_keys": ["product_id"], "min_row_count": 1, "max_row_count": 50}
FRESHNESS = {"max_age_hours": 24, "timestamp_column": "snapshot_date"}


# ── Source Readability ──────────────────────────────────────────


class TestSourceReadability:
    def test_valid_file_passes(self):
        result = check_source_readability(FIXTURES / "inventory_valid.csv")
        assert result["status"] == CheckStatus.PASSED
        assert "5 rows" in result["message"]

    def test_missing_file_fails(self, tmp_path):
        result = check_source_readability(tmp_path / "nope.csv")
        assert result["status"] == CheckStatus.FAILED
        assert "not found" in result["message"]

    def test_empty_file_fails(self, tmp_path):
        empty = tmp_path / "empty.csv"
        empty.write_text("", encoding="utf-8")
        result = check_source_readability(empty)
        assert result["status"] == CheckStatus.FAILED

    def test_result_has_expected_shape(self):
        result = check_source_readability(FIXTURES / "inventory_valid.csv")
        for key in ("status", "expected", "observed", "message"):
            assert key in result


# ── Schema Compatibility ───────────────────────────────────────


class TestSchemaCompatibility:
    def test_valid_schema_passes(self):
        result = check_schema_compatibility(FIXTURES / "inventory_valid.csv", SCHEMA_13)
        assert result["status"] == CheckStatus.PASSED
        assert "13 columns" in result["message"]

    def test_unexpected_column_detected(self):
        result = check_schema_compatibility(FIXTURES / "inventory_schema_drift.csv", SCHEMA_13)
        assert result["status"] == CheckStatus.FAILED
        assert "loyalty_points" in str(result["observed"]["unexpected"])

    def test_missing_column_fails(self, tmp_path):
        """CSV with fewer columns than contract."""
        rows = [{"product_id": "1", "sku": "X"}]
        path = tmp_path / "missing.csv"
        with path.open("w", newline="") as f:
            import csv

            w = csv.DictWriter(f, fieldnames=["product_id", "sku"])
            w.writeheader()
            w.writerows(rows)
        result = check_schema_compatibility(path, SCHEMA_13)
        assert result["status"] == CheckStatus.FAILED
        assert "Missing columns" in result["message"]

    def test_null_in_non_nullable_fails(self):
        result = check_schema_compatibility(FIXTURES / "inventory_schema_drift.csv", SCHEMA_13)
        assert result["status"] == CheckStatus.FAILED
        assert "Null" in result["message"]

    def test_type_mismatch_fails(self, tmp_path):
        """product_id should be integer but is string."""
        rows = [
            {
                "snapshot_date": "2026-07-27",
                "product_id": "abc",
                "sku": "X",
                "warehouse_id": "WH",
                "stock_on_hand": "5",
                "reserved_quantity": "0",
                "reorder_point": "10",
                "reorder_quantity": "20",
                "restock_lead_time_days": "7",
                "unit_cost": "10.00",
                "supplier_id": "S1",
                "supplier_name": "Test",
                "last_restock_date": "2026-07-20",
            }
        ]
        path = tmp_path / "bad_type.csv"
        with path.open("w", newline="") as f:
            import csv

            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        result = check_schema_compatibility(path, SCHEMA_13)
        assert result["status"] == CheckStatus.FAILED
        assert "Type" in result["message"]


# ── Row Count ──────────────────────────────────────────────────


class TestRowCount:
    def test_within_range_passes(self):
        result = check_row_count(FIXTURES / "inventory_valid.csv", QUALITY)
        assert result["status"] == CheckStatus.PASSED

    def test_below_minimum_fails(self, tmp_path):
        rows = [
            {
                "product_id": "1",
                "sku": "X",
                "snapshot_date": "2026-07-27",
                "warehouse_id": "WH",
                "stock_on_hand": "5",
                "reserved_quantity": "0",
                "reorder_point": "10",
                "reorder_quantity": "20",
                "restock_lead_time_days": "7",
                "unit_cost": "10.00",
                "supplier_id": "S1",
                "supplier_name": "Test",
                "last_restock_date": "2026-07-20",
            }
        ]
        path = tmp_path / "one_row.csv"
        with path.open("w", newline="") as f:
            import csv

            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        result = check_row_count(path, {"min_row_count": 10, "max_row_count": 50})
        assert result["status"] == CheckStatus.FAILED
        assert "outside range" in result["message"]

    def test_above_maximum_fails(self):
        result = check_row_count(FIXTURES / "inventory_valid.csv", {"min_row_count": 1, "max_row_count": 2})
        assert result["status"] == CheckStatus.FAILED

    def test_at_boundary_passes(self):
        result = check_row_count(FIXTURES / "inventory_valid.csv", {"min_row_count": 5, "max_row_count": 5})
        assert result["status"] == CheckStatus.PASSED


# ── Freshness ──────────────────────────────────────────────────


class TestFreshness:
    def test_stale_data_fails(self):
        """All fixtures use old dates — should fail freshness."""
        result = check_freshness(FIXTURES / "inventory_valid.csv", FRESHNESS)
        assert result["status"] == CheckStatus.FAILED
        assert "stale" in result["message"]

    def test_recent_data_passes(self, tmp_path):
        """Create a fixture with today's date."""
        from datetime import date

        today = date.today().isoformat()
        rows = [
            {
                "product_id": "1",
                "sku": "X",
                "snapshot_date": today,
                "warehouse_id": "WH",
                "stock_on_hand": "5",
                "reserved_quantity": "0",
                "reorder_point": "10",
                "reorder_quantity": "20",
                "restock_lead_time_days": "7",
                "unit_cost": "10.00",
                "supplier_id": "S1",
                "supplier_name": "Test",
                "last_restock_date": today,
            }
        ]
        path = tmp_path / "fresh.csv"
        with path.open("w", newline="") as f:
            import csv

            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        result = check_freshness(path, FRESHNESS)
        assert result["status"] == CheckStatus.PASSED
        assert "fresh" in result["message"]

    def test_very_stale_data_shows_age(self):
        result = check_freshness(FIXTURES / "inventory_stale.csv", FRESHNESS)
        assert result["status"] == CheckStatus.FAILED
        assert result["observed"]["age_hours"] > 1000  # June 2026 → Aug 2026
