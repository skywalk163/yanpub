"""基准测试历史存储与回归检测

核心类：
- BenchSnapshot: 单次基准测试快照
- BenchHistory: 历史基准数据存储与对比
- RegressionInfo: 性能回归信息
- RegressionDetector: 性能回归自动检测

常量：
- BENCH_HISTORY_DIR: 历史数据存储目录
- REGRESSION_THRESHOLD: 回归阈值
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.core.perf.benchmark import AdapterBenchResult


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

                regressions.append(
                    RegressionInfo(
                        adapter_id=curr.adapter_id,
                        adapter_name=curr.adapter_name,
                        bench_name=curr_bench.name,
                        previous_ms=prev_mean,
                        current_ms=curr_mean,
                        change_pct=change_pct,
                        is_regression=is_regression,
                    )
                )

        return regressions
