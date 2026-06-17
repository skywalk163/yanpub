"""v0.2.0 新功能测试

覆盖:
- 关键字预缓存
- LSP hover 文档
- REPL 多行续行
- 包发布验证
- 关键字文档分类
"""

from __future__ import annotations

import json
from pathlib import Path


from yanpub.core.keyword_docs import categorize_keyword, get_keyword_doc, KEYWORD_CATEGORIES
from yanpub.repl.core import _needs_continuation
from yanpub.adapters._keywords_cache import load_cached_keywords


# ---- 关键字预缓存 ----

class TestKeywordsCache:
    """关键字缓存测试"""

    def test_cache_file_exists_for_all_adapters(self):
        """所有适配器都有 keywords.json 缓存"""
        from yanpub.core.registry import get_registry
        adapters_dir = Path(__file__).resolve().parent.parent / "src" / "yanpub" / "adapters"
        registry = get_registry()
        for adapter in registry:
            cache_file = adapters_dir / adapter.id / "keywords.json"
            assert cache_file.exists(), f"缺少缓存文件: {adapter.id}/keywords.json"

    def test_cache_file_is_valid_json(self):
        """缓存文件是合法 JSON"""
        adapters_dir = Path(__file__).resolve().parent.parent / "src" / "yanpub" / "adapters"
        from yanpub.core.registry import get_registry
        registry = get_registry()
        for adapter in registry:
            cache_file = adapters_dir / adapter.id / "keywords.json"
            if cache_file.exists():
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                assert isinstance(data, list), f"{adapter.id}: 缓存不是列表"
                assert len(data) > 0, f"{adapter.id}: 缓存为空"

    def test_load_cached_keywords_returns_list(self):
        """load_cached_keywords 返回列表"""
        result = load_cached_keywords("duan")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_load_cached_keywords_fallback(self):
        """缓存不存在时走 fallback"""
        result = load_cached_keywords("nonexistent_lang", fallback=["默认"])
        assert result == ["默认"]

    def test_load_cached_keywords_dynamic_fallback(self):
        """缓存和动态加载都失败时走 fallback"""
        result = load_cached_keywords(
            "nonexistent_lang",
            dynamic_loader=lambda: [],
            fallback=["兜底"],
        )
        assert result == ["兜底"]

    def test_adapter_keywords_match_cache(self):
        """适配器关键字与缓存一致"""
        from yanpub.core.registry import get_registry
        adapters_dir = Path(__file__).resolve().parent.parent / "src" / "yanpub" / "adapters"
        registry = get_registry()
        for adapter in registry:
            cache_file = adapters_dir / adapter.id / "keywords.json"
            if cache_file.exists():
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                assert adapter.keywords == cached, f"{adapter.id}: 关键字与缓存不一致"


# ---- 关键字分类文档 ----

class TestKeywordDocs:
    """关键字分类和 hover 文档测试"""

    def test_categorize_known_keywords(self):
        """已知关键字分类正确"""
        assert categorize_keyword("设") == "定义"
        assert categorize_keyword("如果") == "控制流"
        assert categorize_keyword("加") == "运算"
        assert categorize_keyword("真") == "逻辑值"
        assert categorize_keyword("打印") == "IO"
        assert categorize_keyword("类") == "类与对象"

    def test_categorize_unknown_keyword(self):
        """未知关键字返回'其他'"""
        assert categorize_keyword("未知关键字") == "其他"

    def test_get_keyword_doc_returns_markdown(self):
        """get_keyword_doc 返回 Markdown 文档"""
        doc = get_keyword_doc("设", "段言")
        assert doc is not None
        assert "**设**" in doc
        assert "段言" in doc
        assert "定义" in doc

    def test_get_keyword_doc_unknown_returns_none(self):
        """未知关键字返回 None"""
        doc = get_keyword_doc("未知关键字")
        assert doc is None

    def test_keyword_categories_not_empty(self):
        """分类映射非空"""
        assert len(KEYWORD_CATEGORIES) > 0
        for cat, keywords in KEYWORD_CATEGORIES.items():
            assert len(keywords) > 0, f"分类 {cat} 无关键字"


# ---- LSP hover ----

class TestLSPHover:
    """LSP hover 功能测试"""

    def test_adapter_hover_on_keyword(self):
        """适配器 hover 返回关键字文档"""
        from yanpub.core.registry import get_registry
        registry = get_registry()
        # 使用段言测试
        adapter = registry.get("duan")
        if adapter:
            doc = adapter.hover("设甲为三。", 1, 1)
            assert doc is not None
            assert "设" in doc

    def test_adapter_hover_on_non_keyword(self):
        """非关键字位置返回 None"""
        from yanpub.core.registry import get_registry
        registry = get_registry()
        adapter = registry.get("duan")
        if adapter:
            doc = adapter.hover("123", 1, 1)
            # 数字不在关键字列表中
            assert doc is None

    def test_adapter_hover_out_of_range(self):
        """超出范围返回 None"""
        from yanpub.core.registry import get_registry
        registry = get_registry()
        adapter = registry.get("duan")
        if adapter:
            doc = adapter.hover("设甲为三", 5, 1)
            assert doc is None


# ---- REPL 多行续行 ----

class TestREPLContinuation:
    """REPL 多行续行检测测试"""

    def test_simple_statement_no_continuation(self):
        """简单语句不需要续行"""
        assert not _needs_continuation("设甲为三。")

    def test_unclosed_quote_continuation(self):
        """未闭合引号需要续行"""
        assert _needs_continuation('打印("hello')

    def test_unclosed_paren_continuation(self):
        """未闭合括号需要续行"""
        assert _needs_continuation("函数(参数")

    def test_block_keyword_continuation(self):
        """块关键字后需要续行"""
        assert _needs_continuation("如果")
        assert _needs_continuation("当")
        assert _needs_continuation("函数")

    def test_colon_continuation(self):
        """冒号结尾需要续行"""
        assert _needs_continuation("如果 条件:")

    def test_complete_code_no_continuation(self):
        """完整代码不需要续行"""
        assert not _needs_continuation("打印(\"hello\")")

    def test_empty_no_continuation(self):
        """空代码不需要续行"""
        assert not _needs_continuation("")
        assert not _needs_continuation("   ")

    def test_multiline_with_unclosed(self):
        """多行代码中有未闭合结构"""
        code = "如果 条件:\n  打印(\"hello"
        assert _needs_continuation(code)


# ---- 包发布验证 ----

class TestPkgPublishValidation:
    """包发布验证测试"""

    def test_version_parse(self):
        """版本号解析"""
        from yanpub.pkg.resolver import DependencyResolver
        assert DependencyResolver._parse_version("1.0.0") == (1, 0, 0)
        assert DependencyResolver._parse_version("0.2.0") == (0, 2, 0)
        assert DependencyResolver._parse_version("2.1.3-alpha") == (2, 1, 3)

    def test_version_comparison(self):
        """版本号比较"""
        from yanpub.pkg.resolver import DependencyResolver
        v = DependencyResolver._parse_version
        assert v("1.0.0") < v("2.0.0")
        assert v("1.0.0") < v("1.1.0")
        assert v("1.0.0") < v("1.0.1")

    def test_semver_regex(self):
        """semver 正则验证"""
        import re
        semver = re.compile(r'^\d+\.\d+\.\d+([a-zA-Z0-9.+-]*)?$')
        assert semver.match("1.0.0")
        assert semver.match("0.2.0")
        assert semver.match("1.0.0-alpha")
        assert semver.match("2.1.3-beta.1")
        assert not semver.match("1.0")
        assert not semver.match("abc")

    def test_package_name_regex(self):
        """包名正则验证"""
        import re
        pkg_name = re.compile(r'^[a-zA-Z0-9_-]+$')
        assert pkg_name.match("web-framework")
        assert pkg_name.match("math_utils")
        assert pkg_name.match("core")
        assert not pkg_name.match("web framework")
        assert not pkg_name.match("中文包名")
