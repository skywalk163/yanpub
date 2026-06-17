"""缓存策略 — LRU 缓存与适配器专用缓存

核心能力：
1. CacheEntry — 缓存条目（TTL、命中计数、过期检测）
2. LRUCache — 通用 LRU 缓存（OrderedDict + threading.Lock 线程安全）
3. AdapterCache — 适配器专用缓存（执行结果/补全/诊断三类缓存）

命令:
  yanpub cache stats       — 查看缓存统计
  yanpub cache clear       — 清空所有缓存
  yanpub cache invalidate  — 失效指定适配器缓存
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from yanpub.core.adapter import CompletionItem, Diagnostic, ExecutionResult


# ---- 缓存条目 ----

@dataclass
class CacheEntry:
    """缓存条目"""

    key: str
    value: Any
    created_at: float
    accessed_at: float
    hit_count: int = 0
    ttl: float | None = None  # 秒，None 表示永不过期

    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        if self.ttl is None:
            return False
        return (time.monotonic() - self.created_at) > self.ttl


# ---- LRU 缓存 ----

class LRUCache:
    """LRU 缓存（OrderedDict + 线程安全锁）

    Args:
        max_size: 最大缓存条目数
        default_ttl: 默认 TTL（秒），None 表示永不过期
    """

    def __init__(self, max_size: int = 128, default_ttl: float | None = None):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值。命中时移动到末尾（LRU 更新），过期则删除。"""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired:
                # 过期，删除并记为 miss
                del self._data[key]
                self._misses += 1
                return None

            # 命中：更新访问时间和 LRU 顺序
            entry.accessed_at = time.monotonic()
            entry.hit_count += 1
            self._data.move_to_end(key)
            self._hits += 1
            return entry.value

    def put(self, key: str, value: Any, ttl: float | None = None) -> None:
        """写入缓存。超容量时淘汰最久未使用的条目。"""
        effective_ttl = ttl if ttl is not None else self._default_ttl
        now = time.monotonic()

        with self._lock:
            if key in self._data:
                # 已存在：更新值并移到末尾
                self._data[key] = CacheEntry(
                    key=key, value=value,
                    created_at=now, accessed_at=now,
                    ttl=effective_ttl,
                )
                self._data.move_to_end(key)
            else:
                # 新增：容量满时先淘汰
                while len(self._data) >= self._max_size:
                    self._data.popitem(last=False)
                self._data[key] = CacheEntry(
                    key=key, value=value,
                    created_at=now, accessed_at=now,
                    ttl=effective_ttl,
                )

    def invalidate(self, key: str) -> bool:
        """删除指定缓存键。返回是否成功删除。"""
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """按通配符模式删除缓存。

        pattern 中 * 匹配任意字符序列。
        返回删除的条目数。
        """
        import fnmatch

        with self._lock:
            keys_to_remove = [
                k for k in self._data
                if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_remove:
                del self._data[k]
            return len(keys_to_remove)

    def clear(self) -> None:
        """清空所有缓存。"""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """返回缓存统计信息。"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._data),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }


# ---- 适配器专用缓存 ----

# 默认 TTL（秒）
EVAL_TTL = 60.0       # 执行结果缓存 60 秒
COMPLETION_TTL = 30.0  # 补全结果缓存 30 秒
DIAGNOSTIC_TTL = 30.0  # 诊断结果缓存 30 秒


class AdapterCache:
    """适配器专用缓存

    为 eval / complete / diagnose 三类操作分别维护独立缓存，
    支持按适配器 ID 批量失效。

    Args:
        max_size: 每类缓存的最大条目数
    """

    def __init__(self, max_size: int = 256):
        self._eval_cache = LRUCache(max_size=max_size, default_ttl=EVAL_TTL)
        self._completion_cache = LRUCache(max_size=max_size, default_ttl=COMPLETION_TTL)
        self._diagnostic_cache = LRUCache(max_size=max_size, default_ttl=DIAGNOSTIC_TTL)

    # ---- 执行结果缓存 ----

    def get_eval_result(self, adapter_id: str, code_hash: str) -> Optional[ExecutionResult]:
        """获取执行结果缓存"""
        result = self._eval_cache.get(f"eval:{adapter_id}:{code_hash}")
        return result if isinstance(result, ExecutionResult) else None

    def put_eval_result(self, adapter_id: str, code_hash: str, result: ExecutionResult) -> None:
        """写入执行结果缓存"""
        self._eval_cache.put(f"eval:{adapter_id}:{code_hash}", result)

    # ---- 补全结果缓存 ----

    def get_completions(self, adapter_id: str, code_hash: str) -> Optional[list[CompletionItem]]:
        """获取补全结果缓存"""
        result = self._completion_cache.get(f"comp:{adapter_id}:{code_hash}")
        return result if isinstance(result, list) else None

    def put_completions(self, adapter_id: str, code_hash: str, items: list[CompletionItem]) -> None:
        """写入补全结果缓存"""
        self._completion_cache.put(f"comp:{adapter_id}:{code_hash}", items)

    # ---- 诊断结果缓存 ----

    def get_diagnostics(self, adapter_id: str, code_hash: str) -> Optional[list[Diagnostic]]:
        """获取诊断结果缓存"""
        result = self._diagnostic_cache.get(f"diag:{adapter_id}:{code_hash}")
        return result if isinstance(result, list) else None

    def put_diagnostics(self, adapter_id: str, code_hash: str, diags: list[Diagnostic]) -> None:
        """写入诊断结果缓存"""
        self._diagnostic_cache.put(f"diag:{adapter_id}:{code_hash}", diags)

    # ---- 通用方法 ----

    def invalidate_adapter(self, adapter_id: str) -> int:
        """清除指定适配器的所有缓存（通配符模式匹配）"""
        count = 0
        count += self._eval_cache.invalidate_pattern(f"eval:{adapter_id}:*")
        count += self._completion_cache.invalidate_pattern(f"comp:{adapter_id}:*")
        count += self._diagnostic_cache.invalidate_pattern(f"diag:{adapter_id}:*")
        return count

    def clear(self) -> None:
        """清空所有缓存"""
        self._eval_cache.clear()
        self._completion_cache.clear()
        self._diagnostic_cache.clear()

    def stats(self) -> dict:
        """返回各缓存统计信息"""
        return {
            "eval": self._eval_cache.stats(),
            "completion": self._completion_cache.stats(),
            "diagnostic": self._diagnostic_cache.stats(),
        }

    @staticmethod
    def compute_code_hash(code: str) -> str:
        """计算代码哈希（SHA-256 前16位）"""
        return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


# ---- 全局适配器缓存实例 ----

_global_adapter_cache: AdapterCache | None = None


def get_adapter_cache() -> AdapterCache:
    """获取全局适配器缓存（懒加载）"""
    global _global_adapter_cache
    if _global_adapter_cache is None:
        _global_adapter_cache = AdapterCache()
    return _global_adapter_cache
