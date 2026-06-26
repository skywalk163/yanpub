"""性能基准和健康检查命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

@main.command()
@click.argument("lang_id", required=False)
def health(lang_id: str | None):
    """检查语言后端健康状态"""
    from yanpub.core.adapter.health import check_adapter_health, check_all_adapters, format_health_report

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
    from yanpub.core.perf.benchmark import run_all_benchmarks, format_bench_report

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

@main.command("bench-visualize")
@click.argument("lang_id", required=False)
@click.option("--iterations", "-n", default=5, type=int, help="每项测试迭代次数")
@click.option("--output", "-o", default="bench_report.html", help="输出 HTML 文件路径")
def bench_visualize(lang_id: str | None, iterations: int, output: str):
    """生成性能基准测试可视化报告"""
    from yanpub.core.perf.bench_viz import BenchVisualizer, run_bench_with_regression

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
    from yanpub.core.perf.bench_viz import run_bench_with_regression

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
    from yanpub.core.perf.bench_viz import BenchHistory
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
