"""Add notification task details and campus coordinate quality metadata.

Revision ID: 20260809_06
Revises: 20260804_05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_06"
down_revision = "20260804_05"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    location_columns = _columns("locations")
    location_additions = (
        ("coordinate_source", sa.Column("coordinate_source", sa.String(100), nullable=False, server_default="")),
        ("coordinate_accuracy", sa.Column("coordinate_accuracy", sa.String(30), nullable=False, server_default="unknown")),
        ("coordinate_verified_at", sa.Column("coordinate_verified_at", sa.DateTime(timezone=True), nullable=True)),
        ("coordinate_verified_by", sa.Column("coordinate_verified_by", sa.String(100), nullable=False, server_default="")),
        ("coordinate_note", sa.Column("coordinate_note", sa.Text(), nullable=False, server_default="")),
        ("amap_poi_id", sa.Column("amap_poi_id", sa.String(80), nullable=False, server_default="")),
    )
    for name, column in location_additions:
        if name not in location_columns:
            op.add_column("locations", column)

    task_columns = _columns("tasks")
    task_additions = (
        ("conditions", sa.Column("conditions", sa.JSON(), nullable=False, server_default="[]")),
        ("evidence_requirements", sa.Column("evidence_requirements", sa.JSON(), nullable=False, server_default="[]")),
        ("is_expired", sa.Column("is_expired", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("source_title", sa.Column("source_title", sa.String(255), nullable=False, server_default="")),
    )
    for name, column in task_additions:
        if name not in task_columns:
            op.add_column("tasks", column)

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("locations")}
    if "ix_locations_coordinate_accuracy" not in indexes:
        op.create_index("ix_locations_coordinate_accuracy", "locations", ["coordinate_accuracy"])
    if "ix_locations_amap_poi_id" not in indexes:
        op.create_index("ix_locations_amap_poi_id", "locations", ["amap_poi_id"])
    task_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("tasks")}
    if "ix_tasks_is_expired" not in task_indexes:
        op.create_index("ix_tasks_is_expired", "tasks", ["is_expired"])


def downgrade() -> None:
    for index_name, table in (
        ("ix_tasks_is_expired", "tasks"),
        ("ix_locations_amap_poi_id", "locations"),
        ("ix_locations_coordinate_accuracy", "locations"),
    ):
        indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
    for name in ("source_title", "is_expired", "evidence_requirements", "conditions"):
        if name in _columns("tasks"):
            op.drop_column("tasks", name)
    for name in (
        "amap_poi_id",
        "coordinate_note",
        "coordinate_verified_by",
        "coordinate_verified_at",
        "coordinate_accuracy",
        "coordinate_source",
    ):
        if name in _columns("locations"):
            op.drop_column("locations", name)
