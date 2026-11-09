"""suggestions live only while their draft is open

REV-07: a dismissed suggestion is deleted, and activating a draft deletes all of its
suggestions. Existing saved reviews lose theirs, and so do dismissed ones; the history
trigger that protects saved suggestions is out of the way only for this.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-10 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DELETE_TRIGGER = (
    "CREATE TRIGGER review_suggestion_confirmed_no_delete BEFORE DELETE ON review_suggestion "
    "WHEN (SELECT saved_at FROM review WHERE id = OLD.review_id) IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
)


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS review_suggestion_confirmed_no_delete")
    op.execute(
        "DELETE FROM review_suggestion WHERE state = 'dismissed' OR review_id IN "
        "(SELECT id FROM review WHERE saved_at IS NOT NULL)"
    )
    op.execute(DELETE_TRIGGER)


def downgrade() -> None:
    """The deleted suggestions are gone."""
