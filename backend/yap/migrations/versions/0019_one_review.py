"""one review of everything

A review judges the whole policy (scoring version 3, REV-02, REV-03): its verdict is the
semaphore of the thesis, with a reason, and replaces the status the investor set
(THS-04). A manual review names no model any more (REV-17).

- `policy_version.thesis_status` is dropped;
- `review.verdict_reason` is added, and `review.model` may be null;
- reviews of earlier scoring versions keep their kinds (`thesis`, `policy`) and verdicts,
  which the app maps to the semaphore (REV-06).

The downgrade sets the thesis status from the semaphore of each version's review and turns
reviews of the whole policy into thesis reviews without their target-structure aspects.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-08 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("UPDATE", "DELETE")
CHILD_ACTIONS = (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD"))
REVIEW_CHILDREN = ("review_aspect", "review_source", "review_suggestion")

# --- Triggers (NFR-05) ---------------------------------------------------------------------
# Rebuilding a table breaks the triggers of other tables that read it, so every trigger
# that reads one of the rebuilt tables is dropped first and created again at the end.


def _drop_triggers() -> None:
    names = [f"timeline_event_no_{a.lower()}" for a in ACTIONS]
    names += [f"policy_version_activated_no_{a.lower()}" for a in ACTIONS]
    names += [f"policy_position_activated_no_{a.lower()}" for a, _ in CHILD_ACTIONS]
    names += [f"review_confirmed_no_{a.lower()}" for a in ACTIONS]
    names += [f"{t}_confirmed_no_{a.lower()}" for t in REVIEW_CHILDREN for a, _ in CHILD_ACTIONS]
    for name in names:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def _create_triggers() -> None:
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER timeline_event_no_{action.lower()} BEFORE {action} ON "
            "timeline_event BEGIN SELECT RAISE(ABORT, 'timeline_event is append-only'); END"
        )
        op.execute(
            f"CREATE TRIGGER policy_version_activated_no_{action.lower()} BEFORE {action} ON "
            "policy_version WHEN OLD.activated_at IS NOT NULL "
            "BEGIN SELECT RAISE(ABORT, 'activated policy version is immutable'); END"
        )
    for action, row in CHILD_ACTIONS:
        op.execute(
            f"CREATE TRIGGER policy_position_activated_no_{action.lower()} BEFORE {action} ON "
            "policy_position WHEN (SELECT activated_at FROM policy_version WHERE id = "
            f"{row}.policy_version_id) IS NOT NULL "
            "BEGIN SELECT RAISE(ABORT, 'activated policy version is immutable'); END"
        )
    confirmed = (
        "(SELECT activated_at FROM policy_version WHERE id = {row}.policy_version_id) IS NOT NULL"
    )
    child = (
        "(SELECT activated_at FROM policy_version WHERE id = "
        "(SELECT policy_version_id FROM review WHERE id = {row}.review_id)) IS NOT NULL"
    )
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER review_confirmed_no_{action.lower()} BEFORE {action} ON review "
            f"WHEN {confirmed.format(row='OLD')} "
            "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
        )
    for table in REVIEW_CHILDREN:
        for action, row in CHILD_ACTIONS:
            op.execute(
                f"CREATE TRIGGER {table}_confirmed_no_{action.lower()} BEFORE {action} "
                f"ON {table} WHEN {child.format(row=row)} "
                "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
            )


# --- Tables --------------------------------------------------------------------------------

POLICY_VERSION_NEW = """CREATE TABLE policy_version (
    id INTEGER NOT NULL,
    policy_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    thesis_title VARCHAR(200) NOT NULL,
    thesis_md TEXT NOT NULL,
    change_note TEXT,
    activated_at VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32),
    PRIMARY KEY (id),
    FOREIGN KEY(policy_id) REFERENCES policy (id),
    UNIQUE (policy_id, version_no)
)"""
POLICY_VERSION_OLD = POLICY_VERSION_NEW.replace(
    "thesis_md TEXT NOT NULL,", "thesis_md TEXT NOT NULL,\n    thesis_status VARCHAR(20) NOT NULL,"
)
VERSION_COLUMNS = (
    "id, policy_id, version_no, thesis_title, thesis_md, change_note, activated_at, "
    "created_at, updated_at"
)

REVIEW_COLUMNS = (
    "id, kind, policy_version_id, started_by, state, news_from, news_to, verdict, "
    "scoring_version, provider, model, error, started_at, completed_at, ai_reviewer_id, "
    "ai_reviewer_name, legacy_modification, method, prompt_id"
)
REVIEW_NEW = """CREATE TABLE review (
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
    PRIMARY KEY (id),
    FOREIGN KEY(ai_reviewer_id) REFERENCES ai_reviewer (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    FOREIGN KEY(started_by) REFERENCES investor (id),
    UNIQUE (policy_version_id, kind)
)"""
REVIEW_OLD = REVIEW_NEW.replace("    verdict_reason TEXT,\n", "").replace(
    "model VARCHAR(100),", "model VARCHAR(100) NOT NULL,"
)


def _replace(table: str, create: str, columns: str, select: str | None = None) -> None:
    """Rebuilds `table` with `create`; `select` gives the rows from `{old}` (default: the
    same columns). The new table is renamed into place, never the old one away: renaming
    the old table would point the foreign keys of other tables at it."""
    op.execute(create.replace(f"CREATE TABLE {table} (", f"CREATE TABLE _{table}_new (", 1))
    op.execute(
        f"INSERT INTO _{table}_new ({columns}) "
        + (select or f"SELECT {columns} FROM {{old}}").format(old=table)
    )
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE _{table}_new RENAME TO {table}")


def upgrade() -> None:
    _drop_triggers()
    _replace("policy_version", POLICY_VERSION_NEW, VERSION_COLUMNS)
    _replace("review", REVIEW_NEW, REVIEW_COLUMNS)
    _create_triggers()


def downgrade() -> None:
    _drop_triggers()
    # Reviews of the whole policy become thesis reviews with the old verdicts
    op.execute(
        "DELETE FROM review_aspect WHERE aspect LIKE 'P%' AND review_id IN "
        "(SELECT id FROM review WHERE kind = 'full')"
    )
    op.execute(
        "UPDATE review SET kind = 'thesis', verdict = CASE verdict "
        "WHEN 'good' THEN 'intact' WHEN 'warning' THEN 'needs_adaptation' ELSE verdict END "
        "WHERE kind = 'full'"
    )
    op.execute("UPDATE review SET model = 'unknown' WHERE model IS NULL")
    _replace("review", REVIEW_OLD, REVIEW_COLUMNS)
    _replace(
        "policy_version",
        POLICY_VERSION_OLD,
        VERSION_COLUMNS + ", thesis_status",
        f"SELECT {VERSION_COLUMNS}, COALESCE((SELECT r.verdict FROM review r "
        "WHERE r.policy_version_id = {old}.id AND r.kind = 'thesis' AND r.state = 'done'), "
        "'intact') FROM {old}",
    )
    _create_triggers()
