"""timeline params

Timeline events store the values of their summary as JSON, so the UI can write the
summary in its language (TL-02, NFR-10). Events from before keep only their English
summary.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A plain ADD COLUMN keeps the append-only triggers of timeline_event (no rebuild)
    op.add_column("timeline_event", sa.Column("params", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.execute("ALTER TABLE timeline_event DROP COLUMN params")
