"""listings, lookup cache and price sources

Listings and cached lookups are shared by the whole server (PRC-02, PRC-03); the price
source of an asset belongs to the investor (PRC-05).

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-04 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    time = yap.db.types.UTCDateTime(length=32)
    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=100), nullable=False),
        sa.Column("quote_currency", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("not_found_count", sa.Integer(), nullable=False),
        sa.Column("price", yap.db.types.DecimalText(length=64), nullable=True),
        sa.Column("price_date", sa.String(length=10), nullable=True),
        sa.Column("price_updated_at", time, nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["price_provider.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "symbol"),
    )
    op.create_table(
        "ticker_lookup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("result", sa.String(length=10), nullable=False),
        sa.Column("looked_up_at", time, nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["price_provider.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "ticker"),
    )
    op.create_table(
        "ticker_lookup_listing",
        sa.Column("ticker_lookup_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listing.id"]),
        sa.ForeignKeyConstraint(["ticker_lookup_id"], ["ticker_lookup.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ticker_lookup_id", "listing_id"),
    )
    op.create_table(
        "price_source",
        sa.Column("investor_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", time, nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["investor_id"], ["investor.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listing.id"]),
        sa.PrimaryKeyConstraint("investor_id", "asset_id"),
    )


def downgrade() -> None:
    op.drop_table("price_source")
    op.drop_table("ticker_lookup_listing")
    op.drop_table("ticker_lookup")
    op.drop_table("listing")
