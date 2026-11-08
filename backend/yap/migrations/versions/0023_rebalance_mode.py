"""mode of a rebalance

A confirmed rebalance stores whether it sold the whole portfolio (RB-25): `normal` or
`sell_all`; all existing rebalances are `normal`. A plain ADD COLUMN, so the history
triggers stay (NFR-05).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-10 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rebalance",
        sa.Column("mode", sa.String(length=10), nullable=False, server_default="normal"),
    )


def downgrade() -> None:
    op.execute("ALTER TABLE rebalance DROP COLUMN mode")
