"""文档站和语言对比命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.adapter.registry import get_registry

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
