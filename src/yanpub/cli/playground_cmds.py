"""Playground 相关命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

@main.command()
@click.option("--host", default="0.0.0.0", help="监听地址")
@click.option("--port", default=8080, type=int, help="监听端口")
def playground(host: str, port: int):
    """启动在线 Playground"""
    click.echo(f"启动 Playground: http://{host}:{port}")
    try:
        from yanpub.playground.server import create_app
        import uvicorn

        app = create_app()
        uvicorn.run(app, host=host, port=port)
    except ImportError as e:
        click.echo(f"Playground 依赖未安装: {e}", err=True)
        click.echo("请运行: pip install yanpub[playground]", err=True)
        sys.exit(1)

@main.command("share")
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
@click.option("--title", "-t", default="", help="分享标题")
@click.option("--ttl", default=None, type=int, help="过期时间（小时）")
def share_code(lang_id: str, file: str, title: str, ttl: int | None):
    """创建代码分享链接"""
    from pathlib import Path as P
    from yanpub.playground.share import get_share_manager

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    code = P(file).read_text(encoding="utf-8")

    mgr = get_share_manager()
    record = mgr.create_share(
        lang=lang_id,
        code=code,
        title=title,
        ttl_hours=ttl,
    )

    click.echo("[OK] 分享链接已创建")
    click.echo(f"  ID:     {record.id}")
    click.echo(f"  语言:   {adapter.name} ({lang_id})")
    click.echo(f"  标题:   {title or '(无)'}")
    click.echo(f"  文件:   {file}")
    click.echo(f"  代码:   {len(code)} 字符")
    if record.expires_at:
        import datetime

        expires = datetime.datetime.fromtimestamp(record.expires_at)
        click.echo(f"  过期:   {expires.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        click.echo("  过期:   永不过期")
    click.echo()
    click.echo(f"  短链接: /s/{record.id}")
    click.echo(f"  API:    GET /api/share/{record.id}")
    click.echo(f"  二维码: GET /api/share/{record.id}/qr")

@main.command("monitor")
@click.option("--host", default="127.0.0.1", help="监听地址")
@click.option("--port", default=8888, type=int, help="监听端口")
@click.option("--interval", default=5.0, type=float, help="采样间隔（秒）")
def start_monitor(host: str, port: int, interval: float):
    """启动性能监控仪表板"""
    from yanpub.core.monitor import get_monitor

    click.echo(f"启动性能监控仪表板: http://{host}:{port}")
    click.echo(f"采样间隔: {interval}秒")

    try:
        from yanpub.playground.server import create_app
        import uvicorn
        import asyncio

        monitor = get_monitor()
        registry = get_registry()

        # 采样任务：定期对所有适配器执行简单 eval 并记录耗时
        async def sampling_task():
            while True:
                for adapter in registry:
                    try:
                        import time

                        start = time.monotonic()
                        comment = adapter.comment_syntax or "#"
                        test_code = f"{comment} monitor sample\n"
                        result = adapter.eval(test_code)
                        duration_ms = (time.monotonic() - start) * 1000
                        monitor.record(adapter, "eval", duration_ms, success=result.success)
                    except Exception:
                        duration_ms = 0
                        try:
                            duration_ms = (time.monotonic() - start) * 1000
                        except Exception:
                            pass
                        monitor.record(adapter, "eval", duration_ms, success=False)
                await asyncio.sleep(interval)

        app = create_app()

        @app.on_event("startup")
        async def start_sampling():
            asyncio.create_task(sampling_task())

        uvicorn.run(app, host=host, port=port)
    except ImportError as e:
        click.echo(f"监控仪表板依赖未安装: {e}", err=True)
        click.echo("请运行: pip install yanpub[playground]", err=True)
        sys.exit(1)
