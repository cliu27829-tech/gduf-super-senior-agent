"""Add reminders, notes and structured Qingyuan campus facts.

Revision ID: 20260809_07
Revises: 20260809_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_07"
down_revision = "20260809_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "campus_colleges" not in tables:
        op.create_table(
            "campus_colleges",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("education_mode", sa.String(80), nullable=False),
            sa.Column("grades", sa.JSON(), nullable=False),
            sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
            sa.Column("source_title", sa.String(255), nullable=False, server_default=""),
            sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("campus_id", "name", "education_mode", name="uq_campus_college_mode"),
        )
        op.create_index("ix_campus_colleges_campus_id", "campus_colleges", ["campus_id"])
        op.create_index("ix_campus_colleges_name", "campus_colleges", ["name"])
        op.create_index("ix_campus_colleges_education_mode", "campus_colleges", ["education_mode"])
        op.create_index("ix_campus_colleges_verified", "campus_colleges", ["verified"])
    if "campus_facts" not in tables:
        op.create_table(
            "campus_facts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("subject", sa.String(180), nullable=False),
            sa.Column("predicate", sa.String(120), nullable=False),
            sa.Column("object", sa.Text(), nullable=False),
            sa.Column("aliases", sa.JSON(), nullable=False),
            sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
            sa.Column("source_title", sa.String(255), nullable=False, server_default=""),
            sa.Column("source_type", sa.String(60), nullable=False, server_default="official"),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("verification_status", sa.String(40), nullable=False, server_default="needs_verification"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_campus_facts_campus_id", "campus_facts", ["campus_id"])
        op.create_index("ix_campus_facts_subject", "campus_facts", ["subject"])
        op.create_index("ix_campus_facts_predicate", "campus_facts", ["predicate"])
        op.create_index("ix_campus_facts_verified", "campus_facts", ["verified"])
        op.create_index("ix_campus_facts_verification_status", "campus_facts", ["verification_status"])
        op.create_index("ix_campus_fact_subject_predicate", "campus_facts", ["campus_id", "subject", "predicate"])
    if "campus_path_nodes" not in tables:
        op.create_table(
            "campus_path_nodes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("location_id", sa.String(64), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("map_x", sa.Float(), nullable=True),
            sa.Column("map_y", sa.Float(), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("campus_id", "name", name="uq_campus_path_node_name"),
        )
        op.create_index("ix_campus_path_nodes_campus_id", "campus_path_nodes", ["campus_id"])
        op.create_index("ix_campus_path_nodes_location_id", "campus_path_nodes", ["location_id"])
        op.create_index("ix_campus_path_nodes_name", "campus_path_nodes", ["name"])
        op.create_index("ix_campus_path_nodes_verified", "campus_path_nodes", ["verified"])
    if "campus_path_edges" not in tables:
        op.create_table(
            "campus_path_edges",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False),
            sa.Column("from_node_id", sa.String(36), sa.ForeignKey("campus_path_nodes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("to_node_id", sa.String(36), sa.ForeignKey("campus_path_nodes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("distance_meters", sa.Float(), nullable=True),
            sa.Column("instruction", sa.String(500), nullable=False, server_default=""),
            sa.Column("bidirectional", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("accessible", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_url", sa.String(1000), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("from_node_id", "to_node_id", name="uq_campus_path_edge"),
        )
        for name in ("campus_id", "from_node_id", "to_node_id", "verified"):
            op.create_index(f"ix_campus_path_edges_{name}", "campus_path_edges", [name])
    if "notes" not in tables:
        op.create_table(
            "notes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_notes_user_id", "notes", ["user_id"])
        op.create_index("ix_notes_pinned", "notes", ["pinned"])
        op.create_index("ix_notes_owner_updated", "notes", ["user_id", "updated_at"])
    if "reminders" not in tables:
        op.create_table(
            "reminders",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
            sa.Column("note_id", sa.String(36), sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
            sa.Column("repeat_rule", sa.String(120), nullable=False, server_default=""),
            sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
            sa.Column("channels", sa.JSON(), nullable=False),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        for name in ("user_id", "task_id", "note_id", "remind_at", "status"):
            op.create_index(f"ix_reminders_{name}", "reminders", [name])
        op.create_index("ix_reminders_owner_status_time", "reminders", ["user_id", "status", "remind_at"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("reminders", "notes", "campus_path_edges", "campus_path_nodes", "campus_facts", "campus_colleges"):
        if table in tables:
            op.drop_table(table)
