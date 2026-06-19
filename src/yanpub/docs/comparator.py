"""语言对比功能 — 跨语言语法对比与迁移指南生成

核心能力：
1. 同一概念在不同语言中的语法对比表
2. 语言相似度计算
3. 迁移指南自动生成
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from yanpub.core.keyword_docs import KEYWORD_CATEGORIES
from yanpub.core.registry import LanguageRegistry, get_registry
from yanpub.docs.generator import DocsGenerator


@dataclass
class ConceptComparison:
    """概念对比结果"""

    concept: str
    mappings: dict[str, list[str]]  # lang_id -> 该语言的关键字列表


@dataclass
class LanguageSimilarity:
    """语言相似度"""

    lang_id_a: str
    lang_id_b: str
    shared_keywords: list[str]
    shared_categories: list[str]
    similarity_score: float  # 0.0 - 1.0


class LanguageComparator:
    """语言对比器"""

    def __init__(self, registry: LanguageRegistry | None = None):
        self.registry = registry if registry is not None else get_registry()
        self.gen = DocsGenerator(self.registry)

    def compare_all_concepts(self) -> list[ConceptComparison]:
        """生成所有概念的跨语言对比"""
        results = []
        for concept, concept_keywords in KEYWORD_CATEGORIES.items():
            mappings = {}
            for lang_id in self.registry.language_ids:
                adapter = self.registry.get(lang_id)
                if adapter is None:
                    continue
                matching = [kw for kw in adapter.keywords if kw in concept_keywords]
                if matching:
                    mappings[lang_id] = matching

            if len(mappings) > 1:  # 至少2种语言有此概念
                results.append(
                    ConceptComparison(
                        concept=concept,
                        mappings=mappings,
                    )
                )

        return results

    def compute_similarity(self, lang_id_a: str, lang_id_b: str) -> Optional[LanguageSimilarity]:
        """计算两种语言的相似度"""
        adapter_a = self.registry.get(lang_id_a)
        adapter_b = self.registry.get(lang_id_b)
        if adapter_a is None or adapter_b is None:
            return None

        set_a = set(adapter_a.keywords)
        set_b = set(adapter_b.keywords)

        shared = set_a & set_b
        total = set_a | set_b

        # 按分类的共享度
        cats_a = set()
        cats_b = set()
        for kw in set_a:
            for cat, cat_kws in KEYWORD_CATEGORIES.items():
                if kw in cat_kws:
                    cats_a.add(cat)
        for kw in set_b:
            for cat, cat_kws in KEYWORD_CATEGORIES.items():
                if kw in cat_kws:
                    cats_b.add(cat)

        shared_cats = cats_a & cats_b

        # Jaccard 相似度
        score = len(shared) / len(total) if total else 0.0

        return LanguageSimilarity(
            lang_id_a=lang_id_a,
            lang_id_b=lang_id_b,
            shared_keywords=sorted(shared),
            shared_categories=sorted(shared_cats),
            similarity_score=round(score, 4),
        )

    def compute_all_similarities(self) -> list[LanguageSimilarity]:
        """计算所有语言对之间的相似度"""
        lang_ids = self.registry.language_ids
        results = []
        for i, id_a in enumerate(lang_ids):
            for id_b in lang_ids[i + 1 :]:
                sim = self.compute_similarity(id_a, id_b)
                if sim is not None:
                    results.append(sim)
        return sorted(results, key=lambda s: s.similarity_score, reverse=True)

    def generate_migration_guide(self, from_lang: str, to_lang: str) -> Optional[dict]:
        """生成迁移指南

        返回从 from_lang 迁移到 to_lang 的关键字映射和建议。
        """
        adapter_from = self.registry.get(from_lang)
        adapter_to = self.registry.get(to_lang)
        if adapter_from is None or adapter_to is None:
            return None

        sim = self.compute_similarity(from_lang, to_lang)
        if sim is None:
            return None

        # 构建概念映射
        concept_map = {}
        for concept, concept_keywords in KEYWORD_CATEGORIES.items():
            from_kws = [kw for kw in adapter_from.keywords if kw in concept_keywords]
            to_kws = [kw for kw in adapter_to.keywords if kw in concept_keywords]
            if from_kws or to_kws:
                concept_map[concept] = {
                    "from": from_kws,
                    "to": to_kws,
                    "shared": [kw for kw in from_kws if kw in to_kws],
                    "only_from": [kw for kw in from_kws if kw not in to_kws],
                    "only_to": [kw for kw in to_kws if kw not in from_kws],
                }

        return {
            "from": {
                "id": adapter_from.id,
                "name": adapter_from.name,
                "version": adapter_from.version,
            },
            "to": {
                "id": adapter_to.id,
                "name": adapter_to.name,
                "version": adapter_to.version,
            },
            "similarity_score": sim.similarity_score,
            "shared_keywords": sim.shared_keywords,
            "shared_categories": sim.shared_categories,
            "concept_map": concept_map,
        }

    def generate_similarity_matrix(self) -> dict:
        """生成语言相似度矩阵"""
        lang_ids = self.registry.language_ids
        matrix = {}
        for id_a in lang_ids:
            matrix[id_a] = {}
            for id_b in lang_ids:
                if id_a == id_b:
                    matrix[id_a][id_b] = 1.0
                else:
                    sim = self.compute_similarity(id_a, id_b)
                    matrix[id_a][id_b] = sim.similarity_score if sim else 0.0
        return {
            "languages": lang_ids,
            "matrix": matrix,
        }
