"""代码风格检查命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

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

    from yanpub.core.dev.linter import LintRuleEngine

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
