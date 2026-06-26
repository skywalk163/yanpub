"""YanDocs 文档站和语言对比测试"""

from __future__ import annotations

import json

import pytest

from yanpub.core.adapter.registry import LanguageRegistry
from yanpub.core.adapter.adapter import SubprocessAdapter
from yanpub.docs.generator import (
    DocsGenerator,
    _categorize_keyword,
)
from yanpub.docs.comparator import (
    LanguageComparator,
)
from yanpub.docs.site_builder import build_site


# ---- Fixtures ----


class MockAdapter(SubprocessAdapter):
    """用于测试的模拟适配器"""

    def __init__(self, name, lang_id, keywords, color="#000000"):
        super().__init__(
            name=name,
            lang_id=lang_id,
            version="0.1.0",
            extensions=[".test"],
            run_command=["echo"],
            keywords=keywords,
            primary_color=color,
        )


@pytest.fixture
def test_registry():
    """创建测试用的注册中心，注册3种模拟语言"""
    registry = LanguageRegistry()
    registry.register(
        MockAdapter(
            "语言甲",
            "lang_a",
            [
                "定义",
                "设",
                "函数",
                "如果",
                "那么",
                "否则",
                "当",
                "遍历",
                "返回",
                "结束",
                "加",
                "减",
                "乘",
                "除",
                "等于",
                "大于",
                "小于",
                "真",
                "假",
                "空",
                "尝试",
                "捕获",
                "抛出",
                "导入",
                "导出",
            ],
            color="#FF0000",
        )
    )
    registry.register(
        MockAdapter(
            "语言乙",
            "lang_b",
            [
                "定",
                "设",
                "函",
                "若",
                "则",
                "否则",
                "当",
                "遍历",
                "返回",
                "完",
                "加",
                "减",
                "乘",
                "除",
                "等于",
                "大于",
                "小于",
                "真",
                "假",
                "空",
                "尝试",
                "捕获",
                "抛出",
                "导入",
                "从",
            ],
            color="#00FF00",
        )
    )
    registry.register(
        MockAdapter(
            "语言丙",
            "lang_c",
            [
                "定义",
                "赋值",
                "函数",
                "如果",
                "那么",
                "否则",
                "循环",
                "每",
                "返回",
                "完毕",
                "相加",
                "相减",
                "相乘",
                "相除",
                "等于",
                "大于",
                "小于",
                "真",
                "假",
                "空",
                "试",
                "捕获",
                "抛出",
                "导入",
                "导出",
            ],
            color="#0000FF",
        )
    )
    return registry


@pytest.fixture
def generator(test_registry):
    return DocsGenerator(test_registry)


@pytest.fixture
def comparator(test_registry):
    return LanguageComparator(test_registry)


# ---- DocsGenerator 测试 ----


class TestDocsGenerator:
    def test_get_language_overview(self, generator, test_registry):
        overview = generator.get_language_overview("lang_a")
        assert overview is not None
        assert overview.name == "语言甲"
        assert overview.lang_id == "lang_a"
        assert overview.version == "0.1.0"
        assert len(overview.keywords) >= 20

    def test_get_language_overview_not_found(self, generator):
        overview = generator.get_language_overview("nonexistent")
        assert overview is None

    def test_list_all_languages(self, generator):
        languages = generator.list_all_languages()
        assert len(languages) == 3
        names = [lang.name for lang in languages]
        assert "语言甲" in names
        assert "语言乙" in names
        assert "语言丙" in names

    def test_search_keywords(self, generator):
        results = generator.search_keywords("定义")
        assert len(results) >= 1
        # 定义存在于 lang_a 和 lang_c
        lang_ids = {r.lang_id for r in results}
        assert "lang_a" in lang_ids or "lang_c" in lang_ids

    def test_search_keywords_partial(self, generator):
        results = generator.search_keywords("加")
        # 应匹配 "加", "相加"
        assert len(results) >= 3  # 各语言都有"加"或"相加"

    def test_compare_concept(self, generator):
        result = generator.compare_concept("定义")
        assert "lang_a" in result or "lang_c" in result
        if "lang_a" in result:
            assert result["lang_a"].keyword == "定义"

    def test_generate_comparison_table(self, generator):
        table = generator.generate_comparison_table()
        assert len(table) > 0
        # 检查 "运算" 分类
        ops_row = next((r for r in table if r["concept"] == "运算"), None)
        assert ops_row is not None
        # lang_a 和 lang_b 应该有运算关键字
        assert len(ops_row["languages"]["lang_a"]) > 0
        assert len(ops_row["languages"]["lang_b"]) > 0

    def test_generate_keyword_index(self, generator):
        index = generator.generate_keyword_index("lang_a")
        assert len(index) > 0
        # 检查 "定义" 分类存在
        categories = list(index.keys())
        assert "定义" in categories or "函数" in categories

    def test_generate_keyword_index_not_found(self, generator):
        index = generator.generate_keyword_index("nonexistent")
        assert index == {}

    def test_generate_site_data(self, generator):
        data = generator.generate_site_data()
        assert data["site_name"] == "言埠 YanPub"
        assert len(data["languages"]) == 3
        assert data["stats"]["language_count"] == 3
        assert data["stats"]["total_keywords"] > 0
        assert len(data["comparison"]) > 0


# ---- 关键字分类测试 ----


class TestKeywordCategorization:
    def test_categorize_definition(self):
        assert _categorize_keyword("定义") == "定义"
        assert _categorize_keyword("定") == "定义"
        assert _categorize_keyword("设") == "定义"

    def test_categorize_control_flow(self):
        assert _categorize_keyword("如果") == "控制流"
        assert _categorize_keyword("遍历") == "控制流"
        assert _categorize_keyword("返回") == "控制流"

    def test_categorize_operator(self):
        assert _categorize_keyword("加") == "运算"
        assert _categorize_keyword("等于") == "运算"

    def test_categorize_exception(self):
        assert _categorize_keyword("尝试") == "异常"
        assert _categorize_keyword("捕获") == "异常"

    def test_categorize_module(self):
        assert _categorize_keyword("导入") == "模块"
        assert _categorize_keyword("导出") == "模块"

    def test_categorize_unknown(self):
        assert _categorize_keyword("未知关键字") == "其他"


# ---- LanguageComparator 测试 ----


class TestLanguageComparator:
    def test_compare_all_concepts(self, comparator):
        comparisons = comparator.compare_all_concepts()
        assert len(comparisons) > 0
        # 每个对比至少2种语言
        for comp in comparisons:
            assert len(comp.mappings) >= 2

    def test_compute_similarity(self, comparator):
        sim = comparator.compute_similarity("lang_a", "lang_b")
        assert sim is not None
        assert sim.lang_id_a == "lang_a"
        assert sim.lang_id_b == "lang_b"
        assert 0.0 <= sim.similarity_score <= 1.0
        assert len(sim.shared_keywords) > 0
        # lang_a 和 lang_b 共享 "设", "加", "减" 等
        assert "设" in sim.shared_keywords or "加" in sim.shared_keywords

    def test_compute_similarity_same_language(self, comparator):
        sim = comparator.compute_similarity("lang_a", "lang_a")
        assert sim is not None
        assert sim.similarity_score == 1.0

    def test_compute_similarity_not_found(self, comparator):
        sim = comparator.compute_similarity("lang_a", "nonexistent")
        assert sim is None

    def test_compute_all_similarities(self, comparator):
        similarities = comparator.compute_all_similarities()
        assert len(similarities) == 3  # C(3,2) = 3
        # 应该按相似度降序排列
        for i in range(len(similarities) - 1):
            assert similarities[i].similarity_score >= similarities[i + 1].similarity_score

    def test_generate_migration_guide(self, comparator):
        guide = comparator.generate_migration_guide("lang_a", "lang_b")
        assert guide is not None
        assert guide["from"]["id"] == "lang_a"
        assert guide["to"]["id"] == "lang_b"
        assert "similarity_score" in guide
        assert "concept_map" in guide
        # 检查概念映射
        assert "定义" in guide["concept_map"] or "控制流" in guide["concept_map"]

    def test_generate_migration_guide_not_found(self, comparator):
        guide = comparator.generate_migration_guide("lang_a", "nonexistent")
        assert guide is None

    def test_generate_similarity_matrix(self, comparator):
        matrix = comparator.generate_similarity_matrix()
        assert "languages" in matrix
        assert "matrix" in matrix
        assert len(matrix["languages"]) == 3
        # 对角线应为 1.0
        for lang_id in matrix["languages"]:
            assert matrix["matrix"][lang_id][lang_id] == 1.0
        # 对称性
        for a in matrix["languages"]:
            for b in matrix["languages"]:
                assert matrix["matrix"][a][b] == pytest.approx(matrix["matrix"][b][a], abs=1e-4)


# ---- SiteBuilder 测试 ----


class TestSiteBuilder:
    def test_build_site(self, test_registry, tmp_path):
        output = build_site(tmp_path / "yandocs", test_registry)
        assert output.exists()
        assert (output / "index.html").exists()
        assert (output / "data.json").exists()

    def test_build_site_has_language_pages(self, test_registry, tmp_path):
        output = build_site(tmp_path / "yandocs", test_registry)
        assert (output / "lang_lang_a.html").exists()
        assert (output / "lang_lang_b.html").exists()
        assert (output / "lang_lang_c.html").exists()

    def test_build_site_index_content(self, test_registry, tmp_path):
        output = build_site(tmp_path / "yandocs", test_registry)
        html = (output / "index.html").read_text(encoding="utf-8")
        assert "言埠" in html
        assert "语言甲" in html
        assert "语言乙" in html
        assert "语言丙" in html
        assert "语法对比" in html

    def test_build_site_data_json(self, test_registry, tmp_path):
        output = build_site(tmp_path / "yandocs", test_registry)
        data = json.loads((output / "data.json").read_text(encoding="utf-8"))
        assert data["stats"]["language_count"] == 3
        assert len(data["languages"]) == 3

    def test_build_site_search_data(self, test_registry, tmp_path):
        output = build_site(tmp_path / "yandocs", test_registry)
        html = (output / "index.html").read_text(encoding="utf-8")
        assert "searchData" in html


# ---- 全局注册中心集成测试 ----


class TestDocsIntegration:
    def test_real_registry_has_languages(self):
        """验证全局注册中心包含语言（CI 上可能少于10种）"""
        from yanpub.core.adapter.registry import get_registry

        gen = DocsGenerator(get_registry())
        languages = gen.list_all_languages()
        assert len(languages) >= 1, "没有语言加载成功"

    def test_real_comparison_table(self):
        """验证全局注册中心的对比表可以生成"""
        from yanpub.core.adapter.registry import get_registry

        gen = DocsGenerator(get_registry())
        table = gen.generate_comparison_table()
        assert len(table) > 0

    def test_real_keyword_search(self):
        """验证跨语言关键字搜索"""
        from yanpub.core.adapter.registry import get_registry

        gen = DocsGenerator(get_registry())
        results = gen.search_keywords("定义")
        # 至少3种语言有"定义"
        assert len(results) >= 3

    def test_real_similarity(self):
        """验证语言相似度计算"""
        from yanpub.core.adapter.registry import get_registry

        comp = LanguageComparator(get_registry())
        similarities = comp.compute_all_similarities()
        assert len(similarities) > 0
        # 所有相似度应在合理范围
        for sim in similarities:
            assert 0.0 < sim.similarity_score <= 1.0
