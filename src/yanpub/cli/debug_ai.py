"""调试和 AI 辅助命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

@main.command("debug")
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
@click.option("--host", default="127.0.0.1", help="DAP 服务器地址")
@click.option("--port", default=4711, type=int, help="DAP 服务器端口")
@click.option("--stop-on-entry", is_flag=True, help="在入口处暂停")
def debug_file(lang_id: str, file: str, host: str, port: int, stop_on_entry: bool):
    """启动调试会话（DAP 协议）"""
    from yanpub.core.debugger import DebugSession

    registry = get_registry()
    adapter = registry.get_or_raise(lang_id)

    click.echo(f"启动调试: {adapter.name} ({adapter.id})")
    click.echo(f"文件: {file}")

    session = DebugSession(adapter)
    event = session.launch(file, stop_on_entry=stop_on_entry)

    if event.type == "stopped":
        click.echo(f"已暂停 — 原因: {event.reason}")
        if event.frames:
            frame = event.frames[0]
            click.echo(f"  位置: {frame.source}:{frame.line}")
    elif event.type == "exited":
        click.echo("程序已退出")
        if event.output:
            click.echo(event.output, nl=False)
    else:
        click.echo(f"调试事件: {event.type}")

    # 启动 DAP 服务器
    from yanpub.core.dap_server import DAPServer

    server = DAPServer(adapter, host=host, port=port)
    server._debug_adapter._session = session  # 复用已有会话

    click.echo(f"DAP 服务器: {host}:{port}")
    click.echo("按 Ctrl+C 停止")
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        click.echo("\n调试已停止")

@main.command("dap-server")
@click.argument("lang_id")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=4711, type=int)
def start_dap_server(lang_id: str, host: str, port: int):
    """启动 DAP 调试适配器服务器"""
    from yanpub.core.dap_server import DAPServer

    registry = get_registry()
    adapter = registry.get_or_raise(lang_id)

    click.echo(f"启动 {adapter.name} DAP 服务器: {host}:{port}")
    server = DAPServer(adapter, host=host, port=port)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        click.echo("\nDAP 服务器已停止")


@main.command("ai")
@click.argument("text")
@click.option("--lang", "-L", "lang_id", required=True, help="目标语言")
@click.option(
    "--type",
    "ai_type",
    type=click.Choice(["nl2code", "fix", "complete"]),
    default="nl2code",
    help="AI 辅助类型",
)
@click.option("--context", "-c", default=None, help="上下文代码")
@click.option("--error", "-e", default=None, help="错误信息（fix 类型用）")
@click.option("--line", default=1, type=int, help="光标行号（complete 类型用）")
@click.option("--column", default=1, type=int, help="光标列号（complete 类型用）")
def ai_assist(
    text: str,
    lang_id: str,
    ai_type: str,
    context: str | None,
    error: str | None,
    line: int,
    column: int,
):
    """AI 辅助 — 自然语言转代码/错误修复/智能补全"""
    from yanpub.core.ai_assist import AIAssistEngine

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    engine = AIAssistEngine()

    if ai_type == "nl2code":
        result = engine.nl_to_code(adapter, text, context or "")
        click.echo(f"生成的代码（置信度: {result['confidence']:.0%}）：")
        click.echo()
        click.echo(result["code"])
        if result.get("explanation"):
            click.echo()
            click.echo(f"说明: {result['explanation']}")

    elif ai_type == "fix":
        code = text  # text 参数作为代码
        err_msg = error or ""
        if not err_msg:
            # 先执行代码获取错误
            result = adapter.eval(code)
            if result.success:
                click.echo("代码执行成功，无错误需要修复。")
                return
            err_msg = result.stderr

        suggestions = engine.fix_suggestion(adapter, code, err_msg)
        if not suggestions:
            click.echo("未找到修复建议。")
            return

        click.echo(f"找到 {len(suggestions)} 条修复建议：\n")
        for i, s in enumerate(suggestions, 1):
            click.echo(f"  {i}. {s['title']}（置信度: {s['confidence']:.0%}）")
            click.echo(f"     {s['description']}")
            click.echo()

    elif ai_type == "complete":
        code = text  # text 参数作为代码
        items = engine.smart_complete(adapter, code, line, column)
        if not items:
            click.echo("无补全建议。")
            return

        click.echo(f"找到 {len(items)} 条补全建议：\n")
        for i, item in enumerate(items, 1):
            ai_tag = "[AI]" if item.get("is_ai") else ""
            click.echo(f"  {i}. {ai_tag} {item['label']} ({item['kind']})")
            if item.get("detail"):
                click.echo(f"     {item['detail']}")
            if item.get("insert_text") and item["insert_text"] != item["label"]:
                click.echo(f"     插入: {item['insert_text']}")
