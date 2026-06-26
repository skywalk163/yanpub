"""包管理命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main

@click.group()
def pkg():
    """包管理 — 安装/查询/发布包"""
    pass

@pkg.command("install")
@click.argument("package_name")
@click.option("--version", "-v", default=None, help="指定版本")
def pkg_install(package_name: str, version: str | None):
    """安装包（格式: lang:package 或 package）"""
    from yanpub.pkg.installer import install

    click.echo(f"安装 {package_name}...")
    success = install(package_name, version)
    if success:
        click.echo(f"[OK] {package_name} 安装成功")
    else:
        click.echo(f"[FAIL] {package_name} 安装失败", err=True)
        sys.exit(1)

@pkg.command("list")
@click.option("--lang", "-l", default=None, help="按语言筛选")
@click.option("--all", "show_all", is_flag=True, help="显示注册中心所有包（含未安装）")
def pkg_list(lang: str | None, show_all: bool):
    """列出包"""
    if show_all:
        from yanpub.pkg.registry import PackageRegistry

        registry = PackageRegistry()
        pkgs = registry.list_by_lang(lang) if lang else registry.list_all()
        if not pkgs:
            click.echo("注册中心没有包。")
            return
        click.echo(f"注册中心共 {len(pkgs)} 个包：\n")
        for p in pkgs:
            click.echo(f"  {p.name:30s} v{p.version:8s}  {p.description}")
    else:
        from yanpub.pkg.cache import PackageCache

        cache = PackageCache()
        pkgs = cache.list_by_lang(lang) if lang else cache.list_all()
        if not pkgs:
            click.echo("没有已安装的包。")
            return
        click.echo(f"已安装 {len(pkgs)} 个包：\n")
        for p in pkgs:
            click.echo(f"  {p.name:30s} v{p.version:8s}  {p.install_path}")

@pkg.command("search")
@click.argument("query")
@click.option("--lang", "-l", default=None, help="按语言筛选")
def pkg_search(query: str, lang: str | None):
    """搜索包"""
    from yanpub.pkg.registry import PackageRegistry

    registry = PackageRegistry()
    results = registry.search(query, lang)
    if not results:
        click.echo(f"未找到匹配 '{query}' 的包。")
        return
    click.echo(f"找到 {len(results)} 个包：\n")
    for p in results:
        click.echo(f"  {p.name:30s} v{p.version:8s}  {p.description}")

@pkg.command("publish")
@click.argument("package_dir", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="强制发布（跳过版本检查）")
def pkg_publish(package_dir: str, force: bool):
    """发布包（将本地包注册到注册中心）"""
    from pathlib import Path
    from yanpub.pkg.registry import PackageRegistry, PackageInfo
    from yanpub.pkg.resolver import DependencyResolver

    pkg_dir = Path(package_dir)
    toml_file = pkg_dir / "yanpkg.toml"

    if not toml_file.exists():
        click.echo(f"未找到 yanpkg.toml: {toml_file}", err=True)
        sys.exit(1)

    # 解析 yanpkg.toml
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    with open(toml_file, "rb") as f:
        config = tomllib.load(f)

    pkg_config = config.get("package", {})
    name = pkg_config.get("name", "")
    lang_id = pkg_config.get("lang", "")
    version = pkg_config.get("version", "0.1.0")
    description = pkg_config.get("description", "")
    authors = pkg_config.get("authors", [])
    tags = pkg_config.get("tags", [])

    if not name or not lang_id:
        click.echo("yanpkg.toml 中必须指定 package.name 和 package.lang", err=True)
        sys.exit(1)

    # 包名格式验证
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        click.echo(f"包名只能包含字母、数字、下划线和连字符: {name}", err=True)
        sys.exit(1)

    # 版本号格式验证（semver）
    if not re.match(r"^\d+\.\d+\.\d+([a-zA-Z0-9.+-]*)?$", version):
        click.echo(f"版本号格式不正确（需要 semver 如 1.0.0）: {version}", err=True)
        sys.exit(1)

    full_name = f"{lang_id}:{name}"

    # 版本降级检查
    registry = PackageRegistry()
    existing = registry.get(full_name)
    if existing and not force:
        if DependencyResolver._parse_version(version) <= DependencyResolver._parse_version(
            existing.version
        ):
            click.echo(
                f"版本未升级: 当前 {existing.version} -> 发布 {version}\n"
                f"新版本号必须大于当前版本，或使用 --force 跳过检查",
                err=True,
            )
            sys.exit(1)

    # 注册
    pkg_info = PackageInfo(
        name=full_name,
        lang=lang_id,
        package=name,
        version=version,
        description=description,
        authors=authors,
        tags=tags,
        source_type="local",
        source_url=str(pkg_dir),
    )
    registry.add(pkg_info)
    click.echo(f"[OK] {full_name} v{version} 已发布到本地注册中心")

@pkg.command("sync")
@click.option("--remote", "-r", default=None, help="远程注册中心 Git 仓库地址")
@click.option("--branch", "-b", default="main", help="远程仓库分支")
def pkg_sync(remote: str | None, branch: str):
    """同步远程注册中心索引"""
    from yanpub.pkg.remote import RemoteRegistry

    remote_url = (
        remote or RemoteRegistry.remote_url if hasattr(RemoteRegistry, "remote_url") else ""
    )
    click.echo("正在同步远程注册中心...")

    rr = RemoteRegistry(remote_url=remote_url) if remote_url else RemoteRegistry()
    stats = rr.sync(branch=branch)

    click.echo(f"同步完成：{stats['synced']} 个包")
    if stats["added"]:
        click.echo(f"  新增: {stats['added']} 个")
    if stats["updated"]:
        click.echo(f"  更新: {stats['updated']} 个")
    if stats["removed"]:
        click.echo(f"  移除: {stats['removed']} 个")
    for err in stats["errors"]:
        click.echo(f"  错误: {err}", err=True)

@pkg.command("lock")
@click.option("--update", "-u", "update_pkg", default=None, help="更新指定包（默认全部）")
def pkg_lock(update_pkg: str | None):
    """生成或更新依赖锁定文件"""
    from pathlib import Path as P
    from yanpub.pkg.lockfile import LockManager

    project_dir = P.cwd()
    lm = LockManager(project_dir)

    if update_pkg:
        click.echo(f"更新锁定: {update_pkg}...")
        lock = lm.update(update_pkg)
    else:
        click.echo("生成依赖锁定文件...")
        lock = lm.generate()

    click.echo(f"[OK] 已锁定 {len(lock.packages)} 个依赖 → yanpkg.lock")

@pkg.command("verify")
def pkg_verify():
    """验证依赖锁定文件完整性"""
    from pathlib import Path as P
    from yanpub.pkg.lockfile import LockManager

    project_dir = P.cwd()
    lm = LockManager(project_dir)

    if not lm.is_locked:
        click.echo("未找到 yanpkg.lock，请先运行 yanpub pkg lock", err=True)
        sys.exit(1)

    result = lm.verify()
    click.echo(f"验证完成: {result['checked']} 个包")

    if result["errors"]:
        click.echo(f"\n  错误 ({len(result['errors'])}):")
        for err in result["errors"]:
            click.echo(f"    ✗ {err}")

    if result["warnings"]:
        click.echo(f"\n  警告 ({len(result['warnings'])}):")
        for warn in result["warnings"]:
            click.echo(f"    ⚠ {warn}")

    if result["valid"]:
        click.echo("\n  ✅ 所有依赖验证通过")
    else:
        click.echo("\n  ❌ 验证失败")
        sys.exit(1)

@pkg.command("unlock")
def pkg_unlock():
    """删除依赖锁定文件"""
    from pathlib import Path as P
    from yanpub.pkg.lockfile import LockManager

    project_dir = P.cwd()
    lm = LockManager(project_dir)

    if lm.unlock():
        click.echo("[OK] yanpkg.lock 已删除")
    else:
        click.echo("未找到 yanpkg.lock", err=True)

@pkg.command("semantic-release")
@click.option("--dry-run", is_flag=True, help="试运行（不修改文件）")
def pkg_semantic_release(dry_run: bool):
    """语义发布 — 自动版本号 + changelog 生成"""
    from pathlib import Path as P
    from yanpub.pkg.semantic_release import semantic_release

    project_dir = P.cwd()
    result = semantic_release(project_dir, dry_run=dry_run)

    if "error" in result and result.get("error"):
        click.echo(f"错误: {result['error']}", err=True)
        sys.exit(1)

    click.echo(f"当前版本: {result['previous_version']}")
    click.echo(f"新版本:   {result['new_version']}")
    click.echo(f"递增类型: {result['bump_type']}")
    click.echo(f"Commits:  {result['commits_count']}")

    if result["bump_type"] == "none":
        click.echo("无需发布（没有符合条件的 commit）")
        return

    if dry_run:
        click.echo("\n(试运行模式，未修改任何文件)")
    else:
        if result["changelog_path"]:
            click.echo(f"Changelog: {result['changelog_path']}")

@pkg.command("changelog")
@click.option("--output", "-o", default=None, help="输出文件路径（默认 CHANGELOG.md）")
def pkg_changelog(output: str | None):
    """生成 CHANGELOG.md"""
    from pathlib import Path as P
    from yanpub.pkg.semantic_release import _get_commits_since_tag, ChangelogGenerator
    import tomllib

    project_dir = P.cwd()
    toml_path = project_dir / "yanpkg.toml"

    if not toml_path.exists():
        click.echo("未找到 yanpkg.toml", err=True)
        sys.exit(1)

    with open(toml_path, "rb") as f:
        config = tomllib.load(f)
    version_str = config.get("package", {}).get("version", "0.0.0")

    commits = _get_commits_since_tag(project_dir)
    if not commits:
        click.echo("没有找到 Conventional Commits")
        return

    changelog_path = P(output) if output else project_dir / "CHANGELOG.md"
    previous = ""
    if changelog_path.exists():
        previous = changelog_path.read_text(encoding="utf-8")

    content = ChangelogGenerator.generate(commits, version=version_str, previous_changelog=previous)
    changelog_path.write_text(content, encoding="utf-8")
    click.echo(f"[OK] Changelog 已生成: {changelog_path}")

@pkg.command("bump-version")
@click.argument("bump_type", type=click.Choice(["major", "minor", "patch"]))
@click.option("--dry-run", is_flag=True, help="试运行")
def pkg_bump_version(bump_type: str, dry_run: bool):
    """手动递增版本号"""
    from pathlib import Path as P
    from yanpub.pkg.semantic_release import SemanticVersion, VersionBumper, _update_toml_version
    import tomllib

    project_dir = P.cwd()
    toml_path = project_dir / "yanpkg.toml"

    if not toml_path.exists():
        click.echo("未找到 yanpkg.toml", err=True)
        sys.exit(1)

    with open(toml_path, "rb") as f:
        config = tomllib.load(f)
    version_str = config.get("package", {}).get("version", "0.0.0")

    current = SemanticVersion.parse(version_str)
    new = VersionBumper.bump(current, bump_type)

    click.echo(f"{current} → {new}")

    if not dry_run:
        _update_toml_version(toml_path, str(new))
        click.echo("[OK] 版本号已更新")
    else:
        click.echo("(试运行模式，未修改文件)")

main.add_command(pkg)
