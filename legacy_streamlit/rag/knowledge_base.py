"""Deterministic local retrieval with provenance; no fake vector embeddings."""

from __future__ import annotations

from tools.local_knowledge import (
    build_knowledge_context,
    load_local_knowledge,
    search_knowledge,
)


class CampusKnowledgeBase:
    """Compatibility wrapper around the transparent lexical retriever."""

    def __init__(self, api_key: str = "", data_dir: str = "好人师兄"):
        self.api_key = api_key
        self.data_dir = data_dir
        self.documents = load_local_knowledge(data_dir)

    def load_documents(self):
        return list(self.documents)

    def build_vector_store(self):
        # Kept for callers from the old interface. Retrieval is lexical and inspectable.
        self.documents = load_local_knowledge(self.data_dir)
        return bool(self.documents)

    def setup_qa_chain(self):
        return bool(self.documents)

    def manual_update(self):
        try:
            load_local_knowledge.clear()
        except AttributeError:
            pass
        self.documents = load_local_knowledge(self.data_dir)
        return True, f"知识库更新成功，已加载 {len(self.documents)} 篇带时效元数据的资料。"

    def query(self, question: str):
        results = search_knowledge(question, self.documents, top_n=5)
        if not results:
            return "本地资料没有可验证的相关内容，请查看学校官网或由管理员补充来源。"
        return build_knowledge_context(results)
