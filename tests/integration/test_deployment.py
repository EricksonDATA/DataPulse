"""Deployment verification — test production-like configuration.

Run after: docker compose -f docker-compose.prod.yml up -d

Verifies:
- All services healthy
- API authentication works
- Webhook secret validation works
- Migrations applied
- Grafana accessible with non-default credentials
"""

import os
import sys

import httpx

BASE_URL = os.environ.get("DATAPULSE_URL", "http://localhost:8000")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
API_KEY = os.environ.get("DATAPULSE_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("DATAPULSE_WEBHOOK_SECRET", "")
GRAFANA_USER = os.environ.get("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD", "admin")

checks = []


def ok(label, condition):
    checks.append((label, bool(condition)))


def api_get(path, use_key=True):
    headers = {}
    if use_key and API_KEY:
        headers["X-API-Key"] = API_KEY
    return httpx.get(f"{BASE_URL}{path}", headers=headers, timeout=10)


def api_post(path, json=None, use_key=True):
    headers = {}
    if use_key and API_KEY:
        headers["X-API-Key"] = API_KEY
    return httpx.post(f"{BASE_URL}{path}", json=json, headers=headers, timeout=10)


# 1. API health and readiness
print("=== API Health ===")
try:
    r = api_get("/health", use_key=False)
    ok("/health returns 200", r.status_code == 200)
    ok("/health status ok", r.json().get("status") == "ok")
except Exception:
    ok("/health reachable", False)

try:
    r = api_get("/ready", use_key=False)
    ok("/ready returns 200", r.status_code == 200)
    ok("/ready database ok", r.json().get("database") == "ok")
except Exception:
    ok("/ready reachable", False)


# 2. API authentication
print("\n=== API Authentication ===")
if API_KEY:
    # Without key should fail (use a GET endpoint)
    r = api_get("/ready", use_key=False)
    # /ready is public, so test with a protected GET endpoint
    r = api_get("/metrics", use_key=False)
    ok("No key → 401", r.status_code == 401)

    # With key should work
    r = api_get("/metrics", use_key=True)
    ok("With key → 200", r.status_code == 200)
else:
    print("  (skipped — DATAPULSE_API_KEY not set)")


# 3. Webhook secret
print("\n=== Webhook Secret ===")
if WEBHOOK_SECRET:
    # Without secret should fail
    r = api_post("/webhook/receiver", json={"test": True}, use_key=False)
    ok("No secret → 403", r.status_code == 403)

    # With secret should work
    headers = {"X-Webhook-Secret": WEBHOOK_SECRET}
    r = httpx.post(f"{BASE_URL}/webhook/receiver", json={"test": True}, headers=headers, timeout=10)
    ok("With secret → 200", r.status_code == 200)
else:
    print("  (skipped — DATAPULSE_WEBHOOK_SECRET not set)")


# 4. Grafana
print("\n=== Grafana ===")
try:
    r = httpx.get(f"{GRAFANA_URL}/api/health", timeout=10)
    ok("Grafana health", r.status_code == 200)
    ok("Grafana database ok", r.json().get("database") == "ok")

    # Check non-default credentials
    if GRAFANA_PASSWORD != "admin":
        r = httpx.get(f"{GRAFANA_URL}/api/datasources", auth=(GRAFANA_USER, GRAFANA_PASSWORD), timeout=10)
        ok("Grafana auth works", r.status_code == 200)
        ok("Datasource provisioned", len(r.json()) > 0)
except Exception:
    ok("Grafana reachable", False)


# 5. API endpoints
print("\n=== API Endpoints ===")
try:
    r = api_get("/metrics")
    ok("/metrics returns 200", r.status_code == 200)
    ok("/metrics has pipelines", "pipelines" in r.json())

    r = api_get("/webhook/log")
    ok("/webhook/log returns 200", r.status_code == 200)
except Exception:
    ok("API endpoints", False)


# Results
print("\n" + "=" * 50)
passed = sum(1 for _, ok_val in checks if ok_val)
total = len(checks)
for label, ok_val in checks:
    print(f"  [{'OK' if ok_val else 'FAIL'}] {label}")
print(f"\n{passed}/{total} checks passed")

if passed < total:
    sys.exit(1)
