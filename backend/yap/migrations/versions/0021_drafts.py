"""drafts: fingerprints, confirmation time and marks

- `review.fingerprint` (REV-09): of the reviewed content; reviews from before stay null
  and are compared by time;
- `review.saved_at` (REV-11): when the review was confirmed; set from the activation time
  for reviews of activated versions;
- `policy_version.mark` (REV-20): versions activated without a finished review get
  `not_reviewed`.

The immutability triggers of the two updated tables are dropped for the backfill and
created again as they were.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-08 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VERSION_TRIGGER = (
    "CREATE TRIGGER policy_version_activated_no_update BEFORE UPDATE ON policy_version "
    "WHEN OLD.activated_at IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT, 'activated policy version is immutable'); END"
)
REVIEW_TRIGGER = (
    "CREATE TRIGGER review_confirmed_no_update BEFORE UPDATE ON review "
    "WHEN (SELECT activated_at FROM policy_version WHERE id = OLD.policy_version_id) "
    "IS NOT NULL BEGIN SELECT RAISE(ABORT, 'confirmed review is immutable'); END"
)


def upgrade() -> None:
    op.add_column("review", sa.Column("fingerprint", sa.String(64), nullable=True))
    op.add_column("review", sa.Column("saved_at", sa.String(32), nullable=True))
    op.add_column("policy_version", sa.Column("mark", sa.String(30), nullable=True))
    op.execute("DROP TRIGGER policy_version_activated_no_update")
    op.execute("DROP TRIGGER review_confirmed_no_update")
    op.execute(
        "UPDATE review SET saved_at = (SELECT activated_at FROM policy_version v "
        "WHERE v.id = review.policy_version_id) WHERE (SELECT activated_at FROM "
        "policy_version v WHERE v.id = review.policy_version_id) IS NOT NULL"
    )
    op.execute(
        "UPDATE policy_version SET mark = 'not_reviewed' WHERE activated_at IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM review r WHERE r.policy_version_id = "
        "policy_version.id AND r.state = 'done')"
    )
    op.execute(VERSION_TRIGGER)
    op.execute(REVIEW_TRIGGER)


def downgrade() -> None:
    # Plain DROP COLUMN: nothing else refers to these columns
    op.execute("ALTER TABLE policy_version DROP COLUMN mark")
    op.execute("ALTER TABLE review DROP COLUMN saved_at")
    op.execute("ALTER TABLE review DROP COLUMN fingerprint")
