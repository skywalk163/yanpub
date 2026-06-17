"""实时性能监控引擎 — 采集、存储、推送适配器性能指标

核心能力：
1. MetricSample — 单次度量样本
2. MetricSeries — 度量时间序列（滑动窗口）
3. PerformanceMonitor — 性能监控器（采集/查询/推送/趋势分析）

命令:
  yanpub monitor             — 启动性能监控仪表板
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from yanpub.core.adapter import LanguageAdapter
from yanpub.core.profiler import ProfileReport

logger = logging.getLogger("yanpub.monitor")


# ---- 度量样本 ----

@dataclass
class MetricSample:
    """单次度量样本"""

    metric: str              # 度量名称: "eval_duration", "run_duration", "tokenize_duration", "complete_duration", "memory_used", "error_rate"
    adapter_id: str
    value: float
    timestamp: float
    tags: dict = field(default_factory=dict)  # 附加标签

    def to_dict(self) -> dict:
        return asdict(self)


# ---- 度量时间序列 ----

class MetricSeries:
    """度量时间序列（滑动窗口）"""

    def __init__(self, metric: str, adapter_id: str, max_samples: int = 1000):
        self.metric = metric
        self.adapter_id = adapter_id
        self.samples: list[MetricSample] = []
        self.max_samples = max_samples

    def add(self, sample: MetricSample) -> None:
        """添加样本，超出滑动窗口时移除最旧样本"""
        self.samples.append(sample)
        if len(self.samples) > self.max_samples:
            self.samples = self.samples[-self.max_samples:]

    def latest(self) -> Optional[MetricSample]:
        """获取最新样本"""
        return self.samples[-1] if self.samples else None

    def query(self, start_time: float, end_time: float) -> list[MetricSample]:
        """按时间范围查询样本"""
        return [
            s for s in self.samples
            if start_time <= s.timestamp <= end_time
        ]

    def aggregate(self, interval_sec: float) -> list[dict]:
        """按时间窗口聚合数据

        Args:
            interval_sec: 聚合窗口大小（秒）

        Returns:
            聚合结果列表，每项包含: window_start, avg, min, max, count
        """
        if not self.samples:
            return []

        # 按时间窗口分组
        windows: dict[float, list[float]] = {}
        for s in self.samples:
            window_key = int(s.timestamp / interval_sec) * interval_sec
            if window_key not in windows:
                windows[window_key] = []
            windows[window_key].append(s.value)

        result = []
        for window_start in sorted(windows.keys()):
            values = windows[window_start]
            result.append({
                "window_start": window_start,
                "avg": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "count": len(values),
            })

        return result

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "adapter_id": self.adapter_id,
            "sample_count": len(self.samples),
            "samples": [s.to_dict() for s in self.samples[-50:]],  # 最多返回50个
        }


# ---- 性能监控器 ----

class PerformanceMonitor:
    """性能监控器 — 实时采集、存储、推送适配器性能指标

    用法:
        monitor = PerformanceMonitor()
        monitor.record(adapter, "eval", duration_ms=120.5)
        data = monitor.get_dashboard_data()
    """

    def __init__(self):
        # key = (metric, adapter_id) → MetricSeries
        self._series: dict[tuple[str, str], MetricSeries] = {}
        # WebSocket 订阅者
        self._subscribers: dict[object, Optional[str]] = {}  # websocket → adapter_id or None
        # 错误计数（用于 error_rate 计算）
        self._error_counts: dict[str, int] = {}  # adapter_id → error_count
        self._total_counts: dict[str, int] = {}  # adapter_id → total_count

    # ---- 采集 ----

    def record(
        self,
        adapter: LanguageAdapter,
        operation: str,
        duration_ms: float,
        success: bool = True,
        **tags: str,
    ) -> None:
        """记录一次操作度量

        Args:
            adapter: 语言适配器
            operation: 操作名称（eval/run/tokenize/complete）
            duration_ms: 耗时（毫秒）
            success: 是否成功
            tags: 附加标签
        """
        adapter_id = adapter.id
        now = time.time()

        # 记录操作耗时
        metric_name = f"{operation}_duration"
        series = self._get_or_create_series(metric_name, adapter_id)
        sample = MetricSample(
            metric=metric_name,
            adapter_id=adapter_id,
            value=duration_ms,
            timestamp=now,
            tags=tags,
        )
        series.add(sample)

        # 更新错误率
        if adapter_id not in self._error_counts:
            self._error_counts[adapter_id] = 0
            self._total_counts[adapter_id] = 0

        self._total_counts[adapter_id] += 1
        if not success:
            self._error_counts[adapter_id] += 1

        # 更新 error_rate 指标
        total = self._total_counts[adapter_id]
        errors = self._error_counts[adapter_id]
        error_rate = (errors / total) * 100.0 if total > 0 else 0.0

        er_series = self._get_or_create_series("error_rate", adapter_id)
        er_sample = MetricSample(
            metric="error_rate",
            adapter_id=adapter_id,
            value=error_rate,
            timestamp=now,
            tags={"total_ops": str(total), "error_ops": str(errors)},
        )
        er_series.add(er_sample)

        # 广播
        self._broadcast(sample)

    def record_profile(self, report: ProfileReport) -> None:
        """从 ProfileReport 批量记录"""
        for record in report.records:
            metric_name = f"{record.name}_duration"
            series = self._get_or_create_series(metric_name, record.adapter_id)
            sample = MetricSample(
                metric=metric_name,
                adapter_id=record.adapter_id,
                value=record.duration_ms,
                timestamp=record.timestamp,
                tags=record.metadata,
            )
            series.add(sample)

    # ---- 查询 ----

    def get_series(self, metric: str, adapter_id: str) -> Optional[MetricSeries]:
        """获取指定度量时间序列"""
        return self._series.get((metric, adapter_id))

    def get_all_metrics(self, adapter_id: str) -> dict[str, MetricSeries]:
        """获取适配器的所有度量序列"""
        result: dict[str, MetricSeries] = {}
        for (metric, aid), series in self._series.items():
            if aid == adapter_id:
                result[metric] = series
        return result

    def get_dashboard_data(self, adapter_id: str | None = None) -> dict:
        """获取仪表板数据

        Args:
            adapter_id: 适配器ID，None 表示全部

        Returns:
            仪表板数据字典
        """
        adapters_data: dict[str, dict] = {}

        for (metric, aid), series in self._series.items():
            if adapter_id is not None and aid != adapter_id:
                continue

            if aid not in adapters_data:
                adapters_data[aid] = {
                    "adapter_id": aid,
                    "metrics": {},
                }

            latest = series.latest()
            # 计算最近样本的均值
            recent_samples = series.samples[-20:] if series.samples else []
            avg = (
                sum(s.value for s in recent_samples) / len(recent_samples)
                if recent_samples else 0.0
            )

            adapters_data[aid]["metrics"][metric] = {
                "latest": latest.to_dict() if latest else None,
                "avg": round(avg, 2),
                "sample_count": len(series.samples),
            }

        # 补充错误率
        for aid, data in adapters_data.items():
            if "error_rate" not in data["metrics"]:
                total = self._total_counts.get(aid, 0)
                errors = self._error_counts.get(aid, 0)
                rate = (errors / total) * 100.0 if total > 0 else 0.0
                data["metrics"]["error_rate"] = {
                    "latest": {"value": round(rate, 2)} if total > 0 else None,
                    "avg": round(rate, 2),
                    "sample_count": total,
                }

        # 汇总信息
        all_adapter_ids = set(aid for (_, aid) in self._series.keys())
        if adapter_id:
            all_adapter_ids = {aid for aid in all_adapter_ids if aid == adapter_id}

        return {
            "adapters": adapters_data,
            "active_adapters": len(all_adapter_ids),
            "total_samples": sum(len(s.samples) for s in self._series.values()),
            "timestamp": time.time(),
        }

    # ---- WebSocket 推送 ----

    def subscribe(self, websocket, adapter_id: str | None = None) -> None:
        """订阅实时推送

        Args:
            websocket: WebSocket 连接
            adapter_id: 订阅指定适配器，None 表示全部
        """
        self._subscribers[websocket] = adapter_id

    def unsubscribe(self, websocket) -> None:
        """取消订阅"""
        self._subscribers.pop(websocket, None)

    def _broadcast(self, sample: MetricSample) -> None:
        """向订阅者推送度量数据"""
        if not self._subscribers:
            return

        message = {
            "type": "metric",
            "data": sample.to_dict(),
        }

        # 收集需要推送的 WebSocket 连接
        for ws, sub_adapter_id in list(self._subscribers.items()):
            # 过滤：如果订阅了特定适配器，只推送该适配器的数据
            if sub_adapter_id is not None and sub_adapter_id != sample.adapter_id:
                continue

            # 异步推送（如果 ws 支持 send_json）
            if hasattr(ws, "send_json"):
                try:
                    # FastAPI WebSocket 是异步的，需要用 asyncio
                    asyncio.get_event_loop().create_task(
                        ws.send_json(message)
                    )
                except RuntimeError:
                    # 事件循环未运行时忽略
                    pass
                except Exception:
                    logger.debug("推送度量数据失败，可能连接已断开")

    # ---- 趋势分析 ----

    def detect_regression(
        self,
        adapter_id: str,
        metric: str,
        window: int = 10,
        threshold_pct: float = 50.0,
    ) -> Optional[dict]:
        """回归检测

        如果最近 window 个样本的均值比之前增长超过 threshold_pct%，返回回归信息。

        Args:
            adapter_id: 适配器ID
            metric: 度量名称
            window: 对比窗口大小
            threshold_pct: 回归阈值百分比

        Returns:
            回归信息字典，或 None（未检测到回归）
        """
        series = self._series.get((metric, adapter_id))
        if series is None or len(series.samples) < window * 2:
            return None

        samples = series.samples
        # 最近 window 个样本
        recent = samples[-window:]
        # 之前 window 个样本
        previous = samples[-(window * 2):-window]

        recent_avg = sum(s.value for s in recent) / len(recent)
        previous_avg = sum(s.value for s in previous) / len(previous)

        if previous_avg == 0:
            return None

        change_pct = ((recent_avg - previous_avg) / previous_avg) * 100.0

        if change_pct > threshold_pct:
            return {
                "adapter_id": adapter_id,
                "metric": metric,
                "previous_avg": round(previous_avg, 2),
                "recent_avg": round(recent_avg, 2),
                "change_pct": round(change_pct, 1),
                "window": window,
                "threshold_pct": threshold_pct,
                "is_regression": True,
            }

        return None

    def get_trend(
        self,
        adapter_id: str,
        metric: str,
        points: int = 20,
    ) -> list[dict]:
        """获取趋势数据（聚合后的数据点）

        Args:
            adapter_id: 适配器ID
            metric: 度量名称
            points: 返回的数据点数量

        Returns:
            聚合数据点列表
        """
        series = self._series.get((metric, adapter_id))
        if series is None or not series.samples:
            return []

        # 计算合适的聚合窗口
        total_span = series.samples[-1].timestamp - series.samples[0].timestamp
        if total_span <= 0 or points <= 0:
            # 如果所有样本时间戳相同，返回原始数据
            return [s.to_dict() for s in series.samples[-points:]]

        interval_sec = total_span / points
        if interval_sec < 1:
            interval_sec = 1

        aggregated = series.aggregate(interval_sec)

        # 最多返回 points 个数据点
        if len(aggregated) > points:
            step = len(aggregated) // points
            aggregated = aggregated[::step]

        return aggregated

    # ---- 内部方法 ----

    def _get_or_create_series(self, metric: str, adapter_id: str) -> MetricSeries:
        """获取或创建度量序列"""
        key = (metric, adapter_id)
        if key not in self._series:
            self._series[key] = MetricSeries(metric, adapter_id)
        return self._series[key]


# ---- 全局监控器实例 ----

_global_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """获取全局性能监控器实例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
