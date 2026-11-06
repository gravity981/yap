"""account language

The UI language of an account (USR-10); null follows the browser.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A plain ADD COLUMN, so the investor table is not rebuilt
    op.add_column("investor", sa.Column("language", sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("investor", schema=None) as batch_op:
        batch_op.drop_column("language")
