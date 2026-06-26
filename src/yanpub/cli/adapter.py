"""适配器管理和兼容性命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@main.command()
@click.argument("lang_id", required=False)
@click.option("--json", "as_json", is_flag=True, help="输出 JSON 格式")
def compat(lang_id: str | None, as_json: bool):
    """检查适配器版本兼容性"""
    from yanpub.core.adapter.compat import (
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

@click.group()
def adapter():
    """适配器管理 — 热重载/监控"""
    pass

@main.command("cache")
@click.argument("action", type=click.Choice(["stats", "clear", "invalidate"]))
@click.option("--adapter", "-a", default=None, help="适配器 ID（invalidate 时指定）")
def cache_command(action: str, adapter: str | None):
    """缓存管理 — 统计/清除/失效"""
    from yanpub.core.adapter.cache import get_adapter_cache

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
    from yanpub.core.lifecycle.hotreload import AdapterWatcher

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
    from yanpub.core.lifecycle.hotreload import HotReloader

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
    from yanpub.core.perf.profiler import (
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
    from yanpub.core.dev.navigator import SymbolNavigator

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

main.add_command(adapter)
