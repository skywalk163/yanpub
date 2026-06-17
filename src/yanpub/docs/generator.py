"""YanDocs — 统一文档站生成器

从适配器提取 API 文档、生成关键字索引、构建静态文档站。
支持跨语言搜索、语言对比表、迁移指南。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from yanpub.core.keyword_docs import categorize_keyword, KEYWORD_CATEGORIES
from yanpub.core.registry import LanguageRegistry, get_registry


@dataclass
class KeywordDoc:
    """关键字文档条目"""
    keyword: str
    lang_id: str
    lang_name: str
    category: str = ""       # 定义/控制流/函数/运算/模块/IO/异常/数据结构
    syntax_example: str = ""  # 语法示例
    description: str = ""     # 描述


@dataclass
class LanguageOverview:
    """语言概览"""
    lang_id: str
    name: str
    version: str
    extensions: list[str]
    primary_color: str
    description: str = ""
    keywords: list[KeywordDoc] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    comment_syntax: str = "#"
    repl_prompt: str = ""


def _categorize_keyword(keyword: str) -> str:
    """根据关键字推断其分类（委托给公共模块）"""
    return categorize_keyword(keyword)


class DocsGenerator:
    """文档生成器

    从适配器注册中心提取信息，生成文档数据结构。
    """

    def __init__(self, registry: LanguageRegistry | None = None):
        self.registry = registry if registry is not None else get_registry()

    def get_language_overview(self, lang_id: str) -> Optional[LanguageOverview]:
        """获取指定语言的概览"""
        adapter = self.registry.get(lang_id)
        if adapter is None:
            return None

        kw_docs = []
        for kw in adapter.keywords:
            kw_docs.append(KeywordDoc(
                keyword=kw,
                lang_id=adapter.id,
                lang_name=adapter.name,
                category=_categorize_keyword(kw),
            ))

        return LanguageOverview(
            lang_id=adapter.id,
            name=adapter.name,
            version=adapter.version,
            extensions=adapter.file_extensions,
            primary_color=adapter.primary_color,
            description=adapter.description,
            keywords=kw_docs,
            capabilities=adapter.capabilities,
            comment_syntax=adapter.comment_syntax,
            repl_prompt=adapter.repl_prompt,
        )

    def list_all_languages(self) -> list[LanguageOverview]:
        """列出所有语言的概览"""
        return [
            self.get_language_overview(lang_id)
            for lang_id in self.registry.language_ids
            if self.get_language_overview(lang_id) is not None
        ]

    def search_keywords(self, query: str) -> list[KeywordDoc]:
        """跨语言搜索关键字"""
        results = []
        for lang_id in self.registry.language_ids:
            adapter = self.registry.get(lang_id)
            if adapter is None:
                continue
            for kw in adapter.keywords:
                if query in kw:
                    results.append(KeywordDoc(
                        keyword=kw,
                        lang_id=adapter.id,
                        lang_name=adapter.name,
                        category=_categorize_keyword(kw),
                    ))
        return results

    def compare_concept(self, concept: str) -> dict[str, KeywordDoc]:
        """对比同一概念在不同语言中的关键字

        例如 compare_concept("定义") 返回各语言中"定义"相关的关键字。
        """
        results = {}
        category_keywords = KEYWORD_CATEGORIES.get(concept, [concept])

        for lang_id in self.registry.language_ids:
            adapter = self.registry.get(lang_id)
            if adapter is None:
                continue
            for kw in adapter.keywords:
                if kw in category_keywords or kw == concept:
                    results[lang_id] = KeywordDoc(
                        keyword=kw,
                        lang_id=adapter.id,
                        lang_name=adapter.name,
                        category=concept,
                    )
                    break  # 取第一个匹配的

        return results

    def generate_comparison_table(self) -> list[dict]:
        """生成语言对比表

        返回按概念分类的对比数据，每个概念在各语言中的关键字。
        """
        concepts = list(KEYWORD_CATEGORIES.keys())
        lang_ids = self.registry.language_ids
        table = []

        for concept in concepts:
            row = {"concept": concept, "languages": {}}
            for lang_id in lang_ids:
                adapter = self.registry.get(lang_id)
                if adapter is None:
                    continue
                # 找出该语言中属于此概念的所有关键字
                matching = [
                    kw for kw in adapter.keywords
                    if kw in KEYWORD_CATEGORIES.get(concept, []) or kw == concept
                ]
                row["languages"][lang_id] = matching
            table.append(row)

        return table

    def generate_keyword_index(self, lang_id: str) -> dict[str, list[KeywordDoc]]:
        """生成指定语言的关键字索引（按分类）"""
        overview = self.get_language_overview(lang_id)
        if overview is None:
            return {}

        index: dict[str, list[KeywordDoc]] = {}
        for kw_doc in overview.keywords:
            index.setdefault(kw_doc.category, []).append(kw_doc)

        return index

    def generate_site_data(self) -> dict:
        """生成文档站全部数据（供模板渲染使用）"""
        languages = self.list_all_languages()
        comparison = self.generate_comparison_table()

        # 统计信息
        total_keywords = sum(len(lang.keywords) for lang in languages)

        return {
            "site_name": "言埠 YanPub",
            "site_description": "中文编程语言统一基础设施",
            "languages": [
                {
                    "id": lang.lang_id,
                    "name": lang.name,
                    "version": lang.version,
                    "extensions": lang.extensions,
                    "primary_color": lang.primary_color,
                    "description": lang.description,
                    "keyword_count": len(lang.keywords),
                    "capabilities": lang.capabilities,
                    "comment_syntax": lang.comment_syntax,
                    "keywords_by_category": {
                        cat: [{"keyword": kd.keyword, "category": kd.category, "lang_id": kd.lang_id, "lang_name": kd.lang_name} for kd in kws]
                        for cat, kws in self.generate_keyword_index(lang.lang_id).items()
                    },
                }
                for lang in languages
            ],
            "comparison": comparison,
            "stats": {
                "language_count": len(languages),
                "total_keywords": total_keywords,
            },
        }
