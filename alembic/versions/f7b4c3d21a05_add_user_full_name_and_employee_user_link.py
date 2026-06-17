"""add user full_name and employee user link

Revision ID: f7b4c3d21a05
Revises: e6a3f2b40c92
Create Date: 2026-06-18 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7b4c3d21a05"
down_revision: Union[str, None] = "e6a3f2b40c92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_employees_user_id"), "employees", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_employees_user_id_users",
        "employees",
        "users",
        ["user_id"],
        ["id"],
    )

    op.execute(sa.text("UPDATE users SET full_name = 'Администратор' WHERE username = 'admin'"))
    op.execute(sa.text("UPDATE users SET full_name = 'Пользователь' WHERE username = 'user'"))
    op.execute(sa.text("UPDATE users SET full_name = 'Иванов Иван Иванович' WHERE username = 'employee'"))

    op.execute(
        sa.text(
            """
            UPDATE employees
            SET user_id = users.id
            FROM users
            WHERE employees.full_name = users.full_name
              AND employees.user_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_employees_user_id_users", "employees", type_="foreignkey")
    op.drop_index(op.f("ix_employees_user_id"), table_name="employees")
    op.drop_column("employees", "user_id")
    op.drop_column("users", "full_name")
