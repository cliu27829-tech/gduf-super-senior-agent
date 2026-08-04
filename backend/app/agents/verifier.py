from __future__ import annotations

from app.agents.contracts import AgentPlan, Observation, ToolResponse, VerificationReport


TRUSTED = {"official", "verified", "admin_verified", "user_verified", "current"}


class Verifier:
    def verify(self, observation: Observation, plan: AgentPlan, tools: list[ToolResponse]) -> VerificationReport:
        success = all(item.success for item in tools)
        campus_ok = True
        freshness_values: list[str] = []
        for tool in tools:
            rows = tool.data if isinstance(tool.data, list) else [tool.data] if isinstance(tool.data, dict) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                campus = row.get("campus_id")
                if campus and observation.campus_id and campus != observation.campus_id:
                    campus_ok = False
                status = row.get("data_status") or row.get("freshness_status")
                if status:
                    freshness_values.append(str(status))
        nonempty = not tools or any(item.data not in (None, [], {}) for item in tools)
        warnings: list[str] = []
        if not campus_ok:
            warnings.append("工具结果包含错误校区数据，已禁止作为回答依据")
        if tools and not nonempty:
            warnings.append("工具没有返回匹配数据")
        if plan.intent == "campus_navigation" and not any(
            item.tool_name == "calculate_walking_route" and item.success for item in tools
        ):
            warnings.append("没有获得真实步行路线，不能生成路线描述")
        data_status = (
            "verified" if freshness_values and all(value in TRUSTED for value in freshness_values)
            else "needs_verification" if tools else "not_applicable"
        )
        return VerificationReport(
            valid=success and campus_ok,
            checks={"tools_succeeded": success, "campus_isolated": campus_ok, "result_nonempty": nonempty},
            warnings=warnings,
            data_status=data_status,
        )
