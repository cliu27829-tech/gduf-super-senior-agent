"""Create the production website schema.

Revision ID: 20260803_01
Revises:
"""
from alembic import op

from app.core.database import Base
from app.models import entities  # noqa: F401


revision = "20260803_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

