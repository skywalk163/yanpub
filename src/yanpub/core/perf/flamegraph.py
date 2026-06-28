"""火焰图生成器 — 适配器性能分析的 HTML/SVG 可视化

核心能力：
1. FlameGraphGenerator — 火焰图 HTML/SVG 报告生成
2. HTML 辅助函数（色条、表格、热点区域、tooltip 数据）
3. _default_code — 根据适配器生成默认分析代码
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from string import Template

from yanpub.core.adapter.adapter import LanguageAdapter


# ---- HTML 辅助函数 ----


def _calc_success_rate(data: dict) -> float:
    """从 report dict 计算成功率"""
    records = data.get("records", [])
    if not records:
        return 100.0
    success = sum(1 for r in records if r.get("success", True))
    return round(success / len(records) * 100, 1)


def _assign_colors(operations: list[dict]) -> dict[str, str]:
    """为操作分配颜色

    使用色相旋转，保证视觉区分度。
    深浅反映调用层级（第一个最深，后续渐浅）。
    """
    base_hue = 15  # 橙色起点，与 yanpub 品牌色一致
    hue_step = 360 / max(len(operations), 1)
    colors: dict[str, str] = {}
    for i, op in enumerate(operations):
        hue = (base_hue + i * hue_step) % 360
        # 深浅交替：偶数深、奇数浅
        lightness = 45 if i % 2 == 0 else 55
        colors[op["name"]] = f"hsl({hue:.0f}, 75%, {lightness}%)"
    return colors


def _build_flame_bars(operations: list[dict], total_time: float, colors: dict[str, str]) -> str:
    """构建火焰图色条 HTML"""
    if not operations:
        return '<div style="color:#888;text-align:center;padding:20px;">无数据</div>'

    max_ms = max(op["avg_ms"] for op in operations)
    if max_ms == 0:
        max_ms = 1

    rows = []
    for op in operations:
        width_pct = op["avg_ms"] / max_ms * 100
        color = colors.get(op["name"], "#E85D3A")

        rows.append(
            f'<div class="flame-row">'
            f'<span class="flame-label">{op["name"]}</span>'
            f'<div class="flame-bar-track" data-op="{op["name"]}">'
            f'<div class="flame-bar-fill" style="width:{width_pct:.1f}%;background:{color};">'
            f'<span class="bar-text">{op["avg_ms"]:.2f} ms</span>'
            f"</div></div></div>"
        )
    return "\n".join(rows)


def _build_detail_table(operations: list[dict]) -> str:
    """构建详细统计表格 HTML"""
    if not operations:
        return '<p style="color:#888;">无数据</p>'

    rows = []
    for op in operations:
        rows.append(
            f"<tr>"
            f"<td>{op['name']}</td>"
            f"<td>{op['adapter_id']}</td>"
            f"<td>{op['avg_ms']:.2f}</td>"
            f"<td>{op['min_ms']:.2f}</td>"
            f"<td>{op['max_ms']:.2f}</td>"
            f"<td>{op['median_ms']:.2f}</td>"
            f"<td>{op['p95_ms']:.2f}</td>"
            f"<td>{op['iterations']}</td>"
            f"<td>{op['success_rate']}%</td>"
            f"</tr>"
        )

    return f"""
<table class="hotspot-table">
<thead>
<tr>
<th>操作</th><th>适配器</th><th>平均(ms)</th><th>最小(ms)</th>
<th>最大(ms)</th><th>中位数(ms)</th><th>P95(ms)</th><th>迭代</th><th>成功率</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def _build_hotspot_section(report: dict) -> str:
    """构建热点分析 HTML 区域"""
    # 延迟导入避免循环依赖
    from yanpub.core.perf.profiler import (
        HotspotDetector,
        ProfileRecord,
        _build_report,
    )

    # 从 dict 还原 ProfileReport 用于热点检测
    reports: dict = {}
    for op_name, data in report.items():
        records = []
        for r in data.get("records", []):
            records.append(
                ProfileRecord(
                    name=r.get("name", op_name),
                    adapter_id=r.get("adapter_id", ""),
                    duration_ms=r.get("duration_ms", 0),
                    timestamp=r.get("timestamp", 0),
                    metadata=r.get("metadata", {}),
                    success=r.get("success", True),
                )
            )
        reports[op_name] = _build_report(op_name, data.get("adapter_id", ""), records)

    detector = HotspotDetector()
    hotspots = detector.analyze(reports)

    if not hotspots:
        return ""

    rows = []
    for h in hotspots:
        cls = f"severity-{h.severity}"
        rows.append(
            f"<tr>"
            f"<td class='{cls}'>{h.severity.upper()}</td>"
            f"<td>{h.operation}</td>"
            f"<td>{h.avg_ms:.2f} ms</td>"
            f"<td>{h.suggestion}</td>"
            f"</tr>"
        )

    return f"""
<h2>热点分析</h2>
<div class="chart-container">
<table class="hotspot-table">
<thead>
<tr><th>等级</th><th>操作</th><th>平均耗时</th><th>优化建议</th></tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
</div>"""


def _build_tip_data(operations: list[dict]) -> str:
    """构建 tooltip 数据 JSON"""
    data = {}
    for op in operations:
        data[op["name"]] = {
            "adapter_id": op.get("adapter_id", ""),
            "avg_ms": op.get("avg_ms", 0),
            "min_ms": op.get("min_ms", 0),
            "max_ms": op.get("max_ms", 0),
            "median_ms": op.get("median_ms", 0),
            "p95_ms": op.get("p95_ms", 0),
            "iterations": op.get("iterations", 0),
            "success_rate": op.get("success_rate", 100),
        }
    return json.dumps(data, ensure_ascii=False)


# ---- 默认示例代码生成 ----


def _default_code(adapter: LanguageAdapter) -> str:
    """根据适配器生成默认分析代码（优先从模板文件读取）"""
    from yanpub.playground.server import _TEMPLATES_DIR

    template_file = _TEMPLATES_DIR / adapter.id / "default.txt"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    return '打印("你好，世界！")'


# ---- 火焰图生成器 ----


class FlameGraphGenerator:
    """火焰图生成器

    生成 HTML 或 SVG 格式的火焰图，直观展示各操作的时间占比。
    使用 string.Template 避免 JS 花括号与 Python f-string 冲突。
    """

    @staticmethod
    def generate_html(report: dict) -> str:
        """生成火焰图 HTML 报告

        Args:
            report: 多个操作的 ProfileReport.to_dict() 汇总
                    如: {"eval": {...}, "tokenize": {...}, ...}

        Returns:
            完整 HTML 字符串
        """
        # 准备数据
        operations: list[dict] = []
        total_time = 0.0
        slowest_op = ""
        slowest_ms = 0.0

        for op_name, data in report.items():
            avg_ms = data.get("avg_ms", 0)
            operations.append(
                {
                    "name": op_name,
                    "avg_ms": avg_ms,
                    "min_ms": data.get("min_ms", 0),
                    "max_ms": data.get("max_ms", 0),
                    "median_ms": data.get("median_ms", 0),
                    "p95_ms": data.get("p95_ms", 0),
                    "iterations": data.get("iterations", 0),
                    "adapter_id": data.get("adapter_id", ""),
                    "success_rate": _calc_success_rate(data),
                }
            )
            total_time += avg_ms
            if avg_ms > slowest_ms:
                slowest_ms = avg_ms
                slowest_op = op_name

        overall_avg = total_time / len(operations) if operations else 0

        # 色板：每个操作分配不同色相
        colors = _assign_colors(operations)

        # 使用 string.Template 避免与 JS 的 {} 冲突
        tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${title}</title>
<style>
:root {
    --bg: #1a1a2e;
    --card-bg: #16213e;
    --text: #e0e0e0;
    --text-dim: #888;
    --border: #2a2a4a;
    --primary: #E85D3A;
    --success: #4CAF50;
    --warning: #FF9800;
    --error: #f44336;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 20px;
}
h1 { font-size: 24px; margin-bottom: 20px; color: var(--primary); }
h2 { font-size: 18px; margin: 20px 0 10px; color: var(--text); }
.cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
}
.card {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
}
.card h3 { font-size: 13px; color: var(--text-dim); margin-bottom: 6px; }
.card .value { font-size: 24px; font-weight: bold; }
.card .value.good { color: var(--success); }
.card .value.warn { color: var(--warning); }
.card .value.bad { color: var(--error); }
.chart-container {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
    overflow-x: auto;
}
.flame-row {
    display: flex;
    align-items: center;
    margin-bottom: 6px;
}
.flame-label {
    width: 100px;
    font-size: 13px;
    text-align: right;
    flex-shrink: 0;
    margin-right: 10px;
    cursor: default;
}
.flame-bar-track {
    flex: 1;
    height: 36px;
    background: #0d1b2a;
    border-radius: 4px;
    position: relative;
    overflow: hidden;
    cursor: pointer;
}
.flame-bar-fill {
    height: 100%;
    border-radius: 4px;
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-size: 12px;
    color: #fff;
    white-space: nowrap;
    transition: width 0.5s;
    position: relative;
}
.flame-bar-fill:hover {
    filter: brightness(1.2);
}
.flame-bar-fill .bar-text {
    text-shadow: 0 1px 2px rgba(0,0,0,0.6);
}
.tooltip {
    display: none;
    position: fixed;
    background: #2a2a4a;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 12px;
    z-index: 100;
    pointer-events: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    max-width: 320px;
}
.tooltip .tip-title {
    font-weight: bold;
    font-size: 14px;
    margin-bottom: 6px;
}
.tooltip .tip-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
}
.tooltip .tip-label { color: var(--text-dim); }
.tooltip .tip-value { color: var(--text); font-weight: bold; }
.hotspot-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.hotspot-table th, .hotspot-table td {
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}
.hotspot-table th { color: var(--text-dim); font-weight: normal; }
.severity-critical { color: var(--error); font-weight: bold; }
.severity-warning { color: var(--warning); font-weight: bold; }
.severity-normal { color: var(--success); }
footer {
    margin-top: 20px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-dim);
}
</style>
</head>
<body>
<h1>${title}</h1>

<div class="cards">
    <div class="card">
        <h3>分析操作数</h3>
        <div class="value good">${op_count}</div>
    </div>
    <div class="card">
        <h3>总平均耗时</h3>
        <div class="value ${avg_cls}">${overall_avg} ms</div>
    </div>
    <div class="card">
        <h3>最慢操作</h3>
        <div class="value warn">${slowest_op}</div>
    </div>
    <div class="card">
        <h3>最慢耗时</h3>
        <div class="value ${slowest_cls}">${slowest_ms} ms</div>
    </div>
</div>

<h2>火焰图</h2>
<div class="chart-container">
    ${flame_bars}
</div>

<h2>详细统计</h2>
<div class="chart-container">
    ${detail_table}
</div>

${hotspot_section}

<div class="tooltip" id="tooltip">
    <div class="tip-title" id="tip-title"></div>
    <div id="tip-body"></div>
</div>

<script>
var tipData = ${tip_data_json};

var tooltip = document.getElementById('tooltip');
var tipTitle = document.getElementById('tip-title');
var tipBody = document.getElementById('tip-body');

document.querySelectorAll('.flame-bar-track').forEach(function(el) {
    el.addEventListener('mouseenter', function(e) {
        var op = el.getAttribute('data-op');
        var d = tipData[op];
        if (!d) return;
        tipTitle.textContent = op;
        tipBody.innerHTML =
            '<div class="tip-row"><span class="tip-label">适配器</span><span class="tip-value">' + d.adapter_id + '</span></div>' +
            '<div class="tip-row"><span class="tip-label">平均</span><span class="tip-value">' + d.avg_ms.toFixed(2) + ' ms</span></div>' +
            '<div class="tip-row"><span class="tip-label">最小</span><span class="tip-value">' + d.min_ms.toFixed(2) + ' ms</span></div>' +
            '<div class="tip-row"><span class="tip-label">最大</span><span class="tip-value">' + d.max_ms.toFixed(2) + ' ms</span></div>' +
            '<div class="tip-row"><span class="tip-label">中位数</span><span class="tip-value">' + d.median_ms.toFixed(2) + ' ms</span></div>' +
            '<div class="tip-row"><span class="tip-label">P95</span><span class="tip-value">' + d.p95_ms.toFixed(2) + ' ms</span></div>' +
            '<div class="tip-row"><span class="tip-label">迭代</span><span class="tip-value">' + d.iterations + '</span></div>' +
            '<div class="tip-row"><span class="tip-label">成功率</span><span class="tip-value">' + d.success_rate + '%</span></div>';
        tooltip.style.display = 'block';
    });
    el.addEventListener('mousemove', function(e) {
        tooltip.style.left = (e.clientX + 12) + 'px';
        tooltip.style.top = (e.clientY + 12) + 'px';
    });
    el.addEventListener('mouseleave', function() {
        tooltip.style.display = 'none';
    });
});
</script>

<footer>
生成时间: ${gen_time} | 言埠 YanPub 性能分析器
</footer>
</body>
</html>""")

        # 构建替换变量
        avg_cls = "good" if overall_avg < 500 else ("warn" if overall_avg < 1000 else "bad")
        slowest_cls = "good" if slowest_ms < 500 else ("warn" if slowest_ms < 1000 else "bad")

        flame_bars_html = _build_flame_bars(operations, total_time, colors)
        detail_table_html = _build_detail_table(operations)
        hotspot_html = _build_hotspot_section(report)
        tip_data_json = _build_tip_data(operations)

        return tpl.substitute(
            title="言埠 YanPub 性能分析器",
            op_count=str(len(operations)),
            overall_avg=f"{overall_avg:.2f}",
            avg_cls=avg_cls,
            slowest_op=slowest_op,
            slowest_ms=f"{slowest_ms:.2f}",
            slowest_cls=slowest_cls,
            flame_bars=flame_bars_html,
            detail_table=detail_table_html,
            hotspot_section=hotspot_html,
            tip_data_json=tip_data_json,
            gen_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    @staticmethod
    def generate_svg(report: dict) -> str:
        """生成简化版 SVG 火焰图

        Args:
            report: 同 generate_html 的 report 参数

        Returns:
            SVG 字符串
        """
        operations: list[dict] = []
        max_ms = 0.0
        for op_name, data in report.items():
            avg_ms = data.get("avg_ms", 0)
            operations.append(
                {
                    "name": op_name,
                    "avg_ms": avg_ms,
                    "adapter_id": data.get("adapter_id", ""),
                }
            )
            if avg_ms > max_ms:
                max_ms = avg_ms

        if not operations:
            return '<svg xmlns="http://www.w3.org/2000/svg"><text x="10" y="20" fill="#888">无数据</text></svg>'

        # 按平均耗时降序排列
        operations.sort(key=lambda x: x["avg_ms"], reverse=True)

        bar_height = 36
        gap = 6
        label_width = 100
        chart_width = 600
        margin_left = label_width + 10
        margin_right = 20
        bar_max_width = chart_width - margin_left - margin_right

        total_height = len(operations) * (bar_height + gap) + 40

        colors = _assign_colors(operations)

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{chart_width}" height="{total_height}" '
            f'viewBox="0 0 {chart_width} {total_height}">',
            f'<rect width="{chart_width}" height="{total_height}" fill="#1a1a2e"/>',
        ]

        for i, op in enumerate(operations):
            y = 20 + i * (bar_height + gap)
            width = (op["avg_ms"] / max_ms * bar_max_width) if max_ms > 0 else 0
            color = colors.get(op["name"], "#E85D3A")

            # 标签
            svg_parts.append(
                f'<text x="{label_width}" y="{y + bar_height / 2 + 4}" '
                f'fill="#e0e0e0" text-anchor="end" font-size="12" '
                f'font-family="Microsoft YaHei, sans-serif">{op["name"]}</text>'
            )
            # 色块
            svg_parts.append(
                f'<rect x="{margin_left}" y="{y}" width="{width:.1f}" height="{bar_height}" '
                f'fill="{color}" rx="4"/>'
            )
            # 数值标签
            svg_parts.append(
                f'<text x="{margin_left + width + 6:.1f}" y="{y + bar_height / 2 + 4}" '
                f'fill="#888" font-size="11" font-family="Consolas, monospace">'
                f"{op['avg_ms']:.1f}ms</text>"
            )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    @staticmethod
    def save_html(
        report: dict,
        output_path: str = "profile_report.html",
    ) -> Path:
        """生成并保存火焰图 HTML 报告"""
        html = FlameGraphGenerator.generate_html(report)
        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return path

    @staticmethod
    def save_svg(
        report: dict,
        output_path: str = "profile_report.svg",
    ) -> Path:
        """生成并保存火焰图 SVG 报告"""
        svg = FlameGraphGenerator.generate_svg(report)
        path = Path(output_path)
        path.write_text(svg, encoding="utf-8")
        return path
