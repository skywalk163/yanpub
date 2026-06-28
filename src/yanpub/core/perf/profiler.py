"""适配器性能分析器 — 定位中文编程语言适配器的执行热点

核心能力：
1. ProfileRecord — 性能记录数据类
2. AdapterProfiler — 适配器性能分析器（eval/run/tokenize/complete）
3. ProfileReport — 性能分析报告（百分位统计 + 文本表格）
4. HotspotDetector — 热点检测器（critical/warning/normal 三级判定）

火焰图相关已拆分到 yanpub.core.perf.flamegraph：
  FlameGraphGenerator, _default_code, _build_flame_bars, _build_detail_table,
  _build_hotspot_section, _build_tip_data, _assign_colors, _calc_success_rate

命令:
  yanpub adapter profile <lang_id>  — 性能分析适配器
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import TYPE_CHECKING

from yanpub.core.adapter.adapter import LanguageAdapter

if TYPE_CHECKING:
    from yanpub.core.perf.flamegraph import FlameGraphGenerator as FlameGraphGenerator

__all__ = [
    "ProfileRecord",
    "ProfileReport",
    "AdapterProfiler",
    "Hotspot",
    "HotspotDetector",
    "HOTSPOT_CRITICAL_MS",
    "HOTSPOT_WARNING_MS",
    "FlameGraphGenerator",
    "_default_code",
]


# ---- 延迟 re-export 避免循环依赖 ----


def __getattr__(name: str):
    """从 flamegraph 子模块延迟 re-export，保持向后兼容"""
    _reexports = {
        "FlameGraphGenerator",
        "_default_code",
        "_build_flame_bars",
        "_build_detail_table",
        "_build_hotspot_section",
        "_build_tip_data",
        "_assign_colors",
        "_calc_success_rate",
    }
    if name in _reexports:
        from yanpub.core.perf import flamegraph

        return getattr(flamegraph, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---- 性能记录 ----


@dataclass
class ProfileRecord:
    """性能记录数据类"""

    name: str  # 操作名称: "eval", "run", "tokenize", "complete"
    adapter_id: str
    duration_ms: float
    timestamp: float
    metadata: dict = field(default_factory=dict)  # 额外信息（代码长度、输出大小等）
    success: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ---- 性能分析报告 ----


@dataclass
class ProfileReport:
    """性能分析报告"""

    name: str
    adapter_id: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    median_ms: float
    p95_ms: float
    records: list[ProfileRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "adapter_id": self.adapter_id,
            "iterations": self.iterations,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "records": [r.to_dict() for r in self.records],
        }

    def to_table(self) -> str:
        """生成文本表格"""
        success_count = sum(1 for r in self.records if r.success)
        fail_count = self.iterations - success_count

        lines = [
            "┌─────────────────────────────────────────────┐",
            f"│ {self.name:<12s} ({self.adapter_id})",
            "├─────────────────────────────────────────────┤",
            f"│ 迭代次数   {self.iterations:>10d}",
            f"│ 成功/失败   {success_count:>4d}/{fail_count:<4d}",
            f"│ 总耗时     {self.total_ms:>10.2f} ms",
            f"│ 平均耗时   {self.avg_ms:>10.2f} ms",
            f"│ 最小耗时   {self.min_ms:>10.2f} ms",
            f"│ 最大耗时   {self.max_ms:>10.2f} ms",
            f"│ 中位数     {self.median_ms:>10.2f} ms",
            f"│ P95        {self.p95_ms:>10.2f} ms",
            "└─────────────────────────────────────────────┘",
        ]
        return "\n".join(lines)


# ---- 百分位计算 ----


def _percentile(sorted_values: list[float], pct: float) -> float:
    """计算百分位数

    Args:
        sorted_values: 已排序的数值列表
        pct: 百分位（0-100）

    Returns:
        百分位值
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    # 线性插值法
    rank = pct / 100.0 * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    frac = rank - lower
    return sorted_values[lower] + frac * (sorted_values[upper] - sorted_values[lower])


def _build_report(name: str, adapter_id: str, records: list[ProfileRecord]) -> ProfileReport:
    """从记录列表构建 ProfileReport"""
    durations = sorted([r.duration_ms for r in records])
    total = sum(durations)
    avg = total / len(durations) if durations else 0.0

    return ProfileReport(
        name=name,
        adapter_id=adapter_id,
        iterations=len(records),
        total_ms=total,
        avg_ms=avg,
        min_ms=durations[0] if durations else 0.0,
        max_ms=durations[-1] if durations else 0.0,
        median_ms=_percentile(durations, 50),
        p95_ms=_percentile(durations, 95),
        records=records,
    )


# ---- 适配器性能分析器 ----


class AdapterProfiler:
    """适配器性能分析器

    绑定一个 LanguageAdapter，对各操作进行多次迭代计时，
    生成 ProfileReport 报告。
    """

    def __init__(self, adapter: LanguageAdapter):
        self.adapter = adapter

    def profile_eval(self, code: str, iterations: int = 1) -> ProfileReport:
        """分析 eval 执行"""
        records: list[ProfileRecord] = []
        for _ in range(iterations):
            ts = time.perf_counter()
            try:
                result = self.adapter.eval(code)
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="eval",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={
                            "code_length": len(code),
                            "output_length": len(result.stdout),
                        },
                        success=result.success,
                    )
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="eval",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={"code_length": len(code), "error": str(e)},
                        success=False,
                    )
                )
        return _build_report("eval", self.adapter.id, records)

    def profile_run(self, file_path: str, iterations: int = 1) -> ProfileReport:
        """分析 run 执行"""
        records: list[ProfileRecord] = []
        for _ in range(iterations):
            ts = time.perf_counter()
            try:
                result = self.adapter.run(file_path)
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="run",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={
                            "file_path": file_path,
                            "output_length": len(result.stdout),
                        },
                        success=result.success,
                    )
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="run",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={"file_path": file_path, "error": str(e)},
                        success=False,
                    )
                )
        return _build_report("run", self.adapter.id, records)

    def profile_tokenize(self, code: str, iterations: int = 1) -> ProfileReport:
        """分析 tokenize 执行"""
        records: list[ProfileRecord] = []
        for _ in range(iterations):
            ts = time.perf_counter()
            try:
                tokens = self.adapter.tokenize(code)
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="tokenize",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={
                            "code_length": len(code),
                            "token_count": len(tokens),
                        },
                        success=True,
                    )
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="tokenize",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={"code_length": len(code), "error": str(e)},
                        success=False,
                    )
                )
        return _build_report("tokenize", self.adapter.id, records)

    def profile_complete(
        self, code: str, line: int, col: int, iterations: int = 1
    ) -> ProfileReport:
        """分析补全执行"""
        records: list[ProfileRecord] = []
        for _ in range(iterations):
            ts = time.perf_counter()
            try:
                items = self.adapter.complete(code, line, col)
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="complete",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={
                            "code_length": len(code),
                            "completion_count": len(items),
                        },
                        success=True,
                    )
                )
            except Exception as e:
                duration_ms = (time.perf_counter() - ts) * 1000
                records.append(
                    ProfileRecord(
                        name="complete",
                        adapter_id=self.adapter.id,
                        duration_ms=duration_ms,
                        timestamp=ts,
                        metadata={"code_length": len(code), "error": str(e)},
                        success=False,
                    )
                )
        return _build_report("complete", self.adapter.id, records)

    def profile_all(self, code: str, iterations: int = 1) -> dict[str, ProfileReport]:
        """分析所有操作"""
        reports: dict[str, ProfileReport] = {}

        # eval 和 tokenize 不依赖文件
        reports["eval"] = self.profile_eval(code, iterations)
        reports["tokenize"] = self.profile_tokenize(code, iterations)

        # complete 在代码中间行位置测试
        lines = code.split("\n")
        line = max(1, len(lines))
        col = 1
        reports["complete"] = self.profile_complete(code, line, col, iterations)

        return reports


# ---- 热点检测 ----


@dataclass
class Hotspot:
    """热点信息"""

    operation: str
    adapter_id: str
    avg_ms: float
    severity: str  # "critical" | "warning" | "normal"
    suggestion: str

    def to_dict(self) -> dict:
        return asdict(self)


# 热点判定阈值
HOTSPOT_CRITICAL_MS = 1000.0
HOTSPOT_WARNING_MS = 500.0

# 操作优化建议
_SUGGESTIONS: dict[str, str] = {
    "eval": "检查语言后端启动时间，考虑预热（如常驻进程模式）",
    "run": "检查语言后端启动时间，考虑预热或缓存编译结果",
    "tokenize": "实现缓存或简化词法分析，避免重复解析",
    "complete": "减少关键字数量或实现增量补全，避免全量扫描",
}


class HotspotDetector:
    """热点检测器

    分析 ProfileReport，判定操作性能等级并提供优化建议。
    """

    def analyze(self, reports: dict[str, ProfileReport]) -> list[Hotspot]:
        """分析热点

        Args:
            reports: 操作名 → ProfileReport

        Returns:
            热点列表，按严重程度排序（critical > warning > normal）
        """
        hotspots: list[Hotspot] = []
        for op_name, report in reports.items():
            avg = report.avg_ms
            if avg > HOTSPOT_CRITICAL_MS:
                severity = "critical"
            elif avg > HOTSPOT_WARNING_MS:
                severity = "warning"
            else:
                severity = "normal"

            suggestion = _SUGGESTIONS.get(op_name, "检查适配器实现，考虑优化热点路径")

            hotspots.append(
                Hotspot(
                    operation=op_name,
                    adapter_id=report.adapter_id,
                    avg_ms=avg,
                    severity=severity,
                    suggestion=suggestion,
                )
            )

        # 按严重程度排序: critical > warning > normal，同级别按 avg_ms 降序
        severity_order = {"critical": 0, "warning": 1, "normal": 2}
        hotspots.sort(key=lambda h: (severity_order.get(h.severity, 9), -h.avg_ms))
        return hotspots
