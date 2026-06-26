"""适配器协议与注册中心测试"""

import pytest

from yanpub.core.adapter.adapter import (
    ExecutionResult,
    CompletionItem,
    SubprocessAdapter,
)
from yanpub.core.adapter.registry import LanguageRegistry


# ---- 测试用简单适配器 ----

class MockAdapter(SubprocessAdapter):
    def __init__(self):
        super().__init__(
            name="测试语言",
            lang_id="mock",
            version="0.0.1",
            extensions=[".mock"],
            run_command=["echo", "mock"],
            eval_command=["echo", "mock"],
            keywords=["定义", "返回", "若", "则"],
            primary_color="#000000",
        )


# ---- ExecutionResult 测试 ----

class TestExecutionResult:
    def test_success(self):
        r = ExecutionResult(stdout="hello", exit_code=0)
        assert r.success is True

    def test_failure(self):
        r = ExecutionResult(stderr="error", exit_code=1)
        assert r.success is False


# ---- CompletionItem 测试 ----

class TestCompletionItem:
    def test_insert_text_default(self):
        item = CompletionItem(label="定义")
        assert item.insert_text == "定义"

    def test_insert_text_custom(self):
        item = CompletionItem(label="定义函数", insert_text="定义 ")
        assert item.insert_text == "定义 "


# ---- MockAdapter 测试 ----

class TestMockAdapter:
    def test_metadata(self):
        a = MockAdapter()
        assert a.name == "测试语言"
        assert a.id == "mock"
        assert a.version == "0.0.1"
        assert a.file_extensions == [".mock"]

    def test_keywords(self):
        a = MockAdapter()
        assert "定义" in a.keywords
        assert len(a.keywords) == 4

    def test_complete_default(self):
        a = MockAdapter()
        items = a.complete("定义", 1, 1)
        assert len(items) == len(a.keywords)
        assert all(item.kind == "keyword" for item in items)

    def test_capabilities(self):
        a = MockAdapter()
        caps = a.capabilities
        assert caps["repl"] is True
        assert caps["lsp"] is True  # 有关键字就能提供基本 LSP


# ---- LanguageRegistry 测试 ----

class TestLanguageRegistry:
    def test_register_and_get(self):
        reg = LanguageRegistry()
        adapter = MockAdapter()
        reg.register(adapter)
        assert reg.get("mock") is adapter
        assert "mock" in reg

    def test_get_not_found(self):
        reg = LanguageRegistry()
        assert reg.get("nonexistent") is None

    def test_get_or_raise(self):
        reg = LanguageRegistry()
        with pytest.raises(KeyError, match="未注册的语言"):
            reg.get_or_raise("nonexistent")

    def test_list_languages(self):
        reg = LanguageRegistry()
        reg.register(MockAdapter())
        langs = reg.list_languages()
        assert len(langs) == 1
        assert langs[0]["id"] == "mock"
        assert langs[0]["name"] == "测试语言"

    def test_unregister(self):
        reg = LanguageRegistry()
        reg.register(MockAdapter())
        reg.unregister("mock")
        assert "mock" not in reg

    def test_language_ids(self):
        reg = LanguageRegistry()
        reg.register(MockAdapter())
        assert reg.language_ids == ["mock"]

    def test_len(self):
        reg = LanguageRegistry()
        assert len(reg) == 0
        reg.register(MockAdapter())
        assert len(reg) == 1

    def test_iter(self):
        reg = LanguageRegistry()
        adapter = MockAdapter()
        reg.register(adapter)
        assert list(reg) == [adapter]
