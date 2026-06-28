"""WASM 运行时检测与执行器

核心类：
- WasmRuntimeInfo: WASM 运行时信息
- WasmExecutor: WASM 代码执行器
- detect_wasm_runtime(): 检测可用的 WASM 运行时
"""

from __future__ import annotations

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yanpub.core.adapter.adapter import LanguageAdapter, ExecutionResult


@dataclass
class WasmRuntimeInfo:
    """WASM 运行时信息"""

    name: str = ""  # wasmtime / wasmer / pyodide / none
    version: str = ""
    available: bool = False
    path: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "available": self.available,
            "path": self.path,
        }


# ---- WASM 运行时检测 ----


def detect_wasm_runtime() -> WasmRuntimeInfo:
    """检测可用的 WASM 运行时

    检测顺序：
    1. wasmtime（Python 包）
    2. wasmer（Python 包）
    3. wasm（命令行工具）
    4. node（通过 @aspect-build/wasm）
    """
    # 1. wasmtime
    try:
        import wasmtime

        return WasmRuntimeInfo(
            name="wasmtime",
            version=getattr(wasmtime, "__version__", "unknown"),
            available=True,
            path="wasmtime",
        )
    except ImportError:
        pass

    # 2. wasmer
    try:
        import wasmer

        return WasmRuntimeInfo(
            name="wasmer",
            version=getattr(wasmer, "__version__", "unknown"),
            available=True,
            path="wasmer",
        )
    except ImportError:
        pass

    # 3. wasm CLI
    try:
        result = subprocess.run(
            ["wasm", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split()[-1] if result.stdout.strip() else "unknown"
            return WasmRuntimeInfo(
                name="wasm-cli",
                version=version,
                available=True,
                path="wasm",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 4. node (检查是否安装了 wasm 运行支持)
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return WasmRuntimeInfo(
                name="node",
                version=result.stdout.strip(),
                available=True,
                path="node",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return WasmRuntimeInfo(name="none", available=False)


# ---- WASM 执行器 ----


class WasmExecutor:
    """WASM 代码执行器

    执行策略：
    1. 如果有 wasmtime/wasmer → 直接执行 .wasm 文件
    2. 如果有 node → 通过 Node.js 执行 WASM
    3. 如果都没有 → 生成 Pyodide 配置供前端使用
    """

    def __init__(self, runtime: Optional[WasmRuntimeInfo] = None):
        self._runtime = runtime or detect_wasm_runtime()

    @property
    def runtime(self) -> WasmRuntimeInfo:
        return self._runtime

    @property
    def is_available(self) -> bool:
        return self._runtime.available

    def execute_wasm_file(self, wasm_path: str, args: list[str] | None = None) -> ExecutionResult:
        """执行 WASM 文件

        Args:
            wasm_path: .wasm 文件路径
            args: 传递给 WASM 的参数

        Returns:
            ExecutionResult
        """
        if not self._runtime.available:
            return ExecutionResult(
                stderr="无可用的 WASM 运行时",
                exit_code=-1,
            )

        start = time.monotonic()

        try:
            if self._runtime.name == "wasmtime":
                return self._exec_wasmtime(wasm_path, args)
            elif self._runtime.name == "wasmer":
                return self._exec_wasmer(wasm_path, args)
            elif self._runtime.name in ("node", "wasm-cli"):
                return self._exec_via_node(wasm_path, args)
            else:
                return ExecutionResult(
                    stderr=f"不支持的运行时: {self._runtime.name}",
                    exit_code=-1,
                    duration_ms=(time.monotonic() - start) * 1000,
                )
        except Exception as e:
            return ExecutionResult(
                stderr=str(e),
                exit_code=-1,
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def execute_with_adapter(
        self,
        adapter: LanguageAdapter,
        code: str,
    ) -> ExecutionResult:
        """通过 WASM 执行适配器代码

        当前策略：对于 Python 后端的语言适配器，
        生成 Pyodide 兼容的执行脚本。

        Args:
            adapter: 语言适配器
            code: 要执行的代码

        Returns:
            ExecutionResult
        """
        # 尝试使用 wasmtime 执行预编译的 wasm
        wasm_dir = Path.home() / ".yanpub" / "wasm" / adapter.id
        wasm_file = wasm_dir / "runner.wasm"

        if wasm_file.exists():
            # 写入代码到临时文件
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                delete=False,
            ) as f:
                f.write(code)
                code_file = f.name

            try:
                return self.execute_wasm_file(str(wasm_file), [code_file])
            finally:
                Path(code_file).unlink(missing_ok=True)

        # 降级：使用适配器原生执行
        return adapter.eval(code)

    def _exec_wasmtime(self, wasm_path: str, args: list[str] | None = None) -> ExecutionResult:
        """使用 wasmtime 执行"""
        import wasmtime

        start = time.monotonic()
        try:
            engine = wasmtime.Engine()
            module = wasmtime.Module(engine, open(wasm_path, "rb").read())
            store = wasmtime.Store(engine)
            instance = wasmtime.Instance(store, module, [])

            # 尝试调用 _start 或 main 函数
            exports = instance.exports(store)
            for name in ["_start", "main", "run"]:
                if hasattr(exports, name):
                    func = getattr(exports, name)
                    func(store)
                    break

            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stdout="WASM execution completed",
                exit_code=0,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stderr=str(e),
                exit_code=1,
                duration_ms=elapsed,
            )

    def _exec_wasmer(self, wasm_path: str, args: list[str] | None = None) -> ExecutionResult:
        """使用 wasmer 执行"""
        import wasmer

        start = time.monotonic()
        try:
            engine = wasmer.Engine()
            store = wasmer.Store(engine)
            module = wasmer.Module(store, open(wasm_path, "rb").read())
            instance = wasmer.Instance(store, module)

            # 尝试调用入口函数
            exports = instance.exports
            for name in ["_start", "main", "run"]:
                if hasattr(exports, name):
                    getattr(exports, name)()
                    break

            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stdout="WASM execution completed",
                exit_code=0,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stderr=str(e),
                exit_code=1,
                duration_ms=elapsed,
            )

    def _exec_via_node(self, wasm_path: str, args: list[str] | None = None) -> ExecutionResult:
        """通过 Node.js 执行 WASM"""
        # 生成 Node.js 执行脚本
        js_runner = f"""
const fs = require('fs');
const path = '{wasm_path}';
const wasmBuffer = fs.readFileSync(path);
WebAssembly.instantiate(wasmBuffer).then(results => {{
    const instance = results.instance;
    if (instance.exports._start) instance.exports._start();
    else if (instance.exports.main) instance.exports.main();
    else if (instance.exports.run) instance.exports.run();
    else console.error('No entry point found');
}}).catch(err => {{
    console.error(err.message);
    process.exit(1);
}});
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(js_runner)
            js_path = f.name

        try:
            cmd = [self._runtime.path, js_path]
            start = time.monotonic()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(stderr="执行超时", exit_code=-1)
        finally:
            Path(js_path).unlink(missing_ok=True)
