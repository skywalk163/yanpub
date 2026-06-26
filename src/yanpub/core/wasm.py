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


# ---- Pyodide 配置生成 ----


def generate_pyodide_config(adapter: LanguageAdapter) -> dict:
    """生成 Pyodide 前端执行配置

    用于 Playground 前端在浏览器端通过 Pyodide 执行中文编程语言代码。

    Args:
        adapter: 语言适配器

    Returns:
        Pyodide 配置字典
    """
    return {
        "lang_id": adapter.id,
        "lang_name": adapter.name,
        "version": adapter.version,
        "comment_syntax": adapter.comment_syntax,
        "keywords": adapter.keywords[:100] if len(adapter.keywords) > 100 else adapter.keywords,
        "primary_color": adapter.primary_color,
        "file_extensions": adapter.file_extensions,
        "capabilities": adapter.capabilities,
        # Pyodide 执行参数
        "pyodide": {
            "version": "0.24.1",
            "index_url": "https://cdn.jsdelivr.net/pyodide/v0.24.1/full/",
        },
        # 执行模式
        "execution_mode": "pyodide",  # pyodide | wasm | native
        # 预加载的 Python 包
        "preload_packages": ["micropip"],
    }


def generate_pyodide_runner_html(adapter: LanguageAdapter) -> str:
    """生成 Pyodide 执行器 HTML 页面

    可嵌入 Playground 的 iframe 中。

    Args:
        adapter: 语言适配器

    Returns:
        HTML 字符串
    """
    config = generate_pyodide_config(adapter)
    config_json = json.dumps(config, ensure_ascii=False, indent=2)

    # 使用 string.Template 避免与 JS 的 {} 冲突
    from string import Template

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${lang_name} WASM 执行器</title>
<style>
body {
    font-family: 'Microsoft YaHei', monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    margin: 0;
    padding: 10px;
}
#output {
    white-space: pre-wrap;
    font-family: 'Consolas', monospace;
    font-size: 14px;
    line-height: 1.5;
}
.error { color: #f44336; }
.success { color: #4CAF50; }
.loading { color: #FF9800; }
</style>
</head>
<body>
<div id="status" class="loading">正在加载 Pyodide 运行时...</div>
<div id="output"></div>
<script>
// Pyodide 执行器配置
const CONFIG = ${config_json};

let pyodide = null;

async function initPyodide() {
    try {
        pyodide = await loadPyodide({
            indexURL: CONFIG.pyodide.index_url
        });
        document.getElementById('status').className = 'success';
        document.getElementById('status').textContent = 'Pyodide 已加载 (' + CONFIG.lang_name + ')';
        // 通知父页面
        if (window.parent !== window) {
            window.parent.postMessage({ type: 'wasm-ready', langId: CONFIG.lang_id }, '*');
        }
    } catch(e) {
        document.getElementById('status').className = 'error';
        document.getElementById('status').textContent = 'Pyodide 加载失败: ' + e.message;
    }
}

async function executeCode(code) {
    if (!pyodide) {
        return { stdout: '', stderr: 'Pyodide 未加载', exitCode: -1 };
    }
    const output = document.getElementById('output');
    output.textContent = '';
    try {
        // 重定向 stdout/stderr
        pyodide.runPython(`
import sys, io
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
`);
        pyodide.runPython(code);
        const stdout = pyodide.runPython('sys.stdout.getvalue()');
        const stderr = pyodide.runPython('sys.stderr.getvalue()');
        output.textContent = stdout;
        if (stderr) {
            const errDiv = document.createElement('div');
            errDiv.className = 'error';
            errDiv.textContent = stderr;
            output.appendChild(errDiv);
        }
        return { stdout, stderr, exitCode: 0 };
    } catch(e) {
        const errDiv = document.createElement('div');
        errDiv.className = 'error';
        errDiv.textContent = e.message;
        output.appendChild(errDiv);
        return { stdout: '', stderr: e.message, exitCode: 1 };
    }
}

// 监听来自父页面的执行请求
window.addEventListener('message', async function(event) {
    if (event.data.type === 'execute') {
        const result = await executeCode(event.data.code);
        window.parent.postMessage({
            type: 'execute-result',
            langId: CONFIG.lang_id,
            result: result,
            id: event.data.id
        }, '*');
    }
});

// 加载 Pyodide CDN
const script = document.createElement('script');
script.src = CONFIG.pyodide.index_url + 'pyodide.js';
script.onload = initPyodide;
document.head.appendChild(script);
</script>
</body>
</html>""")

    return tpl.substitute(lang_name=adapter.name, config_json=config_json)


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
