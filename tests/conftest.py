"""Shared test fixtures — reusable setup for all tests."""

import csv
import logging
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import datapulse.api.deps as deps
import datapulse.config as config
import datapulse.db.engine as eng
from datapulse.db.base import Base
from datapulse.models import *  # noqa: F401,F403


@pytest.fixture()
def db_session(tmp_path):
    """
    Create a fresh in-memory SQLite database for each test.
    Yields a SQLAlchemy session. Rolls back after each test.
    """
    db_path = tmp_path / f"test_{uuid.uuid4().hex[:6]}.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        engine.dispose()
        if db_path.exists():
            db_path.unlink()


@pytest.fixture()
def client(tmp_path):
    """
    Create a fresh FastAPI TestClient with isolated database.
    Each test gets its own DB file.
    """
    db_path = tmp_path / f"api_{uuid.uuid4().hex[:6]}.db"

    # Reset engine state
    deps._engine = None
    deps._session_factory = None
    config.DATABASE_URL = f"sqlite:///{db_path}"

    # Suppress structured logging noise in test output
    logging.getLogger("datapulse").setLevel(logging.CRITICAL)

    # Import app (lazy to pick up new DB path)
    from datapulse.api.app import app

    # Force fresh engine
    fresh_engine = eng.init_db(eng.get_engine())
    deps._engine = fresh_engine
    deps._session_factory = eng.get_session_factory(fresh_engine)

    test_client = TestClient(app)

    yield test_client

    # Cleanup
    fresh_engine.dispose()
    deps._engine = None
    deps._session_factory = None
    if db_path.exists():
        db_path.unlink()


@pytest.fixture()
def registered_pipeline(client):
    """Register the ecommerce_inventory pipeline and return the response."""
    return client.post(
        "/pipelines",
        json={
            "name": "ecommerce_inventory",
            "owner": "data-platform",
        },
    )


@pytest.fixture()
def registered_dataset(client, registered_pipeline):
    """Register inventory_snapshot dataset + contract and return the response."""
    return client.post(
        "/datasets",
        json={
            "pipeline_name": "ecommerce_inventory",
            "dataset_name": "inventory_snapshot",
            "role": "source",
            "location": "data/inventory/",
            "contract_version": 1,
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
            "freshness": {"max_age_hours": 24, "timestamp_column": "snapshot_date"},
            "quality_rules": {
                "unique_keys": ["product_id"],
                "min_row_count": 1,
                "max_row_count": 50,
                "max_row_count_diff_pct": 5,
            },
        },
    )


def make_csv(tmp_path: Path, rows: list[dict], filename: str = "test.csv") -> str:
    """Helper: write rows to a CSV file and return the path as string."""
    path = tmp_path / filename
    if rows:
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    else:
        # Empty file with no headers
        path.write_text("", encoding="utf-8")
    return str(path)
