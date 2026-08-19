"""
DataPulse SDK — lightweight client for the DataPulse API.

Use this to integrate existing pipelines with DataPulse without
rewriting the pipeline itself. The SDK calls the REST API.

Usage:
    from datapulse.sdk import DataPulseClient

    client = DataPulseClient("http://localhost:8000")
    client.register_pipeline("my_pipeline", "data-team")
    client.register_dataset(...)
    result = client.submit_run(...)
"""

import logging

import httpx

logger = logging.getLogger("datapulse.sdk")


class DataPulseClient:
    """HTTP client for the DataPulse metadata API."""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an HTTP request to the API."""
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)
        # Add API key header if configured
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if headers:
            kwargs["headers"] = headers
        response = getattr(httpx, method)(url, **kwargs)
        response.raise_for_status()
        return response.json()

    # ── Pipeline ────────────────────────────────────────────────

    def register_pipeline(self, name: str, owner: str) -> dict:
        """Register a pipeline. Idempotent — returns existing if already registered."""
        return self._request("post", "/pipelines", json={"name": name, "owner": owner})

    # ── Dataset + Contract ──────────────────────────────────────

    def register_dataset(
        self,
        pipeline_name: str,
        dataset_name: str,
        role: str,
        contract_version: int,
        schema_definition: dict,
        freshness: dict,
        quality_rules: dict,
        location: str | None = None,
    ) -> dict:
        """Register a dataset with its contract. Idempotent per version."""
        return self._request(
            "post",
            "/datasets",
            json={
                "pipeline_name": pipeline_name,
                "dataset_name": dataset_name,
                "role": role,
                "location": location,
                "contract_version": contract_version,
                "schema_definition": schema_definition,
                "freshness": freshness,
                "quality_rules": quality_rules,
            },
        )

    # ── Run ─────────────────────────────────────────────────────

    def submit_run(
        self,
        pipeline_name: str,
        run_id: str,
        source_path: str,
        dataset_name: str,
        target_path: str | None = None,
        target_dataset_name: str | None = None,
        contract_version: int | None = None,
    ) -> dict:
        """Submit a pipeline run. Idempotent — same run_id returns cached result."""
        payload = {
            "pipeline_name": pipeline_name,
            "run_id": run_id,
            "source_path": source_path,
            "dataset_name": dataset_name,
        }
        if target_path:
            payload["target_path"] = target_path
        if target_dataset_name:
            payload["target_dataset_name"] = target_dataset_name
        if contract_version is not None:
            payload["contract_version"] = contract_version
        return self._request("post", "/runs", json=payload)

    # ── Query ───────────────────────────────────────────────────

    def get_run(self, pipeline_name: str, run_id: str) -> dict:
        """Get a specific run's health summary."""
        return self._request("get", f"/pipelines/{pipeline_name}/runs/{run_id}")

    def get_pipeline_health(self, pipeline_name: str) -> dict:
        """Get the latest run health for a pipeline."""
        return self._request("get", f"/pipelines/{pipeline_name}/health")

    def health(self) -> dict:
        """Check API availability."""
        return self._request("get", "/health")
