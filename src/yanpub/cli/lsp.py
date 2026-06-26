"""LSP 命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@main.command(name="lsp")
@click.argument("lang_id")
@click.option("--host", default="127.0.0.1", help="监听地址")
@click.option("--port", default=2087, type=int, help="监听端口")
def start_lsp(lang_id: str, host: str, port: int):
    """启动 LSP 服务"""
    registry = get_registry()
    adapter = registry.get_or_raise(lang_id)
    click.echo(f"启动 {adapter.name} LSP 服务: {host}:{port}")
    try:
        from yanpub.lsp.server import create_lsp_server

        create_lsp_server(adapter, host, port)
    except ImportError as e:
        click.echo(f"LSP 依赖未安装: {e}", err=True)
        sys.exit(1)
