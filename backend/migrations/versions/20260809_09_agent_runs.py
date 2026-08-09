"""add durable agent runs and steps

Revision ID: 20260809_09
Revises: 20260809_08
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_09"
down_revision = "20260809_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The repository's initial migration creates tables from current metadata.
    # A brand-new database can therefore already contain these tables by the
    # time Alembic reaches this incremental revision.
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_runs" not in tables:
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("goal", sa.String(length=500), nullable=False),
            sa.Column("intent", sa.String(length=80), nullable=False, server_default="general_chat"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="planning"),
            sa.Column("completion_condition", sa.String(length=500), nullable=False, server_default="向用户返回经过核验的结果"),
            sa.Column("required_input", sa.JSON(), nullable=False),
            sa.Column("context", sa.JSON(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
        op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
        op.create_index("ix_agent_runs_intent", "agent_runs", ["intent"])
        op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
        op.create_index("ix_agent_runs_owner_status_updated", "agent_runs", ["user_id", "status", "updated_at"])
        op.create_index("ix_agent_runs_conversation_updated", "agent_runs", ["conversation_id", "updated_at"])
    if "agent_run_steps" not in tables:
        op.create_table(
            "agent_run_steps",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("run_id", sa.String(length=36), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("step_type", sa.String(length=40), nullable=False, server_default="tool"),
            sa.Column("tool_name", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("public_label", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
            sa.Column("success", sa.Boolean(), nullable=True),
            sa.Column("input_summary", sa.JSON(), nullable=False),
            sa.Column("output_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("run_id", "sequence", name="uq_agent_run_step_sequence"),
        )
        op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])
        op.create_index("ix_agent_run_steps_step_type", "agent_run_steps", ["step_type"])
        op.create_index("ix_agent_run_steps_tool_name", "agent_run_steps", ["tool_name"])
        op.create_index("ix_agent_run_steps_status", "agent_run_steps", ["status"])
        op.create_index("ix_agent_run_steps_started_at", "agent_run_steps", ["started_at"])
        op.create_index("ix_agent_run_steps_run_round", "agent_run_steps", ["run_id", "round_number"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "agent_run_steps" in tables:
        op.drop_table("agent_run_steps")
    if "agent_runs" in tables:
        op.drop_table("agent_runs")
