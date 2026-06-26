"""沙箱执行命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@click.group()
def sandbox():
    """沙箱执行 — 在安全隔离环境中运行代码"""
    pass

@sandbox.command("run")
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--backend",
    type=click.Choice(["auto", "docker", "podman", "freebsd_jail", "process"]),
    default="auto",
    help="沙箱后端",
)
@click.option("--memory", default="512m", help="内存限制")
@click.option("--timeout", "-t", default=30.0, type=float, help="超时时间（秒）")
@click.option("--network", is_flag=True, help="允许网络访问")
def sandbox_run(lang_id: str, file: str, backend: str, memory: str, timeout: float, network: bool):
    """在沙箱中安全执行代码"""
    from yanpub.core.security.sandbox import SandboxManager, SandboxConfig

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    config = SandboxConfig(
        backend=backend,
        memory_limit=memory,
        timeout=timeout,
        network=network,
    )
    manager = SandboxManager(config)

    click.echo(f"沙箱执行: {adapter.name} ({file})", err=True)
    click.echo(f"后端: {manager._resolve_backend_name()}", err=True)

    result = manager.execute_file(adapter, file)

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)

    try:
        manager.cleanup()
    except Exception:
        pass

    sys.exit(result.exit_code)

@sandbox.command("check")
def sandbox_check():
    """检测可用的沙箱后端"""
    from yanpub.core.security.sandbox import SandboxManager

    status = SandboxManager.get_backend_status()

    click.echo("沙箱后端检测：\n")
    for name, info in status.items():
        available = "✅" if info["available"] else "❌"
        desc = info.get("description", "")
        click.echo(f"  {available} {name:14s} {desc}")

    available_backends = [n for n, i in status.items() if i["available"]]
    click.echo(f"\n推荐后端: {available_backends[0] if available_backends else 'process'}")

main.add_command(sandbox)
