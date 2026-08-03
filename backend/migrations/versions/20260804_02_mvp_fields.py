"""Add functional MVP data and task fields.

Revision ID: 20260804_02
Revises: 20260803_01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_02"
down_revision = "20260803_01"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    canteen_columns = _columns("canteens")
    if "data_status" not in canteen_columns:
        op.add_column("canteens", sa.Column("data_status", sa.String(length=40), nullable=False, server_default="needs_verification"))
        op.create_index("ix_canteens_data_status", "canteens", ["data_status"])

    stall_columns = _columns("food_stalls")
    if "data_status" not in stall_columns:
        op.add_column("food_stalls", sa.Column("data_status", sa.String(length=40), nullable=False, server_default="needs_verification"))
        op.create_index("ix_food_stalls_data_status", "food_stalls", ["data_status"])

    task_columns = _columns("tasks")
    if "submission_target" not in task_columns:
        op.add_column("tasks", sa.Column("submission_target", sa.String(length=255), nullable=False, server_default=""))
    if "file_naming" not in task_columns:
        op.add_column("tasks", sa.Column("file_naming", sa.String(length=255), nullable=False, server_default=""))


def downgrade() -> None:
    task_columns = _columns("tasks")
    if "file_naming" in task_columns:
        op.drop_column("tasks", "file_naming")
    if "submission_target" in task_columns:
        op.drop_column("tasks", "submission_target")

    stall_columns = _columns("food_stalls")
    if "data_status" in stall_columns:
        op.drop_index("ix_food_stalls_data_status", table_name="food_stalls")
        op.drop_column("food_stalls", "data_status")

    canteen_columns = _columns("canteens")
    if "data_status" in canteen_columns:
        op.drop_index("ix_canteens_data_status", table_name="canteens")
        op.drop_column("canteens", "data_status")
