"""add ticket creator username

Revision ID: d5f9b2c31e81
Revises: c4e8a1b29d70
Create Date: 2026-06-18 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5f9b2c31e81"
down_revision: Union[str, None] = "c4e8a1b29d70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("creator_username", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "creator_username")
