"""
轻量级本地知识库检索引擎
使用 Python 标准库实现，无需向量数据库
"""

import os
import re
import math
import streamlit as st


def _tokenize(text):
    """简单的中文分词：按字符切分 + 英文按单词切分"""
    # 提取英文单词
    en_words = re.findall(r'[a-zA-Z]+', text.lower())
    # 提取中文字符（每个字作为一个token）
    cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
    return en_words + cn_chars


def _tokenize_to_set(text):
    """分词并去重，返回集合用于 Jaccard 相似度计算"""
    tokens = _tokenize(text)
    return set(tokens)


def _jaccard_similarity(set_a, set_b):
    """计算两个集合的 Jaccard 相似度"""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _token_frequency(text):
    """计算词频，返回字典"""
    tokens = _tokenize(text)
    freq = {}
    for token in tokens:
        freq[token] = freq.get(token, 0) + 1
    return freq


def _cosine_similarity(tf_a, tf_b):
    """基于词频的余弦相似度"""
    if not tf_a or not tf_b:
        return 0.0
    all_tokens = set(tf_a.keys()) | set(tf_b.keys())
    dot_product = sum(tf_a.get(t, 0) * tf_b.get(t, 0) for t in all_tokens)
    norm_a = math.sqrt(sum(v ** 2 for v in tf_a.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in tf_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


@st.cache_data
def load_local_knowledge(kb_dir="好人师兄"):
    """
    启动时加载本地知识库文件
    遍历 好人师兄 文件夹，读取所有 .md, .txt, .html 文件
    返回格式: [{"filename": "xxx", "content": "xxx"}, ...]
    """
    docs = []

    # 支持的文件扩展名
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

            # 如果是 HTML，提取纯文本
            if filename.lower().endswith('.html'):
                content = _extract_text_from_html(content)

            content = content.strip()
            if content:
                docs.append({
                    "filename": filename,
                    "content": content
                })
        except Exception as e:
            st.warning(f"读取文件 {filename} 失败: {e}")

    return docs


def _extract_text_from_html(html):
    """从 HTML 中提取纯文本"""
    # 移除 script 和 style 标签
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 移除所有 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', html)
    # 压缩空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def search_knowledge(query, docs, top_n=2):
    """
    轻量级文本检索
    使用 Jaccard 相似度 + 余弦相似度的混合评分
    返回匹配度最高的 top_n 篇文章
    """
    if not docs or not query:
        return []

    query_tokens_set = _tokenize_to_set(query)
    query_tf = _token_frequency(query)

    scored_docs = []
    for doc in docs:
        content = doc["content"]
        # 同时用文件名和内容做匹配
        combined_text = doc["filename"] + " " + content
        doc_tokens_set = _tokenize_to_set(combined_text)
        doc_tf = _token_frequency(combined_text)

        # Jaccard 相似度
        jaccard = _jaccard_similarity(query_tokens_set, doc_tokens_set)
        # 余弦相似度
        cosine = _cosine_similarity(query_tf, doc_tf)

        # 混合评分：余弦权重更高
        score = 0.4 * jaccard + 0.6 * cosine
        scored_docs.append((doc, score))

    # 按评分排序，取前 top_n
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    # 过滤掉评分为0的结果
    results = [item[0] for item in scored_docs[:top_n] if item[1] > 0]

    return results


def build_knowledge_context(results):
    """
    将检索结果构建为系统上下文
    """
    if not results:
        return ""

    context = "\n\n<参考资料>\n"
    for i, doc in enumerate(results, 1):
        context += f"\n【文章{i}】来源：{doc['filename']}\n"
        context += f"{doc['content'][:1500]}\n"
    context += "\n</参考资料>\n"

    return context


def get_knowledge_injected_prompt(user_input, docs):
    """
    检索知识库并返回注入了上下文的用户提问
    如果找到相关文章，将文章内容作为参考资料拼接到用户提问前
    """
    results = search_knowledge(user_input, docs, top_n=2)
    if not results:
        return user_input

    context = build_knowledge_context(results)
    injected_prompt = (
        f"{context}\n"
        f"请严格根据以下参考资料回答广金校区相关问题，如果没有提及，请回答不知道。\n\n"
        f"用户问题：{user_input}"
    )
    return injected_prompt
