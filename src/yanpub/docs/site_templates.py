"""站点 HTML 模板 — 首页落地页模板字符串"""

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
