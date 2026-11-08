"""suggestion changes

Suggestions are concrete changes that can be taken over, dismissed and undone (REV-07);
proposed target structures are suggestions of kind `proposal` (REV-22). Each suggestion
gets what Take over applies (`change`), what it replaced (`previous`) and its `state`.
Suggestions from before have no change and stay `open`, read-only.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Plain ADD COLUMN: no rebuild, so the triggers of review_suggestion stay as they are
    op.add_column("review_suggestion", sa.Column("change", sa.JSON(), nullable=True))
    op.add_column("review_suggestion", sa.Column("previous", sa.JSON(), nullable=True))
    op.add_column(
        "review_suggestion",
        sa.Column("state", sa.String(20), nullable=False, server_default="open"),
    )


def downgrade() -> None:
    # SQLite drops a column without a rebuild when nothing refers to it
    for column in ("state", "previous", "change"):
        op.execute(f"ALTER TABLE review_suggestion DROP COLUMN {column}")
