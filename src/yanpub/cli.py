"""统一 CLI 入口"""

from __future__ import annotations

import os
import sys

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
@click.version_option(package_name="yanpub")
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
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        click.echo(f"包名只能包含字母、数字、下划线和连字符: {name}", err=True)
        sys.exit(1)

    # 版本号格式验证（semver）
    if not re.match(r'^\d+\.\d+\.\d+([a-zA-Z0-9.+-]*)?$', version):
        click.echo(f"版本号格式不正确（需要 semver 如 1.0.0）: {version}", err=True)
        sys.exit(1)

    full_name = f"{lang_id}:{name}"

    # 版本降级检查
    registry = PackageRegistry()
    existing = registry.get(full_name)
    if existing and not force:
        if DependencyResolver._parse_version(version) <= DependencyResolver._parse_version(existing.version):
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

    remote_url = remote or RemoteRegistry.remote_url if hasattr(RemoteRegistry, 'remote_url') else ""
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


@main.command()
@click.argument("concept", required=False)
@click.option("--from", "from_lang", default=None, help="源语言ID")
@click.option("--to", "to_lang", default=None, help="目标语言ID")
def compare(concept: str | None, from_lang: str | None, to_lang: str | None):
    """语言对比 — 比较不同中文编程语言的语法"""
    from yanpub.docs.comparator import LanguageComparator
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
            click.echo(f"  {name_a} <-> {name_b}: {sim.similarity_score:.1%} ({len(sim.shared_keywords)}个共享关键字)")

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
    from yanpub.core.compat import check_compatibility, check_all_compatibility, format_compat_matrix, format_compat_detail

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
        registry, lang_id=lang_id, iterations=iterations,
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
        registry, lang_id=lang_id,
    )

    if not regressions:
        click.echo("没有历史数据可供对比")
        return

    click.echo(f"对比结果（阈值: {threshold:.0%}）:\n")
    for r in regressions:
        status = "💥 回归" if r.is_regression else "✅ 正常"
        change = f"+{r.change_pct:.0%}" if r.change_pct > 0 else f"{r.change_pct:.0%}"
        click.echo(f"  {status} {r.adapter_name} — {r.bench_name}: {r.previous_ms:.1f}ms → {r.current_ms:.1f}ms ({change})")

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


if __name__ == "__main__":
    main()
