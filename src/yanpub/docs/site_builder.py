"""YanDocs 静态站点构建器

将文档数据渲染为 HTML 静态站点。
支持 SEO 优化：Sitemap、Open Graph、JSON-LD 结构化数据、robots.txt。

拆分模块：
- yanpub.docs.seo — SEOConfig, SitemapGenerator, OpenGraphBuilder, SEOOptimizer
- yanpub.docs.site_templates — _LANDING_TEMPLATE HTML 模板字符串
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from yanpub.docs.generator import DocsGenerator
from yanpub.docs.seo import SEOConfig, SEOOptimizer, SitemapGenerator
from yanpub.docs.site_templates import _LANDING_TEMPLATE

__all__ = [
    "build_site",
    "_build_language_page",
    "SEOConfig",
    "SitemapGenerator",
    "OpenGraphBuilder",
    "SEOOptimizer",
    "_LANDING_TEMPLATE",
]

# 延迟 re-export SEO 类，保持向后兼容
from yanpub.docs.seo import OpenGraphBuilder  # noqa: F401


def build_site(
    output_dir: str | Path = "yandocs_site",
    registry=None,
    seo_config: SEOConfig | None = None,
) -> Path:
    """构建文档站静态 HTML

    Args:
        output_dir: 输出目录
        registry: 语言注册中心（默认使用全局实例）
        seo_config: SEO 配置（为 None 时使用默认配置）

    Returns:
        输出目录的 Path
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    config = seo_config or SEOConfig()
    optimizer = SEOOptimizer(config)

    gen = DocsGenerator(registry)
    site_data = gen.generate_site_data()

    # 生成语言卡片 HTML
    lang_cards_html = ""
    for lang in site_data["languages"]:
        caps = lang["capabilities"]
        cap_badges = " ".join(
            f'<span class="cap-badge {"active" if v else ""}">{k}</span>' for k, v in caps.items()
        )
        lang_cards_html += f"""
    <div class="lang-card" onclick="location.href='lang_{lang["id"]}.html'">
      <div class="lang-header">
        <span class="lang-dot" style="background:{lang["primary_color"]}"></span>
        <span class="lang-name">{lang["name"]}</span>
        <span class="lang-id">{lang["id"]}</span>
        <span class="lang-version">v{lang["version"]}</span>
      </div>
      <div class="lang-meta">
        <span>关键字 <strong>{lang["keyword_count"]}</strong></span>
        <span>扩展名 <strong>{", ".join(lang["extensions"])}</strong></span>
        <span>注释 <strong>{lang["comment_syntax"]}</strong></span>
      </div>
      <div class="capabilities">{cap_badges}</div>
    </div>"""

    # 生成对比表 HTML
    lang_ids = [lang["id"] for lang in site_data["languages"]]
    lang_names = {lang["id"]: lang["name"] for lang in site_data["languages"]}

    header_cells = "<th>概念</th>" + "".join(f"<th>{lang_names[lid]}</th>" for lid in lang_ids)
    rows_html = ""
    for row in site_data["comparison"]:
        cells = f"<td>{row['concept']}</td>"
        for lid in lang_ids:
            kws = row["languages"].get(lid, [])
            kw_tags = " ".join(f'<span class="kw-tag">{kw}</span>' for kw in kws)
            cells += f"<td><div class='kw-list'>{kw_tags or '-'}</div></td>"
        rows_html += f"<tr>{cells}</tr>"

    comparison_html = f"""<table>
      <tr>{header_cells}</tr>
      {rows_html}
    </table>"""

    # 构建搜索数据
    search_items = []
    for lang in site_data["languages"]:
        for cat, kw_docs in lang["keywords_by_category"].items():
            for kd in kw_docs:
                search_items.append(
                    {
                        "keyword": kd["keyword"],
                        "lang_id": kd["lang_id"],
                        "lang_name": kd["lang_name"],
                        "category": kd["category"],
                    }
                )

    # 渲染首页
    html = _LANDING_TEMPLATE.format(
        site_name=site_data["site_name"],
        site_description=site_data["site_description"],
        lang_count=site_data["stats"]["language_count"],
        kw_count=site_data["stats"]["total_keywords"],
        lang_cards=lang_cards_html,
        comparison_html=comparison_html,
        search_json=json.dumps(search_items, ensure_ascii=False),
    )

    # SEO 优化首页
    kw_list = [lang["name"] for lang in site_data["languages"]]
    keywords = ",".join(kw_list + ["中文编程语言", "YanPub", "言埠"])
    html = optimizer.optimize_html(
        html,
        path="index.html",
        title=f"{site_data['site_name']} - {site_data['site_description']}",
        description=site_data["site_description"],
        keywords=keywords,
    )

    (output / "index.html").write_text(html, encoding="utf-8")

    # 生成各语言详情页
    for lang in site_data["languages"]:
        _build_language_page(output, lang, lang_names, optimizer)

    # 写入数据 JSON（供 API 使用）
    (output / "data.json").write_text(
        json.dumps(site_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 生成 sitemap.xml
    sitemap = SitemapGenerator(config.site_url)
    today = date.today().isoformat()
    sitemap.add_page("index.html", lastmod=today, changefreq="daily", priority=1.0)
    for lang in site_data["languages"]:
        sitemap.add_page(
            f"lang_{lang['id']}.html",
            lastmod=today,
            changefreq="weekly",
            priority=0.8,
        )
    sitemap.write(output)

    # 生成 robots.txt
    (output / "robots.txt").write_text(
        optimizer.generate_robots_txt(),
        encoding="utf-8",
    )

    return output


def _build_language_page(
    output: Path,
    lang: dict,
    lang_names: dict,
    optimizer: SEOOptimizer | None = None,
) -> None:
    """生成单个语言的详情页"""
    lid = lang["id"]
    kw_by_cat = lang["keywords_by_category"]

    category_sections = ""
    for cat, kw_docs in kw_by_cat.items():
        kw_rows = ""
        for kd in kw_docs:
            kw_rows += f"""<tr>
          <td><code>{kd["keyword"]}</code></td>
          <td>{kd["category"]}</td>
        </tr>"""
        category_sections += f"""
      <h3>{cat}</h3>
      <table>
        <tr><th>关键字</th><th>分类</th></tr>
        {kw_rows}
      </table>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{lang["name"]} - 言埠 YanPub</title>
<style>
:root {{
  --bg: #1a1a2e;
  --surface: #16213e;
  --card: #0f3460;
  --text: #e8e8e8;
  --text-dim: #a0a0b0;
  --accent: {lang["primary_color"]};
  --border: #2a2a4a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}}
header {{
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 1.5rem 2rem;
}}
header a {{ color: var(--text-dim); text-decoration: none; }}
header h1 {{ font-size: 1.5rem; }}
header h1 small {{ color: var(--text-dim); font-weight: normal; font-size: 0.9rem; }}
main {{ max-width: 960px; margin: 2rem auto; padding: 0 2rem; }}
h2 {{ font-size: 1.3rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border); }}
h3 {{ font-size: 1.1rem; margin: 1.5rem 0 0.75rem; color: var(--accent); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-bottom: 1rem; }}
th, td {{ padding: 0.5rem 0.75rem; border: 1px solid var(--border); text-align: left; }}
th {{ background: var(--surface); }}
td {{ background: var(--card); }}
code {{ background: var(--surface); padding: 2px 6px; border-radius: 3px; font-size: 0.85rem; }}
.meta {{ display: flex; gap: 2rem; color: var(--text-dim); margin-bottom: 2rem; }}
.meta strong {{ color: var(--text); }}
</style>
</head>
<body>
<header>
  <a href="index.html">&larr; 返回首页</a>
  <h1>{lang["name"]} <small>{lang["id"]} v{lang["version"]}</small></h1>
</header>
<main>
  <div class="meta">
    <span>扩展名 <strong>{", ".join(lang["extensions"])}</strong></span>
    <span>注释 <strong>{lang["comment_syntax"]}</strong></span>
    <span>关键字 <strong>{lang["keyword_count"]}</strong></span>
  </div>

  <h2>关键字索引</h2>
  {category_sections}
</main>
</body>
</html>"""

    # SEO 优化语言详情页
    if optimizer is not None:
        desc = lang.get("description") or f"{lang['name']} 编程语言文档 — 关键字索引与语法参考"
        keywords = f"{lang['name']},{lang['id']},中文编程语言,YanPub,言埠"
        html = optimizer.optimize_html(
            html,
            path=f"lang_{lid}.html",
            title=f"{lang['name']} - 言埠 YanPub",
            description=desc,
            keywords=keywords,
        )

    (output / f"lang_{lid}.html").write_text(html, encoding="utf-8")
