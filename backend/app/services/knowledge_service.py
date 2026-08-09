from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO, StringIO
import csv
import ipaddress
import json
import math
import re
import socket
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import httpx
from pypdf import PdfReader
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import KnowledgeChunk, KnowledgeDocument, KnowledgeImportJob, utcnow


SUPPORTED_EXTENSIONS = {".md", ".txt", ".html", ".htm", ".mhtml", ".pdf", ".docx", ".json", ".csv"}
MAX_EXTRACTED_CHARACTERS = 2_000_000


class KnowledgeImportError(ValueError):
    pass


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignored = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        elif tag.lower() in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        elif tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)


@dataclass(slots=True)
class ImportOutcome:
    document: KnowledgeDocument | None
    duplicate: bool


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _html_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    return "".join(parser.parts)


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\x00", "")
    value = re.sub(r"^---\s.*?\s---\s*", "", value, flags=re.DOTALL)
    value = re.sub(r"!\[[^\]]*]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"<https?://[^>]+>", "", value)
    value = re.sub(r"[\t\f\v ]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    boilerplate = ("在小说阅读器读本章", "去阅读", "阅读原文", "长按识别二维码", "点击关注", "关注我们")
    cleaned_lines: list[str] = []
    seen_lines: set[str] = set()
    for line in value.splitlines():
        normalized = line.strip()
        if normalized and any(marker in normalized for marker in boilerplate):
            continue
        signature = re.sub(r"\s+", "", normalized)
        if len(signature) >= 8 and signature in seen_lines:
            continue
        if signature:
            seen_lines.add(signature)
        cleaned_lines.append(normalized)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()[:MAX_EXTRACTED_CHARACTERS]


def extract_structured_metadata(
    content: str,
    *,
    title: str,
    publisher: str = "",
    url: str = "",
) -> dict:
    lines = [line.strip(" #_*\t") for line in content.splitlines() if line.strip(" #_*\t")]
    date_pattern = r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日(?:\s*[上下]午?\s*\d{1,2}(?::\d{2})?)?"
    dates = list(dict.fromkeys(re.findall(date_pattern, content)))[:20]
    inferred_publisher = publisher.strip()
    if not inferred_publisher:
        inferred_publisher = next(("好人师兄" for line in lines[:8] if "好人师兄" in line), "")

    def matching(*markers: str, limit: int = 12) -> list[str]:
        return list(dict.fromkeys(line[:500] for line in lines if any(marker in line for marker in markers)))[:limit]

    return {
        "title": title.strip()[:255],
        "publisher": inferred_publisher[:255],
        "source_url": url.strip()[:1000],
        "dates": dates,
        "deadlines": matching("截止", "报名时间", "提交时间", "两天内", "三天后"),
        "activity_times": matching("活动时间", "考试时间", "开放时间", "举行时间"),
        "locations": matching("地点", "校区", "办理地址", "报到地点"),
        "materials": matching("材料", "证件", "申请表", "成绩单"),
        "submission": matching("提交方式", "提交对象", "文件命名", "发送至"),
        "contacts": matching("联系电话", "联系方式", "咨询电话"),
        "steps": matching("第一步", "第二步", "办理流程", "操作步骤"),
        "audience": matching("适用对象", "报名对象", "面向", "新生"),
        "learning_resources": matching("学习资料", "课程", "考试", "教材"),
        "canteen_clues": matching("饭堂", "食堂", "档口", "餐品"),
        "location_clues": matching("教学楼", "宿舍", "图书馆", "快递", "医务室"),
        "policy_changes": matching("调整", "变更", "最新通知", "以官方通知为准"),
        "extraction_status": "machine_extracted_needs_review",
    }


def extract_document(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise KnowledgeImportError(f"不支持的文件格式：{extension or '无扩展名'}")
    try:
        if extension in {".md", ".txt"}:
            raw = _decode(data)
        elif extension in {".html", ".htm"}:
            raw = _html_text(_decode(data))
        elif extension == ".mhtml":
            message = BytesParser(policy=policy.default).parsebytes(data)
            preferred = message.get_body(preferencelist=("html", "plain")) if message.is_multipart() else message
            payload = preferred.get_content() if preferred else ""
            raw = _html_text(str(payload)) if preferred and preferred.get_content_type() == "text/html" else str(payload)
        elif extension == ".pdf":
            raw = "\n\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
        elif extension == ".docx":
            with ZipFile(BytesIO(data)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            paragraphs: list[str] = []
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for paragraph in root.iter(f"{namespace}p"):
                text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
                if text.strip():
                    paragraphs.append(text)
            raw = "\n".join(paragraphs)
        elif extension == ".json":
            parsed = json.loads(_decode(data))
            raw = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:
            decoded = _decode(data)
            raw = "\n".join(" | ".join(row) for row in csv.reader(StringIO(decoded)))
    except (BadZipFile, ElementTree.ParseError, json.JSONDecodeError, OSError, ValueError) as exc:
        raise KnowledgeImportError(f"无法解析文件：{type(exc).__name__}") from exc
    cleaned = clean_text(raw)
    if len(cleaned) < 2:
        raise KnowledgeImportError("文件中没有可导入的正文")
    return cleaned


def chunk_text(value: str, *, max_characters: int = 900, overlap: int = 120) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", value) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        units = [paragraph[index:index + max_characters] for index in range(0, len(paragraph), max_characters)]
        for unit in units:
            candidate = f"{current}\n\n{unit}".strip() if current else unit
            if current and len(candidate) > max_characters:
                chunks.append(current)
                current = f"{current[-overlap:]}\n{unit}".strip()
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks or [value[:max_characters]]


def tokenize(value: str) -> list[str]:
    tokens: list[str] = []
    for segment in re.findall(r"[\u3400-\u9fff]+|[A-Za-z0-9_]+", value.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", segment):
            if len(segment) <= 8:
                tokens.append(segment)
            tokens.extend(segment[index:index + 2] for index in range(max(0, len(segment) - 1)))
        else:
            tokens.append(segment)
    return tokens


def import_document(
    db: Session,
    *,
    user_id: str,
    title: str,
    content: str,
    source_type: str,
    original_filename: str = "",
    campus_id: str | None = None,
    publisher: str = "",
    url: str = "",
) -> ImportOutcome:
    cleaned = clean_text(content)
    if len(cleaned) < 2:
        raise KnowledgeImportError("正文不能为空")
    digest = sha256(cleaned.encode("utf-8")).hexdigest()
    existing = db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.owner_user_id == user_id,
        KnowledgeDocument.visibility == "private",
        KnowledgeDocument.content_hash == digest,
        KnowledgeDocument.is_active.is_(True),
    ))
    if existing:
        return ImportOutcome(document=existing, duplicate=True)

    pieces = chunk_text(cleaned)
    document = KnowledgeDocument(
        owner_user_id=user_id,
        campus_id=campus_id,
        title=title.strip()[:255] or original_filename[:255] or "未命名资料",
        content=cleaned,
        publisher=publisher.strip()[:255],
        url=url.strip()[:1000],
        fetched_at=utcnow(),
        is_official=False,
        data_status="private_import",
        visibility="private",
        review_status="private",
        source_type=source_type[:40],
        original_filename=Path(original_filename).name[:255],
        content_hash=digest,
        chunk_count=len(pieces),
        extracted_metadata=extract_structured_metadata(
            cleaned,
            title=title,
            publisher=publisher,
            url=url,
        ),
        is_active=True,
    )
    db.add(document)
    db.flush()
    for index, piece in enumerate(pieces):
        db.add(KnowledgeChunk(
            document_id=document.id,
            owner_user_id=user_id,
            campus_id=campus_id,
            chunk_index=index,
            content=piece,
            token_count=len(tokenize(piece)),
        ))
    return ImportOutcome(document=document, duplicate=False)


def create_import_job(db: Session, *, user_id: str, source_label: str, total_files: int) -> KnowledgeImportJob:
    job = KnowledgeImportJob(user_id=user_id, source_label=source_label[:255], total_files=total_files)
    db.add(job)
    db.flush()
    return job


def finish_import_job(job: KnowledgeImportJob, *, errors: list[str]) -> None:
    job.status = "completed_with_errors" if errors else "completed"
    job.error_summary = "；".join(errors[:10])[:4000]


def reindex_documents(db: Session, *, user_id: str | None, include_public: bool = False) -> int:
    condition = KnowledgeDocument.owner_user_id == user_id
    if include_public:
        condition = or_(condition, KnowledgeDocument.visibility == "public")
    documents = list(db.scalars(select(KnowledgeDocument).options(selectinload(KnowledgeDocument.chunks)).where(
        condition, KnowledgeDocument.is_active.is_(True)
    )))
    count = 0
    for document in documents:
        for chunk in list(document.chunks):
            db.delete(chunk)
        db.flush()
        pieces = chunk_text(clean_text(document.content))
        for index, piece in enumerate(pieces):
            db.add(KnowledgeChunk(
                document_id=document.id,
                owner_user_id=document.owner_user_id,
                campus_id=document.campus_id,
                chunk_index=index,
                content=piece,
                token_count=len(tokenize(piece)),
            ))
        document.content_hash = sha256(clean_text(document.content).encode("utf-8")).hexdigest()
        document.chunk_count = len(pieces)
        count += 1
    return count


def search_knowledge(
    db: Session,
    *,
    user_id: str,
    query: str,
    campus_id: str | None,
    limit: int,
) -> list[dict]:
    visibility = or_(KnowledgeDocument.visibility == "public", KnowledgeDocument.owner_user_id == user_id)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .where(KnowledgeDocument.is_active.is_(True), visibility)
    )
    if campus_id:
        statement = statement.where(or_(KnowledgeDocument.campus_id == campus_id, KnowledgeDocument.campus_id.is_(None)))
    candidates = list(db.execute(statement.limit(5000)).all())
    query_tokens = tokenize(query)
    if not query_tokens or not candidates:
        return []

    token_sets = [set(tokenize(chunk.content)) for chunk, _ in candidates]
    frequencies = Counter(token for values in token_sets for token in set(query_tokens).intersection(values))
    average_length = sum(max(chunk.token_count, 1) for chunk, _ in candidates) / len(candidates)
    scores: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
    for (chunk, document), tokens in zip(candidates, token_sets, strict=True):
        counts = Counter(tokenize(chunk.content))
        length = max(chunk.token_count, 1)
        score = 0.0
        for token in query_tokens:
            frequency = counts[token]
            if not frequency:
                continue
            document_frequency = frequencies[token]
            inverse_frequency = math.log(1 + (len(candidates) - document_frequency + 0.5) / (document_frequency + 0.5))
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * length / average_length)
            score += inverse_frequency * frequency * 2.5 / denominator
        if score > 0:
            scores.append((score, chunk, document))

    results: list[dict] = []
    seen_documents: set[str] = set()
    for score, chunk, document in sorted(scores, key=lambda row: row[0], reverse=True):
        if document.id in seen_documents:
            continue
        seen_documents.add(document.id)
        results.append({
            "document_id": document.id,
            "title": document.title,
            "snippet": chunk.content[:500],
            "score": round(score, 5),
            "publisher": document.publisher,
            "url": document.url,
            "visibility": document.visibility,
            "source_type": document.source_type,
            "created_at": document.created_at,
        })
        if len(results) >= limit:
            break
    return results


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise KnowledgeImportError("只允许不含账号信息的 HTTP/HTTPS 公网地址")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except socket.gaierror as exc:
        raise KnowledgeImportError("文章地址无法解析") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise KnowledgeImportError("不允许访问本机或内网地址")
    return parsed.geturl()


def fetch_article(url: str, *, max_bytes: int) -> tuple[str, str]:
    safe_url = validate_public_url(url)
    with httpx.Client(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=False) as client:
        response = client.get(safe_url, headers={"User-Agent": "GDUF-Knowledge-Importer/1.0"})
    if 300 <= response.status_code < 400:
        raise KnowledgeImportError("文章地址发生跳转，请提交最终公网地址")
    response.raise_for_status()
    if len(response.content) > max_bytes:
        raise KnowledgeImportError("文章正文超过导入大小限制")
    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        raise KnowledgeImportError("文章地址未返回 HTML 或文本正文")
    text = _html_text(response.text) if "html" in content_type else response.text
    cleaned = clean_text(text)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", response.text, flags=re.IGNORECASE | re.DOTALL)
    title = clean_text(_html_text(title_match.group(1))) if title_match else parsed_title(safe_url)
    if len(cleaned) < 2:
        raise KnowledgeImportError("文章地址没有可导入的正文")
    return title or parsed_title(safe_url), cleaned


def parsed_title(url: str) -> str:
    parsed = urlparse(url)
    return Path(parsed.path).name or parsed.hostname or "网页资料"
