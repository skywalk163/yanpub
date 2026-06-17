"""适配器性能调优面板 — 基准测试结果可视化 + 回归检测

核心能力：
1. BenchVisualizer — 生成可视化 HTML 报告（柱状图 + 雷达图 + 对比表）
2. BenchHistory — 历史基准数据存储与对比
3. RegressionDetector — 性能回归自动检测
4. BenchComparator — 多适配器性能对比分析

命令:
  yanpub bench-visualize          — 生成交互式可视化 HTML 报告
  yanpub bench-regress            — 检测性能回归
  yanpub bench-history            — 查看历史基准数据
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.core.benchmark import run_all_benchmarks, AdapterBenchResult
from yanpub.core.registry import LanguageRegistry


# ---- 历史数据存储 ----

BENCH_HISTORY_DIR = Path.home() / ".yanpub" / "bench_history"


@dataclass
class BenchSnapshot:
    """单次基准测试快照"""
    timestamp: str
    adapter_id: str
    adapter_name: str
    results: dict  # adapter_id → AdapterBenchResult.to_dict()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BenchSnapshot":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class BenchHistory:
    """基准测试历史管理

    存储格式: ~/.yanpub/bench_history/YYYY-MM-DD.json
    """

    def __init__(self, history_dir: Optional[Path] = None):
        self._dir = history_dir or BENCH_HISTORY_DIR

    def save(self, results: list[AdapterBenchResult]) -> None:
        """保存基准测试结果到历史"""
        self._dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        # 同一天可能多次运行，追加时间戳
        time_str = datetime.now().strftime("%H%M%S")
        filename = f"{date_str}_{time_str}.json"

        snapshot = BenchSnapshot(
            timestamp=datetime.now().isoformat(),
            adapter_id="all",
            adapter_name="全部",
            results={r.adapter_id: r.to_dict() for r in results},
        )

        filepath = self._dir / filename
        filepath.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_snapshots(self) -> list[Path]:
        """列出所有历史快照文件"""
        if not self._dir.exists():
            return []
        return sorted(self._dir.glob("*.json"))

    def load_latest(self) -> Optional[BenchSnapshot]:
        """加载最新快照"""
        snapshots = self.list_snapshots()
        if not snapshots:
            return None
        return self._load_snapshot(snapshots[-1])

    def load_previous(self) -> Optional[BenchSnapshot]:
        """加载上一次快照"""
        snapshots = self.list_snapshots()
        if len(snapshots) < 2:
            return None
        return self._load_snapshot(snapshots[-2])

    def load_by_date(self, date_str: str) -> Optional[BenchSnapshot]:
        """按日期加载快照"""
        matches = list(self._dir.glob(f"{date_str}_*.json"))
        if not matches:
            return None
        return self._load_snapshot(sorted(matches)[-1])

    def _load_snapshot(self, path: Path) -> BenchSnapshot:
        data = json.loads(path.read_text(encoding="utf-8"))
        return BenchSnapshot.from_dict(data)


# ---- 回归检测 ----

@dataclass
class RegressionInfo:
    """性能回归信息"""
    adapter_id: str
    adapter_name: str
    bench_name: str
    previous_ms: float
    current_ms: float
    change_pct: float
    is_regression: bool  # True 表示性能下降

    def to_dict(self) -> dict:
        return asdict(self)


REGRESSION_THRESHOLD = 0.20  # 性能下降 20% 以上视为回归


class RegressionDetector:
    """性能回归检测器

    比较当前和历史基准数据，检测显著性能下降。
    """

    def __init__(self, threshold: float = REGRESSION_THRESHOLD):
        self.threshold = threshold

    def detect(
        self,
        current: list[AdapterBenchResult],
        previous: Optional[BenchSnapshot],
    ) -> list[RegressionInfo]:
        """检测性能回归

        Args:
            current: 当前基准测试结果
            previous: 上一次快照（None 则无回归）

        Returns:
            回归信息列表
        """
        if previous is None:
            return []

        previous_results = previous.results
        regressions = []

        for curr in current:
            prev_data = previous_results.get(curr.adapter_id)
            if prev_data is None:
                continue

            # 比较各项基准
            for bench_name in ["startup", "keyword_load", "execution", "throughput"]:
                curr_bench = getattr(curr, bench_name, None)
                prev_bench_data = prev_data.get(bench_name)

                if curr_bench is None or prev_bench_data is None:
                    continue

                prev_mean = prev_bench_data.get("mean_ms", 0)
                curr_mean = curr_bench.mean_ms

                if prev_mean <= 0:
                    continue

                change_pct = (curr_mean - prev_mean) / prev_mean
                is_regression = change_pct > self.threshold

                regressions.append(RegressionInfo(
                    adapter_id=curr.adapter_id,
                    adapter_name=curr.adapter_name,
                    bench_name=curr_bench.name,
                    previous_ms=prev_mean,
                    current_ms=curr_mean,
                    change_pct=change_pct,
                    is_regression=is_regression,
                ))

        return regressions


# ---- 可视化 HTML 报告 ----

class BenchVisualizer:
    """基准测试可视化报告生成器

    生成一个独立的 HTML 文件，包含：
    - 各适配器执行延迟柱状图
    - 多维度雷达图对比
    - 详细数据表格
    - 性能回归警告
    """

    @staticmethod
    def generate_html(
        results: list[AdapterBenchResult],
        regressions: Optional[list[RegressionInfo]] = None,
        title: str = "言埠 YanPub 性能调优面板",
    ) -> str:
        """生成可视化 HTML 报告

        Args:
            results: 基准测试结果列表
            regressions: 回归检测结果
            title: 报告标题

        Returns:
            完整 HTML 字符串
        """
        # 准备数据
        chart_data = _prepare_chart_data(results)
        radar_data = _prepare_radar_data(results)
        regression_html = _format_regressions_html(regressions or [])

        # 生成 HTML
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root {{
    --bg: #1a1a2e;
    --card-bg: #16213e;
    --text: #e0e0e0;
    --text-dim: #888;
    --border: #2a2a4a;
    --primary: #E85D3A;
    --success: #4CAF50;
    --warning: #FF9800;
    --error: #f44336;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 20px;
}}
h1 {{ font-size: 24px; margin-bottom: 20px; color: var(--primary); }}
h2 {{ font-size: 18px; margin: 20px 0 10px; color: var(--text); }}
.cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
}}
.card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
}}
.card h3 {{
    font-size: 14px;
    color: var(--text-dim);
    margin-bottom: 8px;
}}
.card .value {{
    font-size: 28px;
    font-weight: bold;
}}
.card .value.good {{ color: var(--success); }}
.card .value.warn {{ color: var(--warning); }}
.card .value.bad {{ color: var(--error); }}
.chart-container {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
}}
.bar-chart {{
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.bar-row {{
    display: flex;
    align-items: center;
    gap: 8px;
}}
.bar-label {{
    width: 80px;
    font-size: 13px;
    text-align: right;
    flex-shrink: 0;
}}
.bar-track {{
    flex: 1;
    height: 24px;
    background: #0d1b2a;
    border-radius: 4px;
    position: relative;
    overflow: hidden;
}}
.bar-fill {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s;
    display: flex;
    align-items: center;
    padding-left: 8px;
    font-size: 11px;
    white-space: nowrap;
}}
.radar-container {{
    display: flex;
    justify-content: center;
    padding: 20px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
th, td {{
    padding: 8px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}}
th {{
    color: var(--text-dim);
    font-weight: normal;
}}
.regression-alert {{
    background: #2a1a1a;
    border: 1px solid var(--error);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 20px;
}}
.regression-alert h3 {{ color: var(--error); margin-bottom: 8px; }}
.regression-item {{ padding: 4px 0; color: var(--warning); }}
footer {{
    margin-top: 20px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-dim);
}}
</style>
</head>
<body>
<h1>{title}</h1>
{regression_html}
<div class="cards">
{_generate_summary_cards(results)}
</div>

<h2>执行延迟对比</h2>
<div class="chart-container">
<div class="bar-chart">
{_generate_bar_chart(chart_data)}
</div>
</div>

<h2>多维性能雷达</h2>
<div class="chart-container">
<div class="radar-container">
<svg width="400" height="400" viewBox="0 0 400 400">
{_generate_radar_svg(radar_data)}
</svg>
</div>
</div>

<h2>详细数据</h2>
<div class="chart-container">
{_generate_detail_table(results)}
</div>

<footer>
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
言埠 YanPub 性能调优面板
</footer>
</body>
</html>"""
        return html

    @staticmethod
    def save_html(
        results: list[AdapterBenchResult],
        output_path: str = "bench_report.html",
        regressions: Optional[list[RegressionInfo]] = None,
    ) -> Path:
        """生成并保存可视化 HTML 报告"""
        html = BenchVisualizer.generate_html(results, regressions)
        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return path


# ---- HTML 生成辅助函数 ----

def _prepare_chart_data(results: list[AdapterBenchResult]) -> dict:
    """准备柱状图数据"""
    data = {}
    for r in results:
        if r.execution:
            data[r.adapter_name] = r.execution.mean_ms
    return data


def _prepare_radar_data(results: list[AdapterBenchResult]) -> list[dict]:
    """准备雷达图数据"""
    data = []
    for r in results:
        axes = {}
        # 归一化到 0-100 分（越低越好 → 越高分越好）
        if r.startup:
            axes["启动"] = max(0, 100 - r.startup.mean_ms)
        if r.keyword_load:
            axes["关键字"] = max(0, 100 - r.keyword_load.mean_ms)
        if r.execution:
            axes["执行"] = max(0, 100 - r.execution.mean_ms / 10)
        if r.throughput:
            axes["吞吐"] = max(0, 100 - r.throughput.mean_ms / 10)
        data.append({"name": r.adapter_name, "axes": axes})
    return data


def _generate_summary_cards(results: list[AdapterBenchResult]) -> str:
    """生成概要卡片"""
    cards = []

    # 总适配器数
    cards.append(f'<div class="card"><h3>适配器数量</h3><div class="value good">{len(results)}</div></div>')

    # 平均执行延迟
    exec_means = [r.execution.mean_ms for r in results if r.execution]
    if exec_means:
        avg = statistics.mean(exec_means)
        cls = "good" if avg < 500 else ("warn" if avg < 2000 else "bad")
        cards.append(f'<div class="card"><h3>平均执行延迟</h3><div class="value {cls}">{avg:.0f}ms</div></div>')

    # 最快适配器
    if results:
        fastest = min(results, key=lambda r: r.execution.mean_ms if r.execution else float("inf"))
        cards.append(f'<div class="card"><h3>最快适配器</h3><div class="value good">{fastest.adapter_name}</div></div>')

    # 最慢适配器
    if results:
        slowest = max(results, key=lambda r: r.execution.mean_ms if r.execution else 0)
        cards.append(f'<div class="card"><h3>最慢适配器</h3><div class="value warn">{slowest.adapter_name}</div></div>')

    return "\n".join(cards)


def _generate_bar_chart(data: dict) -> str:
    """生成柱状图 HTML"""
    if not data:
        return '<div style="color:#888;text-align:center;padding:20px;">无数据</div>'

    max_val = max(data.values()) if data else 1
    rows = []
    for name, value in sorted(data.items(), key=lambda x: x[1]):
        width_pct = (value / max_val * 100) if max_val > 0 else 0
        color = "#4CAF50" if value < 500 else ("#FF9800" if value < 2000 else "#f44336")
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{name}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-fill" style="width:{width_pct:.1f}%;background:{color};">{value:.0f}ms</div>'
            f'</div></div>'
        )
    return "\n".join(rows)


def _generate_radar_svg(data: list[dict]) -> str:
    """生成雷达图 SVG"""
    if not data:
        return '<text x="200" y="200" fill="#888" text-anchor="middle">无数据</text>'

    # 取所有轴名称
    all_axes = []
    for d in data:
        for axis in d["axes"]:
            if axis not in all_axes:
                all_axes.append(axis)

    if len(all_axes) < 3:
        return '<text x="200" y="200" fill="#888" text-anchor="middle">维度不足3个</text>'

    cx, cy, r = 200, 200, 150
    n = len(all_axes)
    colors = ["#E85D3A", "#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5"]

    svg_parts = []

    # 绘制网格
    for level in [0.25, 0.5, 0.75, 1.0]:
        points = []
        for i in range(n):
            angle = 2 * 3.14159 * i / n - 3.14159 / 2
            x = cx + r * level * __import__("math").cos(angle)
            y = cy + r * level * __import__("math").sin(angle)
            points.append(f"{x:.1f},{y:.1f}")
        svg_parts.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="#2a2a4a" stroke-width="1"/>')

    # 绘制轴线和标签
    for i, axis in enumerate(all_axes):
        angle = 2 * 3.14159 * i / n - 3.14159 / 2
        x = cx + r * __import__("math").cos(angle)
        y = cy + r * __import__("math").sin(angle)
        svg_parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#2a2a4a" stroke-width="1"/>')
        # 标签
        lx = cx + (r + 20) * __import__("math").cos(angle)
        ly = cy + (r + 20) * __import__("math").sin(angle)
        svg_parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" fill="#888" text-anchor="middle" font-size="12">{axis}</text>')

    # 绘制数据多边形
    for idx, d in enumerate(data):
        color = colors[idx % len(colors)]
        points = []
        for i, axis in enumerate(all_axes):
            value = d["axes"].get(axis, 0) / 100  # 归一化到 0-1
            angle = 2 * 3.14159 * i / n - 3.14159 / 2
            x = cx + r * value * __import__("math").cos(angle)
            y = cy + r * value * __import__("math").sin(angle)
            points.append(f"{x:.1f},{y:.1f}")
        svg_parts.append(
            f'<polygon points="{" ".join(points)}" fill="{color}" fill-opacity="0.2" '
            f'stroke="{color}" stroke-width="2"/>'
        )
        # 图例
        legend_y = 20 + idx * 16
        svg_parts.append(
            f'<rect x="320" y="{legend_y - 8}" width="10" height="10" fill="{color}"/>'
            f'<text x="335" y="{legend_y}" fill="#ccc" font-size="10">{d["name"]}</text>'
        )

    return "\n".join(svg_parts)


def _generate_detail_table(results: list[AdapterBenchResult]) -> str:
    """生成详细数据表格"""
    if not results:
        return '<p style="color:#888;">无数据</p>'

    rows = []
    for r in results:
        exec_mean = f"{r.execution.mean_ms:.2f}" if r.execution else "-"
        exec_stdev = f"{r.execution.stdev_ms:.2f}" if r.execution else "-"
        startup = f"{r.startup.mean_ms:.2f}" if r.startup else "-"
        kw_load = f"{r.keyword_load.mean_ms:.2f}" if r.keyword_load else "-"
        throughput = f"{r.throughput.mean_ms:.2f}" if r.throughput else "-"

        rows.append(
            f"<tr>"
            f"<td>{r.adapter_name}</td>"
            f"<td>{r.adapter_id}</td>"
            f"<td>{startup}</td>"
            f"<td>{kw_load}</td>"
            f"<td>{exec_mean}</td>"
            f"<td>{exec_stdev}</td>"
            f"<td>{throughput}</td>"
            f"</tr>"
        )

    return f"""
<table>
<thead>
<tr>
<th>语言</th><th>ID</th><th>启动(ms)</th><th>关键字(ms)</th>
<th>执行均值(ms)</th><th>执行标准差(ms)</th><th>吞吐(ms)</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def _format_regressions_html(regressions: list[RegressionInfo]) -> str:
    """格式化回归警告 HTML"""
    actual = [r for r in regressions if r.is_regression]
    if not actual:
        return ""

    items = []
    for r in actual:
        items.append(
            f'<div class="regression-item">'
            f'⚠ {r.adapter_name} — {r.bench_name}: '
            f'{r.previous_ms:.1f}ms → {r.current_ms:.1f}ms '
            f'(+{r.change_pct:.0%})'
            f'</div>'
        )

    return f"""
<div class="regression-alert">
<h3>💥 检测到 {len(actual)} 个性能回归</h3>
{"".join(items)}
</div>"""


def run_bench_with_regression(
    registry: LanguageRegistry,
    lang_id: str | None = None,
    iterations: int = 5,
) -> tuple[list[AdapterBenchResult], list[RegressionInfo]]:
    """运行基准测试并检测回归

    Returns:
        (基准结果列表, 回归信息列表)
    """
    # 运行基准测试
    results = run_all_benchmarks(registry, iterations=iterations, lang_id=lang_id)

    # 保存历史
    history = BenchHistory()
    history.save(results)

    # 加载上一次快照进行对比
    previous = history.load_previous()

    # 检测回归
    detector = RegressionDetector()
    regressions = detector.detect(results, previous)

    return results, regressions
