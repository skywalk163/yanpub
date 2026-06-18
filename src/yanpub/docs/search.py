"""文档站搜索增强 — 全文搜索 + 关键字联想 + 代码示例搜索

核心类:
- SearchIndex: 搜索索引（倒排索引 + 前缀树联想）
- SearchResult: 搜索结果
- DocsSearchEngine: 搜索引擎
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from yanpub.core.registry import get_registry


@dataclass
class SearchResult:
    """搜索结果"""

    title: str
    content: str
    url: str = ""
    score: float = 0.0
    highlights: list[str] = field(default_factory=list)
    category: str = ""  # keyword | doc | example | comparison
    lang_id: str = ""
    lang_name: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "content": self.content[:500],
            "url": self.url,
            "score": round(self.score, 3),
            "highlights": self.highlights[:5],
            "category": self.category,
            "lang_id": self.lang_id,
            "lang_name": self.lang_name,
        }


# ============================================================
# 倒排索引 + 前缀树联想
# ============================================================


class _TrieNode:
    """前缀树节点（用于关键字联想）"""

    __slots__ = ("children", "words", "freq")

    def __init__(self):
        self.children: dict[str, _TrieNode] = {}
        self.words: list[str] = []  # 以此前缀结尾的候选词
        self.freq: int = 0


class SearchIndex:
    """搜索索引

    - 倒排索引：词 -> 文档列表 + TF-IDF
    - 前缀树：支持关键字联想
    """

    def __init__(self):
        self._inverted: dict[str, list[tuple[str, float]]] = defaultdict(list)  # term -> [(doc_id, weight)]
        self._documents: dict[str, dict] = {}  # doc_id -> {title, content, ...}
        self._doc_terms: dict[str, dict[str, int]] = {}  # doc_id -> {term: count}
        self._trie_root = _TrieNode()
        self._total_docs = 0

    # ---- 索引构建 ----

    def add_document(self, doc_id: str, title: str, content: str, **meta) -> None:
        """添加文档到索引"""
        self._total_docs += 1
        self._documents[doc_id] = {"title": title, "content": content, **meta}

        # 分词
        terms = self._tokenize(title + " " + content)
        term_freq: dict[str, int] = {}
        for t in terms:
            term_freq[t] = term_freq.get(t, 0) + 1
        self._doc_terms[doc_id] = term_freq

        # 计算权重（简化 TF-IDF）
        for term, freq in term_freq.items():
            weight = self._tf_idf(freq, len(terms), 1)
            self._inverted[term].append((doc_id, weight))

        # 添加标题词到前缀树
        title_terms = self._tokenize(title)
        for t in set(title_terms):
            self._add_to_trie(t)

    def _tokenize(self, text: str) -> list[str]:
        """简单分词：中文单字 + 英文单词 + 中文关键词"""
        result = []
        # 提取中文词（2-4字连续中文）
        for m in re.finditer(r"[\u4e00-\u9fff]{2,4}", text):
            word = m.group()
            result.append(word)
            # 也拆为单字
            for ch in word:
                result.append(ch)
        # 提取英文单词
        for m in re.finditer(r"[a-zA-Z_][a-zA-Z0-9_]*", text):
            result.append(m.group().lower())
        # 提取中文单字
        for ch in text:
            if "\u4e00" <= ch <= "\u9fff":
                result.append(ch)
        return result

    def _tf_idf(self, term_freq: int, doc_len: int, doc_count: int) -> float:
        """计算 TF-IDF 权重"""
        tf = term_freq / max(doc_len, 1)
        idf = math.log(max(self._total_docs, 1) / max(doc_count, 1) + 1)
        return tf * idf

    def _add_to_trie(self, word: str) -> None:
        """添加词到前缀树"""
        node = self._trie_root
        for ch in word:
            if ch not in node.children:
                node.children[ch] = _TrieNode()
            node = node.children[ch]
            if len(node.words) < 10 and word not in node.words:
                node.words.append(word)
        node.freq += 1

    # ---- 搜索 ----

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """全文搜索"""
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # 计算每个文档的得分
        doc_scores: dict[str, float] = defaultdict(float)
        matched_terms: dict[str, set[str]] = defaultdict(set)

        for qt in query_terms:
            for term in self._expand_term(qt):
                postings = self._inverted.get(term, [])
                doc_count = len(postings)
                for doc_id, base_weight in postings:
                    # 如果查询词与索引词完全匹配，加权重
                    boost = 2.0 if term == qt else 1.0
                    idf = math.log(max(self._total_docs, 1) / max(doc_count, 1) + 1)
                    doc_scores[doc_id] += base_weight * idf * boost
                    matched_terms[doc_id].add(term)

        # 排序并构建结果
        ranked = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        results = []
        for doc_id, score in ranked:
            doc = self._documents.get(doc_id, {})
            # 提取高亮片段
            highlights = self._extract_highlights(doc.get("content", ""), query_terms)
            results.append(SearchResult(
                title=doc.get("title", ""),
                content=doc.get("content", ""),
                url=doc.get("url", ""),
                score=score,
                highlights=highlights,
                category=doc.get("category", ""),
                lang_id=doc.get("lang_id", ""),
                lang_name=doc.get("lang_name", ""),
            ))
        return results

    def suggest(self, prefix: str, limit: int = 8) -> list[str]:
        """关键字联想（前缀匹配）"""
        if not prefix:
            return []
        node = self._trie_root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]
        return node.words[:limit]

    # ---- 辅助 ----

    def _expand_term(self, term: str) -> list[str]:
        """扩展查询词（同义词/别名）"""
        expansions = [term]
        # 中文单字扩展到包含该字的词
        if len(term) == 1 and "\u4e00" <= term <= "\u9fff":
            for key in self._inverted:
                if term in key and key != term:
                    expansions.append(key)
        return expansions[:5]  # 限制扩展数量

    def _extract_highlights(self, content: str, query_terms: list[str], context: int = 40) -> list[str]:
        """提取高亮片段"""
        highlights = []
        for qt in query_terms[:3]:  # 最多3个查询词
            idx = content.lower().find(qt.lower())
            if idx >= 0:
                start = max(0, idx - context)
                end = min(len(content), idx + len(qt) + context)
                snippet = content[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                highlights.append(snippet)
        return highlights

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def term_count(self) -> int:
        return len(self._inverted)


# ============================================================
# 文档站搜索引擎
# ============================================================


class DocsSearchEngine:
    """文档站搜索引擎

    自动从注册中心和示例文件构建索引，提供：
    - 全文搜索
    - 关键字联想
    - 代码示例搜索
    """

    def __init__(self):
        self._index = SearchIndex()
        self._built = False

    def build_index(self) -> dict:
        """构建搜索索引"""
        if self._built:
            return {"status": "already_built", "documents": self._index.document_count}

        registry = get_registry()

        # 1. 索引语言概览
        for adapter in registry:
            doc_id = f"lang:{adapter.id}"
            content_parts = [
                adapter.name,
                adapter.description or "",
                "版本: " + adapter.version,
                "扩展名: " + ", ".join(adapter.file_extensions),
                "关键字: " + ", ".join(adapter.keywords[:50]),
            ]
            if hasattr(adapter, "capabilities"):
                caps = [k for k, v in adapter.capabilities.items() if v]
                content_parts.append("能力: " + ", ".join(caps))
            self._index.add_document(
                doc_id=doc_id,
                title=f"{adapter.name} ({adapter.id}) 语言概览",
                content="\n".join(content_parts),
                category="doc",
                lang_id=adapter.id,
                lang_name=adapter.name,
            )

            # 2. 索引关键字
            for kw in adapter.keywords:
                self._index.add_document(
                    doc_id=f"kw:{adapter.id}:{kw}",
                    title=f"{kw} — {adapter.name} 关键字",
                    content=f"语言: {adapter.name}\n关键字: {kw}\n注释语法: {adapter.comment_syntax}",
                    category="keyword",
                    lang_id=adapter.id,
                    lang_name=adapter.name,
                )

        # 3. 索引代码示例
        templates_dir = Path(__file__).parent.parent / "playground" / "templates"
        if templates_dir.exists():
            for lang_dir in templates_dir.iterdir():
                if not lang_dir.is_dir():
                    continue
                for txt_file in lang_dir.glob("*.txt"):
                    if txt_file.name == "default.txt":
                        continue
                    example_name = txt_file.stem
                    try:
                        code = txt_file.read_text(encoding="utf-8")
                    except Exception:
                        continue
                    # 找到语言名
                    adapter = registry.get(lang_dir.name)
                    lang_name = adapter.name if adapter else lang_dir.name
                    self._index.add_document(
                        doc_id=f"example:{lang_dir.name}:{example_name}",
                        title=f"{example_name} 示例 — {lang_name}",
                        content=code[:2000],
                        category="example",
                        lang_id=lang_dir.name,
                        lang_name=lang_name,
                    )

        self._built = True
        return {
            "status": "built",
            "documents": self._index.document_count,
            "terms": self._index.term_count,
        }

    def search(self, query: str, limit: int = 20, category: str = "") -> list[SearchResult]:
        """全文搜索"""
        if not self._built:
            self.build_index()
        results = self._index.search(query, limit=limit * 2)
        if category:
            results = [r for r in results if r.category == category]
        return results[:limit]

    def suggest(self, prefix: str, limit: int = 8) -> list[str]:
        """关键字联想"""
        if not self._built:
            self.build_index()
        return self._index.suggest(prefix, limit)

    def search_examples(self, query: str, lang_id: str = "", limit: int = 10) -> list[SearchResult]:
        """搜索代码示例"""
        if not self._built:
            self.build_index()
        results = self.search(query, limit=limit * 2, category="example")
        if lang_id:
            results = [r for r in results if r.lang_id == lang_id]
        return results[:limit]

    def stats(self) -> dict:
        return {
            "built": self._built,
            "documents": self._index.document_count,
            "terms": self._index.term_count,
        }


# 全局单例
_engine: DocsSearchEngine | None = None


def get_search_engine() -> DocsSearchEngine:
    global _engine
    if _engine is None:
        _engine = DocsSearchEngine()
    return _engine
