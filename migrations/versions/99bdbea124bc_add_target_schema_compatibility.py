"""add_target_schema_compatibility

Revision ID: 99bdbea124bc
Revises: e66e588be05f
Create Date: 2026-08-19 00:43:34.523953

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '99bdbea124bc'
down_revision: Union[str, Sequence[str], None] = 'e66e588be05f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add target_schema_compatibility to checktype enum."""
    op.execute("ALTER TYPE checktype ADD VALUE IF NOT EXISTS 'TARGET_SCHEMA_COMPATIBILITY'")


def downgrade() -> None:
    """Downgrade — enum values cannot be removed in PostgreSQL."""
    pass
