"""REPL 核心组件测试"""

import pytest

from yanpub.core.adapter import SubprocessAdapter
from yanpub.core.registry import LanguageRegistry
from yanpub.repl.core import ChineseLangLexer, REPLCompleter, YanREPL


# ---- 测试用适配器 ----

class REPLTestAdapter(SubprocessAdapter):
    """用于 REPL 测试的适配器"""

    def __init__(self):
        super().__init__(
            name="测试语言",
            lang_id="testlang",
            version="0.0.1",
            extensions=[".test"],
            run_command=["echo", "test"],
            eval_command=["echo", "test"],
            keywords=["定义", "返回", "如果", "那么", "否则", "函数", "遍历", "当", "真", "假"],
            primary_color="#000000",
        )


# ---- ChineseLangLexer 测试 ----

class TestChineseLangLexer:
    """测试中文语言语法高亮器"""

    def test_keyword_highlight(self):
        """中文关键字应被识别为 keyword 类"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("定义 甲 为 三。", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        # "定义" 应该被高亮为 keyword
        keywords_found = [text for text, style in line_styles if style == "class:keyword"]
        assert "定义" in keywords_found

    def test_comment_highlight(self):
        """注释应被识别为 comment 类"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        # 默认 comment_syntax 是 "#"
        lexer = ChineseLangLexer(adapter)
        doc = Document("# 这是一个注释", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        comments = [text for text, style in line_styles if style == "class:comment"]
        assert any("注释" in c or "#" in c for c in comments)

    def test_string_highlight(self):
        """字符串应被识别为 string 类"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document('打印 "你好"。', cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        strings = [text for text, style in line_styles if style == "class:string"]
        assert any("你好" in s for s in strings)

    def test_number_highlight(self):
        """数字应被识别为 number 类"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("设 甲 为 42。", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        numbers = [text for text, style in line_styles if style == "class:number"]
        assert "42" in numbers

    def test_operator_highlight(self):
        """运算符应被识别为 operator 类"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("1 + 2", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        operators = [text for text, style in line_styles if style == "class:operator"]
        assert "+" in operators

    def test_empty_line(self):
        """空行不应出错"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        assert line_styles == []

    def test_non_keyword_chinese(self):
        """非关键字的中文应被识别为 identifier"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("甲乙丙", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        identifiers = [text for text, style in line_styles if style == "class:identifier"]
        assert "甲乙丙" in identifiers

    def test_comment_syntax_configurable(self):
        """注释语法应可配置"""
        from prompt_toolkit.document import Document

        class DashCommentAdapter(REPLTestAdapter):
            @property
            def comment_syntax(self):
                return "--"

        adapter = DashCommentAdapter()
        lexer = ChineseLangLexer(adapter)
        doc = Document("-- 墨言注释", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        comments = [text for text, style in line_styles if style == "class:comment"]
        assert len(comments) > 0


# ---- REPLCompleter 测试 ----

class TestREPLCompleter:
    """测试 REPL 补全器"""

    def test_command_completion(self):
        """冒号命令应能被补全"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document(":h", cursor_position=2)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert ":help" in texts

    def test_lang_command_completion(self):
        """:lang 后应能补全语言 ID"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document(":lang ", cursor_position=6)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "testlang" in texts

    def test_keyword_completion(self):
        """关键字应能被补全"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document("定", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "定义" in texts

    def test_all_commands_available(self):
        """所有内置命令应可补全"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document(":", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert ":help" in texts
        assert ":lang" in texts
        assert ":langs" in texts
        assert ":keywords" in texts
        assert ":quit" in texts

    def test_exact_keyword_not_in_completion(self):
        """已完整输入的关键字不应出现在补全中"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document("定义", cursor_position=2)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        # "定义" 是精确匹配，不应重复出现
        assert "定义" not in texts

    def test_partial_keyword_completion(self):
        """部分匹配的关键字应出现在补全中"""
        from prompt_toolkit.document import Document
        adapter = REPLTestAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        completer = REPLCompleter(adapter, registry)

        doc = Document("如", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        texts = [c.text for c in completions]
        assert "如果" in texts


# ---- YanREPL 测试 ----

class TestYanREPL:
    """测试 REPL 主类"""

    def test_repl_creation(self):
        """REPL 应能创建"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        assert repl.registry is registry

    def test_repl_no_adapter(self, capsys):
        """没有适配器时 REPL 应输出提示"""
        registry = LanguageRegistry()
        repl = YanREPL(registry=registry)
        repl.start()
        captured = capsys.readouterr()
        assert "没有可用的语言适配器" in captured.out

    def test_repl_welcome(self):
        """适配器的欢迎信息应正确"""
        adapter = REPLTestAdapter()
        assert "测试语言" in adapter.repl_welcome
        assert "0.0.1" in adapter.repl_welcome

    def test_repl_prompt(self):
        """适配器的提示符应包含语言名"""
        adapter = REPLTestAdapter()
        assert "测试语言" in adapter.repl_prompt

    def test_command_handling_quit(self):
        """:quit 命令应触发 KeyboardInterrupt"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)

        with pytest.raises(KeyboardInterrupt):
            repl._handle_command(":quit")

    def test_command_handling_exit(self):
        """:exit 命令应触发 KeyboardInterrupt"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)

        with pytest.raises(KeyboardInterrupt):
            repl._handle_command(":exit")

    def test_command_handling_langs(self, capsys):
        """:langs 命令应列出可用语言"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        repl._handle_command(":langs")
        captured = capsys.readouterr()
        assert "testlang" in captured.out
        assert "测试语言" in captured.out

    def test_command_handling_keywords(self, capsys):
        """:keywords 命令应显示关键字列表"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        repl._handle_command(":keywords")
        captured = capsys.readouterr()
        assert "关键字" in captured.out
        assert "定义" in captured.out

    def test_command_handling_help(self, capsys):
        """:help 命令应显示帮助"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        repl._handle_command(":help")
        captured = capsys.readouterr()
        assert "内置命令" in captured.out
        assert ":lang" in captured.out

    def test_command_handling_unknown(self, capsys):
        """未知命令应显示错误提示"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        repl._handle_command(":xyz")
        captured = capsys.readouterr()
        assert "未知命令" in captured.out

    def test_command_handling_lang_switch(self, capsys):
        """:lang 命令应切换语言"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        new_adapter = repl._handle_command(":lang testlang")
        assert new_adapter is not None
        assert new_adapter.id == "testlang"

    def test_command_handling_lang_unknown(self, capsys):
        """:lang 未知语言应显示错误"""
        registry = LanguageRegistry()
        adapter = REPLTestAdapter()
        registry.register(adapter)
        repl = YanREPL(registry=registry)
        repl._current_adapter = adapter

        new_adapter = repl._handle_command(":lang nonexistent")
        assert new_adapter is None
        captured = capsys.readouterr()
        assert "未知语言" in captured.out


# ---- 段言适配器 REPL 集成测试 ----

class TestDuanREPLIntegration:
    """测试段言适配器的 REPL 集成"""

    def test_duan_keywords_in_lexer(self):
        """段言关键字应在 lexer 中被正确高亮"""
        from prompt_toolkit.document import Document
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        lexer = ChineseLangLexer(adapter)

        doc = Document("段落 你好()。", cursor_position=0)
        get_line = lexer.lex_document(doc)
        line_styles = get_line(0)
        keywords = [text for text, style in line_styles if style == "class:keyword"]
        assert "段落" in keywords

    def test_duan_repl_prompt(self):
        """段言 REPL 提示符应包含语言名"""
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        assert "段言" in adapter.repl_prompt

    def test_duan_repl_welcome(self):
        """段言 REPL 欢迎信息应包含版本号"""
        from yanpub.adapters.duan.adapter import DuanAdapter
        adapter = DuanAdapter()
        assert "段言" in adapter.repl_welcome
