"""语言适配器协议 — 整个 yanpub 的核心接口

每种中文编程语言只需实现此协议，即可接入全部工具链。
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass
class ExecutionResult:
    """代码执行结果"""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class CompletionItem:
    """补全项"""

    label: str
    kind: str = "keyword"  # keyword | function | variable | type | module
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""  # 默认等于 label

    def __post_init__(self):
        if not self.insert_text:
            self.insert_text = self.label


@dataclass
class Diagnostic:
    """诊断信息"""

    line: int  # 1-based
    column: int  # 1-based
    severity: str  # error | warning | info | hint
    message: str
    source: str = ""  # 来源语言


@dataclass
class TokenInfo:
    """词法分析结果"""

    type: str  # keyword | identifier | number | string | operator | comment | punctuation
    value: str
    line: int = 0
    column: int = 0


class LanguageAdapter(ABC):
    """语言适配器抽象基类

    所有中文编程语言的适配器必须继承此类。
    最小实现只需：name, id, version, file_extensions, run, eval
    """

    # ---- 元信息（必须实现）----

    @property
    @abstractmethod
    def name(self) -> str:
        """语言中文名，如 '段言'"""
        ...

    @property
    @abstractmethod
    def id(self) -> str:
        """语言唯一标识，如 'duan'"""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """语言版本，如 '1.3.8'"""
        ...

    @property
    @abstractmethod
    def file_extensions(self) -> list[str]:
        """支持的文件扩展名，如 ['.段', '.duan']"""
        ...

    # ---- 品牌信息（可选覆盖）----

    @property
    def description(self) -> str:
        """语言简介"""
        return f"{self.name} ({self.id})"

    @property
    def primary_color(self) -> str:
        """品牌主色"""
        return "#2C3E50"

    @property
    def secondary_color(self) -> str:
        """品牌辅色"""
        return "#3498DB"

    # ---- 执行（必须实现）----

    @abstractmethod
    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        """运行文件"""
        ...

    @abstractmethod
    def eval(self, code: str) -> ExecutionResult:
        """执行代码片段"""
        ...

    # ---- 语法分析（推荐实现）----

    def tokenize(self, code: str) -> list[TokenInfo]:
        """词法分析。默认实现返回空列表。"""
        return []

    def parse(self, code: str) -> Optional[dict]:
        """语法分析，返回 AST。默认实现返回 None。"""
        return None

    # ---- LSP 支持（可选）----

    def complete(self, code: str, line: int, column: int) -> list[CompletionItem]:
        """代码补全。默认基于关键字列表。支持缓存。"""
        # 缓存检查
        if self._enable_cache:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cached = cache.get_completions(self._id, code_hash)
            if cached is not None:
                return cached

        items = [CompletionItem(label=kw, kind="keyword") for kw in self.keywords]

        # 写入缓存
        if self._enable_cache and items:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cache.put_completions(self._id, code_hash, items)

        return items

    def diagnose(self, code: str) -> list[Diagnostic]:
        """代码诊断。默认实现尝试 eval 并捕获错误。支持缓存。"""
        # 缓存检查
        if self._enable_cache:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cached = cache.get_diagnostics(self._id, code_hash)
            if cached is not None:
                return cached

        result = self.eval(code)
        if result.success:
            diags: list[Diagnostic] = []
        else:
            # 尝试从 stderr 提取错误行号
            diags = [
                Diagnostic(
                    line=1,
                    column=1,
                    severity="error",
                    message=result.stderr.strip() or "执行错误",
                    source=self.id,
                )
            ]

        # 写入缓存
        if self._enable_cache:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cache.put_diagnostics(self._id, code_hash, diags)

        return diags

    def hover(self, code: str, line: int, column: int) -> Optional[str]:
        """悬停文档。默认实现基于关键字分类返回说明。"""
        from yanpub.core.keyword_docs import get_keyword_doc

        # 提取光标位置的词
        lines = code.split("\n")
        if line < 1 or line > len(lines):
            return None
        code_line = lines[line - 1]
        if column < 1 or column > len(code_line) + 1:
            return None

        # 用关键字列表做最长匹配
        # 从光标位置向左找到可能的关键字起始位置
        pos = column - 1  # 0-based
        keyword_set = set(self.keywords)
        if not keyword_set:
            return None

        # 尝试所有可能的关键字，找包含光标位置的最长匹配
        best_match = None
        best_len = 0
        for kw in keyword_set:
            kw_len = len(kw)
            # 关键字在行中的所有出现位置
            start = 0
            while True:
                idx = code_line.find(kw, start)
                if idx == -1:
                    break
                # 检查光标是否在此关键字范围内
                if idx <= pos <= idx + kw_len:
                    if kw_len > best_len:
                        best_match = kw
                        best_len = kw_len
                start = idx + 1

        if best_match:
            return get_keyword_doc(best_match, self.name)

        return None

    def format(self, code: str) -> str:
        """代码格式化。默认实现提供基础格式化规则。

        默认规则：
        1. 行尾空格清理
        2. 多余空行合并（最多2个连续空行）
        3. 文件末尾确保一个换行
        4. Tab 转为 4 空格
        5. 块关键字后冒号规范化（中文冒号→中文冒号，英文冒号→英文冒号）
        """
        lines = code.split("\n")

        # Tab → 4 spaces
        lines = [line.replace("\t", "    ") for line in lines]

        # Trim trailing whitespace
        lines = [line.rstrip() for line in lines]

        # Merge excessive blank lines (max 2 consecutive)
        result_lines: list[str] = []
        blank_count = 0
        for line in lines:
            if line == "":
                blank_count += 1
                if blank_count <= 2:
                    result_lines.append(line)
            else:
                blank_count = 0
                result_lines.append(line)

        # Ensure trailing newline
        # Remove trailing empty lines, then add one
        while result_lines and result_lines[-1] == "":
            result_lines.pop()

        return "\n".join(result_lines) + "\n" if result_lines else "\n"

    def rename(self, code: str, line: int, column: int, new_name: str) -> Optional[list[dict]]:
        """符号重命名。默认实现基于关键字/标识符文本替换。

        Args:
            code: 源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）
            new_name: 新名称

        Returns:
            编辑列表 [{"range": {"start": {"line":..., "character":...},
                                   "end": {"line":..., "character":...}},
                       "newText": "..."}]
            或 None（不支持重命名）
        """
        lines = code.split("\n")
        if line < 1 or line > len(lines):
            return None

        code_line = lines[line - 1]
        if column < 1 or column > len(code_line) + 1:
            return None

        # 提取光标位置的标识符
        # 向左右扩展找到标识符边界
        pos = column - 1  # 0-based
        start = pos
        end = pos

        def is_ident_char(ch: str) -> bool:
            return ch.isalnum() or ch == "_" or "\u4e00" <= ch <= "\u9fff"

        def is_cjk(ch: str) -> bool:
            return "\u4e00" <= ch <= "\u9fff"

        if is_cjk(code_line[pos]):
            # CJK字符：仅取光标所在的单个字符作为标识符
            # 中文编程语言中每个汉字通常是独立token
            old_name = code_line[pos]
            start = pos
            end = pos + 1
        else:
            # ASCII标识符：向左右扩展（alnum/_）
            while (
                start > 0
                and is_ident_char(code_line[start - 1])
                and not is_cjk(code_line[start - 1])
            ):
                start -= 1
            while (
                end < len(code_line)
                and is_ident_char(code_line[end])
                and not is_cjk(code_line[end])
            ):
                end += 1

            if start == end:
                return None  # 光标不在标识符上

            old_name = code_line[start:end]

        # 在整个文档中查找所有匹配的标识符并替换
        edits = []
        for i, ln in enumerate(lines):
            search_start = 0
            while True:
                idx = ln.find(old_name, search_start)
                if idx == -1:
                    break
                if len(old_name) == 1 and is_cjk(old_name):
                    # 单个CJK字符：不做严格边界检查
                    # 中文token之间无分隔符，无法仅凭文本判断边界
                    edits.append(
                        {
                            "range": {
                                "start": {"line": i, "character": idx},
                                "end": {"line": i, "character": idx + len(old_name)},
                            },
                            "newText": new_name,
                        }
                    )
                else:
                    # ASCII标识符：严格边界检查
                    before_ok = idx == 0 or not is_ident_char(ln[idx - 1])
                    after_ok = idx + len(old_name) >= len(ln) or not is_ident_char(
                        ln[idx + len(old_name)]
                    )
                    if before_ok and after_ok:
                        edits.append(
                            {
                                "range": {
                                    "start": {"line": i, "character": idx},
                                    "end": {"line": i, "character": idx + len(old_name)},
                                },
                                "newText": new_name,
                            }
                        )
                search_start = idx + 1

        return edits if edits else None

    def definition(self, code: str, line: int, column: int) -> Optional[list[dict]]:
        """跳转到定义。返回 [{"uri": str, "range": {"start": {"line": int, "character": int}, "end": {...}}}]"""
        return None

    def references(self, code: str, line: int, column: int) -> Optional[list[dict]]:
        """查找所有引用。返回 [{"uri": str, "range": {...}}]"""
        return None

    def call_hierarchy(self, code: str, line: int, column: int) -> Optional[dict]:
        """调用层次。返回 {"items": [{"name": str, "kind": str, "uri": str, "range": {...}, "children": [...]}]}"""
        return None

    def extract_function(
        self, code: str, start_line: int, end_line: int, new_name: str
    ) -> Optional[dict]:
        """提取函数重构

        将选中的代码块提取为一个新的段落/函数。

        Args:
            code: 源代码
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based）
            new_name: 新函数名

        Returns:
            {
                "new_function": str,           # 新函数代码
                "replacement": str,            # 替换选中代码的调用
                "range": {"start": ..., "end": ...}  # 替换范围
            }
            或 None（不支持提取函数重构）
        """
        return None

    def inline_variable(self, code: str, line: int, column: int) -> Optional[dict]:
        """内联变量重构

        将变量使用处替换为变量值，并删除变量声明。

        Args:
            code: 源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）

        Returns:
            {
                "declaration_range": {"start": ..., "end": ...},  # 变量声明范围（要删除）
                "value": str,                                     # 变量值（用于替换使用处）
                "usage_ranges": [{"start": ..., "end": ...}],     # 变量使用位置
            }
            或 None（不支持内联变量重构）
        """
        return None

    # ---- 关键字（推荐覆盖）----

    @property
    def keywords(self) -> list[str]:
        """语言关键字列表。用于语法高亮和补全。"""
        return []

    @property
    def comment_syntax(self) -> str:
        """注释语法。如 '#' 或 '//' 或 '注释'"""
        return "#"

    # ---- 包管理（可选）----

    def list_packages(self) -> list[dict]:
        """列出可用包"""
        return []

    def install_package(self, name: str, version: Optional[str] = None) -> bool:
        """安装包"""
        return False

    # ---- REPL（可选）----

    @property
    def repl_prompt(self) -> str:
        """REPL 提示符"""
        return f"{self.name}> "

    @property
    def repl_welcome(self) -> str:
        """REPL 欢迎信息"""
        return f"欢迎使用 {self.name} v{self.version}！输入 :help 查看帮助。"

    # ---- 能力声明 ----

    @property
    def capabilities(self) -> dict[str, bool]:
        """声明支持的能力"""
        return {
            "repl": True,
            "lsp": len(self.keywords) > 0,  # 有关键字就能提供基本 LSP
            "package_manager": False,
            "debug": False,
            "wasm": False,
        }


class SubprocessAdapter(LanguageAdapter):
    """子进程适配器 — 通过命令行调用语言后端

    最通用的适配器模式，适用于所有语言，零侵入。
    支持缓存策略：eval 结果可缓存，避免重复执行相同代码。
    """

    def __init__(
        self,
        name: str,
        lang_id: str,
        version: str,
        extensions: list[str],
        run_command: list[str],
        eval_command: list[str] | None = None,
        eval_mode: str = "stdin",
        repl_command: list[str] | None = None,
        keywords: list[str] | None = None,
        keywords_loader: Callable[[], list[str]] | None = None,
        primary_color: str = "#2C3E50",
        enable_cache: bool = True,
    ):
        self._name = name
        self._id = lang_id
        self._version = version
        self._extensions = extensions
        self._run_command = run_command
        self._eval_command = eval_command
        self._eval_mode = eval_mode  # "stdin" | "arg"
        self._repl_command = repl_command
        self._keywords = keywords
        self._keywords_loader = keywords_loader
        self._primary_color = primary_color
        self._enable_cache = enable_cache

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> str:
        return self._id

    @property
    def version(self) -> str:
        return self._version

    @property
    def file_extensions(self) -> list[str]:
        return self._extensions

    @property
    def keywords(self) -> list[str]:
        """语言关键字列表（懒加载）"""
        if self._keywords is None:
            if self._keywords_loader is not None:
                self._keywords = self._keywords_loader()
            else:
                self._keywords = []
        return self._keywords

    @property
    def primary_color(self) -> str:
        return self._primary_color

    def _exec(self, cmd: list[str], timeout: float = 30.0, stdin: str = "") -> ExecutionResult:
        """执行子命令"""
        import os as _os

        start = time.monotonic()
        try:
            env = _os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            result = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stderr=f"执行超时（{timeout}秒）",
                exit_code=-1,
                duration_ms=elapsed,
            )
        except FileNotFoundError:
            return ExecutionResult(
                stderr=f"命令未找到：{cmd[0]}",
                exit_code=-2,
            )

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        cmd = self._run_command + [file_path]
        if args:
            cmd.extend(args)
        return self._exec(cmd)

    def eval(self, code: str) -> ExecutionResult:
        # 缓存检查
        if self._enable_cache:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cached = cache.get_eval_result(self._id, code_hash)
            if cached is not None:
                return cached

        if self._eval_command:
            if self._eval_mode == "arg":
                # 代码作为命令行参数追加（如 python cli.py -e "code"）
                result = self._exec(self._eval_command + [code])
            else:
                # 代码通过 stdin 传入
                result = self._exec(self._eval_command, stdin=code)
        else:
            # fallback: 写临时文件再运行
            import tempfile

            # 优先使用 ASCII 扩展名，避免 Windows 上中文文件名编码问题
            suffix = (
                ".duan"
                if ".duan" in self._extensions
                else (self._extensions[-1] if self._extensions else ".txt")
            )
            with tempfile.NamedTemporaryFile(
                suffix=suffix,
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as f:
                f.write(code)
                tmp = f.name
            try:
                result = self._exec(self._run_command + [tmp])
            finally:
                Path(tmp).unlink(missing_ok=True)

        # 写入缓存（仅成功结果缓存，失败结果不缓存）
        if self._enable_cache and result.success:
            from yanpub.core.adapter.cache import get_adapter_cache, AdapterCache

            cache = get_adapter_cache()
            code_hash = AdapterCache.compute_code_hash(code)
            cache.put_eval_result(self._id, code_hash, result)

        return result


class InProcessAdapter(LanguageAdapter, ABC):
    """进程内适配器 — 直接调用语言 Python 模块

    适用于 Python 实现的语言（9/10 项目），零进程开销。
    子类需实现 _get_interpreter() 返回语言的解释器实例。
    """

    @abstractmethod
    def _get_interpreter(self):
        """返回语言解释器实例"""
        ...

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        start = time.monotonic()
        try:
            code = Path(file_path).read_text(encoding="utf-8")
            result = self.eval(code)
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(stderr=str(e), exit_code=1, duration_ms=elapsed)

    def eval(self, code: str) -> ExecutionResult:
        import io
        import sys

        start = time.monotonic()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_stdout = io.StringIO()
        sys.stderr = captured_stderr = io.StringIO()

        exit_code = 0
        try:
            interpreter = self._get_interpreter()
            interpreter.execute(code)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 1
        except Exception as e:
            exit_code = 1
            print(str(e), file=sys.stderr)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            elapsed = (time.monotonic() - start) * 1000

        return ExecutionResult(
            stdout=captured_stdout.getvalue(),
            stderr=captured_stderr.getvalue(),
            exit_code=exit_code,
            duration_ms=elapsed,
        )


class HTTPAdapter(LanguageAdapter, ABC):
    """HTTP 适配器 — 通过 HTTP/WebSocket 与语言后端通信

    适用于非 Python 后端（如明道的 Racket 后端）或远程部署。
    """

    @property
    @abstractmethod
    def base_url(self) -> str:
        """后端 API 地址"""
        ...

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        code = Path(file_path).read_text(encoding="utf-8")
        return self.eval(code)

    def eval(self, code: str) -> ExecutionResult:
        start = time.monotonic()
        try:
            import httpx

            resp = httpx.post(
                f"{self.base_url}/eval",
                json={"code": code},
                timeout=30.0,
            )
            elapsed = (time.monotonic() - start) * 1000
            data = resp.json()
            return ExecutionResult(
                stdout=data.get("stdout", ""),
                stderr=data.get("stderr", ""),
                exit_code=data.get("exit_code", 0),
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stderr=str(e),
                exit_code=-1,
                duration_ms=elapsed,
            )
