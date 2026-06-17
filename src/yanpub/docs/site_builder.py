"""YanDocs 静态站点构建器

将文档数据渲染为 HTML 静态站点。
"""

from __future__ import annotations

import json
from pathlib import Path

from yanpub.docs.generator import DocsGenerator


_LANDING_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{site_name} - {site_description}</title>
<style>
:root {{
  --bg: #1a1a2e;
  --surface: #16213e;
  --card: #0f3460;
  --text: #e8e8e8;
  --text-dim: #a0a0b0;
  --accent: #e94560;
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
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
header h1 {{ font-size: 1.5rem; }}
header h1 small {{ color: var(--text-dim); font-weight: normal; font-size: 0.9rem; }}
.stats {{
  display: flex;
  gap: 2rem;
  color: var(--text-dim);
  font-size: 0.9rem;
}}
.stats strong {{ color: var(--accent); font-size: 1.1rem; }}
main {{ max-width: 1200px; margin: 2rem auto; padding: 0 2rem; }}
.languages {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1.5rem;
  margin-bottom: 3rem;
}}
.lang-card {{
  background: var(--card);
  border-radius: 12px;
  padding: 1.5rem;
  border: 1px solid var(--border);
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}}
.lang-card:hover {{
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}}
.lang-header {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}}
.lang-dot {{
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.lang-name {{ font-size: 1.3rem; font-weight: 600; }}
.lang-id {{ color: var(--text-dim); font-size: 0.85rem; }}
.lang-version {{
  background: var(--surface);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-dim);
}}
.lang-meta {{
  display: flex;
  gap: 1rem;
  color: var(--text-dim);
  font-size: 0.85rem;
  margin-top: 0.75rem;
}}
.lang-meta span strong {{ color: var(--text); }}
.capabilities {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}}
.cap-badge {{
  background: var(--surface);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-dim);
}}
.cap-badge.active {{
  background: rgba(233,69,96,0.2);
  color: var(--accent);
}}
section h2 {{
  font-size: 1.3rem;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
}}
.comparison-table {{
  overflow-x: auto;
  margin-bottom: 3rem;
}}
.comparison-table table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}}
.comparison-table th, .comparison-table td {{
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  text-align: left;
}}
.comparison-table th {{
  background: var(--surface);
  position: sticky;
  top: 0;
}}
.comparison-table td {{
  background: var(--card);
}}
.comparison-table td:first-child {{
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
}}
.kw-list {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.kw-tag {{
  background: var(--surface);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.75rem;
}}
.search-box {{
  width: 100%;
  max-width: 400px;
  padding: 0.75rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 1rem;
  outline: none;
  margin-bottom: 1.5rem;
}}
.search-box:focus {{
  border-color: var(--accent);
}}
.search-results {{
  margin-bottom: 2rem;
  max-height: 300px;
  overflow-y: auto;
}}
.search-result {{
  padding: 0.5rem 0.75rem;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 0.5rem;
}}
.search-result .kw {{ color: var(--accent); font-weight: 600; }}
.search-result .lang {{ color: var(--text-dim); font-size: 0.85rem; }}
.search-result .cat {{ color: var(--text-dim); font-size: 0.75rem; }}
footer {{
  text-align: center;
  padding: 2rem;
  color: var(--text-dim);
  font-size: 0.85rem;
  border-top: 1px solid var(--border);
}}
</style>
</head>
<body>
<header>
  <h1>言埠 YanPub <small>万言归埠，一站集成</small></h1>
  <div class="stats">
    <div>支持语言 <strong>{lang_count}</strong></div>
    <div>关键字总计 <strong>{kw_count}</strong></div>
  </div>
</header>
<main>
  <input type="text" class="search-box" id="search" placeholder="跨语言搜索关键字..." />
  <div class="search-results" id="searchResults"></div>

  <h2>已支持语言</h2>
  <div class="languages">
{lang_cards}
  </div>

  <section>
    <h2>语法对比</h2>
    <div class="comparison-table">
{comparison_html}
    </div>
  </section>
</main>
<footer>言埠 YanPub — 中文编程语言统一基础设施</footer>
<script>
const searchData = {search_json};

document.getElementById('search').addEventListener('input', function(e) {{
  const q = e.target.value.toLowerCase();
  const results = document.getElementById('searchResults');
  if (!q) {{ results.innerHTML = ''; return; }}
  const matches = searchData.filter(item => item.keyword.includes(q));
  results.innerHTML = matches.slice(0, 20).map(m =>
    '<div class="search-result"><span class="kw">' + m.keyword +
    '</span> <span class="lang">(' + m.lang_name + ')</span>' +
    ' <span class="cat">[' + m.category + ']</span></div>'
  ).join('');
}});
</script>
</body>
</html>"""


def build_site(
    output_dir: str | Path = "yandocs_site",
    registry=None,
) -> Path:
    """构建文档站静态 HTML

    Args:
        output_dir: 输出目录
        registry: 语言注册中心（默认使用全局实例）

    Returns:
        输出目录的 Path
    """
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    gen = DocsGenerator(registry)
    site_data = gen.generate_site_data()

    # 生成语言卡片 HTML
    lang_cards_html = ""
    for lang in site_data["languages"]:
        caps = lang["capabilities"]
        cap_badges = " ".join(
            f'<span class="cap-badge {"active" if v else ""}">{k}</span>'
            for k, v in caps.items()
        )
        lang_cards_html += f"""
    <div class="lang-card" onclick="location.href='lang_{lang['id']}.html'">
      <div class="lang-header">
        <span class="lang-dot" style="background:{lang['primary_color']}"></span>
        <span class="lang-name">{lang['name']}</span>
        <span class="lang-id">{lang['id']}</span>
        <span class="lang-version">v{lang['version']}</span>
      </div>
      <div class="lang-meta">
        <span>关键字 <strong>{lang['keyword_count']}</strong></span>
        <span>扩展名 <strong>{', '.join(lang['extensions'])}</strong></span>
        <span>注释 <strong>{lang['comment_syntax']}</strong></span>
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
                search_items.append({
                    "keyword": kd["keyword"],
                    "lang_id": kd["lang_id"],
                    "lang_name": kd["lang_name"],
                    "category": kd["category"],
                })

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

    (output / "index.html").write_text(html, encoding="utf-8")

    # 生成各语言详情页
    for lang in site_data["languages"]:
        _build_language_page(output, lang, lang_names)

    # 写入数据 JSON（供 API 使用）
    (output / "data.json").write_text(
        json.dumps(site_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output


def _build_language_page(output: Path, lang: dict, lang_names: dict) -> None:
    """生成单个语言的详情页"""
    lid = lang["id"]
    kw_by_cat = lang["keywords_by_category"]

    category_sections = ""
    for cat, kw_docs in kw_by_cat.items():
        kw_rows = ""
        for kd in kw_docs:
            kw_rows += f"""<tr>
          <td><code>{kd['keyword']}</code></td>
          <td>{kd['category']}</td>
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
<title>{lang['name']} - 言埠 YanPub</title>
<style>
:root {{
  --bg: #1a1a2e;
  --surface: #16213e;
  --card: #0f3460;
  --text: #e8e8e8;
  --text-dim: #a0a0b0;
  --accent: {lang['primary_color']};
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
  <h1>{lang['name']} <small>{lang['id']} v{lang['version']}</small></h1>
</header>
<main>
  <div class="meta">
    <span>扩展名 <strong>{', '.join(lang['extensions'])}</strong></span>
    <span>注释 <strong>{lang['comment_syntax']}</strong></span>
    <span>关键字 <strong>{lang['keyword_count']}</strong></span>
  </div>

  <h2>关键字索引</h2>
  {category_sections}
</main>
</body>
</html>"""

    (output / f"lang_{lid}.html").write_text(html, encoding="utf-8")
