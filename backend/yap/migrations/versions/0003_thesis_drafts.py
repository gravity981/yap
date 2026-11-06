"""thesis drafts

Theses are edited in drafts like policy versions (THS-02): a revision is a draft
until activated and immutable afterwards. Existing revisions count as activated
when they were created.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import yap.db.types

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("UPDATE", "DELETE")


def upgrade() -> None:
    # SQLite applies DDL statement by statement, so an interrupted run (e.g. a dev server
    # restarted by its reloader) can leave the triggers dropped and the batch copy table
    # behind; both steps are written so that a new run continues from there.
    # The batch operation recreates the table, which would drop its triggers anyway
    for action in ACTIONS:
        op.execute(f"DROP TRIGGER IF EXISTS thesis_revision_no_{action.lower()}")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_thesis_revision")
    with op.batch_alter_table("thesis_revision", schema=None) as batch_op:
        batch_op.alter_column(
            "status", existing_type=sa.String(length=10), type_=sa.String(length=20)
        )
        batch_op.add_column(
            sa.Column("activated_at", yap.db.types.UTCDateTime(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("updated_at", yap.db.types.UTCDateTime(length=32), nullable=True)
        )
    op.execute("UPDATE thesis_revision SET activated_at = created_at")
    # Activated revisions are immutable (NFR-05); the draft is not.
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER thesis_revision_activated_no_{action.lower()} "
            f"BEFORE {action} ON thesis_revision WHEN OLD.activated_at IS NOT NULL "
            "BEGIN SELECT RAISE(ABORT, 'activated thesis revision is immutable'); END"
        )


def downgrade() -> None:
    for action in ACTIONS:
        op.execute(f"DROP TRIGGER thesis_revision_activated_no_{action.lower()}")
    op.execute("DELETE FROM thesis_revision WHERE activated_at IS NULL")
    with op.batch_alter_table("thesis_revision", schema=None) as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("activated_at")
        batch_op.alter_column(
            "status", existing_type=sa.String(length=20), type_=sa.String(length=10)
        )
    for action in ACTIONS:
        op.execute(
            f"CREATE TRIGGER thesis_revision_no_{action.lower()} BEFORE {action} "
            "ON thesis_revision BEGIN SELECT RAISE(ABORT, 'thesis_revision is append-only'); END"
        )
