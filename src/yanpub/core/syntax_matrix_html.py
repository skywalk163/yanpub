"""语法对比矩阵 — HTML 生成

本文件从 syntax_matrix.py 拆分而来，仅包含 HTML 可视化渲染逻辑。
"""

from __future__ import annotations

from yanpub.core.syntax_matrix import SnippetEntry, SyntaxConcept


def build_html(
    lang_ids: list[str],
    matrix: list[dict],
    styles: dict[str, dict[str, str]],
    color_map: dict[str, str],
    registry,
) -> str:
    """构建完整的 HTML 对比页面"""

    # 语言表头
    lang_headers = ""
    for lid in lang_ids:
        adapter = registry.get(lid)
        name = adapter.name if adapter else lid
        version = adapter.version if adapter else ""
        color = color_map.get(lid, "#2C3E50")
        lang_headers += f"""      <th class="lang-header" style="border-top: 3px solid {color}">
        <span class="lang-name">{name}</span><br>
        <span class="lang-id">{lid}</span><br>
        <span class="lang-ver">v{version}</span>
      </th>\n"""

    # 语法风格总览行
    style_rows = ""
    style_labels = {
        "变量风格": "变量声明",
        "函数风格": "函数定义",
        "语句结束": "语句结束",
        "代码块": "代码块",
        "运算风格": "运算符",
        "注释": "注释",
    }
    for style_key, style_label in style_labels.items():
        cells = ""
        for lid in lang_ids:
            feat = styles.get(lid, {})
            val = feat.get(style_key, "—")
            cells += f"      <td>{val}</td>\n"
        style_rows += f"""    <tr>
      <td class="concept-cell">{style_label}</td>
{cells}    </tr>\n"""

    # 概念对比行
    concept_rows = ""
    current_category = ""
    for entry in matrix:
        concept: SyntaxConcept = entry["concept"]
        snippets: dict[str, SnippetEntry] = entry["snippets"]

        # 分类标题行
        if concept.category != current_category:
            current_category = concept.category
            concept_rows += f"""    <tr class="category-row">
      <td colspan="{len(lang_ids) + 1}" class="category-cell">{current_category}</td>
    </tr>\n"""

        cells = ""
        for lid in lang_ids:
            snippet = snippets.get(lid)
            if snippet is None:
                cells += '      <td class="snippet-na">—</td>\n'
            else:
                # HTML 转义
                code_escaped = (
                    snippet.code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                note_html = ""
                if snippet.note:
                    note_html = f'<div class="snippet-note">{snippet.note}</div>'
                cells += f"""      <td class="snippet-cell"><pre class="snippet-code">{code_escaped}</pre>{note_html}</td>\n"""

        difficulty_badge = ""
        if concept.difficulty:
            diff_class = {
                "入门": "diff-beginner",
                "简单": "diff-easy",
                "中等": "diff-medium",
                "困难": "diff-hard",
            }.get(concept.difficulty, "")
            difficulty_badge = (
                f' <span class="difficulty-badge {diff_class}">{concept.difficulty}</span>'
            )

        concept_rows += f"""    <tr>
      <td class="concept-cell">{concept.title}{difficulty_badge}<div class="concept-desc">{concept.description}</div></td>
{cells}    </tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>言埠 YanPub — 中文编程语言语法对比矩阵</title>
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --accent: #58a6ff;
      --hover: #1f2937;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, "Segoe UI", "Noto Sans SC", sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 24px;
      line-height: 1.6;
    }}
    .container {{
      max-width: 100%;
      overflow-x: auto;
    }}
    h1 {{
      text-align: center;
      font-size: 28px;
      margin-bottom: 8px;
    }}
    .subtitle {{
      text-align: center;
      color: var(--text-muted);
      margin-bottom: 24px;
      font-size: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      min-width: 1200px;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 10px 12px;
      vertical-align: top;
      text-align: left;
    }}
    th {{
      background: var(--card-bg);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .lang-header {{
      text-align: center;
      min-width: 140px;
    }}
    .lang-name {{
      font-size: 15px;
      font-weight: 600;
      display: block;
    }}
    .lang-id {{
      font-size: 11px;
      color: var(--text-muted);
      font-family: monospace;
    }}
    .lang-ver {{
      font-size: 10px;
      color: var(--text-muted);
    }}
    .concept-header {{
      text-align: center;
      min-width: 160px;
    }}
    .concept-cell {{
      background: var(--card-bg);
      font-weight: 600;
      position: sticky;
      left: 0;
      z-index: 5;
      min-width: 160px;
    }}
    .concept-desc {{
      font-weight: 400;
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 2px;
    }}
    .category-row td {{
      background: #1c2333;
      font-size: 14px;
      font-weight: 700;
      text-align: center;
      color: var(--accent);
      padding: 6px;
      letter-spacing: 2px;
    }}
    .snippet-cell {{
      background: var(--bg);
    }}
    .snippet-code {{
      font-family: "Fira Code", "Cascadia Code", "Source Code Pro", monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-all;
      margin: 0;
      color: #c9d1d9;
    }}
    .snippet-note {{
      font-size: 10px;
      color: var(--accent);
      margin-top: 4px;
      font-style: italic;
    }}
    .snippet-na {{
      text-align: center;
      color: var(--text-muted);
      background: var(--bg);
    }}
    .difficulty-badge {{
      display: inline-block;
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 8px;
      font-weight: 400;
      margin-left: 4px;
      vertical-align: middle;
    }}
    .diff-beginner {{ background: #1a4731; color: #3fb950; }}
    .diff-easy {{ background: #1a3a5c; color: #58a6ff; }}
    .diff-medium {{ background: #4a3000; color: #d29922; }}
    .diff-hard {{ background: #4a1020; color: #f85149; }}
    .style-section {{
      margin-bottom: 32px;
    }}
    .style-section h2 {{
      font-size: 18px;
      margin-bottom: 12px;
      color: var(--accent);
    }}
    .legend {{
      text-align: center;
      margin-bottom: 16px;
      font-size: 12px;
      color: var(--text-muted);
    }}
    tr:hover td {{
      background: var(--hover);
    }}
    tr:hover .concept-cell {{
      background: #1c2531;
    }}
  </style>
</head>
<body>
  <h1>🧮 中文编程语言语法对比矩阵</h1>
  <p class="subtitle">
    言埠 YanPub — 同一概念，十种写法 · 共 {len(lang_ids)} 种语言 · {len(matrix)} 个语法概念
  </p>
  <p class="legend">
    难度：
    <span class="difficulty-badge diff-beginner">入门</span>
    <span class="difficulty-badge diff-easy">简单</span>
    <span class="difficulty-badge diff-medium">中等</span>
    <span class="difficulty-badge diff-hard">困难</span>
  </p>
  <div class="container">
    <table>
      <thead>
        <tr>
          <th class="concept-header">语法概念</th>
{lang_headers}        </tr>
      </thead>
      <tbody>
    <tr class="category-row">
      <td colspan="{len(lang_ids) + 1}" class="category-cell">语法风格总览</td>
    </tr>
{style_rows}{concept_rows}      </tbody>
    </table>
  </div>
</body>
</html>"""

    return html
