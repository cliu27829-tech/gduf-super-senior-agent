"""Add user-private knowledge imports, chunks, and jobs.

Revision ID: 20260804_04
Revises: 20260804_03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_04"
down_revision = "20260804_03"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    columns = _columns("knowledge_documents")
    additions = (
        ("owner_user_id", sa.Column("owner_user_id", sa.String(36), nullable=True)),
        ("visibility", sa.Column("visibility", sa.String(20), nullable=False, server_default="public")),
        ("review_status", sa.Column("review_status", sa.String(30), nullable=False, server_default="not_required")),
        ("source_type", sa.Column("source_type", sa.String(40), nullable=False, server_default="manual")),
        ("original_filename", sa.Column("original_filename", sa.String(255), nullable=False, server_default="")),
        ("content_hash", sa.Column("content_hash", sa.String(64), nullable=False, server_default="")),
        ("chunk_count", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")),
    )
    for name, column in additions:
        if name not in columns:
            op.add_column("knowledge_documents", column)

    inspector = sa.inspect(op.get_bind())
    foreign_keys = {key.get("name") for key in inspector.get_foreign_keys("knowledge_documents")}
    owner_foreign_key = "fk_knowledge_documents_owner_user_id_users"
    if op.get_bind().dialect.name != "sqlite" and owner_foreign_key not in foreign_keys:
        op.create_foreign_key(
            owner_foreign_key,
            "knowledge_documents",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("knowledge_documents")}
    for name, fields in (
        ("ix_knowledge_documents_owner_user_id", ["owner_user_id"]),
        ("ix_knowledge_documents_visibility", ["visibility"]),
        ("ix_knowledge_documents_review_status", ["review_status"]),
        ("ix_knowledge_documents_content_hash", ["content_hash"]),
        ("ix_knowledge_owner_visibility", ["owner_user_id", "visibility", "is_active"]),
        ("ix_knowledge_owner_hash", ["owner_user_id", "content_hash"]),
    ):
        if name not in indexes:
            op.create_index(name, "knowledge_documents", fields)

    if "knowledge_chunks" not in tables:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
            sa.Column("campus_id", sa.String(36), sa.ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_position"),
        )
        op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])
        op.create_index("ix_knowledge_chunks_owner_user_id", "knowledge_chunks", ["owner_user_id"])
        op.create_index("ix_knowledge_chunks_campus_id", "knowledge_chunks", ["campus_id"])
        op.create_index("ix_knowledge_chunks_created_at", "knowledge_chunks", ["created_at"])
        op.create_index("ix_knowledge_chunk_owner_document", "knowledge_chunks", ["owner_user_id", "document_id"])

    if "knowledge_import_jobs" not in tables:
        op.create_table(
            "knowledge_import_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_label", sa.String(255), nullable=False, server_default=""),
            sa.Column("status", sa.String(30), nullable=False, server_default="running"),
            sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_knowledge_import_jobs_user_id", "knowledge_import_jobs", ["user_id"])
        op.create_index("ix_knowledge_import_jobs_status", "knowledge_import_jobs", ["status"])


def downgrade() -> None:
    tables = _tables()
    if "knowledge_import_jobs" in tables:
        op.drop_table("knowledge_import_jobs")
    if "knowledge_chunks" in tables:
        op.drop_table("knowledge_chunks")
    columns = _columns("knowledge_documents")
    for name in ("chunk_count", "content_hash", "original_filename", "source_type", "review_status", "visibility", "owner_user_id"):
        if name in columns:
            op.drop_column("knowledge_documents", name)
