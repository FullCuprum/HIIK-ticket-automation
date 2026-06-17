"""add ticket extracted building

Revision ID: a8c1d4e92f31
Revises: f7b4c3d21a05
Create Date: 2026-06-18 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8c1d4e92f31"
down_revision: Union[str, None] = "f7b4c3d21a05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("extracted_building", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "extracted_building")
