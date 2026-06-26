"""代码重构命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

@main.command("refactor")
@click.argument("action", type=click.Choice(["extract", "inline", "rename"]))
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
@click.option("--start-line", type=int, help="起始行（extract，1-based）")
@click.option("--end-line", type=int, help="结束行（extract，1-based）")
@click.option("--new-name", "-n", help="新名称")
@click.option("--line", type=int, help="光标行（inline/rename，1-based）")
@click.option("--column", type=int, help="光标列（inline/rename，1-based）")
def refactor_command(
    action: str,
    lang_id: str,
    file: str,
    start_line: int | None,
    end_line: int | None,
    new_name: str | None,
    line: int | None,
    column: int | None,
):
    """代码重构 — 提取函数/内联变量/安全重命名"""
    from pathlib import Path as P
    from yanpub.core.refactor import RefactoringEngine

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    code = P(file).read_text(encoding="utf-8")
    engine = RefactoringEngine(adapter)

    if action == "extract":
        if not start_line or not end_line:
            click.echo("extract 需要 --start-line 和 --end-line 参数", err=True)
            sys.exit(1)
        func_name = new_name or "提取的函数"
        result = engine.extract_function(code, start_line, end_line, func_name)

        click.echo(f"提取函数: {func_name}")
        click.echo(f"替换范围: 第 {start_line} 行 ~ 第 {end_line} 行")
        click.echo()
        click.echo("新函数代码：")
        click.echo(result["new_function"])
        click.echo()
        click.echo("替换代码：")
        click.echo(result["replacement"])

    elif action == "inline":
        if not line or not column:
            click.echo("inline 需要 --line 和 --column 参数", err=True)
            sys.exit(1)
        result = engine.inline_variable(code, line, column)

        if not result["value"]:
            click.echo("光标位置不是有效的变量声明")
            sys.exit(1)

        decl = result["declaration_range"]
        click.echo("内联变量重构：")
        click.echo(f"  变量值: {result['value']}")
        click.echo(f"  声明范围: 第 {decl['start']['line'] + 1} 行")
        click.echo(f"  使用位置: {len(result['usage_ranges'])} 处")
        if result["usage_ranges"]:
            for u in result["usage_ranges"]:
                click.echo(f"    第 {u['start']['line'] + 1} 行, 列 {u['start']['character'] + 1}")

    elif action == "rename":
        if not line or not column:
            click.echo("rename 需要 --line 和 --column 参数", err=True)
            sys.exit(1)
        if not new_name:
            click.echo("rename 需要 --new-name 参数", err=True)
            sys.exit(1)
        result = engine.safe_rename(code, line, column, new_name)

        if result["safe"]:
            click.echo(f"安全重命名: 可以安全地将标识符重命名为 '{new_name}'")
        else:
            click.echo(f"重命名检查: 发现 {len(result['conflicts'])} 个冲突")
            for c in result["conflicts"]:
                click.echo(f"  ⚠ {c}")

        click.echo(f"需要修改的位置: {len(result['changes'])} 处")
        if result["changes"]:
            for ch in result["changes"]:
                r = ch["range"]
                uri_info = f" ({ch['uri']})" if ch["uri"] else ""
                click.echo(
                    f"  第 {r['start']['line'] + 1} 行, 列 {r['start']['character'] + 1}{uri_info}"
                )
