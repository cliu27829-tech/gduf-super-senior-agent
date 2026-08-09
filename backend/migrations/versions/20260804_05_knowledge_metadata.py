"""Add structured extraction metadata to knowledge documents.

Revision ID: 20260804_05
Revises: 20260804_04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_05"
down_revision = "20260804_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("knowledge_documents")}
    if "extracted_metadata" not in columns:
        op.add_column(
            "knowledge_documents",
            sa.Column("extracted_metadata", sa.JSON(), nullable=False, server_default="{}"),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("knowledge_documents")}
    if "extracted_metadata" in columns:
        op.drop_column("knowledge_documents", "extracted_metadata")
