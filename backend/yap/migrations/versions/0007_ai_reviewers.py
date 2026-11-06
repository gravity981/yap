"""ai reviewers

The fixed plans `free` and `pro` become AI reviewers that the admin configures in any
number (REV-13 to REV-17); each investor chooses one (USR-08). A plan with a complete
configuration becomes a reviewer of the same name, and its investors keep it as their
choice; unconfigured plans are dropped. The review limit counts per reviewer, so runs
and reviews refer to it.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-02 20:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_TYPE = yap.db.types.UTCDateTime(length=32)
ACTIONS = ("UPDATE", "DELETE")
PLANS = ("free", "pro")

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


def _drop_run_triggers() -> None:
    """Rebuilding review_run drops its triggers; they are created again."""
    for action in ACTIONS:
        op.execute(f"DROP TRIGGER IF EXISTS review_run_no_{action.lower()}")


def _create_run_triggers() -> None:
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER review_run_no_{action.lower()} BEFORE {action} ON review_run "
            "BEGIN SELECT RAISE(ABORT, 'review_run is append-only'); END"
        )


def _drop_review_triggers() -> None:
    """Rebuilding review drops its triggers, and those of its children refer to it."""
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
    op.create_table(
        "ai_reviewer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("api_key_last4", sa.String(length=4), nullable=False),
        sa.Column("monthly_review_limit", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("archived_at", UTC_TYPE, nullable=True),
        sa.Column("created_at", UTC_TYPE, nullable=False),
        sa.Column("updated_at", UTC_TYPE, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    now = datetime.now(UTC).isoformat()
    op.execute(
        sa.text(
            "INSERT INTO ai_reviewer (name, provider, model, api_key_encrypted, api_key_last4,"
            " monthly_review_limit, enabled, created_at, updated_at)"
            " SELECT code, provider, model, api_key_encrypted, api_key_last4,"
            " monthly_review_limit, 1, COALESCE(updated_at, :now), COALESCE(updated_at, :now)"
            " FROM plan WHERE provider IS NOT NULL AND model IS NOT NULL"
            " AND api_key_encrypted IS NOT NULL ORDER BY code"
        ).bindparams(now=now)
    )
    reviewer_of_plan = "(SELECT id FROM ai_reviewer WHERE name = {table}.plan_code)"

    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_reviewer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_investor_ai_reviewer_id", "ai_reviewer", ["ai_reviewer_id"], ["id"]
        )
    op.execute(f"UPDATE investor SET ai_reviewer_id = {reviewer_of_plan.format(table='investor')}")
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.drop_constraint("fk_investor_plan_code", type_="foreignkey")
        batch_op.drop_column("plan_code")

    _drop_run_triggers()
    with op.batch_alter_table("review_run", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ai_reviewer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_review_run_ai_reviewer_id", "ai_reviewer", ["ai_reviewer_id"], ["id"]
        )
        batch_op.create_index("ix_review_run_ai_reviewer_id", ["ai_reviewer_id"])
    op.execute(
        f"UPDATE review_run SET ai_reviewer_id = {reviewer_of_plan.format(table='review_run')}"
    )
    with op.batch_alter_table("review_run", schema=None) as batch_op:
        batch_op.drop_column("plan_code")
    _create_run_triggers()
    # A plain ADD COLUMN keeps the triggers of review and its children (no table rebuild)
    op.execute(
        "ALTER TABLE review ADD COLUMN ai_reviewer_id INTEGER"
        " CONSTRAINT fk_review_ai_reviewer_id REFERENCES ai_reviewer (id)"
    )
    op.add_column("review", sa.Column("ai_reviewer_name", sa.String(length=100), nullable=True))
    op.drop_table("plan")


def downgrade() -> None:
    """Reviewers named free or pro become those plans again; investors and runs of other
    reviewers fall back to free."""
    plan = op.create_table(
        "plan",
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("monthly_review_limit", sa.Integer(), nullable=False),
        sa.Column("updated_at", UTC_TYPE, nullable=True),
        sa.PrimaryKeyConstraint("code"),
    )
    op.bulk_insert(plan, [{"code": code, "monthly_review_limit": 0} for code in PLANS])
    for code in PLANS:
        op.execute(
            "UPDATE plan SET (provider, model, api_key_encrypted, api_key_last4,"
            " monthly_review_limit, updated_at) = (SELECT provider, model, api_key_encrypted,"
            " api_key_last4, monthly_review_limit, updated_at FROM ai_reviewer"
            f" WHERE name = '{code}' AND archived_at IS NULL)"
            f" WHERE code = '{code}' AND EXISTS (SELECT 1 FROM ai_reviewer"
            f" WHERE name = '{code}' AND archived_at IS NULL)"
        )
    plan_of_reviewer = (
        "COALESCE((SELECT name FROM ai_reviewer WHERE id = {table}.ai_reviewer_id"
        " AND name IN ('free', 'pro')), 'free')"
    )

    _drop_review_triggers()
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_column("ai_reviewer_name")
        batch_op.drop_column("ai_reviewer_id")
    _create_review_triggers()
    _drop_run_triggers()
    with op.batch_alter_table("review_run", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("plan_code", sa.String(length=20), nullable=False, server_default="free")
        )
    op.execute(f"UPDATE review_run SET plan_code = {plan_of_reviewer.format(table='review_run')}")
    with op.batch_alter_table("review_run", schema=None) as batch_op:
        batch_op.alter_column("plan_code", server_default=None)
        batch_op.drop_index("ix_review_run_ai_reviewer_id")
        batch_op.drop_constraint("fk_review_run_ai_reviewer_id", type_="foreignkey")
        batch_op.drop_column("ai_reviewer_id")
    _create_run_triggers()

    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.add_column(sa.Column("plan_code", sa.String(length=20), nullable=True))
        batch_op.create_foreign_key("fk_investor_plan_code", "plan", ["plan_code"], ["code"])
    op.execute(
        f"UPDATE investor SET plan_code = {plan_of_reviewer.format(table='investor')}"
        " WHERE is_investor"
    )
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.drop_constraint("fk_investor_ai_reviewer_id", type_="foreignkey")
        batch_op.drop_column("ai_reviewer_id")
    op.drop_table("ai_reviewer")
