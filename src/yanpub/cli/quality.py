"""质量检查命令"""

from __future__ import annotations

import os

import click

from yanpub.cli import main

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
