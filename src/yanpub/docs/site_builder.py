"""YanDocs 静态站点构建器

将文档数据渲染为 HTML 静态站点。
支持 SEO 优化：Sitemap、Open Graph、JSON-LD 结构化数据、robots.txt。
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from yanpub.docs.generator import DocsGenerator


# ============================================================
# SEO 配置与优化组件
# ============================================================


@dataclass
class SEOConfig:
    """SEO 配置"""

    site_name: str = "言埠 YanPub"
    site_url: str = "https://yanpub.dev"
    site_description: str = "中文编程语言统一基础设施"
    site_language: str = "zh-CN"
    og_image: str = ""  # Open Graph 图片 URL
    twitter_handle: str = ""
    google_analytics_id: str = ""


class SitemapGenerator:
    """Sitemap 生成器"""

    def __init__(self, base_url: str = "https://yanpub.dev"):
        self.base_url = base_url.rstrip("/")
        self._pages: list[dict] = []

    def add_page(
        self,
        path: str,
        lastmod: str = "",
        changefreq: str = "weekly",
        priority: float = 0.8,
    ) -> None:
        """添加页面到 sitemap

        Args:
            path: 页面路径（相对于站点根目录，如 "index.html"）
            lastmod: 最后修改日期（YYYY-MM-DD 格式）
            changefreq: 更新频率（always/hourly/daily/weekly/monthly/yearly/never）
            priority: 优先级（0.0 ~ 1.0）
        """
        self._pages.append({
            "path": path.lstrip("/"),
            "lastmod": lastmod,
            "changefreq": changefreq,
            "priority": max(0.0, min(1.0, priority)),
        })

    def generate_xml(self) -> str:
        """生成 sitemap.xml 内容"""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for page in self._pages:
            loc = f"{self.base_url}/{page['path']}"
            lines.append("  <url>")
            lines.append(f"    <loc>{xml_escape(loc)}</loc>")
            if page["lastmod"]:
                lines.append(f"    <lastmod>{xml_escape(page['lastmod'])}</lastmod>")
            lines.append(f"    <changefreq>{xml_escape(page['changefreq'])}</changefreq>")
            lines.append(f"    <priority>{page['priority']:.1f}</priority>")
            lines.append("  </url>")
        lines.append("</urlset>")
        return "\n".join(lines)

    def write(self, output_dir: Path) -> None:
        """写入 sitemap.xml 文件"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "sitemap.xml").write_text(
            self.generate_xml(), encoding="utf-8",
        )


class OpenGraphBuilder:
    """Open Graph 标签构建器"""

    def __init__(self, config: SEOConfig | None = None):
        self.config = config or SEOConfig()

    def build_tags(
        self,
        title: str,
        description: str,
        url: str,
        image: str = "",
        page_type: str = "website",
    ) -> str:
        """生成 Open Graph HTML meta 标签

        包含：
        - og:title, og:description, og:url, og:image, og:type, og:site_name, og:locale
        - twitter:card, twitter:title, twitter:description, twitter:image
        """
        tags = []
        # Open Graph
        tags.append(f'<meta property="og:title" content="{html_module.escape(title)}" />')
        tags.append(f'<meta property="og:description" content="{html_module.escape(description)}" />')
        tags.append(f'<meta property="og:url" content="{html_module.escape(url)}" />')
        tags.append(f'<meta property="og:type" content="{html_module.escape(page_type)}" />')
        tags.append(f'<meta property="og:site_name" content="{html_module.escape(self.config.site_name)}" />')
        tags.append(f'<meta property="og:locale" content="{html_module.escape(self.config.site_language)}" />')
        og_img = image or self.config.og_image
        if og_img:
            tags.append(f'<meta property="og:image" content="{html_module.escape(og_img)}" />')
        # Twitter Card
        tags.append('<meta name="twitter:card" content="summary_large_image" />')
        tags.append(f'<meta name="twitter:title" content="{html_module.escape(title)}" />')
        tags.append(f'<meta name="twitter:description" content="{html_module.escape(description)}" />')
        if og_img:
            tags.append(f'<meta name="twitter:image" content="{html_module.escape(og_img)}" />')
        if self.config.twitter_handle:
            tags.append(f'<meta name="twitter:site" content="{html_module.escape(self.config.twitter_handle)}" />')
        return "\n".join(tags)

    def build_structured_data(self, page_type: str, data: dict) -> str:
        """生成 JSON-LD 结构化数据

        支持类型：
        - SoftwareApplication: 项目主页
        - WebPage: 文档页面
        - FAQPage: FAQ 页面
        """
        schema: dict = {}

        if page_type == "SoftwareApplication":
            schema = {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": data.get("name", self.config.site_name),
                "description": data.get("description", self.config.site_description),
                "url": data.get("url", self.config.site_url),
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "Cross-platform",
                "programmingLanguage": "Chinese",
                "inLanguage": self.config.site_language,
            }
            if data.get("version"):
                schema["softwareVersion"] = data["version"]
            if data.get("offers"):
                schema["offers"] = data["offers"]
            else:
                schema["offers"] = {
                    "@type": "Offer",
                    "price": "0",
                    "priceCurrency": "CNY",
                }

        elif page_type == "WebPage":
            schema = {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "url": data.get("url", ""),
                "inLanguage": self.config.site_language,
                "isPartOf": {
                    "@type": "WebSite",
                    "name": self.config.site_name,
                    "url": self.config.site_url,
                },
            }
            if data.get("dateModified"):
                schema["dateModified"] = data["dateModified"]

        elif page_type == "FAQPage":
            main_entity = []
            for item in data.get("questions", []):
                main_entity.append({
                    "@type": "Question",
                    "name": item.get("question", ""),
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item.get("answer", ""),
                    },
                })
            schema = {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": main_entity,
            }

        else:
            schema = {
                "@context": "https://schema.org",
                "@type": page_type,
                **data,
            }

        return '<script type="application/ld+json">{}</script>'.format(
            json.dumps(schema, ensure_ascii=False),
        )


class SEOOptimizer:
    """SEO 优化器 — 为文档站添加 SEO 元素"""

    # 支持的多语言区域代码（hreflang）
    HREFLANG_MAP = {
        "zh": "zh-CN",
        "en": "en",
        "ja": "ja",
        "ko": "ko",
    }

    def __init__(self, config: SEOConfig | None = None):
        self.config = config or SEOConfig()
        self.og_builder = OpenGraphBuilder(self.config)

    def optimize_html(
        self,
        html: str,
        path: str,
        title: str,
        description: str,
        keywords: str | None = None,
        alternate_langs: dict[str, str] | None = None,
    ) -> str:
        """优化 HTML 页面

        1. 添加 <meta> 标签（description, keywords, robots）
        2. 添加 Open Graph 标签
        3. 添加 canonical URL
        4. 添加 JSON-LD 结构化数据
        5. 添加 hreflang 标签（多语言）

        Args:
            html: 原始 HTML 内容
            path: 页面路径（如 "index.html"）
            title: 页面标题
            description: 页面描述
            keywords: 关键词（逗号分隔）
            alternate_langs: 多语言替代链接 {lang_code: href}
        """
        # 构建完整的 canonical URL
        canonical_url = f"{self.config.site_url}/{path.lstrip('/')}"

        # 构建 SEO meta 标签块
        meta_tags = []
        meta_tags.append(f'<meta name="description" content="{html_module.escape(description)}" />')
        if keywords:
            meta_tags.append(f'<meta name="keywords" content="{html_module.escape(keywords)}" />')
        meta_tags.append('<meta name="robots" content="index, follow" />')

        # Canonical URL
        meta_tags.append(f'<link rel="canonical" href="{html_module.escape(canonical_url)}" />')

        # Open Graph 标签
        og_tags = self.og_builder.build_tags(
            title=title,
            description=description,
            url=canonical_url,
            page_type="website",
        )
        meta_tags.append(og_tags)

        # hreflang 标签
        if alternate_langs:
            for lang_code, href in alternate_langs.items():
                hreflang = self.HREFLANG_MAP.get(lang_code, lang_code)
                meta_tags.append(
                    f'<link rel="alternate" hreflang="{html_module.escape(hreflang)}" '
                    f'href="{html_module.escape(href)}" />'
                )
            # x-default 指向默认语言版本
            default_href = alternate_langs.get("zh", canonical_url)
            meta_tags.append(
                f'<link rel="alternate" hreflang="x-default" '
                f'href="{html_module.escape(default_href)}" />'
            )

        # JSON-LD 结构化数据
        if path == "index.html":
            structured_data = self.og_builder.build_structured_data(
                "SoftwareApplication",
                {
                    "name": self.config.site_name,
                    "description": description,
                    "url": canonical_url,
                },
            )
        else:
            structured_data = self.og_builder.build_structured_data(
                "WebPage",
                {
                    "name": title,
                    "description": description,
                    "url": canonical_url,
                },
            )
        meta_tags.append(structured_data)

        # Google Analytics
        if self.config.google_analytics_id:
            ga_script = (
                '<script async src="https://www.googletagmanager.com/gtag/js?id='
                f'{html_module.escape(self.config.google_analytics_id)}"></script>\n'
                "<script>\n"
                "  window.dataLayer = window.dataLayer || [];\n"
                "  function gtag(){dataLayer.push(arguments);}\n"
                "  gtag('js', new Date());\n"
                f"  gtag('config', '{html_module.escape(self.config.google_analytics_id)}');\n"
                "</script>"
            )
            meta_tags.append(ga_script)

        seo_block = "\n".join(meta_tags)

        # 将 SEO 块插入 </head> 之前
        if "</head>" in html:
            html = html.replace("</head>", f"{seo_block}\n</head>")
        elif "<body" in html:
            # 没有 </head> 的情况，在 <body> 前插入
            html = html.replace("<body", f"{seo_block}\n<body")

        return html

    def generate_robots_txt(self) -> str:
        """生成 robots.txt"""
        lines = [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "",
            f"Sitemap: {self.config.site_url}/sitemap.xml",
        ]
        return "\n".join(lines)

    def generate_sitemap(self, pages: list[dict]) -> str:
        """生成 sitemap.xml

        Args:
            pages: 页面列表，每项包含 path, lastmod, changefreq, priority
        """
        gen = SitemapGenerator(self.config.site_url)
        for page in pages:
            gen.add_page(
                path=page.get("path", ""),
                lastmod=page.get("lastmod", ""),
                changefreq=page.get("changefreq", "weekly"),
                priority=page.get("priority", 0.8),
            )
        return gen.generate_xml()

    def validate_html(self, html: str) -> dict:
        """验证 HTML 中的 SEO 元素

        Returns:
            包含各检查项结果的字典
        """
        results: dict[str, bool | list[str]] = {}

        # 检查 meta description
        results["has_meta_description"] = bool(
            re.search(r'<meta\s+name=["\']description["\']', html),
        )

        # 检查 Open Graph 标签
        results["has_og_title"] = bool(
            re.search(r'<meta\s+property=["\']og:title["\']', html),
        )
        results["has_og_description"] = bool(
            re.search(r'<meta\s+property=["\']og:description["\']', html),
        )

        # 检查 canonical URL
        results["has_canonical"] = bool(
            re.search(r'<link\s+rel=["\']canonical["\']', html),
        )

        # 检查 JSON-LD
        results["has_structured_data"] = bool(
            re.search(r'<script\s+type=["\']application/ld\+json["\']', html),
        )

        # 检查 robots meta
        results["has_robots_meta"] = bool(
            re.search(r'<meta\s+name=["\']robots["\']', html),
        )

        # 检查 hreflang
        results["has_hreflang"] = bool(
            re.search(r'<link\s+rel=["\']alternate["\']\s+hreflang=', html),
        )

        # 收集问题
        issues: list[str] = []
        if not results["has_meta_description"]:
            issues.append("缺少 meta description")
        if not results["has_og_title"]:
            issues.append("缺少 og:title")
        if not results["has_canonical"]:
            issues.append("缺少 canonical URL")
        if not results["has_structured_data"]:
            issues.append("缺少 JSON-LD 结构化数据")
        results["issues"] = issues
        results["passed"] = len(issues) == 0

        return results


# ============================================================
# HTML 模板
# ============================================================


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
        optimizer.generate_robots_txt(), encoding="utf-8",
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
