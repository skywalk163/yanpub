"""语法对比矩阵功能测试"""

from __future__ import annotations

import pytest

from yanpub.core.syntax_matrix import (
    CONCEPTS,
    SNIPPETS,
    SyntaxConcept,
    SyntaxMatrix,
)


class TestSyntaxConcept:
    """测试 SyntaxConcept 数据类"""

    def test_concept_fields(self):
        c = SyntaxConcept("test", "测试", "基础", "一个测试概念", "入门")
        assert c.id == "test"
        assert c.title == "测试"
        assert c.category == "基础"
        assert c.description == "一个测试概念"
        assert c.difficulty == "入门"

    def test_concepts_defined(self):
        assert len(CONCEPTS) >= 10
        ids = [c.id for c in CONCEPTS]
        # 确保核心概念都存在
        assert "hello" in ids
        assert "var_declare" in ids
        assert "func_def" in ids
        assert "if_else" in ids
        assert "while_loop" in ids
        assert "recursion" in ids

    def test_concept_categories(self):
        categories = set(c.category for c in CONCEPTS)
        assert "基础" in categories
        assert "函数" in categories
        assert "控制流" in categories


class TestSnippets:
    """测试代码片段数据"""

    def test_all_concepts_have_snippets(self):
        concept_ids = [c.id for c in CONCEPTS]
        for cid in concept_ids:
            assert cid in SNIPPETS, f"概念 {cid} 缺少代码片段"

    def test_all_languages_have_snippets(self):
        """至少5种主要语言在每个概念下都有代码片段"""
        main_langs = ["duan", "yan", "moyan", "zhixing", "mingdao"]
        for concept_id, snippets in SNIPPETS.items():
            for lang_id in main_langs:
                assert lang_id in snippets, f"概念 {concept_id} 缺少 {lang_id} 的代码片段"

    def test_snippet_entry_fields(self):
        entry = SNIPPETS["hello"]["duan"]
        assert entry.lang_id == "duan"
        assert "打印" in entry.code
        assert entry.note  # 应有风格说明

    def test_no_empty_snippets(self):
        for concept_id, snippets in SNIPPETS.items():
            for lang_id, entry in snippets.items():
                assert entry.code.strip(), f"概念 {concept_id} 语言 {lang_id} 的代码片段为空"

    def test_not_supported_marking(self):
        """不支持的语言特性应标注暂不支持"""
        class_snippets = SNIPPETS.get("class_def", {})
        # 其他语言应标注暂不支持
        for lang_id in ["yan", "moyan", "zhixing"]:
            if lang_id in class_snippets:
                assert (
                    "暂不支持" in class_snippets[lang_id].note
                    or "暂不支持" in class_snippets[lang_id].code
                )


class TestSyntaxMatrix:
    """测试 SyntaxMatrix 引擎"""

    @pytest.fixture
    def matrix(self):
        return SyntaxMatrix()

    def test_concepts(self, matrix):
        concepts = matrix.concepts
        assert len(concepts) >= 10

    def test_lang_ids(self, matrix):
        lang_ids = matrix.lang_ids
        assert len(lang_ids) >= 5
        assert "duan" in lang_ids
        assert "yan" in lang_ids

    def test_get_concept(self, matrix):
        concept = matrix.get_concept("hello")
        assert concept is not None
        assert concept.title == "你好世界"

    def test_get_concept_nonexistent(self, matrix):
        assert matrix.get_concept("nonexistent") is None

    def test_get_snippet(self, matrix):
        snippet = matrix.get_snippet("hello", "duan")
        assert snippet is not None
        assert snippet.lang_id == "duan"
        assert "打印" in snippet.code

    def test_get_snippet_nonexistent(self, matrix):
        assert matrix.get_snippet("nonexistent", "duan") is None
        assert matrix.get_snippet("hello", "nonexistent") is None

    def test_get_concept_snippets(self, matrix):
        snippets = matrix.get_concept_snippets("hello")
        assert len(snippets) >= 5
        assert "duan" in snippets

    def test_get_language_snippets(self, matrix):
        snippets = matrix.get_language_snippets("duan")
        assert len(snippets) >= 10
        assert "hello" in snippets
        assert "func_def" in snippets

    def test_get_matrix(self, matrix):
        m = matrix.get_matrix()
        assert len(m) >= 10
        # 每项应有 concept 和 snippets
        for entry in m:
            assert "concept" in entry
            assert "snippets" in entry
            assert len(entry["snippets"]) >= 1

    def test_get_categories(self, matrix):
        categories = matrix.get_categories()
        assert "基础" in categories
        assert "函数" in categories

    def test_get_concepts_by_category(self, matrix):
        basic = matrix.get_concepts_by_category("基础")
        assert len(basic) >= 2
        for c in basic:
            assert c.category == "基础"

    def test_compute_syntax_style(self, matrix):
        styles = matrix.compute_syntax_style()
        assert len(styles) >= 5

        # 段言应为"设…为…"风格
        duan_style = styles.get("duan", {})
        assert duan_style.get("变量风格") == "设…为…"
        assert duan_style.get("语句结束") == "中文句号 。"

        # 趣言应为"定…等于…"风格
        traeyan_style = styles.get("traeyan", {})
        assert traeyan_style.get("变量风格") == "定…等于…"

    def test_generate_html(self, matrix, tmp_path):
        html = matrix.generate_html()
        assert "<!DOCTYPE html>" in html
        assert "中文编程语言语法对比矩阵" in html
        assert "打印" in html  # 应包含代码片段内容

    def test_generate_html_to_file(self, matrix, tmp_path):
        out = tmp_path / "test_matrix.html"
        matrix.generate_html(out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_html_contains_all_languages(self, matrix):
        html = matrix.generate_html()
        # 应包含所有语言的名称
        from yanpub.core.adapter.registry import get_registry

        registry = get_registry()
        for adapter in registry:
            assert adapter.name in html

    def test_html_contains_concepts(self, matrix):
        html = matrix.generate_html()
        for concept in CONCEPTS:
            assert concept.title in html


class TestSyntaxMatrixIntegration:
    """集成测试 — 验证矩阵与注册中心的协作"""

    def test_all_registered_langs_in_matrix(self):
        from yanpub.core.adapter.registry import get_registry

        registry = get_registry()
        matrix = SyntaxMatrix()
        matrix_langs = set(matrix.lang_ids)
        for adapter in registry:
            assert adapter.id in matrix_langs, f"{adapter.name} ({adapter.id}) 不在矩阵中"

    def test_matrix_covers_key_concepts(self):
        """矩阵覆盖了关键概念"""
        matrix = SyntaxMatrix()
        matrix_data = matrix.get_matrix()
        concept_ids = [e["concept"].id for e in matrix_data]
        # 基础概念
        assert "hello" in concept_ids
        assert "var_declare" in concept_ids
        # 函数
        assert "func_def" in concept_ids
        # 控制流
        assert "if_else" in concept_ids
        assert "while_loop" in concept_ids

    def test_style_analysis_covers_all_langs(self):
        matrix = SyntaxMatrix()
        styles = matrix.compute_syntax_style()
        from yanpub.core.adapter.registry import get_registry

        registry = get_registry()
        for adapter in registry:
            assert adapter.id in styles, f"{adapter.name} ({adapter.id}) 缺少风格分析"
