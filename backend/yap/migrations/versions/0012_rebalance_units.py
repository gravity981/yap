"""units in rebalance actions

Confirmed rebalances store the calculated and executed units of each action and whether
the position was traded in whole units only (RB-16, RB-24). Actions of earlier
rebalances have none of them; their results are recalculated without units.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-03 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN statements, so the history triggers of rebalance_action stay (NFR-05)
    op.add_column("rebalance_action", sa.Column("whole_units", sa.Boolean(), nullable=True))
    for column in ("calculated_units", "executed_units"):
        op.add_column(
            "rebalance_action",
            sa.Column(column, yap.db.types.DecimalText(length=64), nullable=True),
        )


def downgrade() -> None:
    for column in ("executed_units", "calculated_units", "whole_units"):
        op.execute(f"ALTER TABLE rebalance_action DROP COLUMN {column}")
