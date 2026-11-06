"""withdrawal instead of reinvest setting

Sell proceeds are always reinvested (POL-03); cash leaves the portfolio as the
withdrawal of a rebalance (RB-01, RB-22). A confirmed rebalance whose policy had
"reinvest sell proceeds" off gets its phase 1B sell proceeds as withdrawal, which
recalculates to the same result (F = V + C - S either way).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-03 12:00:00.000000
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Plain ADD/DROP COLUMN statements, so no table is rebuilt and the history triggers
# stay (NFR-05). Only the data update needs the update trigger out of the way.
NO_UPDATE = (
    "CREATE TRIGGER rebalance_no_update BEFORE UPDATE ON rebalance "
    "BEGIN SELECT RAISE(ABORT, 'rebalance is append-only'); END"
)


def upgrade() -> None:
    op.add_column(
        "rebalance",
        sa.Column(
            "withdrawal",
            yap.db.types.DecimalText(length=64),
            nullable=False,
            server_default="0",
        ),
    )
    connection = op.get_bind()
    set_aside = connection.execute(
        sa.text(
            "SELECT r.id, a.calculated_amount FROM rebalance r"
            " JOIN rebalance_action a ON a.rebalance_id = r.id"
            " WHERE r.reinvest_sells = 0 AND a.phase = '1B'"
        )
    ).all()
    sells: dict[int, Decimal] = {}
    for rebalance_id, amount in set_aside:
        sells[rebalance_id] = sells.get(rebalance_id, Decimal(0)) + Decimal(amount)
    op.execute("DROP TRIGGER rebalance_no_update")
    for rebalance_id, amount in sells.items():
        connection.execute(
            sa.text("UPDATE rebalance SET withdrawal = :amount WHERE id = :id"),
            {"amount": str(amount), "id": rebalance_id},
        )
    op.execute(NO_UPDATE)
    op.execute("ALTER TABLE rebalance DROP COLUMN reinvest_sells")
    op.execute("ALTER TABLE policy_version DROP COLUMN reinvest_sells")


def downgrade() -> None:
    # Lossy: a withdrawal becomes "reinvest sell proceeds" off, whatever its amount
    op.add_column(
        "policy_version",
        sa.Column("reinvest_sells", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "rebalance",
        sa.Column("reinvest_sells", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("DROP TRIGGER rebalance_no_update")
    op.execute("UPDATE rebalance SET reinvest_sells = 0 WHERE CAST(withdrawal AS REAL) != 0")
    op.execute(NO_UPDATE)
    op.execute("ALTER TABLE rebalance DROP COLUMN withdrawal")
