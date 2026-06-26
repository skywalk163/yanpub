"""工作空间命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main

@click.group("workspace")
def workspace():
    """工作空间 — monorepo 多包统一管理"""
    pass

@workspace.command("init")
@click.argument("name")
@click.option("--members", "-m", multiple=True, help="成员目录模式（默认 packages/*）")
def workspace_init(name: str, members: tuple[str, ...]):
    """初始化工作空间"""
    from pathlib import Path as P
    from yanpub.pkg.workspace import Workspace

    project_dir = P.cwd()
    ws = Workspace(project_dir)

    try:
        patterns = list(members) if members else None
        ws_path = ws.create(name=name, members_patterns=patterns)
        click.echo(f"[OK] 工作空间已创建: {ws_path}")
        click.echo(f"  名称: {name}")
        if ws.config:
            click.echo(f"  成员模式: {', '.join(ws.config.members)}")
            if ws.members:
                click.echo(f"  发现成员: {len(ws.members)} 个")
                for m in ws.members.values():
                    click.echo(f"    {m.full_name} v{m.version}")
    except FileExistsError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

@workspace.command("status")
def workspace_status():
    """查看工作空间状态"""
    from yanpub.pkg.workspace import load_workspace

    ws = load_workspace()
    if ws is None:
        click.echo("当前目录不在工作空间中（未找到 workspace.toml）", err=True)
        sys.exit(1)

    info = ws.status()
    click.echo(f"工作空间: {info['name']}")
    click.echo(f"根目录:   {info['root']}")
    click.echo(f"成员数:   {info['members_count']}")

    if info["members"]:
        click.echo("\n成员列表：")
        for m in info["members"]:
            int_deps = ", ".join(m["internal_deps"]) if m["internal_deps"] else "无"
            ext_deps = ", ".join(m["external_deps"]) if m["external_deps"] else "无"
            click.echo(f"  {m['full_name']:30s} v{m['version']:8s}  路径: {m['path']}")
            if m["internal_deps"]:
                click.echo(f"    内部依赖: {int_deps}")
            if m["external_deps"]:
                click.echo(f"    外部依赖: {ext_deps}")

    if info["build_order"]:
        click.echo("\n构建顺序：")
        click.echo("  " + " → ".join(info["build_order"]))

    if info["has_cycles"]:
        click.echo("\n⚠ 检测到循环依赖！")

    if info["shared_dependencies"]:
        click.echo("\n共享依赖：")
        for dep, spec in info["shared_dependencies"].items():
            click.echo(f"  {dep}: {spec}")

@workspace.command("list")
def workspace_list():
    """列出工作空间成员"""
    from yanpub.pkg.workspace import load_workspace

    ws = load_workspace()
    if ws is None:
        click.echo("当前目录不在工作空间中", err=True)
        sys.exit(1)

    for m in ws.members.values():
        int_deps = ", ".join(ws.list_internal_deps(m.full_name))
        click.echo(f"  {m.full_name:30s} v{m.version:8s}  {m.path}")
        if int_deps:
            click.echo(f"    内部依赖: {int_deps}")

@workspace.command("add")
@click.argument("member_path")
def workspace_add(member_path: str):
    """添加成员到工作空间"""
    from yanpub.pkg.workspace import load_workspace

    ws = load_workspace()
    if ws is None:
        click.echo("当前目录不在工作空间中", err=True)
        sys.exit(1)

    member = ws.add_member(member_path)
    if member is None:
        click.echo(f"添加失败：{member_path} 不是有效的包目录（缺少 yanpkg.toml）", err=True)
        sys.exit(1)

    click.echo(f"[OK] 已添加成员: {member.full_name} v{member.version}")

@workspace.command("lock")
@click.option("--upgrade", "-u", is_flag=True, help="升级所有依赖到最新兼容版本")
@click.option("--upgrade-package", default=None, help="升级指定依赖")
def workspace_lock(upgrade: bool, upgrade_package: str | None):
    """生成/更新版本锁定文件"""
    from yanpub.pkg.workspace import load_workspace
    from yanpub.pkg.versionset import VersionSetManager

    ws = load_workspace()
    if ws is None:
        click.echo("当前目录不在工作空间中（未找到 workspace.toml）", err=True)
        sys.exit(1)

    mgr = VersionSetManager(ws)

    if upgrade_package:
        click.echo(f"升级锁定: {upgrade_package}...")
        lock = mgr.upgrade(package_name=upgrade_package)
    elif upgrade:
        click.echo("升级所有依赖到最新兼容版本...")
        lock = mgr.upgrade()
    else:
        click.echo("生成版本锁定文件...")
        lock = mgr.resolve()
        mgr.save_lock(lock)

    path = mgr.save_lock(lock)
    click.echo(
        f"[OK] 已锁定 {len(lock.members)} 个成员、{len(lock.dependencies)} 个外部依赖 → {path}"
    )

@workspace.command("check-lock")
def workspace_check_lock():
    """检查锁定是否过时"""
    from yanpub.pkg.workspace import load_workspace
    from yanpub.pkg.versionset import VersionSetManager

    ws = load_workspace()
    if ws is None:
        click.echo("当前目录不在工作空间中（未找到 workspace.toml）", err=True)
        sys.exit(1)

    mgr = VersionSetManager(ws)
    result = mgr.check_freshness()

    if result["fresh"]:
        click.echo("✅ 锁定文件是最新的")
    else:
        click.echo("⚠ 锁定文件已过时")

        if result["outdated"]:
            click.echo(f"\n  过时的依赖 ({len(result['outdated'])}):")
            for item in result["outdated"]:
                click.echo(f"    {item['name']}: 锁定 {item['locked']} → 最新 {item['latest']}")

        if result["missing"]:
            click.echo(f"\n  缺失的依赖 ({len(result['missing'])}):")
            for name in result["missing"]:
                click.echo(f"    {name}")

        sys.exit(1)

main.add_command(workspace)
