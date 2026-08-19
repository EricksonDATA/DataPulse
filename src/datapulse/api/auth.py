"""API authentication — API key middleware."""

import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

# API key configuration
# Set DATAPULSE_API_KEY env var to enable authentication
# If not set, authentication is disabled (development mode)
API_KEY = os.environ.get("DATAPULSE_API_KEY", "")
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Validate API key from request header.

    If DATAPULSE_API_KEY is not set, authentication is disabled.
    If set, all requests must include a valid X-API-Key header.
    """
    # Development mode — no authentication
    if not API_KEY:
        return "dev-mode"

    # Production mode — require valid API key
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header.",
        )

    if api_key != API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key.",
        )

    return api_key
