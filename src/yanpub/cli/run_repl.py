"""run 和 repl 命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@main.command()
@click.argument("lang_id")
@click.argument("file")
@click.option("--args", "-a", multiple=True, help="传递给程序的参数")
def run(lang_id: str, file: str, args: tuple[str, ...]):
    """运行指定语言的代码文件"""
    registry = get_registry()
    adapter = registry.get_or_raise(lang_id)

    click.echo(f">> {adapter.name} v{adapter.version}")
    result = adapter.run(file, list(args))

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)
    sys.exit(result.exit_code)

@main.command()
@click.argument("lang_id", required=False)
@click.option("--simple", is_flag=True, help="使用简易模式（无语法高亮/补全）")
def repl(lang_id: str | None, simple: bool):
    """启动交互式 REPL"""
    registry = get_registry()

    if lang_id is None:
        if len(registry) == 0:
            click.echo("没有可用的语言适配器。", err=True)
            sys.exit(1)
        elif len(registry) == 1:
            lang_id = list(registry.language_ids)[0]
        else:
            click.echo("可用语言：")
            for info in registry.list_languages():
                click.echo(f"  {info['id']:12s} {info['name']}")
            lang_id = click.prompt("请选择语言", type=str)

    if simple:
        # 简易模式：无 prompt_toolkit 依赖
        _simple_repl(lang_id, registry)
    else:
        # 完整模式：语法高亮 + 补全 + 历史
        try:
            from yanpub.repl.core import YanREPL

            yan_repl = YanREPL(registry)
            yan_repl.start(lang_id)
        except ImportError:
            click.echo("prompt_toolkit 未安装，使用简易模式", err=True)
            _simple_repl(lang_id, registry)

def _simple_repl(lang_id: str, registry) -> None:
    """简易 REPL（无 prompt_toolkit）"""
    adapter = registry.get_or_raise(lang_id)
    click.echo(adapter.repl_welcome)

    while True:
        try:
            code = input(adapter.repl_prompt)
        except (EOFError, KeyboardInterrupt):
            click.echo("\n再见！")
            break

        code = code.strip()
        if not code:
            continue

        if code.startswith(":"):
            new_adapter = _handle_command(code, adapter, registry)
            if new_adapter is not None:
                adapter = new_adapter
            continue

        result = adapter.eval(code)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            from yanpub.repl.error_display import parse_error, format_friendly_error

            friendly = parse_error(result.stderr, adapter.name)
            click.echo(format_friendly_error(friendly, adapter.name))

def _handle_command(code: str, adapter, registry):
    """处理 REPL 内置命令"""
    parts = code.split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in (":help", ":h"):
        click.echo("内置命令：")
        click.echo("  :help          显示帮助")
        click.echo("  :lang <id>     切换语言")
        click.echo("  :langs         列出可用语言")
        click.echo("  :keywords      显示当前语言关键字")
        click.echo("  :quit          退出")
    elif cmd == ":lang" and arg:
        new_adapter = registry.get(arg)
        if new_adapter:
            click.echo(f"切换到 {new_adapter.name}")
            return new_adapter
        else:
            click.echo(f"未知语言: {arg}")
    elif cmd == ":langs":
        for info in registry.list_languages():
            click.echo(f"  {info['id']:10s} {info['name']}")
    elif cmd == ":keywords":
        kws = adapter.keywords
        if kws:
            click.echo(f"{adapter.name} 关键字（{len(kws)}个）：")
            click.echo("  " + "、".join(kws))
        else:
            click.echo("未提供关键字列表")
    elif cmd in (":quit", ":q", ":exit"):
        raise KeyboardInterrupt
    else:
        click.echo(f"未知命令: {cmd}，输入 :help 查看帮助")

    return None
