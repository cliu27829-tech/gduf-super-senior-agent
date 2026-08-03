from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.schemas.agent import NotificationDraft
from app.services.time_service import now_china, parse_relative_datetime


logger = logging.getLogger("gduf-api.notifications")


class ExtractedTask(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    deadline_text: str = Field(default="", max_length=120)
    submission_target: str = Field(default="", max_length=255)
    submission_method: str = Field(default="", max_length=255)
    file_naming: str = Field(default="", max_length=255)
    materials: list[str] = Field(default_factory=list, max_length=50)
    location: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=2000)


class ExtractedTasks(BaseModel):
    tasks: list[ExtractedTask] = Field(min_length=1, max_length=50)


class NotificationService:
    @staticmethod
    def _label(text: str, labels: tuple[str, ...]) -> str:
        match = re.search(rf"(?:{'|'.join(map(re.escape, labels))})\s*[：:]\s*([^\n；;]+)", text, re.I)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _segments(text: str) -> list[str]:
        markers = re.compile(r"(?m)(?=^\s*(?:\d{1,2}[.、）)]|任务[一二三四五六七八九十]+\s*[：:]))")
        parts = [part.strip() for part in markers.split(text) if part.strip()]
        numbered = [part for part in parts if re.match(r"^(?:\d{1,2}[.、）)]|任务[一二三四五六七八九十]+\s*[：:])", part)]
        return numbered if numbered else [text.strip()]

    @staticmethod
    def _submission_target(text: str) -> str:
        match = re.search(r"(?:发送|提交|交|报送|递交)[^，。；;\n]{0,80}?(?:给|至|到)\s*([^，。；;\n]+)", text)
        return match.group(1).strip()[:255] if match else NotificationService._label(text, ("提交对象", "接收人", "报送对象"))

    @staticmethod
    def _submission_method(text: str) -> str:
        labeled = NotificationService._label(text, ("提交方式", "提交渠道", "发送方式", "报送方式"))
        if labeled:
            return re.split(r"[，,]", labeled, maxsplit=1)[0].strip()[:255]
        if re.search(r"发送(?:给|至)", text):
            return "发送"
        if re.search(r"上传(?:至|到)", text):
            return "在线上传"
        if re.search(r"交(?:给|至|到)", text):
            return "线下提交"
        return ""

    @staticmethod
    def _file_naming(text: str) -> str:
        match = re.search(r"(?:文件)?(?:命名|名称)(?:为|格式为|要求为)?\s*([^，。；;\n]+)", text)
        return match.group(1).strip()[:255] if match else ""

    @staticmethod
    def _materials(text: str) -> list[str]:
        labeled = NotificationService._label(text, ("材料", "所需材料", "准备材料", "提交材料"))
        if labeled:
            return [item.strip() for item in re.split(r"[、,，;；]", labeled) if item.strip()][:50]
        match = re.search(r"(?:提交|上传|报送)\s*([^，。；;\n]{2,40})", text)
        if not match:
            return []
        candidate = re.sub(r"(?:给|至|到).*$", "", match.group(1)).strip()
        candidate = re.sub(r"^(?:一份|本人的|个人的)", "", candidate)
        return [candidate[:200]] if candidate else []

    @staticmethod
    def _notes(text: str) -> str:
        labeled = NotificationService._label(text, ("注意事项", "注意", "备注", "要求"))
        if labeled:
            return labeled[:2000]
        sentences = [part.strip() for part in re.split(r"[。；;\n]", text) if re.search(r"注意|务必|不得|请确认", part)]
        return "；".join(sentences)[:2000]

    @staticmethod
    def _title(text: str) -> str:
        action = re.search(r"(?:请[^，。；;\n]{0,16})?(提交|上传|报送|发送|领取|参加|完成)\s*([^，。；;\n]{2,50})", text)
        if action:
            subject = re.sub(r"(?:给|至|到).*$", "", action.group(2)).strip()
            subject = re.sub(r"^(?:于\d{1,2}月\d{1,2}日[^前后]*前)", "", subject).strip()
            if subject:
                return f"{action.group(1)}{subject}"[:80]
        for line in text.splitlines():
            cleaned = re.sub(r"^[\s#>*\-\d.、）)]+", "", line).strip()
            if cleaned:
                return re.split(r"(?:截止|时间|地点|材料|提交方式)\s*[：:]", cleaned)[0][:80]
        return "通知待办"

    def fallback(self, text: str, source_url: str = "", reference_time=None) -> list[NotificationDraft]:
        drafts: list[NotificationDraft] = []
        for segment in self._segments(text):
            inferred = parse_relative_datetime(segment, reference_time)
            materials = self._materials(segment)
            drafts.append(
                NotificationDraft(
                    title=self._title(segment),
                    deadline=inferred.value,
                    location=self._label(segment, ("地点", "办理地点", "上课地点", "提交地点")),
                    materials=materials,
                    submission_target=self._submission_target(segment),
                    submission_method=self._submission_method(segment),
                    file_naming=self._file_naming(segment),
                    notes=self._notes(segment),
                    source_text=text,
                    source_url=source_url,
                    needs_confirmation=inferred.requires_confirmation,
                    confidence=max(0.35, min(0.88, inferred.confidence if inferred.value else 0.35)),
                    date_explanation=inferred.explanation,
                )
            )
        return drafts

    def with_model(self, text: str, source_url: str = "", reference_time=None) -> list[NotificationDraft]:
        settings = get_settings()
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url, timeout=20.0)
        prompt = (
            f"当前中国标准时间：{now_china(reference_time).isoformat()}。"
            "只抽取通知原文存在的一个或多个任务，不补写事实。只输出 JSON 对象。"
            "每个任务字段为 title、deadline_text、submission_target、submission_method、file_naming、materials、location、notes。"
            "deadline_text 必须保留原文时间表达；不确定的字段使用空字符串或空数组。"
        )
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        )
        parsed = ExtractedTasks.model_validate(json.loads(response.choices[0].message.content or "{}"))
        drafts: list[NotificationDraft] = []
        for item in parsed.tasks:
            inferred = parse_relative_datetime(item.deadline_text, reference_time)
            drafts.append(
                NotificationDraft(
                    title=item.title,
                    deadline=inferred.value,
                    location=item.location,
                    materials=item.materials,
                    submission_target=item.submission_target,
                    submission_method=item.submission_method,
                    file_naming=item.file_naming,
                    notes=item.notes,
                    source_text=text,
                    source_url=source_url,
                    needs_confirmation=inferred.requires_confirmation,
                    confidence=max(0.45, min(0.98, inferred.confidence if inferred.value else 0.45)),
                    date_explanation=inferred.explanation,
                )
            )
        return drafts

    def extract(self, text: str, source_url: str = "", reference_time=None) -> tuple[list[NotificationDraft], str, str]:
        if not text.strip():
            return [], "none", "没有可解析的通知内容"
        if get_settings().deepseek_api_key:
            try:
                return self.with_model(text, source_url, reference_time), "llm", ""
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                error_id = uuid4().hex[:12]
                logger.warning("notification_model_invalid error_id=%s error_type=%s", error_id, type(exc).__name__)
            except Exception as exc:
                error_id = uuid4().hex[:12]
                logger.warning("notification_model_unavailable error_id=%s error_type=%s", error_id, type(exc).__name__)
            return self.fallback(text, source_url, reference_time), "rules", f"模型暂不可用或返回格式无效，已使用本地规则降级；请逐项核对。错误编号：{error_id}"
        return self.fallback(text, source_url, reference_time), "rules", "当前未配置服务端模型密钥，已使用本地规则解析；请逐项核对。"
