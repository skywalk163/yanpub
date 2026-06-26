"""子进程连接池 — 复用子进程实例

核心能力：
1. PooledProcess — 池化子进程（使用次数限制、空闲超时、健康检查）
2. ProcessPool — 子进程连接池（获取/释放/清理/关闭）

设计要点：
- PooledProcess 基于 subprocess.Popen，通过 stdin/stdout 通信
- ProcessPool 管理进程的获取与归还，自动清理过期进程
- 每个进程绑定 adapter_id，同一适配器可复用进程
- 线程安全：所有公共方法加锁
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class PooledProcess:
    """池化子进程"""

    process: subprocess.Popen
    adapter_id: str
    created_at: float
    last_used: float
    use_count: int = 0
    max_uses: int = 100  # 最大使用次数，超过后重建
    idle_timeout: float = 300.0  # 空闲超时（秒）

    @property
    def is_alive(self) -> bool:
        """进程是否存活"""
        return self.process.poll() is None

    @property
    def is_expired(self) -> bool:
        """进程是否过期（使用次数超限或空闲超时）"""
        if self.use_count >= self.max_uses:
            return True
        if (time.monotonic() - self.last_used) > self.idle_timeout:
            return True
        return False


class ProcessPool:
    """子进程连接池 — 复用子进程实例

    避免每次执行都启动新进程，通过池化复用已有进程。

    Args:
        max_processes: 最大进程数（按 adapter_id 分组计算）
        idle_timeout: 空闲超时时间（秒），超时后自动清理
    """

    def __init__(self, max_processes: int = 4, idle_timeout: float = 300.0):
        self._max_processes = max_processes
        self._idle_timeout = idle_timeout
        self._pools: dict[str, list[PooledProcess]] = defaultdict(list)
        self._lock = threading.Lock()
        self._stats_created = 0
        self._stats_reused = 0
        self._stats_cleaned = 0

    def acquire(self, adapter_id: str, command: list[str]) -> PooledProcess:
        """获取一个进程

        1. 检查是否有可用的空闲进程
        2. 如果没有，创建新进程（不超过 max_processes）
        3. 如果已达上限，等待最旧的进程释放（先关闭再创建）

        Args:
            adapter_id: 适配器 ID
            command: 启动命令（如 ["python", "-i"]）

        Returns:
            PooledProcess 实例
        """
        with self._lock:
            pool = self._pools[adapter_id]

            # 1. 查找可用的空闲进程
            for i, pp in enumerate(pool):
                if pp.is_alive and not pp.is_expired:
                    # 复用
                    pp.use_count += 1
                    pp.last_used = time.monotonic()
                    self._stats_reused += 1
                    return pp

            # 2. 清理过期或已死亡的进程
            to_remove = []
            for i, pp in enumerate(pool):
                if not pp.is_alive or pp.is_expired:
                    to_remove.append(i)
                    self._safe_terminate(pp)

            for i in reversed(to_remove):
                pool.pop(i)
                self._stats_cleaned += 1

            # 3. 如果已达上限，关闭最旧的
            if len(pool) >= self._max_processes:
                oldest = pool.pop(0)
                self._safe_terminate(oldest)
                self._stats_cleaned += 1

            # 4. 创建新进程
            process = self._create_process(command)
            pooled = PooledProcess(
                process=process,
                adapter_id=adapter_id,
                created_at=time.monotonic(),
                last_used=time.monotonic(),
                use_count=1,
                max_uses=100,
                idle_timeout=self._idle_timeout,
            )
            pool.append(pooled)
            self._stats_created += 1
            return pooled

    def release(self, process: PooledProcess) -> None:
        """释放进程（归还到池中）

        如果进程已死亡或过期，直接清理。
        """
        with self._lock:
            if not process.is_alive or process.is_expired:
                self._remove_process(process)
                return
            # 进程仍有效，更新最后使用时间
            process.last_used = time.monotonic()

    def cleanup(self) -> int:
        """清理所有过期/已死亡的进程，返回清理数量"""
        with self._lock:
            count = 0
            for adapter_id in list(self._pools.keys()):
                pool = self._pools[adapter_id]
                to_remove = []
                for i, pp in enumerate(pool):
                    if not pp.is_alive or pp.is_expired:
                        to_remove.append(i)
                        self._safe_terminate(pp)

                for i in reversed(to_remove):
                    pool.pop(i)
                    count += 1

                # 清理空池
                if not pool:
                    del self._pools[adapter_id]

            self._stats_cleaned += count
            return count

    def shutdown(self) -> None:
        """关闭所有进程"""
        with self._lock:
            for adapter_id, pool in self._pools.items():
                for pp in pool:
                    self._safe_terminate(pp)
            self._pools.clear()

    def stats(self) -> dict:
        """返回池统计信息"""
        with self._lock:
            total_active = 0
            adapter_stats = {}
            for adapter_id, pool in self._pools.items():
                alive = sum(1 for pp in pool if pp.is_alive)
                total_active += alive
                adapter_stats[adapter_id] = {
                    "total": len(pool),
                    "alive": alive,
                }

            return {
                "max_processes": self._max_processes,
                "total_active": total_active,
                "adapters": adapter_stats,
                "created": self._stats_created,
                "reused": self._stats_reused,
                "cleaned": self._stats_cleaned,
            }

    # ---- 内部方法 ----

    def _create_process(self, command: list[str]) -> subprocess.Popen:
        """创建子进程"""
        import os

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")

        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def _safe_terminate(self, pp: PooledProcess) -> None:
        """安全终止进程"""
        try:
            if pp.process.poll() is None:
                pp.process.terminate()
                try:
                    pp.process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    pp.process.kill()
                    pp.process.wait(timeout=2.0)
        except Exception:
            pass

    def _remove_process(self, pp: PooledProcess) -> None:
        """从池中移除进程"""
        self._safe_terminate(pp)
        pool = self._pools.get(pp.adapter_id)
        if pool is not None:
            try:
                pool.remove(pp)
            except ValueError:
                pass
            if not pool:
                self._pools.pop(pp.adapter_id, None)


# ---- 全局进程池实例 ----

_global_process_pool: ProcessPool | None = None


def get_process_pool() -> ProcessPool:
    """获取全局进程池（懒加载）"""
    global _global_process_pool
    if _global_process_pool is None:
        _global_process_pool = ProcessPool()
    return _global_process_pool
