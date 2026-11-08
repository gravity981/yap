"""merge theses into policies

A policy version holds its thesis (title, markdown text and, until the semaphore replaces
it, the status) instead of pinning a thesis revision (POL-02, stage 2). Theses and their
revisions are dropped:

- every policy version takes the title, text and status of the revision it pinned;
- the confirmed thesis review of that revision becomes the version's review of kind
  `thesis`, next to its review of kind `policy` (a version has at most one of each);
- a thesis that no policy uses becomes a new policy of its owner, whose draft v1 holds the
  latest revision's text and no positions;
- drafts of theses that policies use are dropped, and so are reviews no version can take;
  timeline events keep their summaries.

Nothing is released yet, so the migration keeps data usable rather than every detail of
history (spec section 4.1). The downgrade gives every policy one thesis with a revision per
version.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-08 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("UPDATE", "DELETE")
CHILD_ACTIONS = (("INSERT", "NEW"), ("UPDATE", "OLD"), ("DELETE", "OLD"))
REVIEW_CHILDREN = ("review_aspect", "review_source", "review_suggestion")

# --- Triggers (NFR-05) ---------------------------------------------------------------------
# Rebuilding a table breaks the triggers of other tables that read it, so every trigger
# that reads one of the rebuilt tables is dropped first and created again at the end.


def _drop_triggers(with_theses: bool) -> None:
    names = [f"timeline_event_no_{a.lower()}" for a in ACTIONS]
    names += [f"policy_version_activated_no_{a.lower()}" for a in ACTIONS]
    names += [f"policy_position_activated_no_{a.lower()}" for a, _ in CHILD_ACTIONS]
    names += [f"review_confirmed_no_{a.lower()}" for a in ACTIONS]
    names += [f"{t}_confirmed_no_{a.lower()}" for t in REVIEW_CHILDREN for a, _ in CHILD_ACTIONS]
    if with_theses:
        names += [f"thesis_revision_activated_no_{a.lower()}" for a in ACTIONS]
    for name in names:
        op.execute(f"DROP TRIGGER IF EXISTS {name}")


def _create_triggers(with_theses: bool) -> None:
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
    if with_theses:
        confirmed = (
            "(SELECT activated_at FROM thesis_revision WHERE id = {row}.thesis_revision_id) "
            "IS NOT NULL OR (SELECT activated_at FROM policy_version WHERE id = "
            "{row}.policy_version_id) IS NOT NULL"
        )
        child = (
            "(SELECT 1 FROM review r WHERE r.id = {row}.review_id AND ("
            "(SELECT activated_at FROM thesis_revision WHERE id = r.thesis_revision_id) "
            "IS NOT NULL OR (SELECT activated_at FROM policy_version WHERE id = "
            "r.policy_version_id) IS NOT NULL)) IS NOT NULL"
        )
        for action in ACTIONS:
            op.execute(
                f"CREATE TRIGGER thesis_revision_activated_no_{action.lower()} BEFORE {action} "
                "ON thesis_revision WHEN OLD.activated_at IS NOT NULL "
                "BEGIN SELECT RAISE(ABORT, 'activated thesis revision is immutable'); END"
            )
    else:
        confirmed = (
            "(SELECT activated_at FROM policy_version WHERE id = {row}.policy_version_id) "
            "IS NOT NULL"
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
    thesis_status VARCHAR(20) NOT NULL,
    change_note TEXT,
    activated_at VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32),
    PRIMARY KEY (id),
    FOREIGN KEY(policy_id) REFERENCES policy (id),
    UNIQUE (policy_id, version_no)
)"""
POLICY_VERSION_OLD = """CREATE TABLE policy_version (
    id INTEGER NOT NULL,
    policy_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    thesis_revision_id INTEGER NOT NULL,
    change_note TEXT,
    activated_at VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32),
    PRIMARY KEY (id),
    FOREIGN KEY(policy_id) REFERENCES policy (id),
    FOREIGN KEY(thesis_revision_id) REFERENCES thesis_revision (id),
    UNIQUE (policy_id, version_no)
)"""

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
    scoring_version VARCHAR(20) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
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
# The new table plus the old thesis link, while thesis reviews move to policy versions
REVIEW_MID = REVIEW_NEW.replace(
    "policy_version_id INTEGER NOT NULL,",
    "thesis_revision_id INTEGER,\n    policy_version_id INTEGER,",
)
REVIEW_OLD = """CREATE TABLE review (
    id INTEGER NOT NULL,
    kind VARCHAR(10) NOT NULL,
    thesis_revision_id INTEGER,
    policy_version_id INTEGER,
    started_by INTEGER NOT NULL,
    state VARCHAR(10) NOT NULL,
    news_from VARCHAR(32),
    news_to VARCHAR(32),
    verdict VARCHAR(20),
    scoring_version VARCHAR(20) NOT NULL,
    provider VARCHAR(20) NOT NULL,
    model VARCHAR(100) NOT NULL,
    error TEXT,
    started_at VARCHAR(32) NOT NULL,
    completed_at VARCHAR(32),
    ai_reviewer_id INTEGER,
    ai_reviewer_name VARCHAR(100),
    legacy_modification TEXT,
    method VARCHAR(10) DEFAULT 'ai' NOT NULL,
    prompt_id VARCHAR(60),
    PRIMARY KEY (id),
    UNIQUE (policy_version_id),
    FOREIGN KEY(ai_reviewer_id) REFERENCES ai_reviewer (id),
    FOREIGN KEY(thesis_revision_id) REFERENCES thesis_revision (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    UNIQUE (thesis_revision_id),
    FOREIGN KEY(started_by) REFERENCES investor (id)
)"""

TIMELINE_COLUMNS = (
    "id, investor_id, occurred_at, type, portfolio_id, policy_version_id, rebalance_id, "
    "review_id, summary, params"
)
TIMELINE_NEW = """CREATE TABLE timeline_event (
    id INTEGER NOT NULL,
    investor_id INTEGER NOT NULL,
    occurred_at VARCHAR(32) NOT NULL,
    type VARCHAR(30) NOT NULL,
    portfolio_id INTEGER,
    policy_version_id INTEGER,
    rebalance_id INTEGER,
    review_id INTEGER,
    summary VARCHAR(500) NOT NULL,
    params JSON,
    PRIMARY KEY (id),
    FOREIGN KEY(investor_id) REFERENCES investor (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolio (id),
    FOREIGN KEY(rebalance_id) REFERENCES rebalance (id),
    FOREIGN KEY(review_id) REFERENCES review (id)
)"""
TIMELINE_OLD = """CREATE TABLE timeline_event (
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
    params JSON,
    PRIMARY KEY (id),
    FOREIGN KEY(investor_id) REFERENCES investor (id),
    FOREIGN KEY(policy_version_id) REFERENCES policy_version (id),
    FOREIGN KEY(portfolio_id) REFERENCES portfolio (id),
    FOREIGN KEY(rebalance_id) REFERENCES rebalance (id),
    FOREIGN KEY(review_id) REFERENCES review (id),
    FOREIGN KEY(thesis_revision_id) REFERENCES thesis_revision (id)
)"""

THESIS = """CREATE TABLE thesis (
    id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    visibility VARCHAR(10) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(owner_id) REFERENCES investor (id)
)"""
THESIS_REVISION = """CREATE TABLE thesis_revision (
    id INTEGER NOT NULL,
    thesis_id INTEGER NOT NULL,
    revision_no INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    content_md TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    change_note TEXT,
    activated_at VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32),
    PRIMARY KEY (id),
    FOREIGN KEY(thesis_id) REFERENCES thesis (id),
    UNIQUE (thesis_id, revision_no)
)"""


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


def _copy_review(conn, review_id: int, version_id: int) -> None:  # type: ignore[no-untyped-def]
    """A copy of a review and its rows for another version."""
    columns = REVIEW_COLUMNS.replace("id, ", "", 1).replace("policy_version_id", ":version")
    new_id = conn.execute(
        text(
            f"INSERT INTO review ({REVIEW_COLUMNS.replace('id, ', '', 1)}, thesis_revision_id) "
            f"SELECT {columns}, NULL FROM review WHERE id = :id RETURNING id"
        ),
        {"id": review_id, "version": version_id},
    ).scalar()
    conn.execute(
        text(
            "INSERT INTO review_aspect (review_id, aspect, half_points, reasoning_md) "
            "SELECT :new, aspect, half_points, reasoning_md FROM review_aspect "
            "WHERE review_id = :id"
        ),
        {"new": new_id, "id": review_id},
    )
    conn.execute(
        text(
            "INSERT INTO review_source (review_id, title, published_on, url) "
            "SELECT :new, title, published_on, url FROM review_source WHERE review_id = :id"
        ),
        {"new": new_id, "id": review_id},
    )
    conn.execute(
        text(
            "INSERT INTO review_suggestion (review_id, kind, content_md) "
            "SELECT :new, kind, content_md FROM review_suggestion WHERE review_id = :id"
        ),
        {"new": new_id, "id": review_id},
    )


def upgrade() -> None:
    conn = op.get_bind()
    _drop_triggers(with_theses=True)

    # Theses no policy uses become policies with a draft v1 (no positions)
    unused = conn.execute(
        text(
            "SELECT t.id, t.owner_id, t.created_at FROM thesis t WHERE NOT EXISTS ("
            "SELECT 1 FROM policy_version v JOIN thesis_revision r "
            "ON r.id = v.thesis_revision_id WHERE r.thesis_id = t.id) ORDER BY t.id"
        )
    ).all()
    for thesis_id, owner_id, created_at in unused:
        latest = conn.execute(
            text(
                "SELECT id, title, updated_at FROM thesis_revision WHERE thesis_id = :t "
                "ORDER BY revision_no DESC LIMIT 1"
            ),
            {"t": thesis_id},
        ).one()
        name, n = latest.title[:100], 2
        while conn.execute(
            text("SELECT 1 FROM policy WHERE owner_id = :o AND name = :n"),
            {"o": owner_id, "n": name},
        ).first():
            name, n = f"{latest.title[:90]} ({n})", n + 1
        policy_id = conn.execute(
            text(
                "INSERT INTO policy (owner_id, name, created_at) VALUES (:o, :n, :c) RETURNING id"
            ),
            {"o": owner_id, "n": name, "c": created_at},
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO policy_version (policy_id, version_no, thesis_revision_id, "
                "created_at, updated_at) VALUES (:p, 1, :r, :c, :u)"
            ),
            {"p": policy_id, "r": latest.id, "c": created_at, "u": latest.updated_at},
        )

    # Thesis reviews: confirmed ones go to the activated versions that pinned their revision
    # (moved to the first, copied for the others); the rest is dropped. The intermediate
    # table allows one review of each kind per version.
    _replace(
        "review",
        REVIEW_MID,
        REVIEW_COLUMNS + ", thesis_revision_id",
        f"SELECT {REVIEW_COLUMNS}, thesis_revision_id FROM {{old}}",
    )
    reviews = conn.execute(
        text(
            "SELECT r.id, r.thesis_revision_id, tr.activated_at FROM review r "
            "JOIN thesis_revision tr ON tr.id = r.thesis_revision_id ORDER BY r.id"
        )
    ).all()
    keep: set[int] = set()
    for review_id, revision_id, activated_at in reviews:
        if activated_at is None:
            continue  # a review of a thesis draft
        versions = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT id FROM policy_version WHERE thesis_revision_id = :r "
                    "AND activated_at IS NOT NULL ORDER BY id"
                ),
                {"r": revision_id},
            )
        ]
        for i, version_id in enumerate(versions):
            if i == 0:
                conn.execute(
                    text("UPDATE review SET policy_version_id = :v WHERE id = :id"),
                    {"v": version_id, "id": review_id},
                )
                keep.add(review_id)
            else:
                _copy_review(conn, review_id, version_id)
    dropped = [r[0] for r in reviews if r[0] not in keep]
    for review_id in dropped:
        for table in (*REVIEW_CHILDREN,):
            conn.execute(text(f"DELETE FROM {table} WHERE review_id = :id"), {"id": review_id})
        conn.execute(text("DELETE FROM review WHERE id = :id"), {"id": review_id})

    _replace(
        "timeline_event",
        TIMELINE_NEW,
        TIMELINE_COLUMNS,
        "SELECT id, investor_id, occurred_at, type, portfolio_id, policy_version_id, "
        "rebalance_id, CASE WHEN review_id IN (SELECT id FROM review) THEN review_id END, "
        "summary, params FROM {old}",
    )
    _replace(
        "review",
        REVIEW_NEW,
        REVIEW_COLUMNS,
        f"SELECT {REVIEW_COLUMNS} FROM {{old}} WHERE policy_version_id IS NOT NULL",
    )
    _replace(
        "policy_version",
        POLICY_VERSION_NEW,
        "id, policy_id, version_no, thesis_title, thesis_md, thesis_status, change_note, "
        "activated_at, created_at, updated_at",
        "SELECT v.id, v.policy_id, v.version_no, r.title, r.content_md, r.status, "
        "v.change_note, v.activated_at, v.created_at, v.updated_at FROM {old} v "
        "JOIN thesis_revision r ON r.id = v.thesis_revision_id",
    )
    op.execute("DROP TABLE thesis_revision")
    op.execute("DROP TABLE thesis")
    _create_triggers(with_theses=False)


def downgrade() -> None:
    """Every policy gets one private thesis with a revision per version."""
    conn = op.get_bind()
    _drop_triggers(with_theses=False)
    op.execute(THESIS)
    op.execute(THESIS_REVISION)
    revision_of: dict[int, int] = {}
    for policy_id, owner_id, created_at in conn.execute(
        text("SELECT id, owner_id, created_at FROM policy ORDER BY id")
    ).all():
        thesis_id = conn.execute(
            text(
                "INSERT INTO thesis (owner_id, visibility, created_at) "
                "VALUES (:o, 'private', :c) RETURNING id"
            ),
            {"o": owner_id, "c": created_at},
        ).scalar()
        for v in conn.execute(
            text(
                "SELECT id, version_no, thesis_title, thesis_md, thesis_status, change_note, "
                "activated_at, created_at, updated_at FROM policy_version "
                "WHERE policy_id = :p ORDER BY version_no"
            ),
            {"p": policy_id},
        ).all():
            revision_of[v.id] = conn.execute(  # type: ignore[assignment]
                text(
                    "INSERT INTO thesis_revision (thesis_id, revision_no, title, content_md, "
                    "status, change_note, activated_at, created_at, updated_at) VALUES "
                    "(:t, :n, :title, :md, :s, :note, :a, :c, :u) RETURNING id"
                ),
                {
                    "t": thesis_id,
                    "n": v.version_no,
                    "title": v.thesis_title or "Thesis",
                    "md": v.thesis_md,
                    "s": v.thesis_status,
                    "note": v.change_note,
                    "a": v.activated_at,
                    "c": v.created_at,
                    "u": v.updated_at,
                },
            ).scalar()
    _replace(
        "policy_version",
        POLICY_VERSION_OLD,
        "id, policy_id, version_no, thesis_revision_id, change_note, activated_at, "
        "created_at, updated_at",
        "SELECT id, policy_id, version_no, 0, change_note, activated_at, created_at, "
        "updated_at FROM {old}",
    )
    for version_id, revision_id in revision_of.items():
        conn.execute(
            text("UPDATE policy_version SET thesis_revision_id = :r WHERE id = :v"),
            {"r": revision_id, "v": version_id},
        )
    # Thesis reviews belong to the revision of their version
    op.execute("CREATE TEMPORARY TABLE _revision_of (version_id INTEGER, revision_id INTEGER)")
    for version_id, revision_id in revision_of.items():
        conn.execute(
            text("INSERT INTO _revision_of VALUES (:v, :r)"), {"v": version_id, "r": revision_id}
        )
    columns = REVIEW_COLUMNS.replace(
        "policy_version_id",
        "CASE WHEN kind = 'thesis' THEN NULL ELSE policy_version_id END",
    )
    _replace(
        "review",
        REVIEW_OLD,
        REVIEW_COLUMNS + ", thesis_revision_id",
        f"SELECT {columns}, CASE WHEN kind = 'thesis' THEN (SELECT revision_id FROM "
        "_revision_of WHERE version_id = {old}.policy_version_id) END FROM {old}",
    )
    op.execute("DROP TABLE _revision_of")
    _replace(
        "timeline_event",
        TIMELINE_OLD,
        TIMELINE_COLUMNS,
    )
    _create_triggers(with_theses=True)
