"""review log and sharing

- A version keeps every saved review (REV-23): the unique (version, kind) of `review` goes;
  a draft still has at most one open review (REV-09), which the app ensures.
- Reviews are immutable once saved (`saved_at` set, REV-11, POL-20), not once their version
  is active: a review of the active version (POL-20) is written while it runs and saved
  when it is done. A saved review's suggestions keep their content, but their state may
  change, as they can be taken over into a draft (REV-07).
- `policy.sharing` (POL-18): private, text or all; private for all existing policies.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-09 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("UPDATE", "DELETE")
CHILD_ACTIONS = (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD"))
REVIEW_CHILDREN = ("review_aspect", "review_source", "review_suggestion")

COLUMNS = (
    "id, kind, policy_version_id, started_by, state, news_from, news_to, verdict, "
    "verdict_reason, scoring_version, provider, model, error, started_at, completed_at, "
    "ai_reviewer_id, ai_reviewer_name, legacy_modification, method, prompt_id, fingerprint, "
    "saved_at"
)
REVIEW = """CREATE TABLE review (
    id INTEGER NOT NULL,
    kind VARCHAR(10) NOT NULL,
    policy_version_id INTEGER NOT NULL,
    started_by INTEGER NOT NULL,
    state VARCHAR(10) NOT NULL,
    news_from VARCHAR(32),
    news_to VARCHAR(32),
    verdict VARCHAR(20),
    verdict_reason TEXT,
    scoring_version VARCHAR(20) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(100),
    error TEXT,
    started_at VARCHAR(32) NOT NULL,
    completed_at VARCHAR(32),
    ai_reviewer_id INTEGER,
    ai_reviewer_name VARCHAR(100),
    legacy_modification TEXT,
    method VARCHAR(10) DEFAULT 'ai' NOT NULL,
    prompt_id VARCHAR(60),
    fingerprint VARCHAR(64),
    saved_at VARCHAR(32),
    PRIMARY KEY (id),
    FOREIGN KEY(ai_reviewer_id) REFERENCES ai_reviewer (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    FOREIGN KEY(started_by) REFERENCES investor (id){unique}
)"""

# Changes of a saved suggestion other than its state (and what Take over replaced)
SUGGESTION_CONTENT = (
    "(NEW.review_id IS NOT OLD.review_id OR NEW.kind IS NOT OLD.kind "
    "OR NEW.content_md IS NOT OLD.content_md OR NEW.change IS NOT OLD.change)"
)


def _drop_triggers() -> None:
    names = [f"review_confirmed_no_{a.lower()}" for a in ACTIONS]
    names += [f"{t}_confirmed_no_{a.lower()}" for t in REVIEW_CHILDREN for a, _ in CHILD_ACTIONS]
    for name in names:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def _create_triggers(saved: bool) -> None:
    """`saved`: immutable once saved (from 0022); otherwise once the version is active."""
    if saved:
        confirmed = "OLD.saved_at IS NOT NULL"
        child = "(SELECT saved_at FROM review WHERE id = {row}.review_id) IS NOT NULL"
    else:
        confirmed = (
            "(SELECT activated_at FROM policy_version WHERE id = OLD.policy_version_id) IS NOT NULL"
        )
        child = (
            "(SELECT activated_at FROM policy_version WHERE id = "
            "(SELECT policy_version_id FROM review WHERE id = {row}.review_id)) IS NOT NULL"
        )
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER review_confirmed_no_{action.lower()} BEFORE {action} ON review "
            f"WHEN {confirmed} BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
        )
    for table in REVIEW_CHILDREN:
        for action, row in CHILD_ACTIONS:
            when = child.format(row=row)
            if saved and table == "review_suggestion" and action == "UPDATE":
                when = f"{when} AND {SUGGESTION_CONTENT}"
            op.execute(
                f"CREATE TRIGGER {table}_confirmed_no_{action.lower()} BEFORE {action} "
                f"ON {table} WHEN {when} "
                "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
            )


def _rebuild_review(unique: bool) -> None:
    create = REVIEW.format(unique=",\n    UNIQUE (policy_version_id, kind)" if unique else "")
    op.execute(create.replace("CREATE TABLE review (", "CREATE TABLE _review_new (", 1))
    op.execute(f"INSERT INTO _review_new ({COLUMNS}) SELECT {COLUMNS} FROM review")
    op.execute("DROP TABLE review")
    op.execute("ALTER TABLE _review_new RENAME TO review")


def upgrade() -> None:
    op.add_column(
        "policy",
        sa.Column("sharing", sa.String(10), nullable=False, server_default="private"),
    )
    _drop_triggers()
    _rebuild_review(unique=False)
    _create_triggers(saved=True)


def downgrade() -> None:
    _drop_triggers()
    # Only the newest saved review of each kind stays with its version
    op.execute(
        "DELETE FROM review WHERE id NOT IN (SELECT MAX(id) FROM review "
        "GROUP BY policy_version_id, kind)"
    )
    for table in REVIEW_CHILDREN:
        op.execute(f"DELETE FROM {table} WHERE review_id NOT IN (SELECT id FROM review)")
    # Timeline events are append-only; one that named a dropped review keeps its summary
    _rebuild_review(unique=True)
    _create_triggers(saved=False)
    op.execute("ALTER TABLE policy DROP COLUMN sharing")
