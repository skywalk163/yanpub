"""国际化命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

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
