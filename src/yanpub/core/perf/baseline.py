"""性能基线管理 — 快照采集、基线对比、CI 回归检测、性能预算

核心能力：
1. BaselineSnapshot — 性能基线快照（适配器 + 环境 + 指标）
2. PerformanceBudget — 性能预算（指标上限检查）
3. BaselineManager — 基线管理器（捕获/存储/对比/回归检测/预算管理）

存储格式：JSON 文件，目录 ~/.yanpub/baselines/{adapter_id}/{snapshot_id}.json

命令:
  yanpub baseline capture -L duan              — 捕获快照
  yanpub baseline list -L duan                 — 列出快照
  yanpub baseline compare -L duan              — 与基线对比
  yanpub baseline delete -s <id>               — 删除快照
  yanpub budget set -L duan -m eval_mean_ms=100  — 设置预算
  yanpub budget check -L duan                  — 检查预算
  yanpub budget list                           — 列出所有预算
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.perf.benchmark import run_benchmarks


# ---- 环境信息采集 ----


def _collect_environment() -> dict:
    """采集运行环境信息（仅使用标准库）"""
    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "os": sys.platform,
        "os_version": platform.version(),
        "cpu_count": os.cpu_count() or 0,
        "hostname": platform.node(),
    }


# ---- 性能基线快照 ----


@dataclass
class BaselineSnapshot:
    """性能基线快照"""

    id: str
    timestamp: float
    adapter_id: str
    adapter_version: str
    metrics: dict  # metric_name → value
    # 例如: {"eval_mean_ms": 45.2, "eval_median_ms": 42.1, ...}
    environment: dict  # 运行环境信息
    # 例如: {"python_version": "3.12", "os": "win32", ...}
    label: str = ""  # 可选标签，如 "v0.8.0-release", "pre-merge"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "metrics": dict(self.metrics),
            "environment": dict(self.environment),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BaselineSnapshot:
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            adapter_id=data["adapter_id"],
            adapter_version=data["adapter_version"],
            metrics=data.get("metrics", {}),
            environment=data.get("environment", {}),
            label=data.get("label", ""),
        )


# ---- 性能预算 ----


@dataclass
class PerformanceBudget:
    """性能预算"""

    adapter_id: str
    budgets: dict  # metric_name → budget_ms
    # 例如: {"eval_mean_ms": 100.0, "run_mean_ms": 500.0, "eval_p95_ms": 200.0}

    def check(self, snapshot: BaselineSnapshot) -> list[dict]:
        """检查快照是否在预算内

        Returns:
            [{"metric": str, "budget": float, "actual": float, "over_budget": bool, "pct_over": float}]
        """
        results = []
        for metric_name, budget_ms in self.budgets.items():
            actual = snapshot.metrics.get(metric_name)
            if actual is None:
                # 指标不存在于快照中，跳过
                continue
            over = actual > budget_ms
            pct_over = ((actual - budget_ms) / budget_ms * 100.0) if budget_ms > 0 else 0.0
            results.append(
                {
                    "metric": metric_name,
                    "budget": budget_ms,
                    "actual": actual,
                    "over_budget": over,
                    "pct_over": round(pct_over, 2),
                }
            )
        return results

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "budgets": dict(self.budgets),
        }

    @classmethod
    def from_dict(cls, data: dict) -> PerformanceBudget:
        return cls(
            adapter_id=data["adapter_id"],
            budgets=data.get("budgets", {}),
        )


# ---- 基线管理器 ----

_DEFAULT_BASELINE_DIR = Path.home() / ".yanpub" / "baselines"
_BUDGET_FILENAME = "_budget.json"


class BaselineManager:
    """基线管理器

    管理性能快照的采集、存储、对比、回归检测和性能预算。
    快照存储为 JSON 文件：~/.yanpub/baselines/{adapter_id}/{snapshot_id}.json
    """

    def __init__(self, storage_dir: Path | None = None):
        self._storage_dir = storage_dir or _DEFAULT_BASELINE_DIR

    # ---- 属性 ----

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    # ---- 快照管理 ----

    def capture_snapshot(self, adapter: LanguageAdapter, label: str = "") -> BaselineSnapshot:
        """捕获当前性能快照

        运行基准测试，记录结果为快照。
        """
        bench_result = run_benchmarks(adapter)

        # 从基准测试结果提取指标
        metrics: dict[str, float] = {}

        if bench_result.startup is not None:
            metrics["startup_mean_ms"] = round(bench_result.startup.mean_ms, 2)
            metrics["startup_median_ms"] = round(bench_result.startup.median_ms, 2)
        if bench_result.keyword_load is not None:
            metrics["keyword_load_mean_ms"] = round(bench_result.keyword_load.mean_ms, 2)
            metrics["keyword_load_median_ms"] = round(bench_result.keyword_load.median_ms, 2)
        if bench_result.execution is not None:
            metrics["eval_mean_ms"] = round(bench_result.execution.mean_ms, 2)
            metrics["eval_median_ms"] = round(bench_result.execution.median_ms, 2)
            metrics["eval_min_ms"] = round(bench_result.execution.min_ms, 2)
            metrics["eval_max_ms"] = round(bench_result.execution.max_ms, 2)
        if bench_result.throughput is not None:
            metrics["throughput_mean_ms"] = round(bench_result.throughput.mean_ms, 2)
            metrics["throughput_median_ms"] = round(bench_result.throughput.median_ms, 2)

        snapshot = BaselineSnapshot(
            id=uuid.uuid4().hex[:12],
            timestamp=time.time(),
            adapter_id=adapter.id,
            adapter_version=adapter.version,
            metrics=metrics,
            environment=_collect_environment(),
            label=label,
        )
        return snapshot

    def save_snapshot(self, snapshot: BaselineSnapshot) -> None:
        """保存快照到磁盘"""
        adapter_dir = self._storage_dir / snapshot.adapter_id
        adapter_dir.mkdir(parents=True, exist_ok=True)

        path = adapter_dir / f"{snapshot.id}.json"
        path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_snapshot(self, snapshot_id: str) -> Optional[BaselineSnapshot]:
        """加载指定 ID 的快照

        遍历所有适配器目录查找文件名匹配的快照。
        """
        if not self._storage_dir.exists():
            return None

        for adapter_dir in self._storage_dir.iterdir():
            if not adapter_dir.is_dir():
                continue
            path = adapter_dir / f"{snapshot_id}.json"
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    return BaselineSnapshot.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    return None

        return None

    def list_snapshots(self, adapter_id: str | None = None) -> list[BaselineSnapshot]:
        """列出快照

        Args:
            adapter_id: 指定适配器，None 表示全部
        """
        if not self._storage_dir.exists():
            return []

        snapshots: list[BaselineSnapshot] = []

        if adapter_id:
            dirs = [self._storage_dir / adapter_id]
        else:
            dirs = sorted(self._storage_dir.iterdir())

        for adapter_dir in dirs:
            if not adapter_dir.is_dir():
                continue
            for path in sorted(adapter_dir.glob("*.json")):
                # 跳过预算文件
                if path.name == _BUDGET_FILENAME:
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    snapshots.append(BaselineSnapshot.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    continue

        # 按时间戳排序（最新的在前）
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)
        return snapshots

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """删除指定快照"""
        if not self._storage_dir.exists():
            return False

        for adapter_dir in self._storage_dir.iterdir():
            if not adapter_dir.is_dir():
                continue
            path = adapter_dir / f"{snapshot_id}.json"
            if path.exists():
                path.unlink()
                return True

        return False

    # ---- 基线对比 ----

    def compare(self, snapshot_a: BaselineSnapshot, snapshot_b: BaselineSnapshot) -> dict:
        """对比两个快照

        Returns:
            {
                "metrics": [{"name": str, "a": float, "b": float, "diff_pct": float, "regression": bool}],
                "regressions": int,
                "improvements": int,
                "neutral": int,
            }
        """
        metric_results = []
        all_metric_names = set(snapshot_a.metrics.keys()) | set(snapshot_b.metrics.keys())

        for name in sorted(all_metric_names):
            val_a = snapshot_a.metrics.get(name)
            val_b = snapshot_b.metrics.get(name)

            # 只对比两个快照都有的指标
            if val_a is None or val_b is None:
                continue

            if val_a == 0:
                diff_pct = 0.0 if val_b == 0 else float("inf")
            else:
                diff_pct = ((val_b - val_a) / val_a) * 100.0

            # 正 diff 表示 b 比 a 慢（回归）
            is_regression = diff_pct > 0
            is_improvement = diff_pct < 0

            metric_results.append(
                {
                    "name": name,
                    "a": val_a,
                    "b": val_b,
                    "diff_pct": round(diff_pct, 2),
                    "regression": is_regression,
                    "improvement": is_improvement,
                }
            )

        regressions = sum(1 for m in metric_results if m["regression"])
        improvements = sum(1 for m in metric_results if m["improvement"])
        neutral = len(metric_results) - regressions - improvements

        return {
            "metrics": metric_results,
            "regressions": regressions,
            "improvements": improvements,
            "neutral": neutral,
        }

    def compare_to_baseline(self, snapshot: BaselineSnapshot) -> dict:
        """与最新基线对比

        自动找到同 adapter 的最新快照作为基线。
        如果没有历史快照，返回空对比结果。
        """
        # 获取同适配器的所有快照（已按时间倒序排列）
        all_snapshots = self.list_snapshots(adapter_id=snapshot.adapter_id)

        # 过滤掉当前快照自身
        baseline_candidates = [s for s in all_snapshots if s.id != snapshot.id]

        if not baseline_candidates:
            # 没有历史基线，返回空对比
            return {
                "metrics": [],
                "regressions": 0,
                "improvements": 0,
                "neutral": 0,
                "baseline": None,
            }

        # 最新的历史快照作为基线
        baseline = baseline_candidates[0]
        comparison = self.compare(baseline, snapshot)
        comparison["baseline"] = baseline.to_dict()
        return comparison

    # ---- CI 回归检测 ----

    def check_regression(
        self,
        adapter_id: str,
        threshold_pct: float = 20.0,
        metrics: list[str] | None = None,
    ) -> dict:
        """CI 回归检测

        捕获当前快照，与最新基线对比，检查是否有指标超过阈值。

        注意：此方法需要先有保存的快照作为基线。
        它仅对比已有快照，不自动捕获新快照（避免 CI 中引入不确定性）。
        如需捕获新快照，请先调用 capture_snapshot + save_snapshot。

        Args:
            adapter_id: 适配器 ID
            threshold_pct: 回归阈值百分比（默认 20%）
            metrics: 仅检查这些指标，None 表示全部

        Returns:
            {
                "passed": bool,
                "baseline": BaselineSnapshot 或 None,
                "latest": BaselineSnapshot 或 None,
                "comparison": dict,
                "regressions": [...],
            }
        """
        all_snapshots = self.list_snapshots(adapter_id=adapter_id)

        if len(all_snapshots) < 2:
            return {
                "passed": True,
                "baseline": None,
                "latest": all_snapshots[0].to_dict() if all_snapshots else None,
                "comparison": None,
                "regressions": [],
                "message": "快照不足（需要至少2个），无法进行回归检测",
            }

        # 最新的两个快照
        latest = all_snapshots[0]
        baseline = all_snapshots[1]

        comparison = self.compare(baseline, latest)

        # 筛选回归
        regressions = []
        for m in comparison["metrics"]:
            if not m["regression"]:
                continue
            # 如果指定了指标列表，只检查列表内的
            if metrics is not None and m["name"] not in metrics:
                continue
            # 检查是否超过阈值
            if m["diff_pct"] > threshold_pct:
                regressions.append(
                    {
                        "metric": m["name"],
                        "baseline_value": m["a"],
                        "current_value": m["b"],
                        "diff_pct": m["diff_pct"],
                        "threshold_pct": threshold_pct,
                    }
                )

        passed = len(regressions) == 0

        return {
            "passed": passed,
            "baseline": baseline.to_dict(),
            "latest": latest.to_dict(),
            "comparison": comparison,
            "regressions": regressions,
        }

    # ---- 性能预算 ----

    def set_budget(self, budget: PerformanceBudget) -> None:
        """设置性能预算"""
        adapter_dir = self._storage_dir / budget.adapter_id
        adapter_dir.mkdir(parents=True, exist_ok=True)

        path = adapter_dir / _BUDGET_FILENAME
        path.write_text(
            json.dumps(budget.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_budget(self, adapter_id: str) -> Optional[PerformanceBudget]:
        """获取适配器的性能预算"""
        path = self._storage_dir / adapter_id / _BUDGET_FILENAME
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PerformanceBudget.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def check_budget(self, adapter_id: str) -> dict:
        """检查适配器是否满足性能预算

        使用最新快照与预算对比。

        Returns:
            {"has_budget": bool, "budget": dict, "snapshot": dict, "results": list, "all_within_budget": bool}
        """
        budget = self.get_budget(adapter_id)
        if budget is None:
            return {
                "has_budget": False,
                "budget": None,
                "snapshot": None,
                "results": [],
                "all_within_budget": True,
            }

        # 获取最新快照
        snapshots = self.list_snapshots(adapter_id=adapter_id)
        if not snapshots:
            return {
                "has_budget": True,
                "budget": budget.to_dict(),
                "snapshot": None,
                "results": [],
                "all_within_budget": True,
                "message": "没有快照可供检查",
            }

        latest = snapshots[0]
        results = budget.check(latest)
        all_within = all(not r["over_budget"] for r in results)

        return {
            "has_budget": True,
            "budget": budget.to_dict(),
            "snapshot": latest.to_dict(),
            "results": results,
            "all_within_budget": all_within,
        }

    # ---- 标签管理 ----

    def tag_snapshot(self, snapshot_id: str, label: str) -> None:
        """为快照设置标签"""
        snapshot = self.load_snapshot(snapshot_id)
        if snapshot is None:
            return

        snapshot.label = label
        self.save_snapshot(snapshot)

    def get_snapshot_by_label(self, adapter_id: str, label: str) -> Optional[BaselineSnapshot]:
        """通过标签查找快照"""
        snapshots = self.list_snapshots(adapter_id=adapter_id)
        for s in snapshots:
            if s.label == label:
                return s
        return None
