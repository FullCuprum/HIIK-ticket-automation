"""add ticket completed_at

Revision ID: b9d2e5f03a42
Revises: a8c1d4e92f31
Create Date: 2026-06-18 22:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b9d2e5f03a42"
down_revision: Union[str, None] = "a8c1d4e92f31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "completed_at")
