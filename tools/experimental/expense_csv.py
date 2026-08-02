"""可选的本地消费文本解析和 CSV 导出。

它不依赖 LLM、不读写全局 API Key，也不在主 Streamlit 交互中暴露。
"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
import re
from typing import Iterable
import uuid

from core.time_service import current_year_china


def categorize_expense(description: str) -> str:
    text = description.casefold()
    rules = {
        "餐饮": ("饭", "餐", "外卖", "吃", "食堂", "饭堂", "奶茶", "咖啡"),
        "交通": ("车", "地铁", "公交", "打车", "滴滴", "出租"),
        "购物": ("买", "购物", "超市", "淘宝", "京东"),
        "娱乐": ("电影", "游戏", "娱乐", "KTV"),
        "学习": ("书", "教材", "文具", "学习", "打印", "课程"),
    }
    return next((category for category, words in rules.items() if any(word.casefold() in text for word in words)), "其他")


def normalize_date(date_text: str, reference_time=None) -> str:
    normalized = (
        date_text.strip()
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("号", "")
        .replace("/", "-")
    )
    explicit = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if explicit:
        return f"{int(explicit.group(1)):04d}-{int(explicit.group(2)):02d}-{int(explicit.group(3)):02d}"
    month_day = re.fullmatch(r"(\d{1,2})-(\d{1,2})", normalized)
    if month_day:
        return f"{current_year_china(reference_time):04d}-{int(month_day.group(1)):02d}-{int(month_day.group(2)):02d}"
    return f"{current_year_china(reference_time):04d}-01-01"


def parse_expenses_fallback(text: str, reference_time=None) -> list[dict]:
    pattern = re.compile(
        r"(?P<date>(?:20\d{2}[-/年])?\d{1,2}[-/月]\d{1,2}[日号]?)"
        r"\s*[：:]?\s*(?P<description>[^\n\d]{1,80}?)\s*"
        r"(?P<amount>\d+(?:\.\d{1,2})?)\s*[元块]"
    )
    results = []
    for match in pattern.finditer(text):
        description = match.group("description").strip(" ：:,，；;")
        results.append(
            {
                "date": normalize_date(match.group("date"), reference_time),
                "category": categorize_expense(description),
                "description": description,
                "amount": float(match.group("amount")),
            }
        )
    return results


def parse_expenses_from_text(text: str, openai_api_key: str = "", reference_time=None) -> list[dict]:
    # The API-key argument remains only for backwards compatibility and is never stored.
    return parse_expenses_fallback(text, reference_time)


def generate_csv_file(expenses: Iterable[dict], filename: str | Path | None = None) -> str:
    output = Path(filename) if filename else Path("data/exports") / f"expenses-{uuid.uuid4().hex}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = list(expenses)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("date", "category", "description", "amount"))
        writer.writeheader()
        writer.writerows(rows)
    return str(output)


def generate_markdown_table(expenses: Iterable[dict]) -> str:
    rows = list(expenses)
    if not rows:
        return "暂无消费记录"
    lines = ["| 日期 | 分类 | 描述 | 金额（元） |", "|---|---|---|---:|"]
    lines.extend(
        f"| {item['date']} | {item['category']} | {item['description']} | {float(item['amount']):.2f} |"
        for item in rows
    )
    lines.append(f"\n**总计：{sum(float(item['amount']) for item in rows):.2f} 元**")
    return "\n".join(lines)


def get_category_summary(expenses: Iterable[dict]) -> dict[str, float]:
    summary: dict[str, float] = {}
    for item in expenses:
        category = str(item["category"])
        summary[category] = summary.get(category, 0.0) + float(item["amount"])
    return summary


def process_expenses(
    text: str,
    openai_api_key: str = "",
    output_filename: str | Path | None = None,
    reference_time=None,
):
    expenses = parse_expenses_from_text(text, openai_api_key, reference_time)
    if not expenses:
        return None, None, "未从文本中提取到消费记录"
    return generate_csv_file(expenses, output_filename), generate_markdown_table(expenses), expenses
