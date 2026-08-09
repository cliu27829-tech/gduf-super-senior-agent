"""Link private tasks to verified campus locations.

Revision ID: 20260809_08
Revises: 20260809_07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_08"
down_revision = "20260809_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "location_id" not in columns:
        with op.batch_alter_table("tasks") as batch:
            batch.add_column(sa.Column("location_id", sa.String(64), nullable=True))
            batch.create_foreign_key(
                "fk_tasks_location_id_locations", "locations", ["location_id"], ["id"], ondelete="SET NULL"
            )
            batch.create_index("ix_tasks_location_id", ["location_id"])


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "location_id" in columns:
        with op.batch_alter_table("tasks") as batch:
            batch.drop_index("ix_tasks_location_id")
            batch.drop_constraint("fk_tasks_location_id_locations", type_="foreignkey")
            batch.drop_column("location_id")
