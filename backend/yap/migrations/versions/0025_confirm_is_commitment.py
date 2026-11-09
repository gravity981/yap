"""confirming a rebalance is a commitment, not a report of executed trades

RB-16: the investor confirms that the trades are carried out as calculated; what was
actually executed is recorded as values afterwards. The executed units and amounts of the
actions are dropped (lossy), and new rebalances store no resulting snapshot; the
result snapshots of earlier rebalances stay linked.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NO_UPDATE = (
    "CREATE TRIGGER rebalance_action_no_update BEFORE UPDATE ON rebalance_action "
    "BEGIN SELECT RAISE(ABORT, 'rebalance_action is append-only'); END"
)


def upgrade() -> None:
    # Plain DROP COLUMN statements, so the history triggers of rebalance_action stay (NFR-05)
    op.execute("ALTER TABLE rebalance_action DROP COLUMN executed_units")
    op.execute("ALTER TABLE rebalance_action DROP COLUMN executed_amount")


def downgrade() -> None:
    # Lossy: the executed amounts and units become the calculated ones
    op.add_column(
        "rebalance_action",
        sa.Column("executed_units", yap.db.types.DecimalText(length=64), nullable=True),
    )
    op.add_column(
        "rebalance_action",
        sa.Column(
            "executed_amount",
            yap.db.types.DecimalText(length=64),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute("DROP TRIGGER rebalance_action_no_update")
    op.execute(
        "UPDATE rebalance_action SET executed_units = calculated_units, "
        "executed_amount = calculated_amount"
    )
    op.execute(NO_UPDATE)
