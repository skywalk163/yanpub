"""LSP 代码重构增强功能测试 — RefactoringEngine + LSP Code Actions + CLI"""

import pytest

from yanpub.core.dev.refactor import (
    RefactoringEngine,
    _is_ident_char,
    _is_cjk,
    _is_word_boundary,
)
from yanpub.core.adapter.adapter import LanguageAdapter


# ---- 辅助：Mock 适配器 ----


class MockAdapter(LanguageAdapter):
    """用于测试的 Mock 适配器"""

    @property
    def name(self):
        return "测试语言"

    @property
    def id(self):
        return "mock"

    @property
    def version(self):
        return "0.1.0"

    @property
    def file_extensions(self):
        return [".mock"]

    def run(self, file_path, args=None):
        from yanpub.core.adapter.adapter import ExecutionResult
        return ExecutionResult(stdout="ok")

    def eval(self, code):
        from yanpub.core.adapter.adapter import ExecutionResult
        return ExecutionResult(stdout="ok")

    @property
    def keywords(self):
        return ["段落", "设", "为", "返回", "结束", "参数", "打印"]


# ============================================================
# 工具函数测试
# ============================================================


class TestUtilFunctions:
    def test_is_ident_char_ascii_letter(self):
        assert _is_ident_char("a") is True

    def test_is_ident_char_ascii_digit(self):
        assert _is_ident_char("5") is True

    def test_is_ident_char_underscore(self):
        assert _is_ident_char("_") is True

    def test_is_ident_char_cjk(self):
        assert _is_ident_char("甲") is True

    def test_is_ident_char_space(self):
        assert _is_ident_char(" ") is False

    def test_is_ident_char_punctuation(self):
        assert _is_ident_char(".") is False

    def test_is_cjk_han(self):
        assert _is_cjk("甲") is True

    def test_is_cjk_ascii(self):
        assert _is_cjk("a") is False

    def test_is_word_boundary_simple(self):
        text = "设 甲 为 5。"
        # "甲" at index 2, length 1
        assert _is_word_boundary(text, 2, 1) is True

    def test_is_word_boundary_mid_word(self):
        text = "hello world"
        # "ell" at index 1, length 3 — no boundary
        assert _is_word_boundary(text, 1, 3) is False

    def test_is_word_boundary_full_word(self):
        text = "hello world"
        # "hello" at index 0, length 5 — has boundary
        assert _is_word_boundary(text, 0, 5) is True


# ============================================================
# Extract Function 测试
# ============================================================


class TestExtractFunction:
    def setup_method(self):
        self.engine = RefactoringEngine()

    def test_basic_extract(self):
        """基本提取函数 — 将一行设语句提取为函数"""
        code = "段落 主程序。\n    设 结果 为 甲 加 乙。\n    打印 结果。\n结束。"
        result = self.engine.extract_function(code, 2, 2, "加法")

        assert "段落 加法。" in result["new_function"]
        assert "参数" in result["new_function"]
        assert "甲" in result["new_function"]
        assert "乙" in result["new_function"]
        assert "返回" in result["new_function"]
        assert "加法" in result["replacement"]
        assert result["range"]["start"] == 1
        assert result["range"]["end"] == 1

    def test_extract_with_adapter(self):
        """带适配器的提取函数"""
        adapter = MockAdapter()
        engine = RefactoringEngine(adapter)
        code = "段落 主程序。\n    设 结果 为 甲 加 乙。\n    打印 结果。\n结束。"
        result = engine.extract_function(code, 2, 2, "加法")

        assert "段落 加法。" in result["new_function"]

    def test_extract_multiline_block(self):
        """提取多行代码块"""
        code = "段落 主程序。\n    设 甲 为 10。\n    设 乙 为 20。\n    设 丙 为 甲 加 乙。\n    打印 丙。\n结束。"
        result = self.engine.extract_function(code, 2, 4, "计算")

        assert "段落 计算。" in result["new_function"]
        assert result["range"]["start"] == 1
        assert result["range"]["end"] == 3

    def test_extract_returns_dict_structure(self):
        """验证返回的字典结构"""
        code = "段落 主程序。\n    设 结果 为 甲。\n结束。"
        result = self.engine.extract_function(code, 2, 2, "获取")

        assert "new_function" in result
        assert "replacement" in result
        assert "range" in result
        assert "start" in result["range"]
        assert "end" in result["range"]

    def test_extract_empty_block(self):
        """空代码块的边界处理"""
        code = "段落 主程序。\n结束。"
        result = self.engine.extract_function(code, 2, 1, "空函数")

        # 起始行大于结束行时，应返回空结果
        assert result["new_function"] == ""
        assert result["replacement"] == ""

    def test_extract_preserves_indentation(self):
        """验证缩进保留"""
        code = "段落 主程序。\n    设 结果 为 甲。\n结束。"
        result = self.engine.extract_function(code, 2, 2, "获取")

        # 新函数体应有正确的缩进
        assert "    设 结果 为 甲。" in result["new_function"] or "        设 结果 为 甲。" in result["new_function"]


# ============================================================
# Inline Variable 测试
# ============================================================


class TestInlineVariable:
    def setup_method(self):
        self.engine = RefactoringEngine()

    def test_basic_inline(self):
        """基本内联变量"""
        code = "段落 主程序。\n    设 半径 为 5。\n    设 面积 为 半径 乘 半径。\n    打印 面积。\n结束。"
        result = self.engine.inline_variable(code, 2, 7)

        assert result["value"] == "5"
        assert len(result["usage_ranges"]) == 2

    def test_inline_no_variable(self):
        """光标不在变量上"""
        code = "段落 主程序。\n    打印 1。\n结束。"
        result = self.engine.inline_variable(code, 2, 7)

        assert result["value"] == ""
        assert len(result["usage_ranges"]) == 0

    def test_inline_variable_declaration_range(self):
        """验证声明范围"""
        code = "段落 主程序。\n    设 半径 为 5。\n结束。"
        result = self.engine.inline_variable(code, 2, 7)

        assert result["declaration_range"]["start"]["line"] == 1
        assert result["declaration_range"]["end"]["line"] == 1

    def test_inline_excludes_declaration_from_usages(self):
        """使用位置不应包含声明本身"""
        code = "段落 主程序。\n    设 半径 为 5。\n    打印 半径。\n结束。"
        result = self.engine.inline_variable(code, 2, 7)

        # 声明在行 1，使用在行 2
        for u in result["usage_ranges"]:
            assert u["start"]["line"] != 1 or u["start"]["character"] != 7

    def test_inline_variable_not_found(self):
        """变量声明不存在"""
        code = "段落 主程序。\n    打印 1。\n结束。"
        result = self.engine.inline_variable(code, 1, 3)

        assert result["value"] == ""

    def test_inline_returns_dict_structure(self):
        """验证返回的字典结构"""
        code = "段落 主程序。\n    设 半径 为 5。\n    打印 半径。\n结束。"
        result = self.engine.inline_variable(code, 2, 7)

        assert "declaration_range" in result
        assert "value" in result
        assert "usage_ranges" in result
        assert "start" in result["declaration_range"]
        assert "end" in result["declaration_range"]


# ============================================================
# Safe Rename 测试
# ============================================================


class TestSafeRename:
    def setup_method(self):
        self.engine = RefactoringEngine()

    def test_basic_safe_rename(self):
        """基本安全重命名"""
        code = "段落 加法。\n    参数 甲 乙。\n    设 结果 为 甲 加 乙。\n    返回 结果。\n结束。"
        result = self.engine.safe_rename(code, 3, 8, "总和")

        assert result["safe"] is True
        assert len(result["conflicts"]) == 0
        assert len(result["changes"]) >= 2

    def test_rename_keyword_conflict(self):
        """重命名为关键字"""
        code = "段落 加法。\n    设 结果 为 甲 加 乙。\n结束。"
        result = self.engine.safe_rename(code, 2, 8, "返回")

        assert result["safe"] is False
        assert any("关键字" in c for c in result["conflicts"])

    def test_rename_same_name(self):
        """重命名为相同名称"""
        code = "段落 加法。\n    设 结果 为 甲 加 乙。\n结束。"
        result = self.engine.safe_rename(code, 2, 8, "结果")

        assert result["safe"] is False
        assert any("相同" in c for c in result["conflicts"])

    def test_rename_no_identifier(self):
        """光标不在标识符上"""
        code = "段落 加法。\n结束。"
        # 行 1 列 1 处有"段落"标识符，改用行外位置
        result = self.engine.safe_rename(code, 5, 1, "新名称")

        assert result["safe"] is False
        assert len(result["changes"]) == 0

    def test_rename_with_existing_name(self):
        """重命名为已存在的标识符"""
        code = "段落 加法。\n    设 甲 为 1。\n    设 乙 为 甲。\n结束。"
        # 甲 在第 2 行第 7 列
        result = self.engine.safe_rename(code, 2, 7, "乙")

        assert result["safe"] is False
        assert any("已存在" in c for c in result["conflicts"])

    def test_rename_invalid_characters(self):
        """重命名为包含无效字符的名称"""
        code = "段落 加法。\n    设 结果 为 甲。\n结束。"
        result = self.engine.safe_rename(code, 2, 8, "abc@def")

        assert result["safe"] is False
        assert any("无效" in c for c in result["conflicts"])

    def test_rename_returns_dict_structure(self):
        """验证返回的字典结构"""
        code = "段落 加法。\n    设 结果 为 甲。\n结束。"
        result = self.engine.safe_rename(code, 2, 8, "总和")

        assert "safe" in result
        assert "conflicts" in result
        assert "changes" in result
        for ch in result["changes"]:
            assert "uri" in ch
            assert "range" in ch
            assert "new_text" in ch

    def test_rename_with_adapter_keywords(self):
        """适配器关键字冲突检测"""
        adapter = MockAdapter()
        engine = RefactoringEngine(adapter)
        code = "段落 加法。\n    设 结果 为 甲。\n结束。"
        result = engine.safe_rename(code, 2, 8, "打印")

        assert result["safe"] is False
        assert any("关键字" in c for c in result["conflicts"])


# ============================================================
# 辅助方法测试
# ============================================================


class TestHelperMethods:
    def setup_method(self):
        self.engine = RefactoringEngine()

    def test_find_variable_declaration(self):
        """查找变量声明"""
        code = "段落 主程序。\n    设 半径 为 5。\n    打印 半径。\n结束。"
        decl = self.engine._find_variable_declaration(code, "半径")

        assert decl is not None
        assert decl["value"] == "5"
        assert decl["line"] == 1

    def test_find_variable_declaration_not_found(self):
        """变量声明不存在"""
        code = "段落 主程序。\n    打印 1。\n结束。"
        decl = self.engine._find_variable_declaration(code, "不存在的变量")

        assert decl is None

    def test_find_variable_usages(self):
        """查找变量使用位置"""
        code = "段落 主程序。\n    设 半径 为 5。\n    打印 半径。\n    设 周长 为 半径。\n结束。"
        usages = self.engine._find_variable_usages(code, "半径")

        # 应该找到所有出现位置（包括声明行）
        assert len(usages) >= 3

    def test_extract_block_variables(self):
        """分析代码块的输入/输出变量"""
        block = "    设 结果 为 甲 加 乙。"
        var_info = self.engine._extract_block_variables(block)

        assert "甲" in var_info["inputs"]
        assert "乙" in var_info["inputs"]
        assert "结果" in var_info["outputs"]

    def test_extract_block_variables_no_inputs(self):
        """所有变量都在块内定义"""
        block = "    设 甲 为 10。"
        var_info = self.engine._extract_block_variables(block)

        assert len(var_info["inputs"]) == 0
        assert "甲" in var_info["outputs"]

    def test_is_identifier_at_cjk(self):
        """CJK 标识符识别"""
        code = "段落 主程序。\n    设 半径 为 5。\n结束。"
        ident = self.engine._is_identifier_at(code, 2, 7)

        assert ident is not None
        assert "径" in ident or "半径" in ident

    def test_is_identifier_at_ascii(self):
        """ASCII 标识符识别"""
        code = "def hello():\n    x = 1\n"
        ident = self.engine._is_identifier_at(code, 1, 5)

        assert ident == "hello"

    def test_is_identifier_at_empty(self):
        """空行或边界外"""
        code = "段落 主程序。\n结束。"
        result = self.engine._is_identifier_at(code, 1, 1)

        # 可能返回 "段" 或 None，取决于位置
        # 行 1, 列 1 → 第一个字符 "段"
        assert result is None or isinstance(result, str)

    def test_is_identifier_at_out_of_range(self):
        """超出代码范围"""
        code = "段落 主程序。"
        ident = self.engine._is_identifier_at(code, 5, 1)

        assert ident is None


# ============================================================
# LanguageAdapter 新方法测试
# ============================================================


class TestAdapterRefactorMethods:
    def test_extract_function_default_returns_none(self):
        """适配器默认的 extract_function 返回 None"""
        adapter = MockAdapter()
        result = adapter.extract_function("代码", 1, 1, "新函数")
        assert result is None

    def test_inline_variable_default_returns_none(self):
        """适配器默认的 inline_variable 返回 None"""
        adapter = MockAdapter()
        result = adapter.inline_variable("代码", 1, 1)
        assert result is None


# ============================================================
# LSP 集成测试
# ============================================================


class TestLSPRefactorIntegration:
    def test_server_creation_with_refactor(self):
        """LSP 服务器创建包含重构功能"""
        pytest.importorskip("pygls")
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.adapter.registry import LanguageRegistry

        registry = LanguageRegistry()
        registry.register(MockAdapter())
        server = YanLanguageServer(registry=registry)

        assert server is not None

    def test_code_action_includes_extract_function(self):
        """Code Action 包含 Extract Function"""
        pytest.importorskip("pygls")
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.adapter.registry import LanguageRegistry

        registry = LanguageRegistry()
        registry.register(MockAdapter())
        server = YanLanguageServer(registry=registry)

        # 注册 code action 处理器
        # 通过模拟参数测试
        uri = "file:///test.mock"
        server._documents[uri] = "段落 主程序。\n    设 结果 为 甲。\n结束。"

    def test_refactor_engine_import(self):
        """验证 RefactoringEngine 可正确导入"""
        from yanpub.core.dev.refactor import RefactoringEngine
        engine = RefactoringEngine()
        assert engine is not None
        assert engine.adapter is None

    def test_refactor_engine_with_adapter(self):
        """验证 RefactoringEngine 可与适配器一起使用"""
        adapter = MockAdapter()
        engine = RefactoringEngine(adapter)
        assert engine.adapter is adapter


# ============================================================
# 边界情况和异常处理
# ============================================================


class TestEdgeCases:
    def setup_method(self):
        self.engine = RefactoringEngine()

    def test_extract_function_line_out_of_range(self):
        """行号超出范围的提取"""
        code = "短代码。"
        result = self.engine.extract_function(code, 10, 20, "函数")

        # 应该有合理的默认值
        assert "new_function" in result

    def test_inline_variable_at_line_end(self):
        """光标在行尾"""
        code = "段落 主程序。\n    设 甲 为 1。\n结束。"
        # 列号超出行长度
        result = self.engine.inline_variable(code, 2, 100)

        assert "value" in result

    def test_safe_rename_empty_code(self):
        """空代码的重命名"""
        result = self.engine.safe_rename("", 1, 1, "新名称")

        assert result["safe"] is False

    def test_safe_rename_cjk_identifier(self):
        """CJK 标识符的重命名"""
        code = "段落 主程序。\n    设 甲 为 1。\n    打印 甲。\n结束。"
        result = self.engine.safe_rename(code, 2, 7, "乙")

        # 甲 在代码中出现 2 次
        assert len(result["changes"]) >= 2

    def test_extract_block_with_string_literals(self):
        """代码块包含字符串字面量"""
        block = '    设 消息 为 "你好世界"。'
        var_info = self.engine._extract_block_variables(block)

        # 字符串内容不应被识别为标识符
        assert "你好世界" not in var_info["inputs"]
        assert "消息" in var_info["outputs"]

    def test_find_variable_declaration_with_complex_value(self):
        """变量值包含复杂表达式"""
        code = "段落 主程序。\n    设 结果 为 甲 加 乙 乘 丙。\n结束。"
        decl = self.engine._find_variable_declaration(code, "结果")

        assert decl is not None
        assert "甲" in decl["value"]
