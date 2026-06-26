"""项目、基线和预算命令"""

from __future__ import annotations

import sys
import time

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

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
