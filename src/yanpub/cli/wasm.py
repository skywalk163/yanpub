"""WASM 执行命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@click.group()
def wasm():
    """WASM 执行 — 构建/运行 WebAssembly 执行环境"""
    pass

@wasm.command("check")
def wasm_check():
    """检查 WASM 运行时可用性"""
    from yanpub.core.wasm import detect_wasm_runtime

    runtime = detect_wasm_runtime()
    if runtime.available:
        click.echo(f"WASM 运行时: {runtime.name} v{runtime.version}")
        click.echo(f"路径: {runtime.path}")
    else:
        click.echo("无可用的 WASM 运行时")
        click.echo("可选方案:")
        click.echo("  pip install wasmtime    # wasmtime 运行时")
        click.echo("  pip install wasmer      # wasmer 运行时")
        click.echo("  安装 Node.js            # 通过 Node.js 执行 WASM")

@wasm.command("build")
@click.argument("lang_id")
@click.option("--output", "-o", default=None, help="输出目录")
def wasm_build(lang_id: str, output: str | None):
    """构建语言的 WASM 执行环境"""
    from yanpub.core.wasm import WasmBuilder
    from pathlib import Path as P

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    output_dir = P(output) if output else None
    builder = WasmBuilder(output_dir)
    result = builder.build(adapter)

    if result.success:
        click.echo(f"[OK] {adapter.name} WASM 环境构建成功")
        click.echo(f"  输出目录: {result.output_path}")
        click.echo(f"  大小: {result.size_bytes} bytes")
        click.echo(f"  耗时: {result.build_time_ms:.0f}ms")
    else:
        click.echo(f"[FAIL] 构建失败: {result.error}", err=True)
        sys.exit(1)

@wasm.command("run")
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
def wasm_run(lang_id: str, file: str):
    """使用 WASM 运行代码文件"""
    from yanpub.core.wasm import WasmExecutor
    from pathlib import Path as P

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    executor = WasmExecutor()
    if not executor.is_available:
        click.echo("无可用的 WASM 运行时，请运行 yanpub wasm check", err=True)
        sys.exit(1)

    code = P(file).read_text(encoding="utf-8")
    result = executor.execute_with_adapter(adapter, code)

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)
    sys.exit(result.exit_code)

main.add_command(wasm)
