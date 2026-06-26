"""统一 REPL — 基于 prompt_toolkit

核心特性：
- 语言热切换：:lang duan 即切换执行环境
- 中文关键字语法高亮
- Tab 补全
- 命令历史持久化
- 多行输入智能续行
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import Lexer

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.adapter.registry import get_registry, LanguageRegistry


# ---- 多行输入智能续行 ----

# 块开始关键字（这些关键字后面通常需要缩进/续行）
_BLOCK_KEYWORDS = {
    "如果",
    "若",
    "当",
    "遍历",
    "循环",
    "对于",
    "尝试",
    "函数",
    "段落",
    "类",
    "定义",
    "设",
    "否则",
    "否则若",
    "捕获",
    "最终",
}

# 块结束关键字（这些关键字表示块结束，不需要续行）
_BLOCK_END_KEYWORDS = {
    "结束",
    "完毕",
    "完",
}


def _needs_continuation(code: str) -> bool:
    """判断代码是否需要续行

    检测以下情况：
    1. 未闭合的引号
    2. 未闭合的括号
    3. 行尾是块开始关键字
    4. 行尾是冒号
    5. 行尾是中文逗号
    """
    if not code.strip():
        return False

    lines = code.split("\n")
    last_line = lines[-1].strip()

    # 空行不续行
    if not last_line:
        return False

    # 检查未闭合的引号（单/双引号数量奇数）
    single_quotes = code.count("'") - code.count("\\'")
    double_quotes = code.count('"') - code.count('\\"')
    if single_quotes % 2 != 0 or double_quotes % 2 != 0:
        return True

    # 检查未闭合的括号
    for open_ch, close_ch in [("(", ")"), ("[", "]"), ("{", "}")]:
        if code.count(open_ch) > code.count(close_ch):
            return True

    # 行尾是冒号（中英文）
    if last_line.endswith(":") or last_line.endswith("："):
        return True

    # 行尾是中文逗号
    if last_line.endswith("，"):
        return True

    # 行尾是块开始关键字
    last_word = re.findall(r"[\u4e00-\u9fff]+", last_line)
    if last_word and last_word[-1] in _BLOCK_KEYWORDS:
        return True

    return False


# ---- 中文语言语法高亮器 ----


class ChineseLangLexer(Lexer):
    """基于关键字列表的语法高亮器

    根据当前适配器的关键字列表，为中文编程语言提供语法高亮。
    """

    def __init__(self, adapter: LanguageAdapter):
        self.adapter = adapter
        self._keyword_set = set(adapter.keywords)
        self._comment_char = adapter.comment_syntax

    def lex_document(self, document: Document):
        """词法分析，返回每行的样式列表"""
        lines = document.lines

        def get_line(lineno: int) -> list[tuple[str, str]]:
            line = lines[lineno] if lineno < len(lines) else ""
            result: list[tuple[str, str]] = []
            pos = 0

            while pos < len(line):
                ch = line[pos]

                # 注释
                if self._comment_char and line[pos:].startswith(self._comment_char):
                    result.append((self._comment_char, "class:comment"))
                    pos += len(self._comment_char)
                    if pos < len(line):
                        result.append((line[pos:], "class:comment"))
                        pos = len(line)
                    continue

                # 中文关键字
                if "\u4e00" <= ch <= "\u9fff":
                    # 匹配连续中文字符
                    match = re.match(r"[\u4e00-\u9fff]+", line[pos:])
                    if match:
                        word = match.group()
                        if word in self._keyword_set:
                            result.append((word, "class:keyword"))
                        else:
                            result.append((word, "class:identifier"))
                        pos += len(word)
                        continue

                # 字符串
                if ch in ('"', "'"):
                    quote = ch
                    end = line.find(quote, pos + 1)
                    if end == -1:
                        end = len(line) - 1
                    result.append((line[pos : end + 1], "class:string"))
                    pos = end + 1
                    continue

                # 数字
                if ch.isdigit():
                    match = re.match(r"\d+(\.\d+)?", line[pos:])
                    if match:
                        result.append((match.group(), "class:number"))
                        pos += len(match.group())
                        continue

                # 运算符
                if ch in "+-*/%=<>!&|^~":
                    result.append((ch, "class:operator"))
                    pos += 1
                    continue

                # 英文标识符
                if ch.isalpha() or ch == "_":
                    match = re.match(r"[a-zA-Z_]\w*", line[pos:])
                    if match:
                        word = match.group()
                        if word in self._keyword_set:
                            result.append((word, "class:keyword"))
                        else:
                            result.append((word, "class:identifier"))
                        pos += len(word)
                        continue

                # 其他字符
                result.append((ch, ""))
                pos += 1

            return result

        return get_line


# ---- REPL 命令补全器 ----


class REPLCompleter(Completer):
    """REPL 命令 + 关键字补全"""

    COMMANDS = [
        (":help", "显示帮助"),
        (":lang", "切换语言（:lang duan）"),
        (":langs", "列出可用语言"),
        (":keywords", "显示当前语言关键字"),
        (":quit", "退出 REPL"),
    ]

    def __init__(self, adapter: LanguageAdapter, registry: LanguageRegistry):
        self.adapter = adapter
        self.registry = registry

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor

        # 命令补全
        if text.startswith(":"):
            for cmd, desc in self.COMMANDS:
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                    )

            # :lang 后的语言 ID 补全
            if text.startswith(":lang "):
                prefix = text[6:]
                for info in self.registry.list_languages():
                    if info["id"].startswith(prefix):
                        yield Completion(
                            info["id"],
                            start_position=-len(prefix),
                            display=f"{info['id']} ({info['name']})",
                            display_meta=f"v{info['version']}",
                        )
            return

        # 关键字补全
        word = text.split()[-1] if text else ""
        if word:
            for kw in self.adapter.keywords:
                if kw.startswith(word) and kw != word:
                    yield Completion(
                        kw,
                        start_position=-len(word),
                        display=kw,
                        display_meta="关键字",
                    )


# ---- REPL 主类 ----


class YanREPL:
    """统一 REPL — 支持多语言热切换"""

    def __init__(self, registry: Optional[LanguageRegistry] = None):
        self.registry = registry if registry is not None else get_registry()
        self._current_adapter: Optional[LanguageAdapter] = None
        self._history_dir = Path.home() / ".yanpub" / "repl_history"
        self._history_dir.mkdir(parents=True, exist_ok=True)

    def start(self, lang_id: Optional[str] = None) -> None:
        """启动 REPL"""
        if lang_id:
            self._current_adapter = self.registry.get_or_raise(lang_id)
        elif len(self.registry) > 0:
            self._current_adapter = list(self.registry)[0]
        else:
            print("没有可用的语言适配器。")
            return

        adapter = self._current_adapter
        print(adapter.repl_welcome)

        # 创建会话
        session = self._create_session(adapter)

        while True:
            try:
                # 多行输入模式
                code_lines = []
                continuation = False

                while True:
                    if continuation:
                        # 续行提示
                        prompt = "... "
                    else:
                        prompt = adapter.repl_prompt

                    try:
                        line = session.prompt(prompt)
                    except (EOFError, KeyboardInterrupt):
                        if continuation:
                            # Ctrl+C 取消多行输入
                            print("  (取消)")
                            continuation = False
                            code_lines = []
                            break
                        raise

                    code_lines.append(line)
                    full_code = "\n".join(code_lines)

                    # 检查是否需要续行
                    if _needs_continuation(full_code):
                        continuation = True
                    else:
                        break

                code = "\n".join(code_lines)
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            code = code.strip()
            if not code:
                continue

            # 内置命令处理
            if code.startswith(":"):
                new_adapter = self._handle_command(code)
                if new_adapter is not None:
                    adapter = new_adapter
                    self._current_adapter = adapter
                    session = self._create_session(adapter)
                continue

            # 执行代码
            result = adapter.eval(code)
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                # 使用友好错误提示
                from yanpub.repl.error_display import parse_error, format_friendly_error

                friendly = parse_error(result.stderr, adapter.name)
                print(format_friendly_error(friendly, adapter.name))

    def _create_session(self, adapter: LanguageAdapter) -> PromptSession:
        """为当前适配器创建 prompt_toolkit 会话"""
        history_path = self._history_dir / f"history_{adapter.id}"

        return PromptSession(
            history=FileHistory(str(history_path)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=REPLCompleter(adapter, self.registry),
            lexer=ChineseLangLexer(adapter),
            complete_while_typing=True,
        )

    def _handle_command(self, code: str) -> Optional[LanguageAdapter]:
        """处理内置命令，返回新的适配器（如果切换了语言）"""
        parts = code.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in (":help", ":h"):
            self._print_help()
        elif cmd == ":lang" and arg:
            new_adapter = self.registry.get(arg)
            if new_adapter:
                print(f"切换到 {new_adapter.name}")
                return new_adapter
            else:
                print(f"未知语言: {arg}")
        elif cmd == ":langs":
            for info in self.registry.list_languages():
                caps = ", ".join(k for k, v in info["capabilities"].items() if v)
                print(f"  {info['id']:10s} {info['name']:8s}  {caps}")
        elif cmd == ":keywords":
            adapter = self._current_adapter
            if adapter and adapter.keywords:
                kws = adapter.keywords
                print(f"{adapter.name} 关键字（{len(kws)}个）：")
                # 分组显示
                for i in range(0, len(kws), 15):
                    group = kws[i : i + 15]
                    print("  " + "、".join(group))
            else:
                print("未提供关键字列表")
        elif cmd in (":quit", ":q", ":exit"):
            raise KeyboardInterrupt
        else:
            print(f"未知命令: {cmd}，输入 :help 查看帮助")

        return None

    def _print_help(self):
        print("内置命令：")
        print("  :help          显示帮助")
        print("  :lang <id>     切换语言（如 :lang duan）")
        print("  :langs         列出可用语言")
        print("  :keywords      显示当前语言关键字")
        print("  :quit          退出")
        print()
        print("快捷键：")
        print("  Tab            补全关键字/命令")
        print("  上/下箭头      浏览历史命令")
