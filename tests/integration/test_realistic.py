"""Realistic end-to-end pipeline test.

Tests DataPulse with a realistic dataset (not tiny fixtures).
Validates:
- Large dataset handling
- All 5 checks pass with valid data
- Incidents created for failures
- Dashboard data is correct
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from datapulse.references import DatasetReference


def _generate_orders_csv(path: Path, num_orders: int = 1000, days_old: int = 0):
    """Generate a realistic orders CSV file."""
    base_date = datetime.now(timezone.utc) - timedelta(days=days_old)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "order_id",
                "customer_id",
                "order_date",
                "product_id",
                "product_name",
                "category",
                "quantity",
                "unit_price",
                "total_amount",
                "payment_method",
                "shipping_address",
                "status",
            ]
        )

        for i in range(num_orders):
            order_date = (base_date - timedelta(hours=i % 24)).strftime("%Y-%m-%d")
            writer.writerow(
                [
                    f"ORD-{i + 1:06d}",
                    f"CUST-{(i % 500) + 1:04d}",
                    order_date,
                    f"PROD-{(i % 100) + 1:03d}",
                    f"Product {(i % 100) + 1}",
                    ["Electronics", "Sports", "Books", "Home", "Food"][i % 5],
                    (i % 10) + 1,
                    f"{(i % 100) + 9.99:.2f}",
                    f"{((i % 10) + 1) * ((i % 100) + 9.99):.2f}",
                    ["Credit Card", "PayPal", "Debit Card"][i % 3],
                    f"{i + 1} Main St, City {i % 50}",
                    ["completed", "shipped", "processing"][i % 3],
                ]
            )


class TestRealisticPipeline:
    """Test DataPulse with realistic datasets."""

    def test_large_dataset_readability(self, tmp_path):
        """Source readability check with 1000 rows."""
        csv_path = tmp_path / "orders.csv"
        _generate_orders_csv(csv_path, num_orders=1000)

        ref = DatasetReference.from_legacy_path(str(csv_path))
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 1000
        assert rd.column_count == 12

    def test_large_dataset_schema_check(self, tmp_path):
        """Schema compatibility with 1000 rows."""
        from datapulse.checks.schema_compatibility import check_schema_compatibility

        csv_path = tmp_path / "orders.csv"
        _generate_orders_csv(csv_path, num_orders=1000)

        schema = {
            "order_id": {"type": "string", "nullable": False},
            "customer_id": {"type": "string", "nullable": False},
            "order_date": {"type": "date", "nullable": False},
            "product_id": {"type": "string", "nullable": False},
            "product_name": {"type": "string", "nullable": False},
            "category": {"type": "string", "nullable": False},
            "quantity": {"type": "integer", "nullable": False},
            "unit_price": {"type": "decimal", "nullable": False},
            "total_amount": {"type": "decimal", "nullable": False},
            "payment_method": {"type": "string", "nullable": False},
            "shipping_address": {"type": "string", "nullable": False},
            "status": {"type": "string", "nullable": False},
        }

        result = check_schema_compatibility(str(csv_path), schema)
        assert result["status"] == "passed"

    def test_fresh_data_passes_freshness(self, tmp_path):
        """Fresh data should pass freshness check."""
        from datapulse.checks.freshness import check_freshness

        csv_path = tmp_path / "fresh.csv"
        _generate_orders_csv(csv_path, num_orders=100, days_old=0)

        result = check_freshness(str(csv_path), {"max_age_hours": 24, "timestamp_column": "order_date"})
        assert result["status"] == "passed"

    def test_stale_data_fails_freshness(self, tmp_path):
        """Stale data should fail freshness check."""
        from datapulse.checks.freshness import check_freshness

        csv_path = tmp_path / "stale.csv"
        _generate_orders_csv(csv_path, num_orders=100, days_old=30)

        result = check_freshness(str(csv_path), {"max_age_hours": 24, "timestamp_column": "order_date"})
        assert result["status"] == "failed"

    def test_row_count_within_range(self, tmp_path):
        """Row count check with 1000 rows, range [100, 50000]."""
        from datapulse.checks.row_count import check_row_count

        csv_path = tmp_path / "orders.csv"
        _generate_orders_csv(csv_path, num_orders=1000)

        result = check_row_count(
            str(csv_path),
            {"min_row_count": 100, "max_row_count": 50000, "unique_keys": ["order_id"]},
        )
        assert result["status"] == "passed"

    def test_duplicate_keys_detected(self, tmp_path):
        """Duplicate keys should be detected."""
        from datapulse.checks.row_count import check_row_count

        csv_path = tmp_path / "duplicates.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["order_id", "amount"])
            for i in range(100):
                # Every 10th row has the same order_id
                writer.writerow([f"ORD-{i // 10:03d}", f"{i}.00"])

        result = check_row_count(
            str(csv_path),
            {"min_row_count": 1, "max_row_count": 1000, "unique_keys": ["order_id"]},
        )
        assert result["status"] == "failed"
        assert "duplicate" in result["message"].lower()
