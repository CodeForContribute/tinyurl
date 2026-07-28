"""create links table

Revision ID: 001
Revises:
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_ip", sa.String(length=45), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Unique so that concurrent inserts racing on the same random code cannot
    # both succeed; the index also serves the redirect lookup.
    op.create_index("ix_links_code", "links", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_links_code", table_name="links")
    op.drop_table("links")
