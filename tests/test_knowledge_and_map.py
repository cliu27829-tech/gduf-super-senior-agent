from datetime import datetime
from pathlib import Path

from core.models import CampusLocation
from core.time_service import CHINA_TZ
from rag.knowledge_base import CampusKnowledgeBase
from tools.local_knowledge import load_local_knowledge
from ui.map_helpers import build_map_rows, filter_locations, is_currently_open


def test_historical_knowledge_is_labeled_and_retrievable_without_fake_embeddings(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "饭堂历史资料.md").write_text(
        "2024年饭堂历史介绍 https://hq.gduf.edu.cn/example",
        encoding="utf-8",
    )
    load_local_knowledge.clear()
    docs = load_local_knowledge(str(knowledge_dir), reference_year=2026)
    assert docs[0]["metadata"]["source_status"] == "historical"
    assert docs[0]["metadata"]["freshness_status"] == "expired"

    kb = CampusKnowledgeBase(data_dir=str(knowledge_dir))
    assert "参考资料" in kb.query("饭堂历史")
    forbidden_name = "Fake" + "Embeddings"
    for source_file in Path(".").glob("**/*.py"):
        if "venv" not in source_file.parts and "tests" not in source_file.parts:
            assert forbidden_name not in source_file.read_text(encoding="utf-8")


def test_map_filter_open_status_and_coordinate_precision():
    item = CampusLocation(
        id="library",
        name="图书馆",
        aliases=["图馆"],
        campus="广州校本部",
        category="library",
        map_x=0.2,
        map_y=0.8,
        opening_hours="08:00-22:00",
        freshness_status="current",
        verified_at="2026-08-01T00:00:00+08:00",
    )
    reference = datetime(2026, 8, 2, 12, tzinfo=CHINA_TZ)
    assert is_currently_open(item, reference)
    assert filter_locations([item], query="图馆", open_only=True, reference_time=reference) == [item]
    assert build_map_rows([item])[0]["coordinate_type"] == "schematic"
