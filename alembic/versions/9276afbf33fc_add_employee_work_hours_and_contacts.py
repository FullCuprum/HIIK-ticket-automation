"""Add employee work hours and contacts

Revision ID: 9276afbf33fc
Revises: a3f10c14fe6e
Create Date: 2026-06-17 12:16:45.154053

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9276afbf33fc"
down_revision: Union[str, Sequence[str], None] = "a3f10c14fe6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("work_start_hour", sa.Integer(), nullable=False, server_default="9"),
    )
    op.add_column(
        "employees",
        sa.Column("work_end_hour", sa.Integer(), nullable=False, server_default="18"),
    )
    op.add_column("employees", sa.Column("phone", sa.String(length=50), nullable=True))
    op.add_column("employees", sa.Column("email", sa.String(length=255), nullable=True))
    op.alter_column("employees", "work_start_hour", server_default=None)
    op.alter_column("employees", "work_end_hour", server_default=None)


def downgrade() -> None:
    op.drop_column("employees", "email")
    op.drop_column("employees", "phone")
    op.drop_column("employees", "work_end_hour")
    op.drop_column("employees", "work_start_hour")
