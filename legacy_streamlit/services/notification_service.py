"""Notification extraction that never creates tasks before user confirmation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any

from openai import OpenAI

from core.time_service import (
    DateInference,
    format_current_time_prompt,
    parse_relative_datetime,
)


@dataclass
class NotificationDraft:
    title: str
    deadline: str | None
    location: str = ""
    materials: list[str] = field(default_factory=list)
    submission_method: str = ""
    source_text: str = ""
    source_url: str = ""
    needs_confirmation: bool = False
    confidence: float = 0.0
    date_explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotificationService:
    def __init__(self, base_url: str = "https://api.deepseek.com/v1", model: str = "deepseek-chat"):
        self.base_url = base_url
        self.model = model

    @staticmethod
    def _extract_label(text: str, labels: tuple[str, ...]) -> str:
        label_pattern = "|".join(re.escape(label) for label in labels)
        match = re.search(
            rf"(?:{label_pattern})\s*[：:]\s*([^\n；;]+)",
            text,
            flags=re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _fallback_title(text: str) -> str:
        for line in text.splitlines():
            cleaned = re.sub(r"^[\s#>*\-\d.、]+", "", line).strip()
            if not cleaned:
                continue
            cleaned = re.split(r"(?:截止|时间|地点|材料|提交方式)\s*[：:]", cleaned)[0].strip()
            if cleaned:
                return cleaned[:80]
        return "通知待办"

    def extract_fallback(self, text: str, reference_time=None, source_url: str = "") -> list[NotificationDraft]:
        date_inference = parse_relative_datetime(text, reference_time)
        location = self._extract_label(text, ("地点", "办理地点", "上课地点"))
        submission = self._extract_label(text, ("提交方式", "提交渠道", "发送至", "交至"))
        material_text = self._extract_label(text, ("材料", "所需材料", "准备材料", "提交材料"))
        materials = [
            item.strip(" ，,、；;")
            for item in re.split(r"[、,，;；]", material_text)
            if item.strip(" ，,、；;")
        ]
        return [
            NotificationDraft(
                title=self._fallback_title(text),
                deadline=date_inference.isoformat(),
                location=location,
                materials=materials,
                submission_method=submission,
                source_text=text,
                source_url=source_url,
                needs_confirmation=date_inference.requires_confirmation,
                confidence=max(0.35, date_inference.confidence),
                date_explanation=date_inference.explanation,
            )
        ]

    def extract_with_model(
        self,
        text: str,
        api_key: str,
        reference_time=None,
        source_url: str = "",
    ) -> list[NotificationDraft]:
        prompt = (
            format_current_time_prompt(reference_time)
            + "\n请从通知中抽取任务。仅输出 JSON 数组，每项包含 title、deadline_text、"
            "location、materials（数组）、submission_method。不要补写通知未出现的事实。"
        )
        client = OpenAI(api_key=api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        raw = response.choices[0].message.content or "[]"
        match = re.search(r"\[[\s\S]*\]", raw)
        items = json.loads(match.group(0) if match else raw)
        drafts = []
        for item in items:
            date_text = str(item.get("deadline_text") or "")
            inferred: DateInference = parse_relative_datetime(date_text, reference_time)
            drafts.append(
                NotificationDraft(
                    title=str(item.get("title") or "通知待办")[:100],
                    deadline=inferred.isoformat(),
                    location=str(item.get("location") or ""),
                    materials=list(item.get("materials") or []),
                    submission_method=str(item.get("submission_method") or ""),
                    source_text=text,
                    source_url=source_url,
                    needs_confirmation=inferred.requires_confirmation,
                    confidence=inferred.confidence,
                    date_explanation=inferred.explanation,
                )
            )
        return drafts or self.extract_fallback(text, reference_time, source_url)

    def extract(
        self,
        text: str,
        api_key: str = "",
        reference_time=None,
        source_url: str = "",
    ) -> list[NotificationDraft]:
        if not text or not text.strip():
            return []
        if api_key:
            try:
                return self.extract_with_model(text, api_key, reference_time, source_url)
            except Exception:
                pass
        return self.extract_fallback(text, reference_time, source_url)
