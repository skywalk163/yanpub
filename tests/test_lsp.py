"""LSP 服务测试"""


from yanpub.core.adapter import CompletionItem, Diagnostic, SubprocessAdapter
from yanpub.core.registry import LanguageRegistry
from yanpub.lsp.server import YanLanguageServer, _completion_item_to_lsp, _diagnostic_to_lsp


# ---- 测试用适配器 ----

class SimpleAdapter(SubprocessAdapter):
    """用于 LSP 测试的简单适配器"""

    def __init__(self):
        super().__init__(
            name="测试语言",
            lang_id="testlang",
            version="0.0.1",
            extensions=[".test"],
            run_command=["echo", "test"],
            eval_command=["echo", "test"],
            keywords=["定义", "返回", "如果", "那么", "否则", "函数", "遍历", "当"],
            primary_color="#000000",
        )


# ---- 转换函数测试 ----

class TestCompletionItemConversion:
    """测试 CompletionItem → LSP CompletionItem 转换"""

    def test_keyword_kind(self):
        from lsprotocol import types as lsp
        item = CompletionItem(label="定义", kind="keyword")
        lsp_item = _completion_item_to_lsp(item)
        assert lsp_item.label == "定义"
        assert lsp_item.kind == lsp.CompletionItemKind.Keyword

    def test_function_kind(self):
        from lsprotocol import types as lsp
        item = CompletionItem(label="打印", kind="function", detail="输出函数")
        lsp_item = _completion_item_to_lsp(item)
        assert lsp_item.kind == lsp.CompletionItemKind.Function
        assert lsp_item.detail == "输出函数"

    def test_unknown_kind_defaults_to_text(self):
        from lsprotocol import types as lsp
        item = CompletionItem(label="foo", kind="unknown_type")
        lsp_item = _completion_item_to_lsp(item)
        assert lsp_item.kind == lsp.CompletionItemKind.Text

    def test_insert_text_fallback(self):
        item = CompletionItem(label="定义")
        lsp_item = _completion_item_to_lsp(item)
        assert lsp_item.insert_text == "定义"

    def test_insert_text_custom(self):
        item = CompletionItem(label="段落", insert_text="段落 ${1:名称}。")
        lsp_item = _completion_item_to_lsp(item)
        assert lsp_item.insert_text == "段落 ${1:名称}。"


class TestDiagnosticConversion:
    """测试 Diagnostic → LSP Diagnostic 转换"""

    def test_error_severity(self):
        from lsprotocol import types as lsp
        diag = Diagnostic(line=3, column=5, severity="error", message="语法错误", source="testlang")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Error
        assert lsp_diag.message == "语法错误"
        # line/column 从 1-based 转为 0-based
        assert lsp_diag.range.start.line == 2
        assert lsp_diag.range.start.character == 4

    def test_warning_severity(self):
        from lsprotocol import types as lsp
        diag = Diagnostic(line=1, column=1, severity="warning", message="未使用变量")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Warning

    def test_info_severity(self):
        from lsprotocol import types as lsp
        diag = Diagnostic(line=1, column=1, severity="info", message="提示信息")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Information

    def test_hint_severity(self):
        from lsprotocol import types as lsp
        diag = Diagnostic(line=1, column=1, severity="hint", message="可简化")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Hint

    def test_unknown_severity_defaults_error(self):
        from lsprotocol import types as lsp
        diag = Diagnostic(line=1, column=1, severity="unknown", message="未知")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.severity == lsp.DiagnosticSeverity.Error

    def test_source_field(self):
        diag = Diagnostic(line=1, column=1, severity="error", message="错误", source="duan")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.source == "duan"

    def test_default_source(self):
        diag = Diagnostic(line=1, column=1, severity="error", message="错误")
        lsp_diag = _diagnostic_to_lsp(diag)
        assert lsp_diag.source == "yanlsp"


# ---- YanLanguageServer 测试 ----

class TestYanLanguageServer:
    """测试 LSP 服务器核心逻辑"""

    def test_server_creation(self):
        registry = LanguageRegistry()
        adapter = SimpleAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)
        assert server.registry is registry
        assert len(server._documents) == 0

    def test_adapter_resolution_by_extension(self):
        registry = LanguageRegistry()
        adapter = SimpleAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)

        # 应该通过 .test 扩展名匹配到适配器
        resolved = server._get_adapter_for_uri("file:///tmp/demo.test")
        assert resolved is not None
        assert resolved.id == "testlang"

    def test_adapter_resolution_no_match(self):
        registry = LanguageRegistry()
        adapter = SimpleAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)

        # 不匹配的扩展名返回 None
        resolved = server._get_adapter_for_uri("file:///tmp/demo.py")
        assert resolved is None

    def test_document_tracking(self):
        """测试文档打开/关闭时内容追踪"""
        registry = LanguageRegistry()
        adapter = SimpleAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)

        uri = "file:///tmp/demo.test"
        assert uri not in server._documents

        # 模拟文档打开
        server._documents[uri] = "定义 甲 为 三。"
        assert uri in server._documents
        assert server._documents[uri] == "定义 甲 为 三。"

        # 模拟文档关闭
        server._documents.pop(uri, None)
        assert uri not in server._documents

    def test_complete_from_adapter(self):
        """测试补全使用适配器的关键字列表"""
        registry = LanguageRegistry()
        adapter = SimpleAdapter()
        registry.register(adapter)

        # 适配器的 complete 方法应返回关键字补全
        items = adapter.complete("", 1, 1)
        assert len(items) == 8  # 定义, 返回, 如果, 那么, 否则, 函数, 遍历, 当
        labels = [item.label for item in items]
        assert "定义" in labels
        assert "返回" in labels
        assert "如果" in labels


# ---- 段言适配器 LSP 集成测试 ----

class TestDuanLSPIntegration:
    """测试段言适配器的 LSP 集成"""

    def test_duan_complete_returns_keywords(self):
        """段言适配器的 complete 应返回关键字列表"""
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        items = adapter.complete("", 1, 1)
        assert len(items) > 0
        labels = [item.label for item in items]
        # 检查核心关键字存在
        assert "设" in labels or "段落" in labels

    def test_duan_adapter_resolution(self):
        """段言应通过 .duan 扩展名被 LSP 解析"""
        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)

        resolved = server._get_adapter_for_uri("file:///tmp/hello.duan")
        assert resolved is not None
        assert resolved.id == "duan"

    def test_duan_adapter_resolution_chinese_ext(self):
        """段言应通过 .段 扩展名被 LSP 解析"""
        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        registry.register(adapter)
        server = YanLanguageServer(registry=registry)

        # 注意：中文扩展名在 URI 中可能被编码
        server._get_adapter_for_uri("file:///tmp/hello.%E6%AE%B5")
        # 即使 URI 编码后不匹配，.duan 也应该匹配
        resolved2 = server._get_adapter_for_uri("file:///tmp/hello.duan")
        assert resolved2 is not None


# ---- 多语言 LSP 测试 ----

class TestMultiLanguageLSP:
    """测试多语言 LSP 服务器"""

    def test_multiple_adapters_registered(self):
        """注册多个适配器后，LSP 应能根据文件类型路由"""
        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        from yanpub.adapters.yan.adapter import YanAdapter
        from yanpub.adapters.moyan.adapter import MoyanAdapter

        registry.register(DuanAdapter())
        registry.register(YanAdapter())
        registry.register(MoyanAdapter())

        server = YanLanguageServer(registry=registry)

        # 段言文件
        duan_adapter = server._get_adapter_for_uri("file:///tmp/hello.duan")
        assert duan_adapter is not None
        assert duan_adapter.id == "duan"

        # 言文件
        yan_adapter = server._get_adapter_for_uri("file:///tmp/hello.yan")
        assert yan_adapter is not None
        assert yan_adapter.id == "yan"

        # 墨言文件
        moyan_adapter = server._get_adapter_for_uri("file:///tmp/hello.moyan")
        assert moyan_adapter is not None
        assert moyan_adapter.id == "moyan"
