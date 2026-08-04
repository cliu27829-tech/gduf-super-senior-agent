"""Add Agent platform preferences, knowledge, uploads, and process metadata.

Revision ID: 20260804_03
Revises: 20260804_02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_03"
down_revision = "20260804_02"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "user_preferences" not in tables:
        op.create_table(
            "user_preferences",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("preferred_name", sa.String(80), nullable=False, server_default=""),
            sa.Column("address_style", sa.String(30), nullable=False, server_default="同学"),
            sa.Column("preferred_location_id", sa.String(64), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
            sa.Column("accessibility_notes", sa.String(500), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("user_id"),
        )
        op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)

    process_columns = _columns("campus_processes")
    for name, column in (
        ("audience", sa.Column("audience", sa.String(255), nullable=False, server_default="")),
        ("location", sa.Column("location", sa.String(500), nullable=False, server_default="")),
        ("opening_hours", sa.Column("opening_hours", sa.String(255), nullable=False, server_default="")),
        ("online_url", sa.Column("online_url", sa.String(1000), nullable=False, server_default="")),
        ("notes", sa.Column("notes", sa.Text(), nullable=False, server_default="")),
        ("confidence", sa.Column("confidence", sa.Float(), nullable=False, server_default="0")),
        ("data_status", sa.Column("data_status", sa.String(40), nullable=False, server_default="needs_verification")),
    ):
        if name not in process_columns:
            op.add_column("campus_processes", column)
    if "data_status" not in process_columns:
        op.create_index("ix_campus_processes_data_status", "campus_processes", ["data_status"])

    if "knowledge_documents" not in tables:
        op.create_table(
            "knowledge_documents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("publisher", sa.String(255), nullable=False, server_default=""),
            sa.Column("url", sa.String(1000), nullable=False, server_default=""),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("data_status", sa.String(40), nullable=False, server_default="needs_verification"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"])
        op.create_index("ix_knowledge_campus_status", "knowledge_documents", ["campus_id", "data_status", "is_active"])

    if "uploaded_documents" not in tables:
        op.create_table(
            "uploaded_documents",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("original_filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False, server_default=""),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
            sa.Column("extraction_status", sa.String(30), nullable=False, server_default="parsed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_uploaded_documents_user_id", "uploaded_documents", ["user_id"])
        op.create_index("ix_uploaded_documents_created_at", "uploaded_documents", ["created_at"])

    if "tool_executions" not in tables:
        op.create_table(
            "tool_executions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("verification", sa.JSON(), nullable=False),
            sa.Column("error_code", sa.String(80), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_tool_executions_conversation_id", "tool_executions", ["conversation_id"])
        op.create_index("ix_tool_executions_tool_name", "tool_executions", ["tool_name"])
        op.create_index("ix_tool_executions_created_at", "tool_executions", ["created_at"])
        op.create_index("ix_tool_execution_conversation_created", "tool_executions", ["conversation_id", "created_at"])


def downgrade() -> None:
    tables = _tables()
    for table in ("tool_executions", "uploaded_documents", "knowledge_documents", "user_preferences"):
        if table in tables:
            op.drop_table(table)
    process_columns = _columns("campus_processes")
    for name in ("data_status", "confidence", "notes", "online_url", "opening_hours", "location", "audience"):
        if name in process_columns:
            if name == "data_status":
                op.drop_index("ix_campus_processes_data_status", table_name="campus_processes")
            op.drop_column("campus_processes", name)
