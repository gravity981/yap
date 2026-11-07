"""drop review modification

Investors no longer change the scores or the verdict of a review (REV-10 dropped). A review
keeps only the AI's values: `ai_verdict` becomes `verdict` and `review_aspect.ai_half_points`
becomes `half_points`. The changes of reviews modified before are kept read-only in
`review.legacy_modification` as JSON: {"note", "verdict", "scores": {aspect: score}}.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
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
    _drop_review_triggers()
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("legacy_modification", sa.Text(), nullable=True))
    op.execute(
        "UPDATE review SET legacy_modification = json_object("
        "'note', modification_note, "
        "'verdict', verdict, "
        "'scores', json((SELECT json_group_object(aspect, half_points / 2.0) "
        "FROM review_aspect WHERE review_id = review.id AND half_points IS NOT NULL)))"
        " WHERE modified"
    )
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_column("modified")
        batch_op.drop_column("modification_note")
        batch_op.drop_column("verdict")
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.alter_column(
            "ai_verdict", new_column_name="verdict", existing_type=sa.String(length=20)
        )
    with op.batch_alter_table("review_aspect", schema=None) as batch_op:
        batch_op.drop_column("half_points")
    with op.batch_alter_table("review_aspect", schema=None) as batch_op:
        batch_op.alter_column(
            "ai_half_points",
            new_column_name="half_points",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    _create_review_triggers()


def downgrade() -> None:
    _drop_review_triggers()
    with op.batch_alter_table("review_aspect", schema=None) as batch_op:
        batch_op.alter_column(
            "half_points",
            new_column_name="ai_half_points",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
    with op.batch_alter_table("review_aspect", schema=None) as batch_op:
        batch_op.add_column(sa.Column("half_points", sa.Integer(), nullable=True))
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.alter_column(
            "verdict", new_column_name="ai_verdict", existing_type=sa.String(length=20)
        )
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("verdict", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("modification_note", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("modified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        "UPDATE review SET modified = 1,"
        " verdict = json_extract(legacy_modification, '$.verdict'),"
        " modification_note = json_extract(legacy_modification, '$.note')"
        " WHERE legacy_modification IS NOT NULL"
    )
    op.execute(
        "UPDATE review_aspect SET half_points = CAST(ROUND(2 * json_extract("
        "(SELECT legacy_modification FROM review WHERE id = review_aspect.review_id),"
        " '$.scores.' || aspect)) AS INTEGER)"
        " WHERE json_extract((SELECT legacy_modification FROM review"
        " WHERE id = review_aspect.review_id), '$.scores.' || aspect) IS NOT NULL"
    )
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.alter_column("modified", server_default=None)
        batch_op.drop_column("legacy_modification")
    _create_review_triggers()
