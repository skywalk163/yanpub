"""热更新命令"""

from __future__ import annotations

import sys
import time

import click

from yanpub.cli import main

@main.command("hot-update")
@click.argument("lang_id")
@click.option("--rollback", "-R", "target_version", type=int, default=None, help="回退到指定版本")
@click.option("--list-versions", is_flag=True, help="列出版本历史")
@click.option("--check", is_flag=True, help="检查是否有代码变更")
def hot_update_command(lang_id, target_version, list_versions, check):
    """适配器热更新 — 运行时代码替换 + 版本回退"""
    from yanpub.core.hotupdate import HotUpdateManager

    manager = HotUpdateManager()

    if list_versions:
        versions = manager.list_versions(lang_id)
        if not versions:
            click.echo(f"适配器 {lang_id} 暂无版本历史")
        else:
            click.echo(f"适配器 {lang_id} 版本历史:")
            for v in versions:
                status = "✓" if v["success"] else "✗"
                click.echo(
                    f"  v{v['version']} {status} {v['adapter_name']} ({time.strftime('%Y-%m-%d %H:%M', time.localtime(v['timestamp']))})"
                )
                if v["error"]:
                    click.echo(f"    错误: {v['error']}")
        return

    if check:
        updates = manager.check_for_updates()
        if not updates:
            click.echo("所有适配器代码无变更")
        else:
            for u in updates:
                click.echo(
                    f"  {u['adapter_id']}: {u['event_type']} {'成功' if u['success'] else '失败: ' + u['error']}"
                )
        return

    if target_version is not None:
        click.echo(f"回退适配器 {lang_id} 到版本 {target_version}...")
        result = manager.rollback(lang_id, target_version)
    else:
        click.echo(f"热更新适配器 {lang_id}...")
        result = manager.update(lang_id)

    if result.success:
        click.echo(f"[OK] 版本 v{result.version} {result.adapter_name}")
    else:
        click.echo(f"[FAIL] 更新失败: {result.error}", err=True)
        sys.exit(1)
