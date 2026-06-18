"""add schedule executors

Revision ID: g8c2d4e51b93
Revises: b9d2e5f03a42
Create Date: 2026-06-18 20:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g8c2d4e51b93"
down_revision: Union[str, None] = "b9d2e5f03a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "schedule_executors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedule_slots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_id", "employee_id", name="uq_schedule_executor"),
    )
    op.create_index(
        op.f("ix_schedule_executors_employee_id"),
        "schedule_executors",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_schedule_executors_id"),
        "schedule_executors",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_schedule_executors_schedule_id"),
        "schedule_executors",
        ["schedule_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO schedule_executors (schedule_id, employee_id)
        SELECT id, employee_id
        FROM schedule_slots
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_executors_schedule_id"), table_name="schedule_executors")
    op.drop_index(op.f("ix_schedule_executors_id"), table_name="schedule_executors")
    op.drop_index(op.f("ix_schedule_executors_employee_id"), table_name="schedule_executors")
    op.drop_table("schedule_executors")
