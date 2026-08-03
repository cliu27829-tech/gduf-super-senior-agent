from __future__ import annotations

import json
import re

from openai import OpenAI

from app.core.config import get_settings
from app.schemas.agent import NotificationDraft
from app.services.time_service import now_china, parse_relative_datetime


class NotificationService:
    @staticmethod
    def _label(text: str, labels: tuple[str, ...]) -> str:
        match = re.search(rf"(?:{'|'.join(map(re.escape, labels))})\s*[：:]\s*([^\n；;]+)", text, re.I)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _title(text: str) -> str:
        for line in text.splitlines():
            cleaned = re.sub(r"^[\s#>*\-\d.、]+", "", line).strip()
            if cleaned:
                return re.split(r"(?:截止|时间|地点|材料|提交方式)\s*[：:]", cleaned)[0][:80]
        return "通知待办"

    def fallback(self, text: str, source_url: str = "", reference_time=None) -> list[NotificationDraft]:
        inferred = parse_relative_datetime(text, reference_time)
        material_text = self._label(text, ("材料", "所需材料", "准备材料", "提交材料"))
        materials = [item.strip() for item in re.split(r"[、,，;；]", material_text) if item.strip()]
        return [
            NotificationDraft(
                title=self._title(text),
                deadline=inferred.value,
                location=self._label(text, ("地点", "办理地点", "上课地点")),
                materials=materials,
                submission_method=self._label(text, ("提交方式", "提交渠道", "发送至", "交至")),
                source_text=text,
                source_url=source_url,
                needs_confirmation=inferred.requires_confirmation,
                confidence=max(0.35, inferred.confidence),
                date_explanation=inferred.explanation,
            )
        ]

    def with_model(self, text: str, source_url: str = "", reference_time=None) -> list[NotificationDraft]:
        settings = get_settings()
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
        prompt = (
            f"当前中国标准时间：{now_china(reference_time).isoformat()}。"
            "只抽取通知原文存在的任务，不补写事实。输出 JSON 对象，格式为 "
            '{"tasks":[{"title":"","deadline_text":"","location":"","materials":[],"submission_method":""}]}。'
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        drafts: list[NotificationDraft] = []
        for item in parsed.get("tasks", []):
            inferred = parse_relative_datetime(str(item.get("deadline_text") or ""), reference_time)
            drafts.append(
                NotificationDraft(
                    title=str(item.get("title") or "通知待办")[:180],
                    deadline=inferred.value,
                    location=str(item.get("location") or "")[:255],
                    materials=[str(value)[:200] for value in item.get("materials", [])][:50],
                    submission_method=str(item.get("submission_method") or "")[:255],
                    source_text=text,
                    source_url=source_url,
                    needs_confirmation=inferred.requires_confirmation,
                    confidence=inferred.confidence,
                    date_explanation=inferred.explanation,
                )
            )
        return drafts or self.fallback(text, source_url, reference_time)

    def extract(self, text: str, source_url: str = "", reference_time=None) -> tuple[list[NotificationDraft], str, str]:
        if not text.strip():
            return [], "none", "没有可解析的通知内容"
        if get_settings().deepseek_api_key:
            try:
                return self.with_model(text, source_url, reference_time), "llm", ""
            except Exception:
                return self.fallback(text, source_url, reference_time), "rules", "模型暂不可用，已使用本地规则降级；请重点核对日期。"
        return self.fallback(text, source_url, reference_time), "rules", "当前未配置服务端模型密钥，已使用本地规则解析；请核对结果。"

