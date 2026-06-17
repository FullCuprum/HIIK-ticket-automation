"""add ticket event datetime

Revision ID: e6a3f2b40c92
Revises: d5f9b2c31e81
Create Date: 2026-06-18 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a3f2b40c92"
down_revision: Union[str, None] = "d5f9b2c31e81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("event_datetime", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "event_datetime")
