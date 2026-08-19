"""Ecommerce orders pipeline contract definitions.

Demonstrates a different integration pattern than healthcare_analytics:
- S3-style path references (simulated with local files)
- Daily partitioned order data
- Shorter freshness window (12h vs 72h)
- Source-to-target row count reconciliation
"""

PIPELINE_NAME = "ecommerce_orders"
PIPELINE_OWNER = "data-platform"

# ── Source: raw orders from S3 ────────────────────────────────

ORDERS_SOURCE_SCHEMA = {
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

ORDERS_SOURCE_FRESHNESS = {
    "max_age_hours": 12,
    "timestamp_column": "order_date",
}

ORDERS_SOURCE_QUALITY = {
    "unique_keys": ["order_id"],
    "min_row_count": 100,
    "max_row_count": 500000,
}

# ── Target: order facts table (dbt output) ────────────────────

ORDER_FACTS_TARGET_SCHEMA = {
    "order_id": {"type": "string", "nullable": False},
    "customer_sk": {"type": "integer", "nullable": False},
    "order_date": {"type": "date", "nullable": False},
    "product_sk": {"type": "integer", "nullable": False},
    "product_name": {"type": "string", "nullable": False},
    "category": {"type": "string", "nullable": False},
    "quantity": {"type": "integer", "nullable": False},
    "unit_price": {"type": "decimal", "nullable": False},
    "total_amount": {"type": "decimal", "nullable": False},
    "payment_method": {"type": "string", "nullable": False},
    "order_status": {"type": "string", "nullable": False},
    "is_completed": {"type": "boolean", "nullable": False},
}

ORDER_FACTS_TARGET_FRESHNESS = {
    "max_age_hours": 12,
    "timestamp_column": "order_date",
}

ORDER_FACTS_TARGET_QUALITY = {
    "unique_keys": ["order_id"],
    "min_row_count": 100,
    "max_row_count": 500000,
}

# ── S3 path references (simulated) ───────────────────────────

SOURCE_S3_PATH = "s3://ecommerce-data-lake/raw/orders/orders.parquet"
TARGET_S3_PATH = "s3://ecommerce-data-lake/warehouse/fact_orders/orders.parquet"
