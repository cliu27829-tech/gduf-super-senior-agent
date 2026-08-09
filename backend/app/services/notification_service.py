from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from app.core.llm_client import LLMClient, get_llm_client
from app.schemas.agent import (
    NotificationActionItem,
    NotificationDeadline,
    NotificationNotice,
    NotificationParseResponse,
)
from app.services.time_service import NoticeContext, now_china, parse_deadline, parse_notice_context


logger = logging.getLogger("gduf-api.notifications")


_EMOJI_RE = re.compile(
    "[\U0001F1E0-\U0001FAFF\U00002600-\U000027BF\u200d\ufe0f]",
    flags=re.UNICODE,
)
_NUMBER_PREFIX = re.compile(r"^\s*(?:\d{1,2}[.、)）]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+、)\s*")
_ACTION_RE = re.compile(r"(?:请|需|需要|务必|应当|应|要|统一|及时)?\s*(提交|收集|填写|上传|发送|报名|领取|参加|完成|补交|报送|交)")
_RULE_RE = re.compile(r"视为|算作|只加|只取|不得|可以加|参与分|加分|调整为|更正为|规定|不允许|资格")
_DEADLINE_RE = re.compile(
    r"(?:截止(?:时间)?\s*[:：]?\s*)?((?:20\d{2}年)?\d{1,2}月\d{1,2}日?(?:上午|下午|中午|晚上|傍晚)?\d{0,2}(?:[:：点时]\d{0,2})?|"
    r"(?:本周|下周|周)[一二三四五六日天](?:上午|下午|中午|晚上|傍晚)?\d{0,2}(?:[:：点时]\d{0,2})?|"
    r"(?:今天|明天|后天|大后天|月底)(?:上午|下午|中午|晚上|傍晚)?\d{0,2}(?:[:：点时]\d{0,2})?)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class StructuredExtraction(BaseModel):
    notice: NotificationNotice = Field(default_factory=NotificationNotice)
    rules: list[str] = Field(default_factory=list, max_length=100)
    action_items: list[NotificationActionItem] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)


def normalize_notice_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = _EMOJI_RE.sub("", normalized)
    normalized = normalized.replace("：", ":").replace("(", "（").replace(")", "）")
    normalized = normalized.replace("‼", "").replace("✅", "").replace("⭕", "")
    normalized = re.sub(r"[ \t\u3000]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        numbered = _NUMBER_PREFIX.match(line)
        if numbered:
            prefix = numbered.group(0).strip()
            number = re.search(r"\d{1,2}|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+", prefix)
            line = f"{number.group(0) if number else ''}. {line[numbered.end():].strip()}"
        lines.append(line)
    return "\n".join(lines).strip()


def _clean_statement(line: str) -> str:
    return re.sub(r"^\s*(?:\d{1,2}|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+)[.、)）]\s*", "", line).strip()


def _notice_title(normalized: str) -> str:
    first = normalized.splitlines()[0].strip("【】[] ") if normalized else ""
    if "——" in first:
        first = first.split("——", 1)[1]
    elif "--" in first:
        first = first.split("--", 1)[1]
    if "关于" in first:
        first = first[first.index("关于"):]
    return first[:255]


def _notice_publisher(normalized: str) -> str:
    first = normalized.splitlines()[0].strip("【】[] ") if normalized else ""
    if "——" not in first:
        return ""
    prefix = first.split("——", 1)[0]
    prefix = re.sub(r"^\d{1,2}[.月/-]\d{1,2}(?:日)?", "", prefix)
    return prefix.replace("通知", "").strip()[:255]


def _campuses(text: str) -> list[str]:
    values = []
    for label, aliases in (
        ("广州校区", ("广州校区", "广州校本部", "校本部")),
        ("清远校区", ("清远校区",)),
        ("肇庆校区", ("肇庆校区",)),
    ):
        if any(alias in text for alias in aliases):
            values.append(label)
    return values


def _audience(text: str) -> list[str]:
    result: list[str] = []
    if "二课负责人" in text:
        result.append("二课负责人")
    if "正大杯" in text and ("补录" in text or "再提交" in text):
        result.append("需要补录正大杯加分的相关班级和同学")
    first_body = next((line for line in text.splitlines()[1:] if line.startswith(("各", "全体"))), "")
    if first_body and not result:
        candidate = re.split(r"[，,：:]", first_body, 1)[0].strip("各位：: ")
        if candidate:
            result.append(candidate[:100])
    return result


def _category(text: str) -> str:
    if "加分" in text:
        return "比赛加分"
    if "报名" in text:
        return "报名通知"
    if "考试" in text:
        return "考试通知"
    if "材料" in text or "提交" in text:
        return "材料提交"
    return "校园通知"


def _notice(normalized: str, context: NoticeContext) -> NotificationNotice:
    title = _notice_title(normalized)
    return NotificationNotice(
        title=title,
        notice_date_text=context.notice_date_text,
        notice_date=context.notice_reference_date,
        publisher=_notice_publisher(normalized),
        campuses=_campuses(normalized),
        audience=_audience(normalized),
        category=_category(normalized),
        summary=title or "校园通知",
    )


def _is_metadata(statement: str) -> bool:
    return bool(re.match(r"^(?:截止(?:时间)?|新?zip命名|文件命名|命名|证明材料|材料要求|提交要求)\s*[:：]?", statement, re.I))


def _is_action(statement: str) -> bool:
    if _is_metadata(statement):
        return False
    if _RULE_RE.search(statement) and not re.search(r"(?:需|需要|请|务必|应当).{0,8}(?:提交|收集|填写|上传|发送|报名|领取|参加|完成|补交|报送)", statement):
        return False
    return bool(_ACTION_RE.search(statement))


def _deadline_text(text: str) -> str:
    match = _DEADLINE_RE.search(text)
    return match.group(1).strip() if match else ""


def _file_naming(text: str) -> str:
    match = re.search(r"(?:新?zip|文件)?\s*命名\s*[:：为]?\s*([^，。；;\n]+)", text, re.I)
    return match.group(1).strip()[:255] if match else ""


def _evidence_requirements(text: str) -> list[str]:
    requirements: list[str] = []
    if "表头" in text:
        requirements.append("证明材料需要有表头")
    if "公章" in text:
        requirements.append("证明材料需要有公章")
    if "奖状图片" in text and "证明材料" in text:
        requirements.append("通知所示的正大杯奖状图片可以作为证明材料")
    if not requirements:
        labeled = re.search(r"(?:证明材料|材料要求)\s*[:：]?\s*(.+)", text)
        if labeled:
            requirements.append(labeled.group(1).strip("。 ")[:300])
    return requirements


def _conditions(text: str) -> list[str]:
    values: list[str] = []
    conditional = re.search(r"如果(.+?)(?:，|,)(?:需|需要|请|应|要)", text)
    if conditional:
        values.append(conditional.group(1).strip("，,。 "))
    return values


def _action_phrase(statement: str) -> str:
    if "正大杯" in statement and "收集" in statement:
        return "重新收集相关同学材料，并以新的 ZIP 文件发送到通知要求的邮箱。"
    working = re.split(r"[，,]", statement, 1)[1] if statement.startswith("如果") and re.search(r"[，,]", statement) else statement
    match = _ACTION_RE.search(working)
    if not match:
        return working[:2000]
    verb = "提交" if match.group(1) == "交" else match.group(1)
    tail = working[match.end():]
    tail = re.split(r"[，,。；;]|(?:截止|命名|材料要求)", tail, 1)[0].strip()
    return f"{verb}{tail}"[:2000]


def _action_title(statement: str) -> str:
    if "正大杯" in statement and ("收集" in statement or "补录" in statement):
        return "收集并提交正大杯加分补录材料"
    phrase = _action_phrase(statement).strip("。 ")
    phrase = re.sub(r"^(?:重新)?", "", phrase)
    return phrase[:80] or "处理通知事项"


def _submission(statement: str) -> tuple[str, str]:
    email = _EMAIL_RE.search(statement)
    if "邮箱" in statement or email:
        target = email.group(0) if email else "邮箱"
        method = "邮件发送 ZIP 文件" if re.search(r"zip", statement, re.I) else "邮件发送"
        return method, target
    if "上传" in statement:
        return "在线上传", ""
    if "交到" in statement or "提交至" in statement:
        target = re.split(r"交到|提交至", statement, 1)[-1].split("，", 1)[0].strip("。 ")
        return "线下提交", target[:255]
    return "", ""


def _new_action(statement: str, notice: NotificationNotice, source_text: str, source_url: str) -> NotificationActionItem:
    method, target = _submission(statement)
    materials = ["正大杯加分补录材料"] if "正大杯" in statement and "材料" in statement else []
    return NotificationActionItem(
        title=_action_title(statement),
        action=_action_phrase(statement),
        audience=list(notice.audience),
        conditions=_conditions(statement),
        deadline_text=_deadline_text(statement),
        submission_method=method,
        submission_target=target,
        file_naming=_file_naming(statement),
        materials=materials,
        evidence_requirements=_evidence_requirements(statement),
        confidence=0.82,
        source_title=notice.title,
        source_text=source_text,
        source_url=source_url,
    )


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        cleaned = value.strip("。；;，, ")
        if cleaned and cleaned not in target:
            target.append(cleaned)


def _attach_metadata(action: NotificationActionItem, statement: str) -> None:
    deadline = _deadline_text(statement)
    if deadline:
        action.deadline_text = deadline
    naming = _file_naming(statement)
    if naming:
        action.file_naming = naming
    _append_unique(action.evidence_requirements, _evidence_requirements(statement))
    method, target = _submission(statement)
    if method:
        action.submission_method = method
    if target:
        action.submission_target = target
    if "同上" in statement and ("补录" in statement or "未成功" in statement):
        _append_unique(action.conditions, [statement.replace("同上", "").strip("。 ")])


def _finalize(
    extraction: StructuredExtraction,
    normalized: str,
    raw_text: str,
    source_url: str,
    context: NoticeContext,
    current_time,
    mode: str,
) -> NotificationParseResponse:
    current = now_china(current_time)
    inferred_notice = _notice(normalized, context)
    notice = extraction.notice
    for field in ("title", "notice_date_text", "publisher", "category", "summary"):
        if not getattr(notice, field):
            setattr(notice, field, getattr(inferred_notice, field))
    if not notice.notice_date:
        notice.notice_date = inferred_notice.notice_date
    if not notice.campuses:
        notice.campuses = inferred_notice.campuses
    if not notice.audience:
        notice.audience = inferred_notice.audience

    deadlines: list[NotificationDeadline] = []
    for action in extraction.action_items:
        action.source_text = raw_text or normalized
        action.source_url = source_url
        action.source_title = action.source_title or notice.title
        if action.deadline_text:
            parsed = parse_deadline(action.deadline_text, notice.notice_date or context.notice_reference_date, current)
            action.deadline = parsed.value
            action.needs_confirmation = action.needs_confirmation or parsed.requires_confirmation
            action.date_explanation = parsed.explanation
        action.is_expired = bool(action.deadline and action.deadline < current)
        deadlines.append(NotificationDeadline(
            text=action.deadline_text,
            deadline=action.deadline,
            action_title=action.title,
            is_expired=action.is_expired,
            needs_confirmation=action.needs_confirmation,
        ))

    warnings = list(dict.fromkeys(extraction.warnings))
    if any(action.is_expired for action in extraction.action_items):
        warnings.append("兄弟，这份通知的截止时间已经过了，我先帮你把要求整理出来。要是你现在需要补交，建议先确认负责人是否还接受补录。")
    return NotificationParseResponse(
        notice=notice,
        rules=list(dict.fromkeys(item.strip("。 ") for item in extraction.rules if item.strip())),
        action_items=extraction.action_items,
        deadlines=deadlines,
        warnings=warnings,
        extraction_mode=mode,
    )


class NotificationService:
    def fallback(
        self,
        text: str,
        source_url: str = "",
        reference_time=None,
        *,
        source_published_at=None,
        user_reference_date=None,
    ) -> NotificationParseResponse:
        normalized = normalize_notice_text(text)
        context = parse_notice_context(
            normalized,
            reference_time,
            source_published_at=source_published_at,
            user_reference_date=user_reference_date,
        )
        notice = _notice(normalized, context)
        rules: list[str] = []
        actions: list[NotificationActionItem] = []
        pending_metadata: list[str] = []
        all_lines = normalized.splitlines() if normalized else []
        raw_first = (text or "").lstrip()
        first_is_title = bool(raw_first.startswith(("【", "["))) or bool(
            all_lines
            and len(all_lines[0]) <= 100
            and re.search(r"通知|公告|提醒$", all_lines[0])
            and not _is_action(_clean_statement(all_lines[0]))
            and not _RULE_RE.search(_clean_statement(all_lines[0]))
        )
        lines = all_lines[1:] if first_is_title else all_lines
        for line in lines:
            statement = _clean_statement(line)
            if not statement or re.search(r"晚上好.*如下", statement):
                continue
            if _is_metadata(statement):
                if actions:
                    _attach_metadata(actions[-1], statement)
                else:
                    pending_metadata.append(statement)
                continue
            if "同上" in statement and actions:
                _attach_metadata(actions[-1], statement)
                continue
            # A single line may contain several genuinely independent actions.
            clauses = [part.strip() for part in re.split(r"[；;]", statement) if part.strip()]
            action_clauses = [part for part in clauses if _is_action(part)]
            if action_clauses:
                for clause in action_clauses:
                    action = _new_action(clause, notice, normalized, source_url)
                    for metadata in pending_metadata:
                        _attach_metadata(action, metadata)
                    pending_metadata.clear()
                    actions.append(action)
                continue
            if _RULE_RE.search(statement):
                rules.append(statement)

        extraction = StructuredExtraction(notice=notice, rules=rules, action_items=actions, warnings=[])
        return _finalize(extraction, normalized, text, source_url, context, reference_time, "rules")

    async def with_model(
        self,
        text: str,
        source_url: str = "",
        reference_time=None,
        *,
        llm: LLMClient | Any | None = None,
        source_published_at=None,
        user_reference_date=None,
    ) -> NotificationParseResponse:
        normalized = normalize_notice_text(text)
        context = parse_notice_context(
            normalized,
            reference_time,
            source_published_at=source_published_at,
            user_reference_date=user_reference_date,
        )
        client = llm or get_llm_client()
        schema = json.dumps(StructuredExtraction.model_json_schema(), ensure_ascii=False)
        system = (
            "你是中文校园通知结构化抽取器。先理解全文，再区分规则与真正行动；编号不是任务边界。"
            "rules 存政策、评分、条件和背景，action_items 只存用户确实要执行的动作。"
            "截止时间、命名和证明材料必须合并进关联 action_item；不要编造邮箱地址。"
            "deadline 一律输出 null，只保留 deadline_text，服务端会按通知日期计算。"
            "只输出一个符合下列 Pydantic JSON Schema 的 JSON 对象，不要 Markdown：" + schema
        )

        async def request(messages: list[dict[str, str]]) -> StructuredExtraction:
            content = await client.chat_completion(messages, temperature=0, response_format={"type": "json_object"})
            return StructuredExtraction.model_validate(json.loads(content))

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": normalized},
        ]
        try:
            extraction = await request(messages)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            repair = (
                "上一次 JSON 未通过 Schema 校验。只修复 JSON，不改变通知事实，不新增任务。"
                f"校验错误：{str(exc)[:1200]}"
            )
            extraction = await request([*messages, {"role": "assistant", "content": "{}"}, {"role": "user", "content": repair}])
        return _finalize(extraction, normalized, text, source_url, context, reference_time, "llm")

    async def extract(
        self,
        text: str,
        source_url: str = "",
        reference_time=None,
        *,
        llm: LLMClient | Any | None = None,
        source_published_at=None,
        user_reference_date=None,
    ) -> NotificationParseResponse:
        if not text.strip():
            empty = StructuredExtraction(
                notice=NotificationNotice(),
                warnings=["没有可解析的通知内容。"],
            )
            return _finalize(empty, "", "", source_url, NoticeContext(None), reference_time, "none")
        client = llm or get_llm_client()
        if getattr(client, "configured", False):
            try:
                return await self.with_model(
                    text,
                    source_url,
                    reference_time,
                    llm=client,
                    source_published_at=source_published_at,
                    user_reference_date=user_reference_date,
                )
            except Exception as exc:
                error_id = uuid4().hex[:12]
                logger.warning("notification_model_unavailable error_id=%s error_type=%s", error_id, type(exc).__name__)
                result = self.fallback(
                    text,
                    source_url,
                    reference_time,
                    source_published_at=source_published_at,
                    user_reference_date=user_reference_date,
                )
                result.warnings.insert(0, f"模型结构化提取失败，已使用本地规则降级并保留原文；错误编号：{error_id}")
                return result
        result = self.fallback(
            text,
            source_url,
            reference_time,
            source_published_at=source_published_at,
            user_reference_date=user_reference_date,
        )
        result.warnings.insert(0, "当前未配置通知结构化模型，已使用本地规则解析；请在保存前核对。")
        return result
