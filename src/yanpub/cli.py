"""统一 CLI 入口"""

from __future__ import annotations

import os
import sys
import time

import click

# Windows 终端 UTF-8 输出支持
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from yanpub.core.registry import get_registry


@click.group()
@click.version_option(version="1.4.0")
@click.option("--lang", "-L", "cli_lang", default=None, help="语言设置（zh/en）")
def main(cli_lang: str | None):
    """言埠 YanPub -- 中文编程语言统一基础设施"""
    if cli_lang:
        from yanpub.i18n import set_lang

        set_lang(cli_lang)


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


@main.group()
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


@main.command()
@click.option("--output", "-o", default="yandocs_site", help="输出目录")
def docs(output: str):
    """生成统一文档站"""
    from yanpub.docs.site_builder import build_site

    click.echo("正在生成文档站...")
    out = build_site(output)
    click.echo(f"文档站已生成: {out}")
    click.echo(f"打开 {out / 'index.html'} 查看首页")


@main.command("seo")
@click.argument("action", type=click.Choice(["generate", "validate", "sitemap"]))
@click.option("--output", "-o", type=click.Path(), help="输出目录")
@click.option("--base-url", default="https://yanpub.dev", help="站点 URL")
def seo_command(action: str, output: str | None, base_url: str):
    """SEO 优化 — 生成/验证/sitemap"""
    from pathlib import Path as P
    from yanpub.docs.site_builder import SEOConfig, SEOOptimizer, SitemapGenerator, build_site

    config = SEOConfig(site_url=base_url)

    if action == "generate":
        # 生成带 SEO 优化的文档站
        out_dir = output or "yandocs_site"
        click.echo(f"正在生成 SEO 优化文档站（站点 URL: {base_url}）...")
        out = build_site(out_dir, seo_config=config)
        click.echo(f"[OK] 文档站已生成: {out}")
        click.echo(f"  sitemap.xml: {out / 'sitemap.xml'}")
        click.echo(f"  robots.txt:   {out / 'robots.txt'}")
        click.echo(f"  首页:         {out / 'index.html'}")

    elif action == "validate":
        # 验证已生成站点的 SEO 元素
        out_dir = P(output) if output else P("yandocs_site")
        optimizer = SEOOptimizer(config)

        if not out_dir.exists():
            click.echo(f"目录不存在: {out_dir}，请先运行 yanpub seo generate", err=True)
            sys.exit(1)

        # 收集 HTML 文件
        html_files = sorted(out_dir.glob("*.html"))
        if not html_files:
            click.echo("未找到 HTML 文件", err=True)
            sys.exit(1)

        click.echo(f"SEO 验证（{len(html_files)} 个页面）:\n")
        all_passed = True
        for html_file in html_files:
            content = html_file.read_text(encoding="utf-8")
            result = optimizer.validate_html(content)
            status = "✅" if result["passed"] else "❌"
            click.echo(f"  {status} {html_file.name}")
            if not result["passed"]:
                all_passed = False
                for issue in result["issues"]:
                    click.echo(f"     - {issue}")

        # 检查 sitemap 和 robots
        click.echo()
        sitemap_path = out_dir / "sitemap.xml"
        robots_path = out_dir / "robots.txt"
        click.echo(f"  {'✅' if sitemap_path.exists() else '❌'} sitemap.xml")
        click.echo(f"  {'✅' if robots_path.exists() else '❌'} robots.txt")

        if all_passed and sitemap_path.exists() and robots_path.exists():
            click.echo("\n✅ SEO 验证通过")
        else:
            click.echo("\n❌ SEO 验证未通过")
            sys.exit(1)

    elif action == "sitemap":
        # 单独生成 sitemap.xml
        out_dir = P(output) if output else P("yandocs_site")
        out_dir.mkdir(parents=True, exist_ok=True)

        optimizer = SEOOptimizer(config)
        sitemap = SitemapGenerator(base_url)

        # 检查已有 HTML 文件
        html_files = sorted(out_dir.glob("*.html"))
        if not html_files:
            click.echo("未找到 HTML 文件，请先运行 yanpub docs 或 yanpub seo generate", err=True)
            sys.exit(1)

        from datetime import date

        today = date.today().isoformat()

        for html_file in html_files:
            name = html_file.name
            if name == "index.html":
                sitemap.add_page(name, lastmod=today, changefreq="daily", priority=1.0)
            else:
                sitemap.add_page(name, lastmod=today, changefreq="weekly", priority=0.8)

        sitemap.write(out_dir)

        # 同时生成 robots.txt
        (out_dir / "robots.txt").write_text(
            optimizer.generate_robots_txt(),
            encoding="utf-8",
        )

        click.echo(f"[OK] sitemap.xml 已生成: {out_dir / 'sitemap.xml'}")
        click.echo(f"[OK] robots.txt 已生成: {out_dir / 'robots.txt'}")
        click.echo(f"  包含 {len(html_files)} 个页面")


@main.command()
@click.argument("concept", required=False)
@click.option("--from", "from_lang", default=None, help="源语言ID")
@click.option("--to", "to_lang", default=None, help="目标语言ID")
@click.option("--matrix", "show_matrix", is_flag=True, help="显示语法对比矩阵")
@click.option("--html", "html_path", default=None, help="生成 HTML 对比页面（指定输出路径）")
@click.option(
    "--concept-id",
    "concept_ids",
    multiple=True,
    help="只对比指定概念（可多次使用）",
)
def compare(
    concept: str | None,
    from_lang: str | None,
    to_lang: str | None,
    show_matrix: bool,
    html_path: str | None,
    concept_ids: tuple[str, ...],
):
    """语言对比 — 比较不同中文编程语言的语法

    \b
    yanpub compare                    # 相似度排行 + 概念对比
    yanpub compare --matrix           # 语法对比矩阵（代码级）
    yanpub compare --html matrix.html # 生成 HTML 可视化页面
    yanpub compare --from duan --to yan  # 迁移指南
    yanpub compare 定义               # 搜索概念在各语言中的关键字
    yanpub compare --matrix --concept-id var_declare --concept-id func_def
    """
    from yanpub.docs.comparator import LanguageComparator

    # 生成 HTML 对比页面
    if html_path:
        from yanpub.core.syntax_matrix import SyntaxMatrix

        sm = SyntaxMatrix()
        click.echo("正在生成 HTML 对比页面...", err=True)
        sm.generate_html(html_path)
        click.echo(f"对比页面已生成: {html_path}")
        return

    # 语法对比矩阵
    if show_matrix:
        from yanpub.core.syntax_matrix import SyntaxMatrix

        sm = SyntaxMatrix()
        registry = get_registry()
        lang_ids = sm.lang_ids

        # 过滤概念
        matrix = sm.get_matrix()
        if concept_ids:
            matrix = [e for e in matrix if e["concept"].id in concept_ids]

        # 打印语法风格总览
        styles = sm.compute_syntax_style()
        click.echo("语法风格总览：\n")

        style_keys = ["变量风格", "函数风格", "语句结束", "代码块", "运算风格", "注释"]
        header = f"{'特征':10s}"
        for lid in lang_ids:
            adapter = registry.get(lid)
            name = adapter.name if adapter else lid
            header += f" {name:12s}"
        click.echo(header)
        click.echo("─" * len(header))

        for style_key in style_keys:
            row = f"{style_key:10s}"
            for lid in lang_ids:
                feat = styles.get(lid, {})
                val = feat.get(style_key, "—")
                row += f" {val:12s}"
            click.echo(row)

        # 打印代码对比矩阵
        click.echo("\n\n代码对比矩阵：\n")

        for entry in matrix:
            concept_obj = entry["concept"]
            snippets = entry["snippets"]
            click.echo(f"── {concept_obj.title} [{concept_obj.category}] ──")
            click.echo(f"   {concept_obj.description}\n")

            for lid in lang_ids:
                snippet = snippets.get(lid)
                if snippet is None:
                    continue
                adapter = registry.get(lid)
                name = adapter.name if adapter else lid
                for line in snippet.code.split("\n"):
                    click.echo(f"  {name:4s} | {line}")
                if snippet.note:
                    click.echo(f"       └─ {snippet.note}")
                click.echo()
            click.echo()

        return

    comparator = LanguageComparator()

    if from_lang and to_lang:
        # 生成迁移指南
        guide = comparator.generate_migration_guide(from_lang, to_lang)
        if guide is None:
            click.echo(f"未找到语言: {from_lang} 或 {to_lang}", err=True)
            sys.exit(1)

        click.echo(f"\n{guide['from']['name']} -> {guide['to']['name']} 迁移指南")
        click.echo(f"相似度: {guide['similarity_score']:.1%}")
        click.echo(f"共享关键字: {len(guide['shared_keywords'])}个")
        click.echo(f"共享概念分类: {', '.join(guide['shared_categories'])}\n")

        click.echo("概念映射：")
        for cat, mapping in guide["concept_map"].items():
            shared = mapping["shared"]
            only_from = mapping["only_from"]
            only_to = mapping["only_to"]
            if shared:
                click.echo(f"  {cat}: 共享 {'、'.join(shared)}")
            if only_from:
                click.echo(f"  {cat}: 仅{guide['from']['name']} {'、'.join(only_from)}")
            if only_to:
                click.echo(f"  {cat}: 仅{guide['to']['name']} {'、'.join(only_to)}")

    elif concept:
        # 搜索特定概念在各语言中的关键字
        results = comparator.compare_all_concepts()
        found = [r for r in results if r.concept == concept]
        if not found:
            click.echo(f"未找到概念: {concept}")
            click.echo(f"可用概念: {', '.join(r.concept for r in results)}")
            return
        for comp in found:
            click.echo(f"\n概念: {comp.concept}")
            for lang_id, kws in comp.mappings.items():
                adapter = get_registry().get(lang_id)
                name = adapter.name if adapter else lang_id
                click.echo(f"  {name}: {'、'.join(kws)}")
    else:
        # 显示相似度排行
        similarities = comparator.compute_all_similarities()
        if not similarities:
            click.echo("需要至少2种语言才能对比。")
            return

        click.echo("语言相似度排行：\n")
        for sim in similarities[:10]:
            adapter_a = get_registry().get(sim.lang_id_a)
            adapter_b = get_registry().get(sim.lang_id_b)
            name_a = adapter_a.name if adapter_a else sim.lang_id_a
            name_b = adapter_b.name if adapter_b else sim.lang_id_b
            click.echo(
                f"  {name_a} <-> {name_b}: {sim.similarity_score:.1%} ({len(sim.shared_keywords)}个共享关键字)"
            )

        # 全部概念对比
        click.echo("\n概念对比表：\n")
        all_comps = comparator.compare_all_concepts()
        for comp in all_comps:
            parts = []
            for lang_id, kws in comp.mappings.items():
                adapter = get_registry().get(lang_id)
                name = adapter.name if adapter else lang_id
                parts.append(f"{name}={','.join(kws)}")
            click.echo(f"  {comp.concept}: {' | '.join(parts)}")


@main.command()
def languages():
    """列出所有已注册的语言"""
    registry = get_registry()
    if not registry:
        click.echo("没有注册任何语言适配器。")
        return

    click.echo(f"已注册 {len(registry)} 种语言：\n")
    for info in registry.list_languages():
        exts = ", ".join(info["extensions"])
        caps = [k for k, v in info["capabilities"].items() if v]
        click.echo(f"  {info['name']:8s} ({info['id']:10s}) v{info['version']:8s}  {exts}")
        if caps:
            click.echo(f"          能力: {', '.join(caps)}")


@main.command()
@click.argument("lang_id", required=False)
@click.option("--run", "-r", "example_name", default=None, help="运行指定示例（传入示例名称）")
@click.option("--show", "-s", "show_code", is_flag=True, help="显示示例代码内容")
@click.option("--search", "-S", "keyword", default=None, help="按关键字搜索示例")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出")
def examples(
    lang_id: str | None,
    example_name: str | None,
    show_code: bool,
    keyword: str | None,
    as_json: bool,
):
    """查看和运行各语言的示例代码

    不带参数：列出所有语言的可用示例

    \b
    yanpub examples              # 列出所有语言的示例
    yanpub examples duan         # 列出段言的所有示例
    yanpub examples duan -s      # 显示段言所有示例的代码
    yanpub examples duan -r hello  # 运行段言的 hello 示例
    yanpub examples -S 递归       # 搜索包含"递归"的示例
    """
    from yanpub.core.examples import get_example_manager

    manager = get_example_manager()

    # 搜索模式
    if keyword:
        results = manager.search(keyword)
        if not results:
            click.echo(f"未找到包含「{keyword}」的示例。")
            return
        _print_search_results(results, show_code, as_json)
        return

    # 指定语言
    if lang_id:
        ex_list = manager.list_for_language(lang_id)
        if not ex_list:
            registry = get_registry()
            if lang_id not in registry:
                click.echo(f"未知语言: {lang_id}", err=True)
                click.echo(f"可用语言: {', '.join(registry.language_ids)}")
                sys.exit(1)
            adapter = registry.get(lang_id)
            click.echo(f"{adapter.name} ({lang_id}) 暂无示例。")
            return

        # 运行指定示例
        if example_name:
            click.echo(f"正在运行 {lang_id}/{example_name} ...", err=True)
            result = manager.run_example(lang_id, example_name)
            if result is None:
                click.echo(f"示例不存在: {lang_id}/{example_name}", err=True)
                available = ", ".join(ex.name for ex in ex_list)
                click.echo(f"可用示例: {available}")
                sys.exit(1)
            if result["stdout"]:
                click.echo(result["stdout"], nl=False)
            if result["stderr"]:
                click.echo(result["stderr"], nl=False, err=True)
            if not result["success"]:
                sys.exit(1)
            return

        # 显示/列出示例
        adapter = get_registry().get(lang_id)
        lang_name = adapter.name if adapter else lang_id
        if as_json:
            _print_examples_json(ex_list)
        elif show_code:
            _print_examples_with_code(lang_name, lang_id, ex_list)
        else:
            _print_examples_list(lang_name, lang_id, ex_list)
        return

    # 列出所有语言的示例
    all_examples = manager.list_all()
    if not all_examples:
        click.echo("暂无任何示例。")
        return

    if as_json:
        _print_all_examples_json(all_examples)
    else:
        total = sum(len(ex_list) for ex_list in all_examples.values())
        click.echo(f"共 {len(all_examples)} 种语言，{total} 个示例：\n")
        for lid in sorted(all_examples.keys()):
            ex_list = all_examples[lid]
            adapter = get_registry().get(lid)
            lang_name = adapter.name if adapter else lid
            names = ", ".join(ex.name for ex in ex_list)
            click.echo(f"  {lang_name} ({lid}): {names}")


def _print_examples_list(lang_name: str, lang_id: str, examples_list: list):
    """打印某语言的示例列表"""
    click.echo(f"{lang_name} ({lang_id}) 的示例：\n")
    for ex in examples_list:
        line = f"  {ex.name}"
        if ex.title != ex.name:
            line += f" — {ex.title}"
        if ex.difficulty:
            line += f" [{ex.difficulty}]"
        if ex.tags:
            line += f" #{' #'.join(ex.tags)}"
        if ex.source == "adapter":
            line += " (语言维护)"
        click.echo(line)


def _print_examples_with_code(lang_name: str, lang_id: str, examples_list: list):
    """打印某语言的示例及代码内容"""
    for i, ex in enumerate(examples_list):
        if i > 0:
            click.echo("\n" + "─" * 60 + "\n")
        header = f"{lang_name}/{ex.name}"
        if ex.title != ex.name:
            header += f" — {ex.title}"
        click.echo(f"── {header} ──\n")
        click.echo(ex.code)


@main.command()
@click.argument("lang_id")
@click.option("--name", "-n", default=None, help="示例名称（文件名，不含扩展名）")
@click.option("--title", "-t", default=None, help="显示标题")
@click.option("--tags", default=None, help="标签，逗号分隔（如: 递归,算法）")
@click.option("--difficulty", "-d", type=click.Choice(["入门", "简单", "中等", "困难"]), default=None, help="难度")
@click.option("--description", "-D", default=None, help="简短描述")
@click.option("--author", "-a", default=None, help="作者署名")
@click.option("--code", "-c", default=None, help="示例代码（或从 stdin 读取）")
@click.option("--file", "-f", "code_file", default=None, help="从文件读取示例代码")
@click.option("--dry-run", is_flag=True, help="仅预览，不写入文件")
@click.option("--output-dir", "-o", default=None, help="输出目录（默认自动推断）")
def contribute(
    lang_id: str,
    name: str | None,
    title: str | None,
    tags: str | None,
    difficulty: str | None,
    description: str | None,
    author: str | None,
    code: str | None,
    code_file: str | None,
    dry_run: bool,
    output_dir: str | None,
):
    """贡献一个示例到指定语言

    交互式创建示例，也可以通过选项直接指定所有参数。

    \b
    yanpub examples contribute duan                    # 交互式创建段言示例
    yanpub examples contribute duan -n sort -t "排序"   # 指定名称和标题
    yanpub examples contribute duan -c "打印('hi')"     # 直接传入代码
    yanpub examples contribute duan -f code.duan        # 从文件读取代码
    echo "打印('hi')" | yanpub examples contribute duan -n hello  # 从 stdin 读取
    """
    from yanpub.core.examples import get_example_manager, validate_example_meta

    registry = get_registry()
    if lang_id not in registry:
        click.echo(f"未知语言: {lang_id}", err=True)
        click.echo(f"可用语言: {', '.join(sorted(registry.language_ids))}")
        sys.exit(1)

    adapter = registry.get(lang_id)
    lang_name = adapter.name if adapter else lang_id

    # 获取代码内容
    if code_file:
        from pathlib import Path as PathLib

        p = PathLib(code_file)
        if not p.exists():
            click.echo(f"文件不存在: {code_file}", err=True)
            sys.exit(1)
        code_content = p.read_text(encoding="utf-8")
    elif code:
        code_content = code
    elif not sys.stdin.isatty():
        code_content = sys.stdin.read()
    else:
        code_content = None

    # 判断是否为交互模式：缺少必需参数时提示
    interactive = sys.stdin.isatty() and (name is None or code_content is None)

    if name is None:
        if not sys.stdin.isatty():
            click.echo("错误：非交互模式下必须指定 --name", err=True)
            sys.exit(1)
        name = click.prompt("示例名称（文件名，不含扩展名）", type=str)
    if title is None:
        if interactive:
            title = click.prompt("显示标题", default=name)
        else:
            title = name
    if code_content is None:
        if not interactive:
            click.echo("错误：非交互模式下必须指定 --code 或 --file", err=True)
            sys.exit(1)
        click.echo(f"\n请输入 {lang_name} 示例代码（输入空行结束）：")
        lines: list[str] = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        code_content = "\n".join(lines)
        if not code_content.strip():
            click.echo("代码不能为空。", err=True)
            sys.exit(1)

    # 可选参数：交互模式下提示，非交互模式下默认为空
    if difficulty is None and interactive:
        difficulty = click.prompt(
            "难度",
            type=click.Choice(["入门", "简单", "中等", "困难", ""]),
            default="",
        )
    elif difficulty is None:
        difficulty = ""
    if tags is None:
        if interactive:
            tags_input = click.prompt("标签（逗号分隔，留空跳过）", default="")
            tags_list = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
        else:
            tags_list = []
    else:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    if description is None and interactive:
        description = click.prompt("简短描述（留空跳过）", default="")
    elif description is None:
        description = ""
    if author is None and interactive:
        author = click.prompt("作者署名（留空跳过）", default="")
    elif author is None:
        author = ""

    # 验证
    issues = validate_example_meta(
        name=name,
        title=title,
        code=code_content,
        lang_id=lang_id,
        tags=tags_list,
        difficulty=difficulty,
    )
    if issues:
        click.echo("\n验证失败：", err=True)
        for issue in issues:
            click.echo(f"  - {issue}", err=True)
        sys.exit(1)

    # 构建预览
    from yanpub.core.examples import _build_example_file

    file_content = _build_example_file(
        title=title,
        tags=tags_list,
        difficulty=difficulty,
        description=description,
        author=author,
        code=code_content,
    )

    # 确定输出路径
    out_dir = PathLib(output_dir) if output_dir else None
    manager = get_example_manager()
    if out_dir is None:
        ext = manager._get_extension_for_lang(lang_id)
    else:
        ext = manager._get_extension_for_lang(lang_id)

    if dry_run:
        click.echo(f"\n--- 预览: {lang_id}/{name}{ext} ---\n")
        click.echo(file_content)
        click.echo("\n--- 预览结束（dry-run 模式，未写入文件）---")
        return

    # 写入文件
    try:
        file_path = manager.contribute_example(
            lang_id=lang_id,
            name=name,
            code=code_content,
            title=title,
            tags=tags_list,
            difficulty=difficulty,
            description=description,
            author=author,
            output_dir=out_dir,
        )
        click.echo(f"示例已创建: {file_path}")
        click.echo(f"  语言: {lang_name} ({lang_id})")
        click.echo(f"  名称: {name}")
        click.echo(f"  标题: {title}")
        if tags_list:
            click.echo(f"  标签: {', '.join(tags_list)}")
        if difficulty:
            click.echo(f"  难度: {difficulty}")
        if author:
            click.echo(f"  作者: {author}")
        click.echo("\n使用以下命令查看:")
        click.echo(f"  yanpub examples {lang_id} -s")
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"创建失败: {e}", err=True)
        sys.exit(1)


@main.command("validate-examples")
@click.argument("lang_id")
@click.argument("name", required=False)
def validate_examples(lang_id: str, name: str | None):
    """验证示例的元数据和代码

    \b
    yanpub examples validate duan          # 验证段言所有示例
    yanpub examples validate duan hello    # 验证指定示例
    """
    from yanpub.core.examples import get_example_manager, validate_example_meta

    manager = get_example_manager()
    ex_list = manager.list_for_language(lang_id)

    if not ex_list:
        registry = get_registry()
        if lang_id not in registry:
            click.echo(f"未知语言: {lang_id}", err=True)
            sys.exit(1)
        click.echo(f"{lang_id} 暂无示例。")
        return

    if name:
        ex_list = [e for e in ex_list if e.name == name]
        if not ex_list:
            click.echo(f"示例不存在: {lang_id}/{name}", err=True)
            sys.exit(1)

    total = len(ex_list)
    passed = 0
    failed = 0

    for ex in ex_list:
        issues = validate_example_meta(
            name=ex.name,
            title=ex.title,
            code=ex.code,
            lang_id=ex.lang_id,
            tags=ex.tags,
            difficulty=ex.difficulty,
        )
        if issues:
            failed += 1
            click.echo(f"  FAIL {ex.name}")
            for issue in issues:
                click.echo(f"       {issue}")
        else:
            passed += 1

    click.echo(f"\n验证完成: {passed}/{total} 通过", nl=False)
    if failed:
        click.echo(f"，{failed} 个失败")
    else:
        click.echo()


def _print_search_results(results: dict, show_code: bool, as_json: bool):
    """打印搜索结果"""
    if as_json:
        _print_all_examples_json(results)
        return

    total = sum(len(ex_list) for ex_list in results.values())
    click.echo(f"找到 {total} 个示例：\n")
    for lid in sorted(results.keys()):
        ex_list = results[lid]
        adapter = get_registry().get(lid)
        lang_name = adapter.name if adapter else lid
        for ex in ex_list:
            line = f"  {lang_name}/{ex.name}"
            if ex.title != ex.name:
                line += f" — {ex.title}"
            click.echo(line)
            if show_code:
                # 缩进显示代码
                for code_line in ex.code.split("\n"):
                    click.echo(f"    {code_line}")
                click.echo()


def _print_examples_json(examples_list: list):
    """以 JSON 格式打印示例列表"""
    import json as json_mod

    data = []
    for ex in examples_list:
        data.append(
            {
                "name": ex.name,
                "title": ex.title,
                "lang_id": ex.lang_id,
                "path": str(ex.path),
                "source": ex.source,
                "tags": ex.tags,
                "difficulty": ex.difficulty,
                "description": ex.description,
                "author": ex.author,
            }
        )
    click.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))


def _print_all_examples_json(all_examples: dict):
    """以 JSON 格式打印所有语言的示例"""
    import json as json_mod

    data = {}
    for lid, ex_list in all_examples.items():
        data[lid] = [
            {
                "name": ex.name,
                "title": ex.title,
                "lang_id": ex.lang_id,
                "path": str(ex.path),
                "source": ex.source,
                "tags": ex.tags,
                "difficulty": ex.difficulty,
                "description": ex.description,
                "author": ex.author,
            }
            for ex in ex_list
        ]
    click.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))


@main.command()
@click.argument("lang_id", required=False)
def health(lang_id: str | None):
    """检查语言后端健康状态"""
    from yanpub.core.health import check_adapter_health, check_all_adapters, format_health_report

    registry = get_registry()

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知语言: {lang_id}", err=True)
            sys.exit(1)
        result = check_adapter_health(adapter)
        click.echo(format_health_report([result]))
        if not result.is_available:
            sys.exit(1)
    else:
        results = check_all_adapters(registry)
        click.echo(format_health_report(results))
        unhealthy = sum(1 for r in results if not r.is_available)
        if unhealthy > 0:
            sys.exit(1)


@main.command()
@click.argument("lang_id", required=False)
@click.option("--iterations", "-n", default=5, type=int, help="每项测试迭代次数")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
def bench(lang_id: str | None, iterations: int, as_json: bool):
    """运行性能基准测试"""
    from yanpub.core.benchmark import run_all_benchmarks, format_bench_report

    registry = get_registry()

    click.echo("正在运行基准测试...", err=True)
    results = run_all_benchmarks(registry, iterations=iterations, lang_id=lang_id)

    if not results:
        if lang_id:
            click.echo(f"未知语言: {lang_id}", err=True)
        else:
            click.echo("没有可用的适配器", err=True)
        sys.exit(1)

    if as_json:
        import json

        click.echo(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        click.echo(format_bench_report(results))


@main.command()
@click.argument("lang_id", required=False)
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
def compat(lang_id: str | None, as_json: bool):
    """检查适配器版本兼容性"""
    from yanpub.core.compat import (
        check_compatibility,
        check_all_compatibility,
        format_compat_matrix,
        format_compat_detail,
    )

    registry = get_registry()

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知语言: {lang_id}", err=True)
            sys.exit(1)
        result = check_compatibility(adapter)
        if as_json:
            import json

            click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            click.echo(format_compat_detail(result))
    else:
        results = check_all_compatibility(registry)
        if as_json:
            import json

            click.echo(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        else:
            click.echo(format_compat_matrix(results))
        incompatible = sum(1 for r in results if not r.is_compatible)
        if incompatible > 0:
            sys.exit(1)


@main.group()
def plugin():
    """插件管理 — 安装/卸载/管理第三方工具链插件"""
    pass


@main.group()
def adapter():
    """适配器管理 — 热重载/监控"""
    pass


@main.command("cache")
@click.argument("action", type=click.Choice(["stats", "clear", "invalidate"]))
@click.option("--adapter", "-a", default=None, help="适配器 ID（invalidate 时指定）")
def cache_command(action: str, adapter: str | None):
    """缓存管理 — 统计/清除/失效"""
    from yanpub.core.cache import get_adapter_cache

    cache = get_adapter_cache()

    if action == "stats":
        stats = cache.stats()
        click.echo("适配器缓存统计：\n")
        for cache_type, info in stats.items():
            click.echo(f"  {cache_type}:")
            click.echo(f"    条目数:  {info['size']}/{info['max_size']}")
            click.echo(f"    命中:    {info['hits']}")
            click.echo(f"    未命中:  {info['misses']}")
            click.echo(f"    命中率:  {info['hit_rate']:.1%}")
            click.echo()

    elif action == "clear":
        cache.clear()
        click.echo("[OK] 所有缓存已清空")

    elif action == "invalidate":
        if not adapter:
            click.echo("请指定适配器 ID: --adapter <id> 或 -a <id>", err=True)
            sys.exit(1)
        count = cache.invalidate_adapter(adapter)
        click.echo(f"[OK] 已失效 {adapter} 的 {count} 条缓存")


@adapter.command("watch")
@click.option("--poll", is_flag=True, help="使用轮询模式（无需 watchdog）")
@click.option("--interval", "-i", default=2.0, type=float, help="轮询间隔（秒）")
def adapter_watch(poll: bool, interval: float):
    """监控适配器文件变更，自动热重载"""
    from yanpub.core.hotreload import AdapterWatcher

    registry = get_registry()
    click.echo(f"已注册 {len(registry)} 种适配器，开始监控...")

    watcher = AdapterWatcher(registry, poll_interval=interval)

    def on_reload(event):
        status = "✅" if event.success else "❌"
        click.echo(f"  {status} [{event.event_type}] {event.adapter_name} ({event.adapter_id})")
        if not event.success:
            click.echo(f"     错误: {event.error}")

    watcher.on_reload(on_reload)
    watcher.start()

    click.echo("按 Ctrl+C 停止监控")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        click.echo("\n监控已停止")


@adapter.command("reload")
@click.argument("lang_id", required=False)
def adapter_reload(lang_id: str | None):
    """手动重载适配器"""
    from yanpub.core.hotreload import HotReloader

    registry = get_registry()
    reloader = HotReloader(registry)

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知适配器: {lang_id}", err=True)
            sys.exit(1)

    click.echo("检查适配器变更...")
    events = reloader.check_and_reload()

    if not events:
        click.echo("没有检测到变更")
        return

    for event in events:
        status = "✅" if event.success else "❌"
        click.echo(f"  {status} [{event.event_type}] {event.adapter_name} ({event.adapter_id})")
        if not event.success:
            click.echo(f"     错误: {event.error}")


@adapter.command("profile")
@click.argument("lang_id")
@click.option("--iterations", "-n", default=5, type=int, help="迭代次数")
@click.option("--code", "-c", default=None, help="分析代码（默认用适配器示例代码）")
@click.option("--output", "-o", default=None, help="输出报告路径（默认控制台输出）")
@click.option(
    "--format", "fmt", type=click.Choice(["text", "html", "svg"]), default="text", help="输出格式"
)
@click.option("--hotspots", is_flag=True, help="是否显示热点分析")
def adapter_profile(
    lang_id: str, iterations: int, code: str | None, output: str | None, fmt: str, hotspots: bool
):
    """性能分析适配器"""
    from yanpub.core.profiler import (
        AdapterProfiler,
        FlameGraphGenerator,
        HotspotDetector,
        _default_code,
    )

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知适配器: {lang_id}", err=True)
        sys.exit(1)

    # 确定分析代码
    sample_code = code or _default_code(adapter)

    click.echo(f"性能分析: {adapter.name} ({adapter.id})")
    click.echo(f"迭代次数: {iterations}")
    click.echo()

    profiler = AdapterProfiler(adapter)
    reports = profiler.profile_all(sample_code, iterations=iterations)

    if fmt == "text":
        # 控制台输出文本报告
        for op_name, report in reports.items():
            click.echo(report.to_table())
            click.echo()

        if hotspots:
            detector = HotspotDetector()
            hotspot_list = detector.analyze(reports)
            click.echo("热点分析:")
            click.echo("─" * 60)
            for h in hotspot_list:
                icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢"}.get(h.severity, "⚪")
                click.echo(f"  {icon} {h.operation}: {h.avg_ms:.2f}ms [{h.severity}]")
                if h.severity != "normal":
                    click.echo(f"     💡 {h.suggestion}")
            click.echo()

    elif fmt == "html":
        from pathlib import Path as P

        report_dict = {name: r.to_dict() for name, r in reports.items()}
        html = FlameGraphGenerator.generate_html(report_dict)
        if output:
            path = P(output)
            path.write_text(html, encoding="utf-8")
            click.echo(f"HTML 报告已保存: {path}")
        else:
            click.echo(html)

    elif fmt == "svg":
        from pathlib import Path as P

        report_dict = {name: r.to_dict() for name, r in reports.items()}
        svg = FlameGraphGenerator.generate_svg(report_dict)
        if output:
            path = P(output)
            path.write_text(svg, encoding="utf-8")
            click.echo(f"SVG 报告已保存: {path}")
        else:
            click.echo(svg)


@adapter.command("navigate")
@click.argument("lang_id")
@click.argument("symbol")
@click.option(
    "--type",
    "nav_type",
    type=click.Choice(["definition", "references", "callers", "callees"]),
    default="definition",
)
def adapter_navigate(lang_id: str, symbol: str, nav_type: str):
    """导航 — 查找定义/引用/调用者/被调用者"""
    from yanpub.core.navigator import SymbolNavigator

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知适配器: {lang_id}", err=True)
        sys.exit(1)

    navigator = SymbolNavigator(keywords=adapter.keywords)
    import json

    if nav_type == "definition":
        # 使用空代码 + 空文档，仅通过符号名搜索定义
        # 实际使用中应传入文件内容，此处为 CLI 演示
        code = ""
        docs: dict[str, str] = {}
        results = navigator.find_definition(code, 1, 1, uri="", documents=docs)
        # CLI 模式下：如果没有文档，尝试从关键字推断
        if not results:
            click.echo(f"未找到 '{symbol}' 的定义（无打开的文档）")
            click.echo("提示：在 LSP 模式下使用可获得完整导航功能")
            return
        click.echo(f"定义 ({len(results)} 个)：")
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))

    elif nav_type == "references":
        code = ""
        docs: dict[str, str] = {}
        results = navigator.find_references(code, 1, 1, uri="", documents=docs)
        if not results:
            click.echo(f"未找到 '{symbol}' 的引用（无打开的文档）")
            click.echo("提示：在 LSP 模式下使用可获得完整导航功能")
            return
        click.echo(f"引用 ({len(results)} 个)：")
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))

    elif nav_type == "callers":
        code = ""
        docs: dict[str, str] = {}
        results = navigator._find_incoming_calls(symbol, "", docs)
        if not results:
            click.echo(f"未找到调用 '{symbol}' 的函数（无打开的文档）")
            return
        click.echo(f"调用者 ({len(results)} 个)：")
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))

    elif nav_type == "callees":
        code = ""
        docs: dict[str, str] = {}
        results = navigator._find_outgoing_calls(
            code,
            symbol,
            {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
            "",
            docs,
        )
        if not results:
            click.echo(f"未找到 '{symbol}' 调用的函数（无打开的文档）")
            return
        click.echo(f"被调用者 ({len(results)} 个)：")
        click.echo(json.dumps(results, ensure_ascii=False, indent=2))


@adapter.command("test")
@click.argument("lang_id", required=False)
@click.option("--category", "-c", multiple=True, help="测试分类（可多次指定）")
@click.option("--output", "-o", type=click.Path(), help="报告输出路径")
@click.option("--format", "fmt", type=click.Choice(["table", "json", "html"]), default="table")
@click.option("--generate-regression", is_flag=True, help="生成回归测试")
def adapter_test(
    lang_id: str | None,
    category: tuple[str, ...],
    output: str | None,
    fmt: str,
    generate_regression: bool,
):
    """运行适配器测试套件"""
    from yanpub.core.adapter_test import get_builtin_suite, RegressionTestGenerator

    registry = get_registry()
    suite = get_builtin_suite()
    categories = list(category) if category else None

    if generate_regression:
        gen = RegressionTestGenerator()
        for adapter in registry:
            if lang_id and adapter.id != lang_id:
                continue
            code_samples = [
                adapter.comment_syntax + " regression sample\n",
            ]
            tests = gen.generate_from_execution(adapter, code_samples)
            for t in tests:
                suite.add_test(t)
        click.echo(f"已生成回归测试，共 {suite.test_count} 个用例", err=True)

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知适配器: {lang_id}", err=True)
            sys.exit(1)
        click.echo(f"运行适配器测试: {adapter.name} ({adapter.id})\n", err=True)
        report = suite.run(adapter, categories=categories)
        _output_report(report, fmt, output)
        if report.failed > 0:
            sys.exit(1)
    else:
        click.echo(f"运行所有适配器测试（{len(registry)} 个适配器）\n", err=True)
        reports = suite.run_all(registry, categories=categories)
        total_failed = 0
        for adapter_id, report in reports.items():
            _output_report(report, fmt, output, is_multiple=True)
            total_failed += report.failed
        if total_failed > 0:
            sys.exit(1)


def _output_report(report, fmt: str, output: str | None, is_multiple: bool = False):
    """输出测试报告"""
    from pathlib import Path as P

    if fmt == "json":
        import json

        content = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        if output:
            P(output).write_text(content, encoding="utf-8")
            click.echo(f"报告已保存: {output}")
        else:
            click.echo(content)
    elif fmt == "html":
        content = report.to_html()
        if output:
            P(output).write_text(content, encoding="utf-8")
            click.echo(f"HTML 报告已保存: {output}")
        else:
            click.echo(content)
    else:
        click.echo(report.to_table())
        if is_multiple:
            click.echo()


@adapter.command("validate")
@click.argument("lang_id", required=False)
def adapter_validate(lang_id: str | None):
    """验证适配器兼容性"""
    from yanpub.core.adapter_test import AdapterCompatibilityValidator

    registry = get_registry()
    validator = AdapterCompatibilityValidator(registry)

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知适配器: {lang_id}", err=True)
            sys.exit(1)
        result = validator.validate_adapter(adapter)
        _print_validation(adapter.name, adapter.id, result)
        if not result["valid"]:
            sys.exit(1)
    else:
        results = validator.validate_all()
        any_invalid = False
        for aid, result in results.items():
            adapter = registry.get(aid)
            name = adapter.name if adapter else aid
            _print_validation(name, aid, result)
            click.echo()
            if not result["valid"]:
                any_invalid = True
        if any_invalid:
            sys.exit(1)


def _print_validation(name: str, adapter_id: str, result: dict):
    """打印验证结果"""
    icon = "✅" if result["valid"] else "❌"
    click.echo(f"{icon} {name} ({adapter_id})")

    for err in result["errors"]:
        click.echo(f"  ✗ {err}")
    for warn in result["warnings"]:
        click.echo(f"  ⚠ {warn}")

    if not result["errors"] and not result["warnings"]:
        click.echo("  所有检查通过")


@adapter.command("create")
@click.option("--lang-id", prompt=True, help="语言英文ID（小写字母数字下划线）")
@click.option("--name", prompt=True, help="语言中文名")
@click.option("--version", default="0.1.0", help="语言版本号")
@click.option("--extensions", default=None, help="文件扩展名（逗号分隔，如 .my,.mylang）")
@click.option("--comment", default="#", help="注释语法")
@click.option("--run", prompt=True, help="运行命令（用 {file} 表示文件路径）")
@click.option("--eval", "eval_cmd", default=None, help="eval 命令（用 {code} 表示代码）")
@click.option(
    "--eval-mode", type=click.Choice(["stdin", "arg"]), default="stdin", help="eval 代码传递方式"
)
@click.option("--repl", default=None, help="REPL 命令")
@click.option("--color", default="#2C3E50", help="品牌主色（十六进制）")
@click.option("--keywords", default=None, help="关键字（逗号分隔）")
@click.option("--description", default="", help="语言简介")
@click.option("--author", default="", help="适配器维护者")
@click.option("--dry-run", is_flag=True, help="只显示将生成的文件，不实际创建")
def adapter_create(
    lang_id: str,
    name: str,
    version: str,
    extensions: str | None,
    comment: str,
    run: str,
    eval_cmd: str | None,
    eval_mode: str,
    repl: str | None,
    color: str,
    keywords: str | None,
    description: str,
    author: str,
    dry_run: bool,
):
    """创建新语言适配器 — 交互式生成完整的适配器目录

    \b
    yanpub adapter create                        # 交互式向导
    yanpub adapter create --lang-id mylang --name 我语 --run "python mylang.py {file}"
    yanpub adapter create --dry-run ...          # 只预览不创建
    """
    from yanpub.core.adapter_template import AdapterSpec, AdapterTemplateEngine

    # 解析扩展名
    ext_list = []
    if extensions:
        ext_list = [e.strip() for e in extensions.split(",") if e.strip()]

    # 解析关键字
    kw_list = []
    if keywords:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

    spec = AdapterSpec(
        lang_id=lang_id,
        name=name,
        version=version,
        extensions=ext_list,
        comment_syntax=comment,
        primary_color=color,
        run_command=run,
        eval_command=eval_cmd or "",
        eval_mode=eval_mode,
        repl_command=repl or "",
        keywords=kw_list,
        description=description,
        author=author,
    )

    engine = AdapterTemplateEngine()

    # 验证
    errors = engine.validate_spec(spec)
    if errors:
        click.echo("适配器规格验证失败：", err=True)
        for err in errors:
            click.echo(f"  ✗ {err}", err=True)
        sys.exit(1)

    if dry_run:
        click.echo(f"\n将创建适配器: {name} ({lang_id}) v{version}")
        click.echo(f"  目录: {engine.adapters_dir / lang_id}")
        click.echo("  文件: adapter.py, adapter.yaml, CONTRIBUTING.md")
        click.echo(
            f"  示例: examples/hello{spec.extensions[0]}, examples/function{spec.extensions[0]}"
        )
        click.echo("\n规格摘要：")
        click.echo(f"  ID:       {lang_id}")
        click.echo(f"  名称:     {name}")
        click.echo(f"  版本:     {version}")
        click.echo(f"  扩展名:   {', '.join(spec.extensions)}")
        click.echo(f"  注释:     {comment}")
        click.echo(f"  运行:     {run}")
        click.echo(f"  eval:     {eval_cmd or '(临时文件fallback)'}")
        click.echo(f"  eval模式: {eval_mode}")
        click.echo(f"  REPL:     {repl or '(无)'}")
        click.echo(f"  主色:     {color}")
        if kw_list:
            click.echo(f"  关键字:   {', '.join(kw_list)}")
        return

    # 确认
    click.echo(f"\n即将创建适配器: {name} ({lang_id})")
    click.echo(f"  目标目录: {engine.adapters_dir / lang_id}")
    if not click.confirm("确认创建？"):
        click.echo("已取消。")
        return

    # 生成
    output = engine.generate(spec)
    click.echo(f"\n✅ 适配器已创建: {output}")
    click.echo("\n生成的文件：")
    for f in sorted(output.iterdir()):
        if f.is_file():
            click.echo(f"  {f.name}")
    examples_dir = output / "examples"
    if examples_dir.exists():
        for f in sorted(examples_dir.iterdir()):
            if f.is_file():
                click.echo(f"  examples/{f.name}")

    # 自动验证
    click.echo("\n自动验证中...")
    check_result = engine.check_adapter(lang_id)
    if check_result["valid"]:
        click.echo("✅ 适配器验证通过！")
    else:
        click.echo("⚠ 适配器已创建，但存在以下问题：")
        for err in check_result["errors"]:
            click.echo(f"  ✗ {err}")
    for warn in check_result["warnings"]:
        click.echo(f"  ⚠ {warn}")

    click.echo("\n下一步：")
    click.echo(f"  1. 编辑 {output / 'adapter.py'} 填入实际的语言后端路径")
    click.echo("  2. 在 examples/ 目录添加更多示例")
    click.echo(f"  3. 运行 yanpub adapter validate {lang_id} 验证兼容性")
    click.echo(f"  4. 运行 yanpub examples {lang_id} 查看示例列表")


@adapter.command("check")
@click.argument("lang_id")
def adapter_check(lang_id: str):
    """检查适配器是否可被正确发现和注册

    验证目录结构、文件格式、类定义、实例化等。
    """
    from yanpub.core.adapter_template import AdapterTemplateEngine

    engine = AdapterTemplateEngine()

    click.echo(f"检查适配器: {lang_id}\n")
    click.echo(f"  目录: {engine.adapters_dir / lang_id}")

    result = engine.check_adapter(lang_id)

    # 文件列表
    if result["files"]:
        click.echo("\n  已发现文件：")
        for f in result["files"]:
            click.echo(f"    ✓ {f}")

    # 错误
    if result["errors"]:
        click.echo("\n  ❌ 错误：")
        for err in result["errors"]:
            click.echo(f"    ✗ {err}")

    # 警告
    if result["warnings"]:
        click.echo("\n  ⚠ 警告：")
        for warn in result["warnings"]:
            click.echo(f"    ⚠ {warn}")

    # 结论
    if result["valid"]:
        click.echo(f"\n  ✅ 适配器 {lang_id} 检查通过，可被正常发现和注册。")
    else:
        click.echo(f"\n  ❌ 适配器 {lang_id} 检查未通过，请修复上述错误。")
        sys.exit(1)


@main.group()
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


@main.group()
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
    from yanpub.core.sandbox import SandboxManager, SandboxConfig

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
    from yanpub.core.sandbox import SandboxManager

    status = SandboxManager.get_backend_status()

    click.echo("沙箱后端检测：\n")
    for name, info in status.items():
        available = "✅" if info["available"] else "❌"
        desc = info.get("description", "")
        click.echo(f"  {available} {name:14s} {desc}")

    available_backends = [n for n, i in status.items() if i["available"]]
    click.echo(f"\n推荐后端: {available_backends[0] if available_backends else 'process'}")


@main.group()
def wasm():
    """WASM 执行 — 构建/运行 WebAssembly 执行环境"""
    pass


@wasm.command("check")
def wasm_check():
    """检查 WASM 运行时可用性"""
    from yanpub.core.wasm import detect_wasm_runtime

    runtime = detect_wasm_runtime()
    if runtime.available:
        click.echo(f"WASM 运行时: {runtime.name} v{runtime.version}")
        click.echo(f"路径: {runtime.path}")
    else:
        click.echo("无可用的 WASM 运行时")
        click.echo("可选方案:")
        click.echo("  pip install wasmtime    # wasmtime 运行时")
        click.echo("  pip install wasmer      # wasmer 运行时")
        click.echo("  安装 Node.js            # 通过 Node.js 执行 WASM")


@wasm.command("build")
@click.argument("lang_id")
@click.option("--output", "-o", default=None, help="输出目录")
def wasm_build(lang_id: str, output: str | None):
    """构建语言的 WASM 执行环境"""
    from yanpub.core.wasm import WasmBuilder
    from pathlib import Path as P

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    output_dir = P(output) if output else None
    builder = WasmBuilder(output_dir)
    result = builder.build(adapter)

    if result.success:
        click.echo(f"[OK] {adapter.name} WASM 环境构建成功")
        click.echo(f"  输出目录: {result.output_path}")
        click.echo(f"  大小: {result.size_bytes} bytes")
        click.echo(f"  耗时: {result.build_time_ms:.0f}ms")
    else:
        click.echo(f"[FAIL] 构建失败: {result.error}", err=True)
        sys.exit(1)


@wasm.command("run")
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
def wasm_run(lang_id: str, file: str):
    """使用 WASM 运行代码文件"""
    from yanpub.core.wasm import WasmExecutor
    from pathlib import Path as P

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    executor = WasmExecutor()
    if not executor.is_available:
        click.echo("无可用的 WASM 运行时，请运行 yanpub wasm check", err=True)
        sys.exit(1)

    code = P(file).read_text(encoding="utf-8")
    result = executor.execute_with_adapter(adapter, code)

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)
    sys.exit(result.exit_code)


@main.command("bench-visualize")
@click.argument("lang_id", required=False)
@click.option("--iterations", "-n", default=5, type=int, help="每项测试迭代次数")
@click.option("--output", "-o", default="bench_report.html", help="输出 HTML 文件路径")
def bench_visualize(lang_id: str | None, iterations: int, output: str):
    """生成性能基准测试可视化报告"""
    from yanpub.core.bench_viz import BenchVisualizer, run_bench_with_regression

    registry = get_registry()

    click.echo("正在运行基准测试...", err=True)
    results, regressions = run_bench_with_regression(
        registry,
        lang_id=lang_id,
        iterations=iterations,
    )

    if not results:
        click.echo("没有可用的适配器", err=True)
        sys.exit(1)

    path = BenchVisualizer.save_html(results, output, regressions)
    click.echo(f"[OK] 可视化报告已生成: {path}")

    if regressions:
        actual = [r for r in regressions if r.is_regression]
        if actual:
            click.echo(f"\n⚠ 检测到 {len(actual)} 个性能回归:")
            for r in actual:
                click.echo(f"  {r.adapter_name} — {r.bench_name}: +{r.change_pct:.0%}")


@main.command("bench-regress")
@click.argument("lang_id", required=False)
@click.option("--threshold", "-t", default=0.20, type=float, help="回归阈值（默认 20%%）")
def bench_regress(lang_id: str | None, threshold: float):
    """检测性能回归"""
    from yanpub.core.bench_viz import run_bench_with_regression

    registry = get_registry()

    click.echo("正在运行基准测试并对比历史数据...", err=True)
    results, regressions = run_bench_with_regression(
        registry,
        lang_id=lang_id,
    )

    if not regressions:
        click.echo("没有历史数据可供对比")
        return

    click.echo(f"对比结果（阈值: {threshold:.0%}）:\n")
    for r in regressions:
        status = "💥 回归" if r.is_regression else "✅ 正常"
        change = f"+{r.change_pct:.0%}" if r.change_pct > 0 else f"{r.change_pct:.0%}"
        click.echo(
            f"  {status} {r.adapter_name} — {r.bench_name}: {r.previous_ms:.1f}ms → {r.current_ms:.1f}ms ({change})"
        )

    actual = [r for r in regressions if r.is_regression]
    if actual:
        sys.exit(1)


@main.command("bench-history")
@click.option("--limit", "-n", default=5, type=int, help="显示最近 N 条")
def bench_history(limit: int):
    """查看历史基准数据"""
    from yanpub.core.bench_viz import BenchHistory
    import json

    history = BenchHistory()
    snapshots = history.list_snapshots()

    if not snapshots:
        click.echo("没有历史基准数据")
        return

    click.echo(f"历史快照（最近 {min(limit, len(snapshots))} 条）:\n")
    for snap_path in snapshots[-limit:]:
        try:
            data = json.loads(snap_path.read_text(encoding="utf-8"))
            ts = data.get("timestamp", "unknown")
            count = len(data.get("results", {}))
            click.echo(f"  {snap_path.name}  时间: {ts}  适配器: {count}")
        except Exception:
            click.echo(f"  {snap_path.name}  (解析失败)")


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


# ============================================================
# 代码签名 CLI 命令
# ============================================================


@main.command("sign")
@click.argument("file", type=click.Path(exists=True))
@click.option("--key", "-k", required=True, help="私钥文件路径")
@click.option("--signer", "-s", required=True, help="签名者标识")
@click.option(
    "--algorithm", "-a", type=click.Choice(["ed25519", "hmac-sha256"]), default="hmac-sha256"
)
def sign_file(file: str, key: str, signer: str, algorithm: str):
    """对源代码文件进行签名"""
    from pathlib import Path as P
    from yanpub.core.signing import CodeSigner

    # 读取私钥
    key_path = P(key)
    if not key_path.exists():
        click.echo(f"私钥文件不存在: {key}", err=True)
        sys.exit(1)
    private_key = key_path.read_text(encoding="utf-8").strip()

    # 签名
    code_signer = CodeSigner()
    try:
        signature = code_signer.sign_file(file, private_key, signer, algorithm=algorithm)
    except Exception as e:
        click.echo(f"签名失败: {e}", err=True)
        sys.exit(1)

    sig_path = P(file).with_suffix(P(file).suffix + ".yanpub-sig")
    click.echo("[OK] 签名成功")
    click.echo(f"  签名者: {signature.signer}")
    click.echo(f"  密钥ID: {signature.key_id}")
    click.echo(f"  算法:   {signature.algorithm}")
    click.echo(f"  哈希:   {signature.content_hash[:16]}...")
    click.echo(f"  签名文件: {sig_path}")


@main.command("verify")
@click.argument("file", type=click.Path(exists=True))
def verify_file(file: str):
    """验证源代码文件签名"""
    from yanpub.core.signing import CodeSigner

    code_signer = CodeSigner()
    valid, message = code_signer.verify_file(file)

    if valid:
        click.echo(f"[OK] {message}")
    else:
        click.echo(f"[FAIL] {message}", err=True)
        sys.exit(1)


@main.group("trust")
def trust_group():
    """信任密钥管理"""
    pass


@trust_group.command("add")
@click.argument("key_file", type=click.Path(exists=True))
@click.option("--signer", "-s", required=True)
@click.option("--level", type=click.Choice(["full", "ca", "user"]), default="user")
def trust_add(key_file: str, signer: str, level: str):
    """添加受信任的密钥"""
    import json
    from pathlib import Path as P
    from yanpub.core.signing import SigningKey, TrustStore

    # 读取密钥文件（JSON 格式）
    key_path = P(key_file)
    try:
        key_data = json.loads(key_path.read_text(encoding="utf-8"))
        key = SigningKey.from_dict(key_data)
    except Exception as e:
        click.echo(f"密钥文件格式错误: {e}", err=True)
        sys.exit(1)

    store = TrustStore()
    store.add_trusted_key(key, signer, level)
    click.echo("[OK] 已添加受信任密钥")
    click.echo(f"  密钥ID: {key.key_id}")
    click.echo(f"  算法:   {key.algorithm}")
    click.echo(f"  签名者: {signer}")
    click.echo(f"  信任级别: {level}")


@trust_group.command("list")
def trust_list():
    """列出受信任的密钥"""
    from yanpub.core.signing import TrustStore

    store = TrustStore()
    keys = store.list_keys()

    if not keys:
        click.echo("没有受信任的密钥。")
        return

    click.echo(f"受信任密钥 ({len(keys)} 个)：\n")
    for k in keys:
        click.echo(f"  {k['key_id']:10s} {k['algorithm']:14s} {k['signer']:20s} {k['trust_level']}")


@trust_group.command("remove")
@click.argument("key_id")
def trust_remove(key_id: str):
    """移除受信任的密钥"""
    from yanpub.core.signing import TrustStore

    store = TrustStore()
    trusted, level = store.is_trusted(key_id)
    if not trusted:
        click.echo(f"未找到密钥: {key_id}", err=True)
        sys.exit(1)

    store.remove_key(key_id)
    click.echo(f"[OK] 已移除密钥: {key_id}")


@main.command("keygen")
@click.option(
    "--algorithm", "-a", type=click.Choice(["ed25519", "hmac-sha256"]), default="hmac-sha256"
)
@click.option("--output", "-o", default=None, help="输出目录")
def generate_key(algorithm: str, output: str):
    """生成签名密钥对"""
    import json
    from pathlib import Path as P
    from yanpub.core.signing import SigningKey

    key, private_key = SigningKey.generate(algorithm)

    # 确定输出目录
    out_dir = P(output) if output else P.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写入公钥文件
    pub_path = out_dir / f"yanpub_{key.key_id}.pub"
    pub_path.write_text(
        json.dumps(key.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 写入私钥文件
    priv_path = out_dir / f"yanpub_{key.key_id}.key"
    priv_path.write_text(private_key, encoding="utf-8")

    actual_algo = key.algorithm
    click.echo("[OK] 密钥对已生成")
    click.echo(f"  密钥ID: {key.key_id}")
    click.echo(f"  算法:   {actual_algo}")
    if actual_algo != algorithm:
        click.echo(f"  注意: Ed25519 不可用，已降级到 {actual_algo}")
    click.echo(f"  公钥:   {pub_path}")
    click.echo(f"  私钥:   {priv_path}")
    click.echo()
    click.echo("  请妥善保管私钥文件，不要提交到版本控制！")


@main.command("audit")
@click.option("--action", type=click.Choice(["list", "stats", "export"]), default="list")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
def audit_log(action: str, fmt: str):
    """查看安全审计日志"""
    from yanpub.core.audit import AuditLog

    log = AuditLog()

    if action == "list":
        entries = log.query()
        if not entries:
            click.echo("没有审计记录。")
            return

        click.echo(f"审计记录 ({len(entries)} 条)：\n")
        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            click.echo(f"  [{ts}] {entry.action:14s} signer={entry.signer} key={entry.key_id}")
            if entry.details:
                for k, v in entry.details.items():
                    click.echo(f"    {k}: {v}")

    elif action == "stats":
        stats = log.get_stats()
        click.echo("审计统计：")
        click.echo(f"  总记录数: {stats['total']}")
        if stats["by_action"]:
            click.echo("  按操作类型:")
            for act, count in stats["by_action"].items():
                click.echo(f"    {act}: {count}")
        if stats["by_signer"]:
            click.echo("  按签名者:")
            for signer, count in stats["by_signer"].items():
                click.echo(f"    {signer}: {count}")

    elif action == "export":
        content = log.export(format=fmt)
        click.echo(content)


@main.command("project")
@click.argument("action", type=click.Choice(["create", "list", "run", "delete"]))
@click.option("--name", "-n", help="项目名称")
@click.option("--language", "-L", "lang_id", help="主语言")
@click.option("--project-id", "-p", help="项目 ID")
@click.option("--template", "-t", default="default", help="项目模板")
def project_command(
    action: str, name: str | None, lang_id: str | None, project_id: str | None, template: str
):
    """项目管理 — 创建/列出/运行/删除"""
    from yanpub.playground.project import get_project_manager

    pm = get_project_manager()

    if action == "create":
        project_name = name or "未命名项目"
        project_lang = lang_id or "duan"
        project = pm.create_project(project_name, project_lang, template=template)
        click.echo("[OK] 项目已创建")
        click.echo(f"  ID:   {project.id}")
        click.echo(f"  名称: {project.name}")
        click.echo(f"  语言: {project.language}")
        click.echo(f"  文件: {len(project.files)} 个")
        click.echo(f"  入口: {project.main_file}")
        for pf in project.list_files():
            click.echo(f"    {pf.path} ({len(pf.content)} 字符)")

    elif action == "list":
        projects = pm.list_projects()
        if not projects:
            click.echo("没有项目。")
            return
        click.echo(f"项目列表 ({len(projects)} 个)：\n")
        for p in projects:
            click.echo(
                f"  {p['id']:12s} {p['name']:20s} {p['language']:8s} "
                f"文件:{p['fileCount']} 入口:{p['mainFile']}"
            )

    elif action == "run":
        pid = project_id
        if not pid:
            # 尝试找第一个项目
            projects = pm.list_projects()
            if not projects:
                click.echo("没有项目可运行。请先用 create 创建。", err=True)
                sys.exit(1)
            pid = projects[0]["id"]
            click.echo(f"未指定项目ID，使用: {pid}")

        project = pm.get_project(pid)
        if project is None:
            click.echo(f"项目不存在: {pid}", err=True)
            sys.exit(1)

        registry = get_registry()
        adapter = registry.get(project.language)
        if adapter is None:
            click.echo(f"未知语言: {project.language}", err=True)
            sys.exit(1)

        click.echo(f"运行项目: {project.name} ({project.id})")
        click.echo(f"  语言: {adapter.name} v{adapter.version}")
        click.echo(f"  入口: {project.main_file}")
        click.echo()

        result = pm.execute_project(pid, adapter)

        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            click.echo(result.stderr, nl=False, err=True)
        click.echo(f"\n耗时: {result.duration_ms:.0f}ms, 退出码: {result.exit_code}")
        sys.exit(result.exit_code)

    elif action == "delete":
        pid = project_id
        if not pid:
            click.echo("请指定项目ID: --project-id", err=True)
            sys.exit(1)
        if pm.delete_project(pid):
            click.echo(f"[OK] 项目已删除: {pid}")
        else:
            click.echo(f"项目不存在: {pid}", err=True)
            sys.exit(1)


@main.command("baseline")
@click.argument("action", type=click.Choice(["capture", "list", "compare", "delete"]))
@click.option("--lang", "-L", "lang_id", help="适配器 ID")
@click.option("--label", "-l", default="", help="快照标签")
@click.option("--threshold", "-t", default=20.0, type=float, help="回归阈值（百分比）")
@click.option("--snapshot-id", "-s", help="快照 ID")
def baseline_command(
    action: str, lang_id: str | None, label: str, threshold: float, snapshot_id: str | None
):
    """性能基线管理 — 捕获/列出/对比/删除"""
    from yanpub.core.baseline import BaselineManager

    mgr = BaselineManager()

    if action == "capture":
        if not lang_id:
            click.echo("请指定适配器: --lang <id>", err=True)
            sys.exit(1)
        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            click.echo(f"未知适配器: {lang_id}", err=True)
            sys.exit(1)

        click.echo(f"捕获 {adapter.name} 性能快照...", err=True)
        snapshot = mgr.capture_snapshot(adapter, label=label)
        mgr.save_snapshot(snapshot)
        click.echo(f"[OK] 快照已保存: {snapshot.id}")
        click.echo(f"  适配器: {adapter.name} v{adapter.version}")
        click.echo(f"  标签:   {label or '(无)'}")
        click.echo(f"  指标数: {len(snapshot.metrics)}")
        for name, value in sorted(snapshot.metrics.items()):
            click.echo(f"    {name}: {value}")

    elif action == "list":
        snapshots = mgr.list_snapshots(adapter_id=lang_id)
        if not snapshots:
            click.echo("没有快照记录。")
            return

        click.echo(f"快照列表 ({len(snapshots)} 个):\n")
        for s in snapshots:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s.timestamp))
            label_str = f" [{s.label}]" if s.label else ""
            click.echo(f"  {s.id}  {ts}  {s.adapter_id} v{s.adapter_version}{label_str}")
            # 显示关键指标
            for name in ["eval_mean_ms", "eval_median_ms", "startup_mean_ms"]:
                if name in s.metrics:
                    click.echo(f"    {name}: {s.metrics[name]}")

    elif action == "compare":
        if not lang_id:
            click.echo("请指定适配器: --lang <id>", err=True)
            sys.exit(1)

        # 获取快照
        snapshots = mgr.list_snapshots(adapter_id=lang_id)
        if not snapshots:
            click.echo(f"没有 {lang_id} 的快照记录。", err=True)
            sys.exit(1)

        if snapshot_id:
            # 与指定快照对比
            target = mgr.load_snapshot(snapshot_id)
            if target is None:
                click.echo(f"未找到快照: {snapshot_id}", err=True)
                sys.exit(1)
            # 找到最新基线（排除目标自身）
            baseline_candidates = [s for s in snapshots if s.id != target.id]
            if not baseline_candidates:
                click.echo("没有可对比的基线快照。", err=True)
                sys.exit(1)
            baseline = baseline_candidates[0]
            comparison = mgr.compare(baseline, target)
        else:
            # 使用最新两个快照对比
            if len(snapshots) < 2:
                click.echo("快照不足，需要至少2个才能对比。", err=True)
                sys.exit(1)
            latest = snapshots[0]
            baseline = snapshots[1]
            comparison = mgr.compare(baseline, latest)
            target = latest

        click.echo(f"对比结果: {baseline.id} → {target.id}\n")
        click.echo("  指标       基线      当前     变化    状态")
        click.echo(f"  {'─' * 55}")

        for m in comparison["metrics"]:
            status = (
                "💥 回归" if m["regression"] else ("✅ 改善" if m["improvement"] else "➖ 持平")
            )
            diff_str = f"+{m['diff_pct']:.1f}%" if m["diff_pct"] > 0 else f"{m['diff_pct']:.1f}%"
            click.echo(
                f"  {m['name']:20s} {m['a']:>8.2f}  {m['b']:>8.2f}  {diff_str:>7s}  {status}"
            )

        click.echo(
            f"\n  回归: {comparison['regressions']}  改善: {comparison['improvements']}  持平: {comparison['neutral']}"
        )

        # 回归检测
        if comparison["regressions"] > 0:
            regressions_above_threshold = [
                m for m in comparison["metrics"] if m["regression"] and m["diff_pct"] > threshold
            ]
            if regressions_above_threshold:
                click.echo(f"\n⚠ 回归超过阈值（{threshold}%）:")
                for m in regressions_above_threshold:
                    click.echo(f"    {m['name']}: +{m['diff_pct']:.1f}%")
                sys.exit(1)

    elif action == "delete":
        if not snapshot_id:
            click.echo("请指定快照 ID: --snapshot-id <id>", err=True)
            sys.exit(1)
        if mgr.delete_snapshot(snapshot_id):
            click.echo(f"[OK] 快照 {snapshot_id} 已删除")
        else:
            click.echo(f"未找到快照: {snapshot_id}", err=True)
            sys.exit(1)


@main.command("budget")
@click.argument("action", type=click.Choice(["set", "check", "list"]))
@click.option("--lang", "-L", "lang_id", help="适配器 ID")
@click.option("--metric", "-m", multiple=True, help="指标名=预算值（如 eval_mean_ms=100）")
def budget_command(action: str, lang_id: str | None, metric: tuple[str, ...]):
    """性能预算管理 — 设置/检查/列出"""
    from yanpub.core.baseline import BaselineManager, PerformanceBudget

    mgr = BaselineManager()

    if action == "set":
        if not lang_id:
            click.echo("请指定适配器: --lang <id>", err=True)
            sys.exit(1)
        if not metric:
            click.echo("请指定预算: --metric name=value", err=True)
            sys.exit(1)

        # 解析 metric=values
        budgets: dict[str, float] = {}
        for m in metric:
            if "=" not in m:
                click.echo(f"格式错误: {m}（应为 name=value）", err=True)
                sys.exit(1)
            name, value_str = m.split("=", 1)
            try:
                budgets[name] = float(value_str)
            except ValueError:
                click.echo(f"数值错误: {value_str}", err=True)
                sys.exit(1)

        budget = PerformanceBudget(adapter_id=lang_id, budgets=budgets)
        mgr.set_budget(budget)

        click.echo(f"[OK] {lang_id} 性能预算已设置:")
        for name, value in budgets.items():
            click.echo(f"  {name}: {value}ms")

    elif action == "check":
        if not lang_id:
            click.echo("请指定适配器: --lang <id>", err=True)
            sys.exit(1)

        result = mgr.check_budget(lang_id)

        if not result["has_budget"]:
            click.echo(f"{lang_id} 未设置性能预算。")
            click.echo("使用 yanpub budget set --lang <id> --metric name=value 设置")
            return

        if not result["snapshot"]:
            click.echo("没有快照可供检查。")
            return

        click.echo(f"{lang_id} 性能预算检查:\n")
        click.echo(f"  {'指标':20s} {'预算(ms)':>10s} {'实际(ms)':>10s} {'状态':>8s}")
        click.echo(f"  {'─' * 55}")

        for r in result["results"]:
            status = "❌ 超出" if r["over_budget"] else "✅ 通过"
            click.echo(
                f"  {r['metric']:20s} {r['budget']:>10.2f} {r['actual']:>10.2f} {status:>8s}"
            )
            if r["over_budget"]:
                click.echo(f"    超出 {r['pct_over']:.1f}%")

        if result["all_within_budget"]:
            click.echo("\n✅ 所有指标在预算内")
        else:
            click.echo("\n❌ 有指标超出预算")
            sys.exit(1)

    elif action == "list":
        # 列出所有有预算的适配器
        if not mgr.storage_dir.exists():
            click.echo("没有设置任何性能预算。")
            return

        found = False
        for adapter_dir in sorted(mgr.storage_dir.iterdir()):
            if not adapter_dir.is_dir():
                continue
            budget = mgr.get_budget(adapter_dir.name)
            if budget is not None:
                found = True
                click.echo(f"{budget.adapter_id}:")
                for name, value in budget.budgets.items():
                    click.echo(f"  {name}: {value}ms")
                click.echo()

        if not found:
            click.echo("没有设置任何性能预算。")


@main.command("refactor")
@click.argument("action", type=click.Choice(["extract", "inline", "rename"]))
@click.argument("lang_id")
@click.argument("file", type=click.Path(exists=True))
@click.option("--start-line", type=int, help="起始行（extract，1-based）")
@click.option("--end-line", type=int, help="结束行（extract，1-based）")
@click.option("--new-name", "-n", help="新名称")
@click.option("--line", type=int, help="光标行（inline/rename，1-based）")
@click.option("--column", type=int, help="光标列（inline/rename，1-based）")
def refactor_command(
    action: str,
    lang_id: str,
    file: str,
    start_line: int | None,
    end_line: int | None,
    new_name: str | None,
    line: int | None,
    column: int | None,
):
    """代码重构 — 提取函数/内联变量/安全重命名"""
    from pathlib import Path as P
    from yanpub.core.refactor import RefactoringEngine

    registry = get_registry()
    adapter = registry.get(lang_id)
    if adapter is None:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    code = P(file).read_text(encoding="utf-8")
    engine = RefactoringEngine(adapter)

    if action == "extract":
        if not start_line or not end_line:
            click.echo("extract 需要 --start-line 和 --end-line 参数", err=True)
            sys.exit(1)
        func_name = new_name or "提取的函数"
        result = engine.extract_function(code, start_line, end_line, func_name)

        click.echo(f"提取函数: {func_name}")
        click.echo(f"替换范围: 第 {start_line} 行 ~ 第 {end_line} 行")
        click.echo()
        click.echo("新函数代码：")
        click.echo(result["new_function"])
        click.echo()
        click.echo("替换代码：")
        click.echo(result["replacement"])

    elif action == "inline":
        if not line or not column:
            click.echo("inline 需要 --line 和 --column 参数", err=True)
            sys.exit(1)
        result = engine.inline_variable(code, line, column)

        if not result["value"]:
            click.echo("光标位置不是有效的变量声明")
            sys.exit(1)

        decl = result["declaration_range"]
        click.echo("内联变量重构：")
        click.echo(f"  变量值: {result['value']}")
        click.echo(f"  声明范围: 第 {decl['start']['line'] + 1} 行")
        click.echo(f"  使用位置: {len(result['usage_ranges'])} 处")
        if result["usage_ranges"]:
            for u in result["usage_ranges"]:
                click.echo(f"    第 {u['start']['line'] + 1} 行, 列 {u['start']['character'] + 1}")

    elif action == "rename":
        if not line or not column:
            click.echo("rename 需要 --line 和 --column 参数", err=True)
            sys.exit(1)
        if not new_name:
            click.echo("rename 需要 --new-name 参数", err=True)
            sys.exit(1)
        result = engine.safe_rename(code, line, column, new_name)

        if result["safe"]:
            click.echo(f"安全重命名: 可以安全地将标识符重命名为 '{new_name}'")
        else:
            click.echo(f"重命名检查: 发现 {len(result['conflicts'])} 个冲突")
            for c in result["conflicts"]:
                click.echo(f"  ⚠ {c}")

        click.echo(f"需要修改的位置: {len(result['changes'])} 处")
        if result["changes"]:
            for ch in result["changes"]:
                r = ch["range"]
                uri_info = f" ({ch['uri']})" if ch["uri"] else ""
                click.echo(
                    f"  第 {r['start']['line'] + 1} 行, 列 {r['start']['character'] + 1}{uri_info}"
                )


@main.command("i18n")
@click.option(
    "--action", type=click.Choice(["export", "import", "check", "translate"]), required=True
)
@click.option("--lang", "-L", "target_lang", default="en", help="目标语言")
@click.option("--output", "-o", default=None, help="输出文件路径")
def i18n_command(action: str, target_lang: str, output: str | None):
    """国际化管理 — 导出/导入/检查/翻译"""
    from pathlib import Path as P
    from yanpub.i18n import I18nManager

    mgr = I18nManager()

    if action == "export":
        # 导出指定语言的翻译为 YAML
        out_path = P(output) if output else P(f"{target_lang}.yaml")
        mgr.export_translations(target_lang, out_path)
        click.echo(f"[OK] {target_lang} 翻译已导出: {out_path}")

    elif action == "import":
        # 从目录加载自定义翻译
        if output is None:
            click.echo("请指定翻译目录: --output <dir>", err=True)
            sys.exit(1)
        lang_dir = P(output)
        mgr.load_translations(lang_dir)
        click.echo(f"[OK] 已从 {lang_dir} 加载翻译")

    elif action == "check":
        # 检查缺失的翻译键
        missing = mgr.get_missing_keys("zh", target_lang)
        if not missing:
            click.echo(f"{target_lang} 翻译完整，无缺失键。")
        else:
            click.echo(f"{target_lang} 缺失 {len(missing)} 个翻译键：\n")
            for key in missing:
                click.echo(f"  {key}")

    elif action == "translate":
        # 自动翻译缺失键
        suggestions = mgr.auto_translate("zh", target_lang)
        if not suggestions:
            click.echo(f"{target_lang} 无需翻译（已完整或无源文本）。")
        else:
            click.echo(f"自动翻译建议（{len(suggestions)} 个）：\n")
            for key, suggestion in suggestions.items():
                click.echo(f"  {key}:")
                click.echo(f"    → {suggestion}")


@main.command("docs-i18n")
@click.argument("lang_id")
@click.option("--lang", "-L", "target_lang", default="en", help="目标语言")
@click.option("--output", "-o", default=None, help="输出目录")
def docs_i18n(lang_id: str, target_lang: str, output: str | None):
    """生成多语言适配器文档"""
    from pathlib import Path as P
    from yanpub.docs.i18n_docs import I18nDocsGenerator
    import json

    registry = get_registry()
    generator = I18nDocsGenerator(registry)

    if output:
        out_dir = P(output)
    else:
        out_dir = P("yandocs_i18n") / target_lang

    # 生成 API 参考
    api_ref = generator.generate_api_reference(lang_id, target_lang)
    if not api_ref:
        click.echo(f"未知语言: {lang_id}", err=True)
        sys.exit(1)

    # 生成语言概览
    overview = generator.generate_language_overview(lang_id, target_lang)

    # 写入文件
    out_dir.mkdir(parents=True, exist_ok=True)

    api_file = out_dir / f"{lang_id}_api.json"
    api_file.write_text(
        json.dumps(api_ref, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overview_file = out_dir / f"{lang_id}_overview.json"
    overview_file.write_text(
        json.dumps(overview, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    click.echo(f"[OK] {lang_id} 的 {target_lang} 文档已生成: {out_dir}")
    click.echo(f"  API 参考: {api_file}")
    click.echo(f"  语言概览: {overview_file}")


# ---- v1.2.0: Lint 代码风格检查 ----


@main.command("lint")
@click.argument("path", type=click.Path(exists=True))
@click.option("--lang", "-L", "lang_id", default=None, help="语言 ID")
@click.option("--fix", is_flag=True, help="自动修复可修复的问题")
@click.option("--rule", "-r", multiple=True, help="仅运行指定规则 (可多次使用)")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
def lint_command(path, lang_id, fix, rule, as_json):
    """代码风格检查 — Lint 规则引擎"""
    import json as json_mod
    from pathlib import Path as PathLib

    from yanpub.core.linter import LintRuleEngine

    file_path = PathLib(path)
    if not file_path.is_file():
        click.echo(f"错误: {path} 不是文件", err=True)
        sys.exit(1)

    code = file_path.read_text(encoding="utf-8")

    # 推断语言
    if not lang_id:
        registry = get_registry()
        ext = file_path.suffix.lower()
        for adapter in registry:
            if ext in adapter.file_extensions:
                lang_id = adapter.id
                break
    if not lang_id:
        lang_id = "unknown"

    engine = LintRuleEngine()

    if fix:
        fixed_code, fixed_results = engine.fix(code, lang_id)
        if fixed_results:
            file_path.write_text(fixed_code, encoding="utf-8")
            click.echo(f"已修复 {len(fixed_results)} 个问题")
        else:
            click.echo("无需修复")

    if rule:
        results = engine.lint_with_rule(code, lang_id, list(rule))
    else:
        results = engine.lint(code, lang_id)

    if as_json:
        summary = engine.summary(results)
        click.echo(
            json_mod.dumps(
                {
                    "file": str(file_path),
                    "lang_id": lang_id,
                    "results": [r.to_dict() for r in results],
                    "summary": summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not results:
            click.echo(f"[OK] {file_path.name}: 无风格问题")
        else:
            for r in results:
                icon = {"error": "✗", "warning": "⚠", "info": "ℹ", "hint": "💡"}.get(
                    r.severity.value, "?"
                )
                click.echo(
                    f"  {icon} {file_path.name}:{r.line}:{r.column} [{r.rule_id}] {r.message}"
                )
            click.echo(f"\n共 {len(results)} 个问题")
            summary = engine.summary(results)
            for sev, count in summary["by_severity"].items():
                click.echo(f"  {sev}: {count}")


# ---- v1.2.0: 适配器热更新 ----


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


# ---- v1.2.0: 文档搜索 ----


@main.command("search")
@click.argument("query")
@click.option(
    "--category",
    "-c",
    type=click.Choice(["keyword", "doc", "example"]),
    default=None,
    help="搜索类别",
)
@click.option("--lang", "-L", "lang_id", default=None, help="限定语言")
@click.option("--suggest", is_flag=True, help="关键字联想模式")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
def search_command(query, category, lang_id, suggest, as_json):
    """文档搜索 — 全文搜索 + 关键字联想 + 代码搜索"""
    import json as json_mod

    from yanpub.docs.search import get_search_engine

    engine = get_search_engine()
    engine.build_index()

    if suggest:
        suggestions = engine.suggest(query)
        if as_json:
            click.echo(
                json_mod.dumps({"prefix": query, "suggestions": suggestions}, ensure_ascii=False)
            )
        else:
            for s in suggestions:
                click.echo(f"  {s}")
        return

    if category == "example":
        results = engine.search_examples(query, lang_id=lang_id or "")
    else:
        results = engine.search(query, category=category or "")

    if as_json:
        click.echo(json_mod.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
    else:
        if not results:
            click.echo(f"未找到与 '{query}' 相关的结果")
        else:
            click.echo(f"搜索 '{query}' — 找到 {len(results)} 个结果:")
            for r in results:
                cat_icon = {"keyword": "🔑", "doc": "📄", "example": "💻"}.get(r.category, "📝")
                click.echo(f"  {cat_icon} [{r.category}] {r.title} (score: {r.score:.2f})")
                if r.lang_name:
                    click.echo(f"    语言: {r.lang_name}")
                for hl in r.highlights[:2]:
                    click.echo(f"    {hl}")


# ---- v1.4.0: 私有注册中心 ----


@main.group("private-registry")
def private_registry():
    """私有注册中心 — Git 仓库存储 + 镜像同步 + 权限管理"""


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


# ---- v1.4.0: 代码挑战赛 ----


@main.group("challenge")
def challenge():
    """代码挑战赛 — 题目/评判/排行榜"""


@challenge.command("list")
@click.option("--difficulty", "-d", default=None, help="按难度筛选")
@click.option("--tag", "-t", default=None, help="按标签筛选")
def challenge_list(difficulty, tag):
    """列出所有挑战"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    challenges = mgr.list_challenges(difficulty=difficulty, tag=tag)
    if not challenges:
        click.echo("暂无挑战")
        return
    click.echo(f"共 {len(challenges)} 个挑战:")
    for c in challenges:
        rate = f"{c.pass_rate:.0%}" if c.pass_rate else "N/A"
        click.echo(f"  [{c.difficulty}] {c.title} ({c.id}) — {c.score}分 通过率:{rate}")


@challenge.command("show")
@click.argument("challenge_id")
def challenge_show(challenge_id):
    """查看挑战详情"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    c = mgr.get_challenge(challenge_id)
    if c is None:
        click.echo(f"挑战不存在: {challenge_id}", err=True)
        return
    click.echo(f"标题: {c.title}")
    click.echo(f"难度: {c.difficulty}  分值: {c.score}分")
    click.echo(f"标签: {', '.join(c.tags) if c.tags else '无'}")
    click.echo(f"描述: {c.description}")
    click.echo(f"时间限制: {c.time_limit_ms}ms  内存限制: {c.memory_limit_mb}MB")
    if c.supported_langs:
        click.echo(f"支持语言: {', '.join(c.supported_langs)}")
    else:
        click.echo("支持语言: 全部")
    click.echo(f"提交数: {c.submit_count}  通过数: {c.pass_count}")
    if c.public_test_cases:
        click.echo(f"公开测试用例: {len(c.public_test_cases)} 个")
        for i, tc in enumerate(c.public_test_cases, 1):
            click.echo(f"  用例{i}: 输入={tc.input!r} 期望输出={tc.expected_output!r}")


@challenge.command("submit")
@click.argument("challenge_id")
@click.argument("lang_id")
@click.option("--user", "-u", default="anonymous", help="用户名")
@click.option("--file", "-f", default=None, help="代码文件路径")
@click.option("--code", "-c", default=None, help="直接传入代码")
def challenge_submit(challenge_id, lang_id, user, file, code):
    """提交挑战解答"""
    from yanpub.playground.challenge import ChallengeManager

    if file:
        from pathlib import Path as PathLib
        code = PathLib(file).read_text(encoding="utf-8")
    elif not code:
        click.echo("请通过 --file 或 --code 提供代码", err=True)
        return

    mgr = ChallengeManager()
    try:
        submission = mgr.submit(challenge_id, user=user, lang_id=lang_id, code=code)
    except ValueError as e:
        click.echo(str(e), err=True)
        return

    status_icons = {
        "passed": "通过", "failed": "未通过", "error": "错误",
        "timeout": "超时", "pending": "等待中", "running": "运行中",
    }
    icon = status_icons.get(submission.status, submission.status)
    click.echo(f"提交结果: {icon}")
    click.echo(f"  通过用例: {submission.passed_cases}/{submission.total_cases}")
    click.echo(f"  得分: {submission.score}")
    click.echo(f"  执行时间: {submission.execution_time_ms:.1f}ms")
    if submission.error_message:
        click.echo(f"  错误: {submission.error_message}")


@challenge.command("leaderboard")
@click.argument("challenge_id", required=False)
def challenge_leaderboard(challenge_id):
    """查看排行榜"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    entries = mgr.get_leaderboard(challenge_id=challenge_id)
    if not entries:
        click.echo("暂无排行数据")
        return
    scope = f"挑战 {challenge_id}" if challenge_id else "总排行"
    click.echo(f"{'='*50}")
    click.echo(f"  {scope} 排行榜")
    click.echo(f"{'='*50}")
    click.echo(f"{'排名':>4}  {'用户':<12}  {'总分':>6}  {'通过':>4}  {'平均耗时':>10}  {'常用语言':<8}")
    click.echo(f"{'-'*50}")
    for e in entries:
        click.echo(f"{e.rank:>4}  {e.user:<12}  {e.total_score:>6}  {e.challenges_passed:>4}  {e.avg_time_ms:>8.1f}ms  {e.best_lang:<8}")


@challenge.command("create")
@click.option("--id", "challenge_id", default=None, help="挑战ID")
@click.option("--title", "-t", default=None, help="标题")
@click.option("--difficulty", "-d", type=click.Choice(["入门", "简单", "中等", "困难", "地狱"]), default="中等", help="难度")
@click.option("--description", "-D", default=None, help="描述")
@click.option("--expected-output", "-o", default=None, help="期望输出（快速创建单测试用例）")
@click.option("--score", "-s", default=100, type=int, help="满分")
@click.option("--author", "-a", default="", help="作者")
def challenge_create(challenge_id, title, difficulty, description, expected_output, score, author):
    """创建新挑战"""
    from yanpub.playground.challenge import Challenge, TestCase, ChallengeManager

    if not title:
        title = click.prompt("标题")
    if not description:
        description = click.prompt("描述")

    if not challenge_id:
        challenge_id = title.lower().replace(" ", "-").replace("，", "-")

    test_cases = []
    if expected_output:
        test_cases.append(TestCase(input="", expected_output=expected_output))
    else:
        # 交互式添加测试用例
        click.echo("添加测试用例（空行结束）:")
        idx = 1
        while True:
            inp = click.prompt(f"  用例{idx} 输入", default="", show_default=False)
            out = click.prompt(f"  用例{idx} 期望输出", default="", show_default=False)
            if not out:
                break
            hidden = click.confirm(f"  用例{idx} 是否隐藏", default=False)
            test_cases.append(TestCase(input=inp, expected_output=out, is_hidden=hidden))
            idx += 1

    c = Challenge(
        id=challenge_id,
        title=title,
        description=description,
        difficulty=difficulty,
        test_cases=test_cases,
        score=score,
        author=author,
    )

    mgr = ChallengeManager()
    mgr.create_challenge(c)
    click.echo(f"挑战已创建: {c.id} ({c.title}), {len(c.test_cases)} 个测试用例")


# ---- v1.4.0: 适配器质量评分 ----


@main.command("quality")
@click.argument("lang_id", required=False)
@click.option("--html", "html_path", default=None, help="生成 HTML 报告")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
@click.option("--ci", "ci_mode", is_flag=True, help="CI 模式：输出 GitHub Actions 兼容格式")
def quality_check(lang_id, html_path, as_json, ci_mode):
    """适配器质量评分 — 自动化检查完整度、文档、示例"""
    import json as json_mod
    from yanpub.core.quality import QualityChecker

    checker = QualityChecker()

    if lang_id:
        report = checker.check_one(lang_id)
        if report is None:
            click.echo(f"适配器不存在: {lang_id}", err=True)
            return
        reports = [report]
    else:
        reports = checker.check_all()

    if not reports:
        click.echo("未找到任何适配器", err=True)
        return

    if as_json:
        click.echo(json_mod.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2))
        return

    if ci_mode:
        _quality_ci_output(reports)
        return

    if html_path:
        from pathlib import Path as PathLib
        output = PathLib(html_path)
        checker.generate_html(reports, output)
        click.echo(f"HTML 报告已生成: {output}")
        return

    # 终端输出
    for r in reports:
        grade_color = {"S": "green", "A": "green", "B": "blue", "C": "yellow", "D": "red", "F": "red"}.get(r.grade, "white")
        click.echo(click.style(f"  {r.grade}", fg=grade_color, bold=True), nl=False)
        click.echo(f"  {r.lang_name} ({r.lang_id}) — {r.total_score}/{r.max_score} ({r.percentage:.1f}%)")
        for d in r.dimensions:
            bar_len = 20
            filled = int(bar_len * d.score / d.max_score) if d.max_score > 0 else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            click.echo(f"    {d.name:<8} {bar} {d.score}/{d.max_score}")
        if any(d.suggestions for d in r.dimensions):
            suggestions = [s for d in r.dimensions for s in d.suggestions[:2]]
            click.echo(f"    建议: {'; '.join(suggestions[:3])}")
        click.echo()


def _quality_ci_output(reports: list) -> None:
    """输出 GitHub Actions 兼容的质量评分结果

    生成：
    1. JSON 报告文件 quality-report.json
    2. 徽章数据文件 quality-badge.json
    3. GitHub Actions Job Summary（Markdown）
    4. PR 评论内容文件 quality-comment.md
    """
    import json as json_mod
    from pathlib import Path as PathLib

    from yanpub.core.quality import DimensionScore

    avg_score = sum(r.total_score for r in reports) / len(reports) if reports else 0
    max_score = reports[0].max_score if reports else 100
    avg_pct = avg_score / max_score * 100 if max_score > 0 else 0

    # 等级分布
    grade_counts: dict[str, int] = {}
    for r in reports:
        grade_counts[r.grade] = grade_counts.get(r.grade, 0) + 1

    # 1. JSON 报告
    report_data = {
        "schema_version": 1,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "summary": {
            "total_adapters": len(reports),
            "average_score": round(avg_score, 1),
            "max_score": max_score,
            "average_percentage": round(avg_pct, 1),
            "grade_distribution": grade_counts,
        },
        "adapters": [r.to_dict() for r in reports],
    }
    PathLib("quality-report.json").write_text(
        json_mod.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 2. 徽章数据（shields.io endpoint 格式）
    badge_color = "brightgreen" if avg_pct >= 85 else "green" if avg_pct >= 70 else "yellow" if avg_pct >= 55 else "orange" if avg_pct >= 40 else "red"
    badge_data = {
        "schemaVersion": 1,
        "label": "adapter quality",
        "message": f"{avg_score:.0f}/{max_score} avg",
        "color": badge_color,
    }
    PathLib("quality-badge.json").write_text(
        json_mod.dumps(badge_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. GitHub Actions Job Summary
    grade_emoji = {"S": "🌟", "A": "✅", "B": "🔵", "C": "⚠️", "D": "🟠", "F": "❌"}
    summary_lines = [
        "## 🔍 适配器质量评分报告\n",
        f"**{len(reports)}** 个适配器 | 平均分 **{avg_score:.1f}/{max_score}** ({avg_pct:.1f}%)\n",
        "| 适配器 | ID | 等级 | 得分 | 基础完整度 | 元数据质量 | 示例丰富度 | 文档覆盖 | 功能验证 |",
        "|--------|----|------|------|-----------|-----------|-----------|---------|---------|",
    ]
    for r in sorted(reports, key=lambda x: x.total_score, reverse=True):
        dims = {d.name: d for d in r.dimensions}
        emoji = grade_emoji.get(r.grade, "")
        row = (
            f"| {r.lang_name} | `{r.lang_id}` | {emoji} {r.grade} "
            f"| **{r.total_score}/{r.max_score}** "
            f"| {dims.get('基础完整度', DimensionScore('',0,0)).score}/25 "
            f"| {dims.get('元数据质量', DimensionScore('',0,0)).score}/20 "
            f"| {dims.get('示例丰富度', DimensionScore('',0,0)).score}/20 "
            f"| {dims.get('文档覆盖', DimensionScore('',0,0)).score}/15 "
            f"| {dims.get('功能验证', DimensionScore('',0,0)).score}/20 |"
        )
        summary_lines.append(row)

    # 建议汇总
    all_suggestions: list[tuple[str, str]] = []
    for r in reports:
        for d in r.dimensions:
            for s in d.suggestions[:2]:
                all_suggestions.append((r.lang_name, s))
    if all_suggestions:
        summary_lines.append("\n### 📋 改进建议\n")
        for name, sug in all_suggestions[:15]:
            summary_lines.append(f"- **{name}**: {sug}")

    summary_md = "\n".join(summary_lines)

    # 写入 GITHUB_STEP_SUMMARY（如果可用）
    import os
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        PathLib(step_summary).write_text(summary_md, encoding="utf-8")

    # 4. PR 评论内容
    comment_lines = [
        "## 🔍 适配器质量评分\n",
        f"平均分: **{avg_score:.1f}/{max_score}** ({avg_pct:.1f}%) | 适配器: {len(reports)} 个\n",
    ]
    for r in sorted(reports, key=lambda x: x.total_score, reverse=True):
        emoji = grade_emoji.get(r.grade, "")
        comment_lines.append(f"- {emoji} **{r.lang_name}** (`{r.lang_id}`): {r.total_score}/{r.max_score} — {r.grade}")
    top_suggestions = all_suggestions[:5]
    if top_suggestions:
        comment_lines.append("\n**主要改进建议:**")
        for name, sug in top_suggestions:
            comment_lines.append(f"- {name}: {sug}")
    PathLib("quality-comment.md").write_text("\n".join(comment_lines), encoding="utf-8")

    # 终端也输出简短摘要
    click.echo(f"适配器质量评分: {len(reports)} 个适配器, 平均分 {avg_score:.1f}/{max_score}")
    click.echo(f"等级分布: {' '.join(f'{g}:{c}' for g, c in sorted(grade_counts.items(), key=lambda x: 'SABCDF'.index(x[0]) if x[0] in 'SABCDF' else 9))}")
    click.echo("已生成: quality-report.json, quality-badge.json, quality-comment.md")


if __name__ == "__main__":
    main()
