"""manual reviews

A review is made by an AI reviewer or manually with an AI outside the app (REV-18): its
method, and the ID of the prompt it answers (REV-19). A manual review has the provider
`manual` and the model the investor named (REV-17). An investor can choose `manual` as
the default method (USR-08). Plain ADD COLUMN keeps the history triggers of review.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-07 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("UPDATE", "DELETE")

# A review is confirmed when its draft is activated (REV-11); as in 0005
CONFIRMED = (
    "(SELECT activated_at FROM thesis_revision WHERE id = {row}.thesis_revision_id) IS NOT NULL "
    "OR (SELECT activated_at FROM policy_version WHERE id = {row}.policy_version_id) IS NOT NULL"
)
CHILD_CONFIRMED = (
    "(SELECT 1 FROM review r WHERE r.id = {row}.review_id AND ("
    "(SELECT activated_at FROM thesis_revision WHERE id = r.thesis_revision_id) IS NOT NULL "
    "OR (SELECT activated_at FROM policy_version WHERE id = r.policy_version_id) IS NOT NULL"
    ")) IS NOT NULL"
)
REVIEW_CHILDREN = ("review_aspect", "review_source", "review_suggestion")
CHILD_ACTIONS = (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD"))


def _drop_review_triggers() -> None:
    """Confirmed reviews are immutable (NFR-05); the triggers are lifted while the data
    moves and rebuilding the tables drops them anyway."""
    for action in ACTIONS:
        op.execute(f"DROP TRIGGER IF EXISTS review_confirmed_no_{action.lower()}")
    for table in REVIEW_CHILDREN:
        for action, _ in CHILD_ACTIONS:
            op.execute(f"DROP TRIGGER IF EXISTS {table}_confirmed_no_{action.lower()}")


def _create_review_triggers() -> None:
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER review_confirmed_no_{action.lower()} BEFORE {action} ON review "
            f"WHEN {CONFIRMED.format(row='OLD')} "
            "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
        )
    for table in REVIEW_CHILDREN:
        for action, row in CHILD_ACTIONS:
            op.execute(
                f"CREATE TRIGGER {table}_confirmed_no_{action.lower()} BEFORE {action} "
                f"ON {table} WHEN {CHILD_CONFIRMED.format(row=row)} "
                "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
            )


def upgrade() -> None:
    op.add_column(
        "review",
        sa.Column("method", sa.String(length=10), nullable=False, server_default="ai"),
    )
    op.add_column("review", sa.Column("prompt_id", sa.String(length=60), nullable=True))
    op.add_column(
        "investor",
        sa.Column("manual_review_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Manual reviews stay, as reviews of the provider `manual`; history is never deleted."""
    _drop_review_triggers()
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_column("prompt_id")
        batch_op.drop_column("method")
    _create_review_triggers()
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.drop_column("manual_review_default")
