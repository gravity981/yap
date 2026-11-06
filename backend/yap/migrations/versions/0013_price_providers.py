"""price providers and their daily calls

The admin's price providers (PRC-01) and the calls per provider and UTC day (PRC-08). The
built-in exchange rate source is a fixed row (PRC-11).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04 09:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    time = yap.db.types.UTCDateTime(length=32)
    provider = op.create_table(
        "price_provider",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("built_in", sa.Boolean(), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("daily_call_limit", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("archived_at", time, nullable=True),
        sa.Column("created_at", time, nullable=False),
        sa.Column("updated_at", time, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "provider_usage",
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("quota_exhausted", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["price_provider.id"]),
        sa.PrimaryKeyConstraint("provider_id", "day"),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        provider,
        [
            {
                "provider": "frankfurter",
                "built_in": True,
                "enabled": True,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("provider_usage")
    op.drop_table("price_provider")
