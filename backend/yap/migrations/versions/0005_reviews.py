"""reviews

Thesis and policy reviews of drafts (REV-01 to REV-17). Replaces the unused review
tables of the first design (thesis_review, review_portfolio_score, ...), counts review
runs for the monthly limit, and records when a policy draft last changed (REV-09).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC = yap.db.types.UTCDateTime(length=32)
ACTIONS = ("UPDATE", "DELETE")

# timeline_event, with review_id referencing the given table. Rebuilt with plain SQL,
# because its foreign keys have no names that a batch operation could address.
TIMELINE = """CREATE TABLE timeline_event (
    id INTEGER NOT NULL,
    investor_id INTEGER NOT NULL,
    occurred_at VARCHAR(32) NOT NULL,
    type VARCHAR(30) NOT NULL,
    portfolio_id INTEGER,
    policy_version_id INTEGER,
    rebalance_id INTEGER,
    review_id INTEGER,
    thesis_revision_id INTEGER,
    summary VARCHAR(500) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(investor_id) REFERENCES investor (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolio (id),
    FOREIGN KEY(rebalance_id) REFERENCES rebalance (id),
    FOREIGN KEY(review_id) REFERENCES {review_table} (id),
    FOREIGN KEY(thesis_revision_id) REFERENCES thesis_revision (id)
)"""
TIMELINE_COLUMNS = (
    "id, investor_id, occurred_at, type, portfolio_id, policy_version_id, rebalance_id, "
    "review_id, thesis_revision_id, summary"
)

# A review is confirmed when its draft is activated (REV-11)
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


def _rebuild_timeline(review_table: str) -> None:
    for action in ACTIONS:
        op.execute(f"DROP TRIGGER IF EXISTS timeline_event_no_{action.lower()}")
    op.execute("ALTER TABLE timeline_event RENAME TO _timeline_event_old")
    op.execute(TIMELINE.format(review_table=review_table))
    op.execute(
        f"INSERT INTO timeline_event ({TIMELINE_COLUMNS}) "
        f"SELECT {TIMELINE_COLUMNS} FROM _timeline_event_old"
    )
    op.execute("DROP TABLE _timeline_event_old")
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER timeline_event_no_{action.lower()} BEFORE {action} ON "
            "timeline_event BEGIN SELECT RAISE(ABORT, 'timeline_event is append-only'); END"
        )


def upgrade() -> None:
    # The old review tables were never written to
    for table in ("review_portfolio_score", "review_suggestion", "review_source", "thesis_review"):
        op.drop_table(table)

    op.create_table(
        "review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("thesis_revision_id", sa.Integer(), nullable=True),
        sa.Column("policy_version_id", sa.Integer(), nullable=True),
        sa.Column("started_by", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("news_from", UTC, nullable=True),
        sa.Column("news_to", UTC, nullable=True),
        sa.Column("ai_verdict", sa.String(length=20), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=True),
        sa.Column("modification_note", sa.Text(), nullable=True),
        sa.Column("modified", sa.Boolean(), nullable=False),
        sa.Column("scoring_version", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", UTC, nullable=False),
        sa.Column("completed_at", UTC, nullable=True),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_version.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["investor.id"]),
        sa.ForeignKeyConstraint(["thesis_revision_id"], ["thesis_revision.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_version_id"),
        sa.UniqueConstraint("thesis_revision_id"),
    )
    op.create_table(
        "review_aspect",
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("aspect", sa.String(length=5), nullable=False),
        sa.Column("ai_half_points", sa.Integer(), nullable=False),
        sa.Column("half_points", sa.Integer(), nullable=True),
        sa.Column("reasoning_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["review.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("review_id", "aspect"),
    )
    op.create_table(
        "review_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("published_on", sa.String(length=10), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["review.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_suggestion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["review.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investor_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("plan_code", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("started_at", UTC, nullable=False),
        sa.ForeignKeyConstraint(["investor_id"], ["investor.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_run_investor_id", "review_run", ["investor_id"])
    # policy_version has triggers, but a plain ADD COLUMN keeps them (no table rebuild)
    op.add_column("policy_version", sa.Column("updated_at", UTC, nullable=True))
    _rebuild_timeline("review")

    # History protection (NFR-05): the run log is append-only, a confirmed review and its
    # rows are immutable; reviews of drafts can be replaced or modified.
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER review_run_no_{action.lower()} BEFORE {action} ON review_run "
            "BEGIN SELECT RAISE(ABORT, 'review_run is append-only'); END"
        )
        op.execute(
            f"CREATE TRIGGER review_confirmed_no_{action.lower()} BEFORE {action} ON review "
            f"WHEN {CONFIRMED.format(row='OLD')} "
            "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
        )
    for table in REVIEW_CHILDREN:
        for action, row in (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD")):
            op.execute(
                f"CREATE TRIGGER {table}_confirmed_no_{action.lower()} BEFORE {action} "
                f"ON {table} WHEN {CHILD_CONFIRMED.format(row=row)} "
                "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
            )


def downgrade() -> None:
    op.execute("UPDATE timeline_event SET review_id = NULL WHERE review_id IS NOT NULL")
    for table in ("review_run", "review_suggestion", "review_source", "review_aspect", "review"):
        op.drop_table(table)
    op.drop_column("policy_version", "updated_at")
    op.create_table(
        "thesis_review",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thesis_revision_id", sa.Integer(), nullable=False),
        sa.Column("policy_version_id", sa.Integer(), nullable=False),
        sa.Column("started_by", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("news_from", UTC, nullable=False),
        sa.Column("news_to", UTC, nullable=False),
        sa.Column("thesis_assessment", sa.String(length=10), nullable=True),
        sa.Column("thesis_score", sa.Integer(), nullable=True),
        sa.Column("scoring_version", sa.String(length=20), nullable=True),
        sa.Column("reasoning_md", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", UTC, nullable=False),
        sa.Column("completed_at", UTC, nullable=True),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_version.id"]),
        sa.ForeignKeyConstraint(["started_by"], ["investor.id"]),
        sa.ForeignKeyConstraint(["thesis_revision_id"], ["thesis_revision.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("published_on", sa.String(length=10), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["thesis_review.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_suggestion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["thesis_review.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "review_portfolio_score",
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_score", sa.Integer(), nullable=False),
        sa.Column("reasoning_md", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolio.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["thesis_review.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshot.id"]),
        sa.PrimaryKeyConstraint("review_id", "portfolio_id"),
    )
    for table in ("review_source", "review_suggestion", "review_portfolio_score"):
        for action in ACTIONS:
            op.execute(
                f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
            )
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER thesis_review_finished_no_{action.lower()} "
            f"BEFORE {action} ON thesis_review WHEN OLD.state IN ('done', 'failed') "
            "BEGIN SELECT RAISE(ABORT, 'finished thesis review is immutable'); END"
        )
    _rebuild_timeline("thesis_review")
