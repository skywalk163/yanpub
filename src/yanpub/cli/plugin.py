"""插件管理命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main

@click.group()
def plugin():
    """插件管理 — 安装/卸载/管理第三方工具链插件"""
    pass

@plugin.command("list")
def plugin_list():
    """列出已安装的插件"""
    from yanpub.core.plugin import get_plugin_manager, format_plugin_list

    pm = get_plugin_manager()
    plugins = pm.list_plugins()
    click.echo(format_plugin_list(plugins))

@plugin.command("install")
@click.argument("source_path", type=click.Path(exists=True))
@click.option("--name", "-n", default=None, help="插件名称（覆盖 plugin.json）")
def plugin_install(source_path: str, name: str | None):
    """安装插件（指定插件源目录）"""
    from yanpub.core.plugin import get_plugin_manager

    pm = get_plugin_manager()
    try:
        info = pm.install(source_path, name)
        click.echo(f"[OK] 插件 {info.name} v{info.version} 已安装")
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

@plugin.command("uninstall")
@click.argument("name")
def plugin_uninstall(name: str):
    """卸载插件"""
    from yanpub.core.plugin import get_plugin_manager

    pm = get_plugin_manager()
    if pm.uninstall(name):
        click.echo(f"[OK] 插件 {name} 已卸载")
    else:
        click.echo(f"未找到插件: {name}", err=True)
        sys.exit(1)

@plugin.command("enable")
@click.argument("name")
def plugin_enable(name: str):
    """启用插件"""
    from yanpub.core.plugin import get_plugin_manager

    pm = get_plugin_manager()
    if pm.enable(name):
        click.echo(f"[OK] 插件 {name} 已启用")
    else:
        click.echo(f"未找到插件: {name}", err=True)
        sys.exit(1)

@plugin.command("disable")
@click.argument("name")
def plugin_disable(name: str):
    """禁用插件"""
    from yanpub.core.plugin import get_plugin_manager

    pm = get_plugin_manager()
    if pm.disable(name):
        click.echo(f"[OK] 插件 {name} 已禁用")
    else:
        click.echo(f"未找到插件: {name}", err=True)
        sys.exit(1)

main.add_command(plugin)
