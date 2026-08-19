"""S3 client factory — injectable S3 client for DataPulse.

Supports:
- Real boto3 client (production)
- LocalStack/MinIO (testing)
- Mock mode (development, no credentials needed)

Environment variables:
- DATAPULSE_S3_ENDPOINT_URL: Custom endpoint (LocalStack, MinIO)
- DATAPULSE_S3_REGION: AWS region (default: us-east-1)
- DATAPULSE_S3_ACCESS_KEY: AWS access key (or use IAM roles)
- DATAPULSE_S3_SECRET_KEY: AWS secret key (or use IAM roles)
- DATAPULSE_S3_MOCK: Set to "true" for mock mode (no real S3 calls)
"""

import os
from typing import Any


def create_s3_client() -> Any | None:
    """Create an S3 client based on environment configuration.

    Returns:
        boto3 S3 client if boto3 is available and credentials are configured.
        None if mock mode is enabled or boto3 is not installed.

    Priority:
    1. DATAPULSE_S3_MOCK=true → return None (caller uses mock)
    2. DATAPULSE_S3_ENDPOINT_URL → use custom endpoint (LocalStack/MinIO)
    3. DATAPULSE_S3_ACCESS_KEY + DATAPULSE_S3_SECRET_KEY → use explicit creds
    4. Default boto3 credentials (IAM roles, ~/.aws/credentials, env vars)
    """
    mock_mode = os.environ.get("DATAPULSE_S3_MOCK", "").lower() == "true"
    if mock_mode:
        return None

    try:
        import boto3
    except ImportError:
        return None

    endpoint_url = os.environ.get("DATAPULSE_S3_ENDPOINT_URL")
    region = os.environ.get("DATAPULSE_S3_REGION", "us-east-1")
    access_key = os.environ.get("DATAPULSE_S3_ACCESS_KEY")
    secret_key = os.environ.get("DATAPULSE_S3_SECRET_KEY")

    # Only auto-create client when explicitly configured
    # Don't use default AWS credentials — require explicit opt-in
    if not endpoint_url and not access_key:
        return None

    kwargs = {"region_name": region}

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    try:
        client = boto3.client("s3", **kwargs)
        # Quick connectivity check
        try:
            client.list_buckets()
        except Exception:
            return None
        return client
    except Exception:
        return None


def create_s3_client_from_config(
    endpoint_url: str | None = None,
    region: str = "us-east-1",
    access_key: str | None = None,
    secret_key: str | None = None,
) -> Any | None:
    """Create an S3 client from explicit configuration.

    Use this when you want to create a client for a specific
    endpoint (e.g., LocalStack in tests) without relying on env vars.
    """
    try:
        import boto3
    except ImportError:
        return None

    kwargs = {"region_name": region}

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    try:
        return boto3.client("s3", **kwargs)
    except Exception:
        return None
