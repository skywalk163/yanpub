"""SEO 优化组件 — Sitemap、Open Graph、JSON-LD、robots.txt

核心能力：
1. SEOConfig — SEO 配置数据类
2. SitemapGenerator — Sitemap 生成器
3. OpenGraphBuilder — Open Graph 标签与 JSON-LD 结构化数据
4. SEOOptimizer — 文档站 SEO 优化器
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


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
        self._pages.append(
            {
                "path": path.lstrip("/"),
                "lastmod": lastmod,
                "changefreq": changefreq,
                "priority": max(0.0, min(1.0, priority)),
            }
        )

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
            self.generate_xml(),
            encoding="utf-8",
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
        tags.append(
            f'<meta property="og:description" content="{html_module.escape(description)}" />'
        )
        tags.append(f'<meta property="og:url" content="{html_module.escape(url)}" />')
        tags.append(f'<meta property="og:type" content="{html_module.escape(page_type)}" />')
        tags.append(
            f'<meta property="og:site_name" content="{html_module.escape(self.config.site_name)}" />'
        )
        tags.append(
            f'<meta property="og:locale" content="{html_module.escape(self.config.site_language)}" />'
        )
        og_img = image or self.config.og_image
        if og_img:
            tags.append(f'<meta property="og:image" content="{html_module.escape(og_img)}" />')
        # Twitter Card
        tags.append('<meta name="twitter:card" content="summary_large_image" />')
        tags.append(f'<meta name="twitter:title" content="{html_module.escape(title)}" />')
        tags.append(
            f'<meta name="twitter:description" content="{html_module.escape(description)}" />'
        )
        if og_img:
            tags.append(f'<meta name="twitter:image" content="{html_module.escape(og_img)}" />')
        if self.config.twitter_handle:
            tags.append(
                f'<meta name="twitter:site" content="{html_module.escape(self.config.twitter_handle)}" />'
            )
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
                main_entity.append(
                    {
                        "@type": "Question",
                        "name": item.get("question", ""),
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": item.get("answer", ""),
                        },
                    }
                )
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
