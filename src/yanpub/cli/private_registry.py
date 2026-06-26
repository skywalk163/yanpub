"""私有注册中心命令"""

from __future__ import annotations

import click

from yanpub.cli import main

@click.group("private-registry")
def private_registry():
    """私有注册中心 — Git 仓库存储 + 镜像同步 + 权限管理"""
    pass

@private_registry.command("init")
@click.option("--url", default="", help="远程仓库 URL（不提供则在本地创建）")
def private_registry_init(url):
    """初始化私有注册中心"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry(repo_url=url)
    result = reg.init_repo(url)
    if result["success"]:
        click.echo(f"私有注册中心初始化成功: {result['path']}")
    else:
        click.echo(f"初始化失败: {result['message']}", err=True)

@private_registry.command("publish")
@click.argument("package_dir")
@click.option("--user", "-u", default="", help="发布者（权限检查用）")
@click.option("--message", "-m", default="", help="提交信息")
def private_registry_publish(package_dir, user, message):
    """发布包到私有注册中心"""
    import json as json_mod
    from pathlib import Path as PathLib
    from yanpub.pkg.private_registry import PrivateRegistry
    from yanpub.pkg.registry import PackageInfo

    pkg_path = PathLib(package_dir)
    pkg_file = pkg_path / "package.json"
    if not pkg_file.exists():
        click.echo(f"未找到 package.json: {pkg_file}", err=True)
        return

    data = json_mod.loads(pkg_file.read_text(encoding="utf-8"))
    pkg = PackageInfo.from_dict(data)

    reg = PrivateRegistry()
    result = reg.publish(pkg, user=user, commit_message=message)
    if result["success"]:
        click.echo(f"发布成功: {result['package']}@{result.get('version', '?')}")
    else:
        click.echo(f"发布失败: {result['message']}", err=True)

@private_registry.command("unpublish")
@click.argument("name")
@click.option("--user", "-u", default="", help="操作者（权限检查用）")
def private_registry_unpublish(name, user):
    """撤销发布"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    result = reg.unpublish(name, user=user)
    if result["success"]:
        click.echo(f"撤销成功: {result['package']}")
    else:
        click.echo(f"撤销失败: {result['message']}", err=True)

@private_registry.command("search")
@click.argument("query")
@click.option("--lang", "-L", default=None, help="限定语言")
@click.option("--user", "-u", default="", help="用户（权限检查用）")
def private_registry_search(query, lang, user):
    """搜索私有注册中心的包"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    results = reg.search(query, lang=lang, user=user)
    if not results:
        click.echo(f"未找到与 '{query}' 相关的包")
    else:
        click.echo(f"搜索 '{query}' — 找到 {len(results)} 个包:")
        for pkg in results:
            click.echo(f"  {pkg.name} ({pkg.version}) — {pkg.description}")

@private_registry.group("mirror")
def pr_mirror():
    """镜像同步管理"""
    pass

@pr_mirror.command("add")
@click.argument("name")
@click.argument("url")
@click.option("--direction", type=click.Choice(["push", "pull", "bidirectional"]), default="push", help="同步方向")
@click.option("--auth", type=click.Choice(["ssh", "https", "token"]), default="https", help="认证方式")
@click.option("--branch", default="main", help="分支名")
def pr_mirror_add(name, url, direction, auth, branch):
    """添加镜像仓库"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    mirror = reg.mirrors.add_mirror(name, url, sync_direction=direction, auth_type=auth, branch=branch)
    click.echo(f"镜像已添加: {mirror.name} ({mirror.url}) 方向={mirror.sync_direction}")

@pr_mirror.command("remove")
@click.argument("name")
def pr_mirror_remove(name):
    """移除镜像"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    if reg.mirrors.remove_mirror(name):
        click.echo(f"镜像已移除: {name}")
    else:
        click.echo(f"镜像不存在: {name}", err=True)

@pr_mirror.command("list")
def pr_mirror_list():
    """列出所有镜像"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    mirrors = reg.mirrors.list_mirrors()
    if not mirrors:
        click.echo("暂无镜像配置")
        return
    click.echo(f"共 {len(mirrors)} 个镜像:")
    for m in mirrors:
        status = "启用" if m.enabled else "禁用"
        click.echo(f"  {m.name}: {m.url} ({m.sync_direction}) [{status}]")
        if m.last_sync:
            click.echo(f"    上次同步: {m.last_sync} ({m.last_sync_status})")

@pr_mirror.command("sync")
@click.argument("name", required=False)
@click.option("--all", "sync_all", is_flag=True, help="同步所有镜像")
def pr_mirror_sync(name, sync_all):
    """同步镜像"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    if sync_all:
        results = reg.mirrors.sync_all()
        for r in results:
            status = "成功" if r["success"] else "失败"
            click.echo(f"  {r['mirror']}: {status} — {r['message']} ({r['duration_ms']}ms)")
    elif name:
        result = reg.mirrors.sync_mirror(name)
        status = "成功" if result["success"] else "失败"
        click.echo(f"  {result['mirror']}: {status} — {result['message']} ({result['duration_ms']}ms)")
    else:
        click.echo("请指定镜像名称或使用 --all")

@private_registry.group("permission")
def pr_permission():
    """权限管理"""
    pass

@pr_permission.command("grant")
@click.argument("user")
@click.argument("role", type=click.Choice(["owner", "maintainer", "developer", "guest"]))
@click.option("--scope", default="*", help="权限作用域（* 或 lang:xxx）")
@click.option("--granted-by", default="", help="授权人")
def pr_permission_grant(user, role, scope, granted_by):
    """授予用户权限"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    entry = reg.permissions.grant(user, role, scope=scope, granted_by=granted_by)
    click.echo(f"权限已授予: {entry.user} = {entry.role} (scope={entry.scope})")

@pr_permission.command("revoke")
@click.argument("user")
@click.option("--scope", default="*", help="权限作用域")
def pr_permission_revoke(user, scope):
    """撤销用户权限"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    if reg.permissions.revoke(user, scope=scope):
        click.echo(f"权限已撤销: {user} (scope={scope})")
    else:
        click.echo(f"未找到该权限: {user} (scope={scope})", err=True)

@pr_permission.command("list")
def pr_permission_list():
    """列出所有权限"""
    from yanpub.pkg.private_registry import PrivateRegistry

    reg = PrivateRegistry()
    entries = reg.permissions.list_all()
    if not entries:
        click.echo("暂无权限配置")
        return
    click.echo(f"共 {len(entries)} 条权限:")
    for e in entries:
        click.echo(f"  {e.user}: {e.role} (scope={e.scope})")

main.add_command(private_registry)
private_registry.add_command(pr_mirror)
private_registry.add_command(pr_permission)
