from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IntentDecision(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    query: str = ""
    tool_plan: list[str] = Field(default_factory=list)


class AgentPlanStep(BaseModel):
    tool: str
    purpose: str
    reason: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    required_input: list[str] = Field(default_factory=list)
    requires_user_action: bool = False


class AgentPlan(BaseModel):
    intent: str
    goal: str
    steps: list[AgentPlanStep] = Field(default_factory=list, max_length=6)
    required_tools: list[str] = Field(default_factory=list, max_length=6)
    requires_knowledge: bool = False
    requires_confirmation: bool = False
    missing_information: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    risks: list[str] = Field(default_factory=list)
    agent_round: int = Field(default=1, ge=1, le=6)
    completion_condition: str = "向用户返回经过核验的结果"


class Observation(BaseModel):
    user_id: str
    campus_id: str | None
    campus_name: str
    current_time: datetime
    history: list[dict[str, str]] = Field(default_factory=list)
    pending_tasks: list[dict[str, Any]] = Field(default_factory=list)
    preferred_address: str
    preferred_location_id: str | None = None


class ToolResponse(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    summary: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    requires_user_action: bool = False


class VerificationReport(BaseModel):
    valid: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    data_status: str = "not_applicable"
