"""plans

The plans `free` and `pro` with their LLM access and review limit (REV-13 to REV-15);
every investor gets a plan, existing investors start on `free` (USR-08).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-01 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLANS = ("free", "pro")


def upgrade() -> None:
    plan = op.create_table(
        "plan",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("monthly_review_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", yap.db.types.UTCDateTime(length=32), nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )
    # Plans are data, so later versions can add plans without a schema change (REV-13)
    op.bulk_insert(plan, [{"code": code, "monthly_review_limit": 0} for code in PLANS])
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_code", sa.String(length=20), nullable=True))
        batch_op.create_foreign_key("fk_investor_plan_code", "plan", ["plan_code"], ["code"])
    op.execute("UPDATE investor SET plan_code = 'free' WHERE role = 'investor'")


def downgrade() -> None:
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.drop_constraint("fk_investor_plan_code", type_="foreignkey")
        batch_op.drop_column("plan_code")
    op.drop_table("plan")
