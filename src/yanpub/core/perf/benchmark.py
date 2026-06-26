"""性能基准测试套件 — 测量各语言适配器的性能指标

基准测试项目：
1. 启动时间（adapter 加载延迟）
2. 代码执行延迟（eval 简单代码）
3. 关键字加载时间
4. 吞吐量（多次执行的平均时间）

使用方式：
  yanpub bench           # 所有适配器
  yanpub bench duan      # 指定适配器
  yanpub bench --iterations 10  # 自定义迭代次数
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.adapter.registry import LanguageRegistry


@dataclass
class BenchResult:
    """单个基准测试结果"""

    name: str
    iterations: int = 1
    times_ms: list[float] = field(default_factory=list)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.times_ms) if self.times_ms else 0.0

    @property
    def median_ms(self) -> float:
        return statistics.median(self.times_ms) if self.times_ms else 0.0

    @property
    def stdev_ms(self) -> float:
        return statistics.stdev(self.times_ms) if len(self.times_ms) > 1 else 0.0

    @property
    def min_ms(self) -> float:
        return min(self.times_ms) if self.times_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.times_ms) if self.times_ms else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "mean_ms": round(self.mean_ms, 2),
            "median_ms": round(self.median_ms, 2),
            "stdev_ms": round(self.stdev_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


@dataclass
class AdapterBenchResult:
    """适配器完整基准测试结果"""

    adapter_id: str
    adapter_name: str
    startup: Optional[BenchResult] = None
    keyword_load: Optional[BenchResult] = None
    execution: Optional[BenchResult] = None
    throughput: Optional[BenchResult] = None

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "startup": self.startup.to_dict() if self.startup else None,
            "keyword_load": self.keyword_load.to_dict() if self.keyword_load else None,
            "execution": self.execution.to_dict() if self.execution else None,
            "throughput": self.throughput.to_dict() if self.throughput else None,
        }


def run_benchmarks(
    adapter: LanguageAdapter,
    iterations: int = 5,
    warmup: int = 1,
) -> AdapterBenchResult:
    """对单个适配器执行基准测试

    Args:
        adapter: 语言适配器
        iterations: 每项测试的迭代次数
        warmup: 预热次数（不计入结果）

    Returns:
        AdapterBenchResult 包含所有基准测试结果
    """
    result = AdapterBenchResult(
        adapter_id=adapter.id,
        adapter_name=adapter.name,
    )

    # ---- 基准1: 启动时间 ----
    result.startup = _bench_startup(adapter, iterations, warmup)

    # ---- 基准2: 关键字加载时间 ----
    result.keyword_load = _bench_keyword_load(adapter, iterations, warmup)

    # ---- 基准3: 代码执行延迟 ----
    result.execution = _bench_execution(adapter, iterations, warmup)

    # ---- 基准4: 吞吐量 ----
    result.throughput = _bench_throughput(adapter, iterations, warmup)

    return result


def _bench_startup(adapter: LanguageAdapter, iterations: int, warmup: int) -> BenchResult:
    """测量适配器启动时间（创建新实例的时间）"""
    bench = BenchResult(name="启动时间", iterations=iterations)

    # 预热
    for _ in range(warmup):
        _ = adapter.keywords  # 触发懒加载

    # 测量：重新创建适配器并触发关键字加载
    for _ in range(iterations):
        start = time.monotonic()
        _ = adapter.keywords  # 触发关键字加载
        elapsed = (time.monotonic() - start) * 1000
        bench.times_ms.append(elapsed)

    return bench


def _bench_keyword_load(adapter: LanguageAdapter, iterations: int, warmup: int) -> BenchResult:
    """测量关键字加载时间（访问 keywords 属性）"""
    bench = BenchResult(name="关键字加载", iterations=iterations)

    # 预热
    for _ in range(warmup):
        _ = adapter.keywords

    # 测量
    for _ in range(iterations):
        start = time.monotonic()
        kws = adapter.keywords
        _ = len(kws)  # 确保完全加载
        elapsed = (time.monotonic() - start) * 1000
        bench.times_ms.append(elapsed)

    return bench


def _bench_execution(adapter: LanguageAdapter, iterations: int, warmup: int) -> BenchResult:
    """测量代码执行延迟"""
    bench = BenchResult(name="代码执行", iterations=iterations)

    # 测试代码
    comment = adapter.comment_syntax or "#"
    test_code = f'{comment} bench test\n打印("hello")。\n'

    # 预热
    for _ in range(warmup):
        try:
            adapter.eval(test_code)
        except Exception:
            pass

    # 测量
    for _ in range(iterations):
        start = time.monotonic()
        try:
            exec_result = adapter.eval(test_code)
            elapsed = (time.monotonic() - start) * 1000
            # 只计入成功的执行
            if exec_result.exit_code >= 0 or exec_result.exit_code == -2:
                bench.times_ms.append(elapsed)
            else:
                bench.times_ms.append(elapsed)
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            bench.times_ms.append(elapsed)

    return bench


def _bench_throughput(adapter: LanguageAdapter, iterations: int, warmup: int) -> BenchResult:
    """测量吞吐量（快速连续执行多次的平均时间）"""
    bench = BenchResult(name="吞吐量", iterations=iterations)

    comment = adapter.comment_syntax or "#"
    test_code = f"{comment} throughput\n"

    # 预热
    for _ in range(warmup):
        try:
            adapter.eval(test_code)
        except Exception:
            pass

    # 测量：每次连续执行3次取总时间
    batch_size = 3
    for _ in range(iterations):
        start = time.monotonic()
        for _ in range(batch_size):
            try:
                adapter.eval(test_code)
            except Exception:
                pass
        elapsed = (time.monotonic() - start) * 1000
        bench.times_ms.append(elapsed / batch_size)  # 每次平均

    return bench


def run_all_benchmarks(
    registry: LanguageRegistry,
    iterations: int = 5,
    lang_id: str | None = None,
) -> list[AdapterBenchResult]:
    """对所有（或指定）适配器执行基准测试"""
    results = []

    if lang_id:
        adapter = registry.get(lang_id)
        if adapter is None:
            return results
        results.append(run_benchmarks(adapter, iterations))
    else:
        for adapter in registry:
            results.append(run_benchmarks(adapter, iterations))

    return results


def format_bench_report(results: list[AdapterBenchResult]) -> str:
    """格式化基准测试报告"""
    lines = []
    lines.append("性能基准测试报告")
    lines.append("=" * 60)

    for r in results:
        lines.append(f"\n{r.adapter_name} ({r.adapter_id})")
        lines.append("-" * 40)

        for bench in [r.startup, r.keyword_load, r.execution, r.throughput]:
            if bench is None:
                continue
            lines.append(
                f"  {bench.name:12s}  "
                f"均值: {bench.mean_ms:8.2f}ms  "
                f"中位: {bench.median_ms:8.2f}ms  "
                f"标准差: {bench.stdev_ms:6.2f}ms  "
                f"范围: [{bench.min_ms:.1f}, {bench.max_ms:.1f}]"
            )

    # 汇总比较表
    if len(results) > 1:
        lines.append(f"\n{'=' * 60}")
        lines.append("执行延迟比较")
        lines.append(f"{'语言':12s} {'均值(ms)':>10s} {'中位(ms)':>10s} {'最小(ms)':>10s}")
        for r in results:
            if r.execution:
                lines.append(
                    f"{r.adapter_name:12s} "
                    f"{r.execution.mean_ms:10.2f} "
                    f"{r.execution.median_ms:10.2f} "
                    f"{r.execution.min_ms:10.2f}"
                )

    return "\n".join(lines)
