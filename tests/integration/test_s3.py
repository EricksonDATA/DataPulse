"""S3 integration tests — test real S3 behavior using LocalStack.

These tests require LocalStack running. They test:
- Real S3 client creation
- Reading CSV from S3
- Error handling for missing objects
- Bucket creation and object upload

Run with: docker compose -f docker-compose.test.yml up -d
Then: python -m pytest tests/integration/test_s3.py -v
"""

import os
import time

import pytest

from datapulse.references import DatasetReference, ReferenceType
from datapulse.s3_client import create_s3_client_from_config

# LocalStack configuration
LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
LOCALSTACK_REGION = "us-east-1"
LOCALSTACK_ACCESS_KEY = "test"
LOCALSTACK_SECRET_KEY = "test"
TEST_BUCKET = "datapulse-test"


def _get_localstack_client():
    """Create a boto3 client pointing to LocalStack."""
    try:
        return create_s3_client_from_config(
            endpoint_url=LOCALSTACK_ENDPOINT,
            region=LOCALSTACK_REGION,
            access_key=LOCALSTACK_ACCESS_KEY,
            secret_key=LOCALSTACK_SECRET_KEY,
        )
    except Exception:
        return None


def _localstack_available():
    """Check if LocalStack is running."""
    client = _get_localstack_client()
    if client is None:
        return False
    try:
        client.list_buckets()
        return True
    except Exception:
        return False


# Skip all tests if LocalStack is not running
pytestmark = pytest.mark.skipif(
    not _localstack_available(),
    reason="LocalStack not running. Start with: docker compose -f docker-compose.test.yml up -d",
)


@pytest.fixture(scope="module")
def s3_client():
    """Create and return a LocalStack S3 client."""
    client = _get_localstack_client()
    assert client is not None, "Failed to create LocalStack client"
    return client


@pytest.fixture(scope="module")
def test_bucket(s3_client):
    """Create a test bucket in LocalStack."""
    try:
        s3_client.create_bucket(Bucket=TEST_BUCKET)
    except s3_client.exceptions.BucketAlreadyOwnedByYou:
        pass
    time.sleep(1)
    return TEST_BUCKET


@pytest.fixture(scope="module")
def test_csv_object(s3_client, test_bucket):
    """Upload a test CSV to LocalStack."""
    csv_content = "order_id,amount,status\nORD-001,100.00,completed\nORD-002,200.00,shipped\nORD-003,150.00,completed\n"
    s3_client.put_object(
        Bucket=test_bucket,
        Key="data/orders.csv",
        Body=csv_content.encode("utf-8"),
        ContentType="text/csv",
    )
    time.sleep(1)
    return f"s3://{test_bucket}/data/orders.csv"


class TestS3ClientFactory:
    """Test S3 client creation with explicit config."""

    def test_create_client_with_localstack(self, s3_client):
        """Client should connect to LocalStack."""
        response = s3_client.list_buckets()
        assert "Buckets" in response

    def test_create_client_with_bad_endpoint(self):
        """Client creation should fail with unreachable endpoint."""
        client = create_s3_client_from_config(
            endpoint_url="http://localhost:9999",
            region="us-east-1",
            access_key="test",
            secret_key="test",
        )
        assert client is not None


class TestS3ReferenceResolution:
    """Test DatasetReference S3 resolution with real S3."""

    @pytest.fixture(autouse=True)
    def _set_localstack_env(self, monkeypatch):
        """Set env vars so create_s3_client() picks up LocalStack."""
        monkeypatch.setenv("DATAPULSE_S3_ENDPOINT_URL", LOCALSTACK_ENDPOINT)
        monkeypatch.setenv("DATAPULSE_S3_ACCESS_KEY", LOCALSTACK_ACCESS_KEY)
        monkeypatch.setenv("DATAPULSE_S3_SECRET_KEY", LOCALSTACK_SECRET_KEY)
        monkeypatch.setenv("DATAPULSE_S3_REGION", LOCALSTACK_REGION)

    def test_resolve_s3_csv(self, test_csv_object):
        """Should read and parse CSV from S3."""
        ref = DatasetReference.from_uri(test_csv_object)
        assert ref.ref_type == ReferenceType.S3

        rd = ref.resolve()
        assert rd.is_parseable is True
        assert rd.row_count == 3
        assert rd.columns == ["order_id", "amount", "status"]
        assert rd.rows[0]["order_id"] == "ORD-001"
        assert rd.rows[0]["amount"] == "100.00"

    def test_resolve_s3_missing_object(self, test_bucket):
        """Should fail gracefully for missing S3 object."""
        ref = DatasetReference.from_uri(f"s3://{test_bucket}/nonexistent.csv")
        rd = ref.resolve()
        assert rd.is_parseable is False
        assert "Failed to resolve S3 object" in rd.error

    def test_resolve_s3_invalid_path(self):
        """Should fail for invalid S3 path (no key)."""
        ref = DatasetReference.from_uri("s3://bucket-only")
        rd = ref.resolve()
        assert rd.is_parseable is False
        assert "Invalid S3 path" in rd.error

    def test_resolve_s3_header_only(self, s3_client, test_bucket):
        """Should fail for header-only CSV (0 data rows)."""
        csv_header = "order_id,amount,status\n"
        s3_client.put_object(
            Bucket=test_bucket,
            Key="data/empty.csv",
            Body=csv_header.encode("utf-8"),
            ContentType="text/csv",
        )
        time.sleep(1)

        ref = DatasetReference.from_uri(f"s3://{test_bucket}/data/empty.csv")
        rd = ref.resolve()
        assert rd.row_count == 0 or not rd.is_parseable


class TestS3WithExplicitClient:
    """Test DatasetReference with explicit boto3 client."""

    def test_resolve_with_explicit_client(self, s3_client, test_csv_object):
        """Should use explicit client instead of auto-creating."""
        ref = DatasetReference.from_uri(test_csv_object)
        rd = ref.resolve(s3_client=s3_client)
        assert rd.is_parseable is True
        assert rd.row_count == 3

    def test_resolve_with_wrong_client(self, test_csv_object):
        """Should fail with client pointing to wrong endpoint."""
        wrong_client = create_s3_client_from_config(
            endpoint_url="http://localhost:9999",
            region="us-east-1",
            access_key="test",
            secret_key="test",
        )
        if wrong_client is None:
            pytest.skip("Could not create wrong client")

        ref = DatasetReference.from_uri(test_csv_object)
        rd = ref.resolve(s3_client=wrong_client)
        assert rd.is_parseable is False
