"""Tests for DatasetReference abstraction."""

from pathlib import Path

from datapulse.references import DatasetReference, ReferenceType, ResolvedData

# ── URI parsing ────────────────────────────────────────────────


class TestURIParsing:
    """Test that URIs are parsed into correct reference types."""

    def test_local_uri(self):
        ref = DatasetReference.from_uri("local://data/file.csv")
        assert ref.ref_type == ReferenceType.LOCAL
        assert ref.raw_path == "data/file.csv"
        assert ref.uri == "local://data/file.csv"

    def test_s3_uri(self):
        ref = DatasetReference.from_uri("s3://bucket/key.parquet")
        assert ref.ref_type == ReferenceType.S3
        assert ref.raw_path == "bucket/key.parquet"
        assert ref.uri == "s3://bucket/key.parquet"

    def test_table_uri(self):
        ref = DatasetReference.from_uri("table://warehouse.fact_orders")
        assert ref.ref_type == ReferenceType.TABLE
        assert ref.raw_path == "warehouse.fact_orders"

    def test_query_uri(self):
        ref = DatasetReference.from_uri("query://SELECT * FROM orders")
        assert ref.ref_type == ReferenceType.QUERY
        assert ref.raw_path == "SELECT * FROM orders"

    def test_partition_uri(self):
        ref = DatasetReference.from_uri("partition://s3://bucket/dt=2026-08-19/")
        assert ref.ref_type == ReferenceType.PARTITION
        assert ref.raw_path == "s3://bucket/dt=2026-08-19/"

    def test_bare_path_treated_as_local(self):
        ref = DatasetReference.from_uri("/data/file.csv")
        assert ref.ref_type == ReferenceType.LOCAL
        assert ref.raw_path == "/data/file.csv"

    def test_unknown_scheme_treated_as_local(self):
        ref = DatasetReference.from_uri("ftp://server/file.csv")
        assert ref.ref_type == ReferenceType.LOCAL

    def test_legacy_path_conversion(self):
        ref = DatasetReference.from_legacy_path("/data/file.csv")
        assert ref.ref_type == ReferenceType.LOCAL
        assert ref.uri == "local:///data/file.csv"

    def test_legacy_path_with_uri(self):
        ref = DatasetReference.from_legacy_path("s3://bucket/key")
        assert ref.ref_type == ReferenceType.S3


# ── ResolvedData ───────────────────────────────────────────────


class TestResolvedData:
    """Test ResolvedData construction and helpers."""

    def test_from_error(self):
        rd = ResolvedData.from_error("local://bad.csv", "not found")
        assert rd.is_parseable is False
        assert rd.error == "not found"
        assert rd.row_count == 0
        assert rd.columns == []

    def test_successful_resolution(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")

        ref = DatasetReference.from_uri(f"local://{csv_file}")
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.error is None
        assert rd.row_count == 2
        assert rd.column_count == 2
        assert rd.columns == ["id", "name"]
        assert rd.rows[0] == {"id": "1", "name": "Alice"}
        assert rd.rows[1] == {"id": "2", "name": "Bob"}


# ── Local file resolver ───────────────────────────────────────


class TestLocalResolver:
    """Test local file resolution."""

    def test_resolve_valid_csv(self, tmp_path):
        csv_file = tmp_path / "orders.csv"
        csv_file.write_text(
            "order_id,amount\nORD-001,100.00\nORD-002,200.00\n",
            encoding="utf-8",
        )

        ref = DatasetReference.from_uri(f"local://{csv_file}")
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 2
        assert rd.columns == ["order_id", "amount"]

    def test_resolve_missing_file(self):
        ref = DatasetReference.from_uri("local:///nonexistent/file.csv")
        rd = ref.resolve()

        assert rd.is_parseable is False
        assert "not found" in rd.error.lower()

    def test_resolve_empty_file(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("", encoding="utf-8")

        ref = DatasetReference.from_uri(f"local://{csv_file}")
        rd = ref.resolve()

        assert rd.is_parseable is False

    def test_resolve_directory(self, tmp_path):
        ref = DatasetReference.from_uri(f"local://{tmp_path}")
        rd = ref.resolve()

        assert rd.is_parseable is False


# ── S3 mock resolver ──────────────────────────────────────────


class TestS3MockResolver:
    """Test S3 resolution in mock mode (requires DATAPULSE_S3_MOCK=true)."""

    def test_s3_mock_returns_synthetic_data(self, monkeypatch):
        monkeypatch.setenv("DATAPULSE_S3_MOCK", "true")
        ref = DatasetReference.from_uri("s3://bucket/orders.parquet")
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 10
        assert rd.columns == ["order_id", "amount", "status"]
        assert rd.rows[0]["order_id"] == "MOCK-001"
        assert rd.source_uri == "s3://bucket/orders.parquet"

    def test_s3_without_client_and_no_mock_fails(self):
        ref = DatasetReference.from_uri("s3://bucket/orders.parquet")
        rd = ref.resolve()

        assert rd.is_parseable is False
        assert "S3 client required" in rd.error

    def test_s3_mock_different_uris(self, monkeypatch):
        monkeypatch.setenv("DATAPULSE_S3_MOCK", "true")
        ref1 = DatasetReference.from_uri("s3://bucket-a/data.csv")
        ref2 = DatasetReference.from_uri("s3://bucket-b/data.csv")

        rd1 = ref1.resolve()
        rd2 = ref2.resolve()

        assert rd1.is_parseable is True
        assert rd2.is_parseable is True
        assert rd1.source_uri != rd2.source_uri


# ── Integration with real fixtures ────────────────────────────


class TestFixtureIntegration:
    """Test DatasetReference with actual project fixtures."""

    FIXTURES = Path(__file__).resolve().parent.parent.parent / "examples" / "fixtures"

    def test_resolve_healthcare_admissions(self):
        csv_path = self.FIXTURES / "healthcare_admissions.csv"
        ref = DatasetReference.from_legacy_path(str(csv_path))
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 5
        assert rd.column_count == 15
        assert "admission_id" in rd.columns

    def test_resolve_ecommerce_orders(self):
        csv_path = self.FIXTURES / "ecommerce_orders.csv"
        ref = DatasetReference.from_legacy_path(str(csv_path))
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 10
        assert rd.column_count == 12
        assert "order_id" in rd.columns

    def test_resolve_ecommerce_orders_fresh(self):
        csv_path = self.FIXTURES / "ecommerce_orders_fresh.csv"
        ref = DatasetReference.from_legacy_path(str(csv_path))
        rd = ref.resolve()

        assert rd.is_parseable is True
        assert rd.row_count == 101
        assert "order_date" in rd.columns


class TestURIPreservation:
    """Test that URI schemes survive from API to resolver."""

    def test_s3_uri_preserved_in_from_uri(self):
        """S3 URI should not be converted to a local path."""
        ref = DatasetReference.from_uri("s3://my-bucket/data/orders.csv")
        assert ref.ref_type == ReferenceType.S3
        assert ref.raw_path == "my-bucket/data/orders.csv"
        assert ref.uri == "s3://my-bucket/data/orders.csv"
        # The scheme should NOT be destroyed
        assert "\\" not in ref.raw_path  # No Windows path mangling

    def test_local_path_still_works(self):
        """Bare local paths should still resolve as local."""
        ref = DatasetReference.from_uri("/data/file.csv")
        assert ref.ref_type == ReferenceType.LOCAL
        assert ref.raw_path == "/data/file.csv"

    def test_s3_uri_resolves_in_mock_mode(self, monkeypatch):
        """S3 URI should resolve to mock data when DATAPULSE_S3_MOCK=true."""
        monkeypatch.setenv("DATAPULSE_S3_MOCK", "true")
        ref = DatasetReference.from_uri("s3://bucket/key.csv")
        rd = ref.resolve()
        assert rd.is_parseable is True
        assert rd.source_uri == "s3://bucket/key.csv"

    def test_s3_uri_fails_without_mock(self):
        """S3 URI should fail clearly when mock mode is off."""
        ref = DatasetReference.from_uri("s3://bucket/key.csv")
        rd = ref.resolve()
        assert rd.is_parseable is False
        assert "S3 client required" in rd.error
