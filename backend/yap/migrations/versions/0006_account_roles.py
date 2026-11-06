"""account roles

An account can have the admin role, the investor role or both (USR-05, USR-09): the
column `role` becomes the flags `is_admin` and `is_investor`.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("is_investor", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute("UPDATE investor SET is_admin = (role = 'admin'), is_investor = (role = 'investor')")
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.alter_column("is_admin", server_default=None)
        batch_op.alter_column("is_investor", server_default=None)
        batch_op.drop_column("role")
        batch_op.create_check_constraint("ck_investor_has_role", "is_admin OR is_investor")
        batch_op.create_check_constraint(
            "ck_investor_base_currency", "NOT is_investor OR base_currency IS NOT NULL"
        )


def downgrade() -> None:
    """An account with both roles becomes an investor, so its data stays reachable."""
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("role", sa.String(length=20), nullable=False, server_default="investor")
        )
    op.execute("UPDATE investor SET role = CASE WHEN is_investor THEN 'investor' ELSE 'admin' END")
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.alter_column("role", server_default=None)
        batch_op.drop_constraint("ck_investor_base_currency", type_="check")
        batch_op.drop_constraint("ck_investor_has_role", type_="check")
        batch_op.drop_column("is_investor")
        batch_op.drop_column("is_admin")
