"""WASM 在线执行支持 — WebAssembly 执行器 + Playground 集成

核心能力：
1. WasmExecutor — 本地 WASM 运行时执行器（基于 wasmer/wasmtime 或 Pyodide）
2. WasmBuilder — 将 Python 语言后端编译为 WASM
3. Playground 前端集成 — 浏览器端 WASM 执行

当前实现策略：
- 本地模式：使用 wasmtime Python 包执行 .wasm 文件
- 浏览器模式：生成 Pyodide 配置，在 Playground 前端通过 Pyodide 执行
- 降级策略：如果 wasmtime 不可用，回退到子进程执行

命令:
  yanpub wasm build <lang_id>   — 构建语言的 WASM 执行环境
  yanpub wasm run <lang_id>     — 使用 WASM 运行代码
  yanpub wasm check             — 检查 WASM 运行时可用性
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yanpub.core.adapter.adapter import LanguageAdapter

from .wasm_executor import WasmRuntimeInfo, WasmExecutor, detect_wasm_runtime  # noqa: F401
from .wasm_pyodide import generate_pyodide_config, generate_pyodide_runner_html  # noqa: F401


def __getattr__(name):
    _moved = {"WasmRuntimeInfo", "WasmExecutor", "detect_wasm_runtime", "generate_pyodide_config", "generate_pyodide_runner_html"}
    if name in _moved:
        import importlib
        if name in {"WasmRuntimeInfo", "WasmExecutor", "detect_wasm_runtime"}:
            mod = importlib.import_module(".wasm_executor", __name__)
        else:
            mod = importlib.import_module(".wasm_pyodide", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@dataclass
class WasmBuildResult:
    """WASM 构建结果"""

    success: bool = False
    output_path: str = ""
    size_bytes: int = 0
    build_time_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "size_bytes": self.size_bytes,
            "build_time_ms": self.build_time_ms,
            "error": self.error,
        }


# ---- WASM 构建 ----

WASM_OUTPUT_DIR = Path.home() / ".yanpub" / "wasm"


class WasmBuilder:
    """WASM 执行环境构建器

    当前策略：
    - 对于 Python 后端语言 → 生成 Pyodide 兼容包
    - 对于有 .wasm 文件的语言 → 直接使用
    - 未来：支持通过 Emscripten 编译 C/Rust 后端
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self._output_dir = output_dir or WASM_OUTPUT_DIR

    def build(self, adapter: LanguageAdapter) -> WasmBuildResult:
        """构建语言的 WASM 执行环境

        Args:
            adapter: 语言适配器

        Returns:
            WasmBuildResult
        """
        start = time.monotonic()
        lang_dir = self._output_dir / adapter.id
        lang_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 生成 Pyodide 配置
            config = generate_pyodide_config(adapter)
            config_path = lang_dir / "pyodide_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 2. 生成 Pyodide runner HTML
            html = generate_pyodide_runner_html(adapter)
            html_path = lang_dir / "runner.html"
            html_path.write_text(html, encoding="utf-8")

            # 3. 生成 adapter 包装脚本
            wrapper = self._generate_wrapper_script(adapter)
            wrapper_path = lang_dir / "wrapper.py"
            wrapper_path.write_text(wrapper, encoding="utf-8")

            # 4. 生成元信息
            meta = {
                "lang_id": adapter.id,
                "lang_name": adapter.name,
                "version": adapter.version,
                "build_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "execution_mode": "pyodide",
                "files": {
                    "config": str(config_path),
                    "runner": str(html_path),
                    "wrapper": str(wrapper_path),
                },
            }
            meta_path = lang_dir / "meta.json"
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            elapsed = (time.monotonic() - start) * 1000
            total_size = sum(f.stat().st_size for f in lang_dir.iterdir() if f.is_file())

            return WasmBuildResult(
                success=True,
                output_path=str(lang_dir),
                size_bytes=total_size,
                build_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return WasmBuildResult(
                success=False,
                error=str(e),
                build_time_ms=elapsed,
            )

    def _generate_wrapper_script(self, adapter: LanguageAdapter) -> str:
        """生成 Pyodide 环境下的语言适配器包装脚本"""
        keywords_json = json.dumps(adapter.keywords[:50], ensure_ascii=False)

        return f'''"""Pyodide 环境下的 {adapter.name} 执行包装

此脚本在 Pyodide 运行时中执行，提供与原生适配器相同的接口。
"""

KEYWORDS = {keywords_json}

def execute(code: str) -> dict:
    """执行 {adapter.name} 代码

    在 Pyodide 环境下，直接通过 Python eval 执行。
    """
    import sys, io
    stdout = io.StringIO()
    stderr = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr

    exit_code = 0
    try:
        exec(code, {{"__builtins__": __builtins__}})
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(str(e), file=sys.stderr)
        exit_code = 1
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr

    return {{
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "exit_code": exit_code,
    }}

def get_keywords() -> list:
    return KEYWORDS
'''
