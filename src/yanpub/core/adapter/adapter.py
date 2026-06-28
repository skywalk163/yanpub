"""语言适配器协议 — 整个 yanpub 的核心接口

每种中文编程语言只需实现此协议，即可接入全部工具链。
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

# Re-export types and base for backward compatibility
from .types import CompletionItem, Diagnostic, ExecutionResult, TokenInfo  # noqa: F401
from .base import LanguageAdapter  # noqa: F401


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


def __getattr__(name):
    """Lazy re-export fallback for attributes moved to submodules."""
    import importlib

    _MODULES = (
        "yanpub.core.adapter.types",
        "yanpub.core.adapter.base",
    )
    for mod_name in _MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        try:
            return getattr(mod, name)
        except AttributeError:
            continue
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
