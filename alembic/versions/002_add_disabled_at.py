"""add disabled_at to links

Soft delete rather than a row delete: an abusive link is evidence, and keeping
the row preserves what the code pointed at, when it was created and from which
IP. It also guarantees the code is never reissued to someone else.

Revision ID: 002
Revises: 001
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "links",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("links", sa.Column("disabled_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("links", "disabled_reason")
    op.drop_column("links", "disabled_at")
