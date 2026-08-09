from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import AgentRun, AgentRunStep, Conversation, User


RUN_STATUSES = {
    "planning",
    "waiting_for_location",
    "waiting_for_confirmation",
    "waiting_for_user_input",
    "executing",
    "verifying",
    "completed",
    "failed",
}


def public_step(step: AgentRunStep) -> dict[str, Any]:
    return {
        "id": step.id,
        "sequence": step.sequence,
        "round_number": step.round_number,
        "step_type": step.step_type,
        "tool_name": step.tool_name,
        "public_label": step.public_label,
        "status": step.status,
        "success": step.success,
        "output_summary": step.output_summary,
        "started_at": step.started_at,
        "completed_at": step.completed_at,
    }


def public_run(run: AgentRun, include_steps: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": run.id,
        "conversation_id": run.conversation_id,
        "goal": run.goal,
        "intent": run.intent,
        "status": run.status,
        "completion_condition": run.completion_condition,
        "required_input": run.required_input,
        "summary": run.summary,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "updated_at": run.updated_at,
    }
    if include_steps:
        payload["steps"] = [public_step(step) for step in run.steps]
    return payload


class AgentRunStore:
    def __init__(self, db: Session):
        self.db = db

    def create_or_resume(
        self,
        user: User,
        conversation: Conversation,
        goal: str,
        *,
        run_id: str | None = None,
        intent: str = "general_chat",
        completion_condition: str = "向用户返回经过核验的结果",
        context: dict[str, Any] | None = None,
    ) -> AgentRun:
        if run_id:
            run = self.db.scalar(
                select(AgentRun)
                .options(selectinload(AgentRun.steps))
                .where(AgentRun.id == run_id, AgentRun.user_id == user.id)
            )
            if not run:
                raise HTTPException(status_code=404, detail="Agent 执行不存在")
            if run.conversation_id != conversation.id:
                raise HTTPException(status_code=409, detail="Agent 执行与当前对话不匹配")
            if run.status in {"completed", "failed"}:
                raise HTTPException(status_code=409, detail="该 Agent 执行已经结束，请发起新请求")
            return run
        run = AgentRun(
            user_id=user.id,
            conversation_id=conversation.id,
            goal=goal[:500],
            intent=intent,
            status="planning",
            completion_condition=completion_condition[:500],
            context_data=self._safe_context(context or {}),
            required_input=[],
        )
        self.db.add(run)
        self.db.flush()
        return run

    @staticmethod
    def _safe_context(value: dict[str, Any]) -> dict[str, Any]:
        allowed = {"campus_id", "destination_location_id", "origin_location_id", "conversation_id"}
        return {key: item for key, item in value.items() if key in allowed and isinstance(item, (str, int, bool, type(None)))}

    def transition(
        self,
        run: AgentRun,
        status: str,
        *,
        required_input: list[dict[str, Any]] | None = None,
        summary: str | None = None,
    ) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"invalid Agent run status: {status}")
        run.status = status
        if required_input is not None:
            run.required_input = required_input
        if summary is not None:
            run.summary = summary[:4000]
        if status in {"completed", "failed"}:
            run.completed_at = datetime.now(UTC)
        self.db.flush()

    def start_step(
        self,
        run: AgentRun,
        *,
        step_type: str,
        public_label: str,
        tool_name: str = "",
        round_number: int = 1,
        input_summary: dict[str, Any] | None = None,
    ) -> AgentRunStep:
        sequence = int(self.db.scalar(select(func.count()).select_from(AgentRunStep).where(AgentRunStep.run_id == run.id)) or 0) + 1
        step = AgentRunStep(
            run_id=run.id,
            sequence=sequence,
            round_number=round_number,
            step_type=step_type,
            tool_name=tool_name,
            public_label=public_label[:255],
            status="running",
            input_summary=self._safe_context(input_summary or {}),
        )
        self.db.add(step)
        self.db.flush()
        return step

    def finish_step(self, step: AgentRunStep, success: bool, summary: str = "") -> None:
        step.success = success
        step.status = "completed" if success else "failed"
        step.output_summary = summary[:4000]
        step.completed_at = datetime.now(UTC)
        self.db.flush()
