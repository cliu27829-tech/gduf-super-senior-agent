"""
轻量级本地知识库检索引擎
使用 Python 标准库实现，无需向量数据库
改进点：
1. 中文 bigram（双字）分词，提升短语匹配质量
2. 标题（文件名）加权，标题命中的文档得分大幅提升
3. 相关性阈值过滤，避免低质量匹配误导 LLM
"""

import os
import re
import math
import streamlit as st


# ---------------------------------------------------------------------------
# 分词
# ---------------------------------------------------------------------------

def _tokenize(text):
    """
    改进的中文分词：
    - 英文按单词切分
    - 中文按单字 + 双字 bigram 切分（bigram 能更好地匹配"学院""校区"等短语）
    """
    if not text:
        return []
    text = text.lower()
    # 英文单词
    en_words = re.findall(r'[a-zA-Z]+', text)
    # 中文字符序列
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    # 中文双字 bigram（滑动窗口）
    cn_bigrams = [cn_chars[i] + cn_chars[i + 1] for i in range(len(cn_chars) - 1)]
    return en_words + cn_chars + cn_bigrams


def _tokenize_to_set(text):
    return set(_tokenize(text))


def _token_frequency(text):
    tokens = _tokenize(text)
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return freq


# ---------------------------------------------------------------------------
# 相似度计算
# ---------------------------------------------------------------------------

def _jaccard_similarity(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _cosine_similarity(tf_a, tf_b):
    if not tf_a or not tf_b:
        return 0.0
    all_tokens = set(tf_a.keys()) | set(tf_b.keys())
    dot_product = sum(tf_a.get(t, 0) * tf_b.get(t, 0) for t in all_tokens)
    norm_a = math.sqrt(sum(v ** 2 for v in tf_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in tf_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _substring_boost(query, text):
    """
    子串命中加成：查询中的关键短语若作为子串出现在文本中，给予加成。
    主要针对 2~4 字的中文短语。
    """
    if not query or not text:
        return 0.0
    # 提取查询中的中文短语（连续中文字符）
    cn_phrases = re.findall(r'[\u4e00-\u9fff]{2,6}', query)
    if not cn_phrases:
        return 0.0
    hits = 0
    for phrase in cn_phrases:
        if phrase in text:
            hits += 1
    # 命中越多加成越高
    return min(hits / max(len(cn_phrases), 1), 1.0)


# ---------------------------------------------------------------------------
# 知识库加载
# ---------------------------------------------------------------------------

@st.cache_data
def load_local_knowledge(kb_dir="好人师兄"):
    """
    启动时加载本地知识库文件
    遍历 好人师兄 文件夹，读取所有 .md, .txt, .html 文件
    返回格式: [{"filename": "xxx", "content": "xxx"}, ...]
    """
    docs = []
    valid_extensions = ('.md', '.txt', '.html')

    if not os.path.exists(kb_dir):
        return docs

    for filename in os.listdir(kb_dir):
        filepath = os.path.join(kb_dir, filename)
        if not os.path.isfile(filepath):
            continue
        if not filename.lower().endswith(valid_extensions):
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if filename.lower().endswith('.html'):
                content = _extract_text_from_html(content)
            content = content.strip()
            if content:
                docs.append({"filename": filename, "content": content})
        except Exception as e:
            st.warning(f"读取文件 {filename} 失败: {e}")
    return docs


def _extract_text_from_html(html):
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------

# 相关性阈值：低于此分数的文档不返回，避免低质量匹配误导 LLM
RELEVANCE_THRESHOLD = 0.03


def search_knowledge(query, docs, top_n=4):
    """
    改进的轻量级文本检索
    评分 = 0.35*Jaccard + 0.35*Cosine + 0.15*标题子串加成 + 0.15*正文子串加成
    标题命中会额外获得 1.5x 倍率提升
    返回匹配度最高的 top_n 篇文章（分数须高于阈值）
    """
    if not docs or not query:
        return []

    query_tokens_set = _tokenize_to_set(query)
    query_tf = _token_frequency(query)

    scored_docs = []
    for doc in docs:
        filename = doc["filename"]
        content = doc["content"]

        # 正文评分（内容 + 文件名联合）
        combined_text = filename + " " + content
        doc_tokens_set = _tokenize_to_set(combined_text)
        doc_tf = _token_frequency(combined_text)

        jaccard = _jaccard_similarity(query_tokens_set, doc_tokens_set)
        cosine = _cosine_similarity(query_tf, doc_tf)

        # 子串加成
        title_substring = _substring_boost(query, filename)
        content_substring = _substring_boost(query, content)

        base_score = (
            0.35 * jaccard
            + 0.35 * cosine
            + 0.15 * title_substring
            + 0.15 * content_substring
        )

        # 标题命中倍率提升
        if title_substring > 0:
            base_score *= 1.5

        scored_docs.append((doc, base_score))

    # 按评分排序
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    # 过滤掉低于阈值的结果
    results = [item[0] for item in scored_docs[:top_n] if item[1] >= RELEVANCE_THRESHOLD]
    return results


def build_knowledge_context(results):
    """将检索结果构建为系统上下文"""
    if not results:
        return ""
    context = "\n\n<参考资料>\n"
    for i, doc in enumerate(results, 1):
        context += f"\n【文章{i}】来源：{doc['filename']}\n"
        context += f"{doc['content'][:1500]}\n"
    context += "\n</参考资料>\n"
    return context


def get_knowledge_injected_prompt(user_input, docs):
    """检索知识库并返回注入了上下文的用户提问（兼容旧调用）"""
    results = search_knowledge(user_input, docs, top_n=2)
    if not results:
        return user_input
    context = build_knowledge_context(results)
    injected_prompt = (
        f"{context}\n"
        f"请优先参考以上资料回答广金校区相关问题，如资料未提及，可结合联网搜索结果或通用知识回答。\n\n"
        f"用户问题：{user_input}"
    )
    return injected_prompt
