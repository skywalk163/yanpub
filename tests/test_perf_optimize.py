"""适配器性能优化功能测试 — 缓存策略、延迟加载、进程池"""

from __future__ import annotations

import subprocess
import time

import pytest

from yanpub.core.adapter import CompletionItem, Diagnostic, ExecutionResult, SubprocessAdapter
from yanpub.core.cache import AdapterCache, CacheEntry, LRUCache, get_adapter_cache
from yanpub.core.lazy_loader import LazyAdapter, LazyRegistry
from yanpub.core.pool import PooledProcess, ProcessPool, get_process_pool


# ============================================================
# 1. LRUCache 测试
# ============================================================


class TestCacheEntry:
    """缓存条目"""

    def test_not_expired_when_no_ttl(self):
        entry = CacheEntry(key="k", value="v", created_at=time.monotonic(), accessed_at=time.monotonic())
        assert not entry.is_expired

    def test_expired_after_ttl(self):
        entry = CacheEntry(
            key="k", value="v",
            created_at=time.monotonic() - 10,
            accessed_at=time.monotonic(),
            ttl=5.0,
        )
        assert entry.is_expired

    def test_not_expired_within_ttl(self):
        entry = CacheEntry(
            key="k", value="v",
            created_at=time.monotonic(),
            accessed_at=time.monotonic(),
            ttl=60.0,
        )
        assert not entry.is_expired


class TestLRUCache:
    """LRU 缓存"""

    def test_put_and_get(self):
        cache = LRUCache(max_size=10)
        cache.put("a", 1)
        assert cache.get("a") == 1

    def test_get_miss(self):
        cache = LRUCache(max_size=10)
        assert cache.get("nonexist") is None

    def test_lru_eviction(self):
        cache = LRUCache(max_size=2)
        cache.put("a", 1)
        cache.put("b", 2)
        # 访问 a，使 b 成为最久未用
        cache.get("a")
        cache.put("c", 3)
        assert cache.get("a") == 1  # a 被访问过，不会被淘汰
        assert cache.get("b") is None  # b 被淘汰
        assert cache.get("c") == 3

    def test_ttl_expired(self):
        cache = LRUCache(max_size=10, default_ttl=0.1)
        cache.put("ttl_key", "value")
        assert cache.get("ttl_key") == "value"
        time.sleep(0.15)
        assert cache.get("ttl_key") is None  # 过期

    def test_custom_ttl(self):
        cache = LRUCache(max_size=10)
        cache.put("short", "val", ttl=0.1)
        cache.put("long", "val", ttl=60.0)
        time.sleep(0.15)
        assert cache.get("short") is None
        assert cache.get("long") == "val"

    def test_invalidate(self):
        cache = LRUCache(max_size=10)
        cache.put("a", 1)
        assert cache.invalidate("a") is True
        assert cache.get("a") is None
        assert cache.invalidate("a") is False  # 已删除

    def test_invalidate_pattern(self):
        cache = LRUCache(max_size=10)
        cache.put("ns:a", 1)
        cache.put("ns:b", 2)
        cache.put("other:c", 3)
        count = cache.invalidate_pattern("ns:*")
        assert count == 2
        assert cache.get("ns:a") is None
        assert cache.get("ns:b") is None
        assert cache.get("other:c") == 3

    def test_clear(self):
        cache = LRUCache(max_size=10)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.clear()
        assert cache.stats()["size"] == 0

    def test_stats(self):
        cache = LRUCache(max_size=10)
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("nonexist")  # miss
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert 0 < stats["hit_rate"] < 1

    def test_overwrite_existing_key(self):
        cache = LRUCache(max_size=10)
        cache.put("a", 1)
        cache.put("a", 2)
        assert cache.get("a") == 2
        assert cache.stats()["size"] == 1

    def test_thread_safety(self):
        """多线程并发访问缓存"""
        import threading

        cache = LRUCache(max_size=100)
        errors = []

        def writer(start, count):
            try:
                for i in range(start, start + count):
                    cache.put(f"key_{i}", i)
            except Exception as e:
                errors.append(e)

        def reader(start, count):
            try:
                for i in range(start, start + count):
                    cache.get(f"key_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(4):
            threads.append(threading.Thread(target=writer, args=(t * 25, 25)))
            threads.append(threading.Thread(target=reader, args=(t * 25, 25)))

        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert not errors, f"Thread safety errors: {errors}"


# ============================================================
# 2. AdapterCache 测试
# ============================================================


class TestAdapterCache:
    """适配器专用缓存"""

    def test_compute_code_hash(self):
        h1 = AdapterCache.compute_code_hash('打印("hello")')
        h2 = AdapterCache.compute_code_hash('打印("hello")')
        h3 = AdapterCache.compute_code_hash('打印("world")')
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16

    def test_eval_cache(self):
        cache = AdapterCache(max_size=64)
        code_hash = AdapterCache.compute_code_hash("test code")
        result = ExecutionResult(stdout="hello", exit_code=0)

        # 未缓存
        assert cache.get_eval_result("duan", code_hash) is None

        # 写入缓存
        cache.put_eval_result("duan", code_hash, result)
        cached = cache.get_eval_result("duan", code_hash)
        assert cached is not None
        assert cached.stdout == "hello"

    def test_completion_cache(self):
        cache = AdapterCache(max_size=64)
        code_hash = AdapterCache.compute_code_hash("test code")
        items = [CompletionItem(label="设"), CompletionItem(label="为")]

        cache.put_completions("duan", code_hash, items)
        cached = cache.get_completions("duan", code_hash)
        assert cached is not None
        assert len(cached) == 2
        assert cached[0].label == "设"

    def test_diagnostic_cache(self):
        cache = AdapterCache(max_size=64)
        code_hash = AdapterCache.compute_code_hash("test code")
        diags = [Diagnostic(line=1, column=1, severity="error", message="test")]

        cache.put_diagnostics("duan", code_hash, diags)
        cached = cache.get_diagnostics("duan", code_hash)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].severity == "error"

    def test_invalidate_adapter(self):
        cache = AdapterCache(max_size=64)
        code_hash = AdapterCache.compute_code_hash("test")

        cache.put_eval_result("duan", code_hash, ExecutionResult())
        cache.put_completions("duan", code_hash, [])
        cache.put_diagnostics("duan", code_hash, [])

        count = cache.invalidate_adapter("duan")
        assert count >= 3
        assert cache.get_eval_result("duan", code_hash) is None
        assert cache.get_completions("duan", code_hash) is None
        assert cache.get_diagnostics("duan", code_hash) is None

    def test_isolation_between_adapters(self):
        cache = AdapterCache(max_size=64)
        code_hash = AdapterCache.compute_code_hash("same code")

        cache.put_eval_result("duan", code_hash, ExecutionResult(stdout="duan_result"))
        cache.put_eval_result("yan", code_hash, ExecutionResult(stdout="yan_result"))

        assert cache.get_eval_result("duan", code_hash).stdout == "duan_result"
        assert cache.get_eval_result("yan", code_hash).stdout == "yan_result"

    def test_stats(self):
        cache = AdapterCache(max_size=64)
        stats = cache.stats()
        assert "eval" in stats
        assert "completion" in stats
        assert "diagnostic" in stats

    def test_get_adapter_cache_singleton(self):
        """全局缓存单例"""
        import yanpub.core.cache as cache_mod
        cache_mod._global_adapter_cache = None  # 重置
        c1 = get_adapter_cache()
        c2 = get_adapter_cache()
        assert c1 is c2


# ============================================================
# 3. LazyAdapter 测试
# ============================================================


class TestLazyAdapter:
    """延迟加载适配器"""

    def test_not_loaded_initially(self):
        lazy = LazyAdapter(SubprocessAdapter, "测试", "test", "1.0", [".t"], ["python"])
        assert not lazy.is_loaded
        assert lazy.load_time_ms is None

    def test_load_on_property_access(self):
        lazy = LazyAdapter(SubprocessAdapter, "测试", "test_lz", "1.0", [".t"], ["python"])
        # 访问 name 触发加载
        assert lazy.name == "测试"
        assert lazy.is_loaded
        assert lazy.load_time_ms is not None
        assert lazy.load_time_ms >= 0

    def test_proxy_all_properties(self):
        lazy = LazyAdapter(SubprocessAdapter, "段言", "duan_lz", "1.3.8", [".段"], ["python"])
        assert lazy.name == "段言"
        assert lazy.id == "duan_lz"
        assert lazy.version == "1.3.8"
        assert lazy.file_extensions == [".段"]
        assert lazy.is_loaded

    def test_proxy_methods(self):
        lazy = LazyAdapter(
            SubprocessAdapter, "测试", "test_proxy", "1.0", [".t"],
            ["python"], eval_command=["python", "-c"], eval_mode="arg",
        )
        # eval 触发加载
        result = lazy.eval("print(42)")
        assert result.success
        assert lazy.is_loaded

    def test_isinstance_check(self):
        from yanpub.core.adapter import LanguageAdapter
        lazy = LazyAdapter(SubprocessAdapter, "测试", "t", "1.0", [".t"], ["python"])
        assert isinstance(lazy, LanguageAdapter)

    def test_load_only_once(self):
        lazy = LazyAdapter(SubprocessAdapter, "测试", "t_once", "1.0", [".t"], ["python"])
        lazy.name  # 首次加载
        first_load_time = lazy.load_time_ms
        lazy.id  # 再次访问
        assert lazy.load_time_ms == first_load_time  # 未重新加载


# ============================================================
# 4. LazyRegistry 测试
# ============================================================


class TestLazyRegistry:
    """延迟加载注册中心"""

    def test_register_and_get(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_reg", "1.3.8", [".段"], ["python"])
        registry.register(adapter)

        result = registry.get("duan_reg")
        assert result is not None
        assert result.name == "段言"

    def test_get_nonexist(self):
        registry = LazyRegistry()
        assert registry.get("nonexist") is None

    def test_get_or_raise(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_r", "1.3.8", [".段"], ["python"])
        registry.register(adapter)

        result = registry.get_or_raise("duan_r")
        assert result.id == "duan_r"

        with pytest.raises(KeyError):
            registry.get_or_raise("nonexist")

    def test_len_and_contains(self):
        registry = LazyRegistry()
        assert len(registry) == 0
        adapter = SubprocessAdapter("段言", "duan_len", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        assert len(registry) == 1
        assert "duan_len" in registry

    def test_unregister(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_un", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        registry.unregister("duan_un")
        assert len(registry) == 0

    def test_language_ids(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_ids", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        assert "duan_ids" in registry.language_ids

    def test_loaded_and_total_count(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_cnt", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        # register() 直接包装已实例化适配器，所以 loaded_count == total_count
        assert registry.loaded_count == 1
        assert registry.total_count == 1

    def test_preload(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_pre", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        registry.preload("duan_pre")
        assert registry.loaded_count == 1

    def test_preload_all(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_preall", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        registry.preload_all()
        assert registry.loaded_count == 1

    def test_iter(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_iter", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        adapters = list(registry)
        assert len(adapters) == 1
        assert adapters[0].id == "duan_iter"

    def test_list_languages(self):
        registry = LazyRegistry()
        adapter = SubprocessAdapter("段言", "duan_list", "1.3.8", [".段"], ["python"])
        registry.register(adapter)
        langs = registry.list_languages()
        assert len(langs) == 1
        assert langs[0]["id"] == "duan_list"


# ============================================================
# 5. ProcessPool 测试
# ============================================================


class TestPooledProcess:
    """池化子进程"""

    def test_is_alive(self):
        proc = subprocess.Popen(
            ["python", "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        pp = PooledProcess(
            process=proc, adapter_id="test",
            created_at=time.monotonic(), last_used=time.monotonic(),
        )
        assert pp.is_alive
        proc.terminate()
        proc.wait(timeout=5)
        assert not pp.is_alive

    def test_is_expired_by_use_count(self):
        proc = subprocess.Popen(
            ["python", "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        pp = PooledProcess(
            process=proc, adapter_id="test",
            created_at=time.monotonic(), last_used=time.monotonic(),
            use_count=100, max_uses=100,
        )
        assert pp.is_expired
        proc.terminate()
        proc.wait(timeout=5)

    def test_is_not_expired_within_limits(self):
        proc = subprocess.Popen(
            ["python", "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        pp = PooledProcess(
            process=proc, adapter_id="test",
            created_at=time.monotonic(), last_used=time.monotonic(),
            use_count=1, max_uses=100, idle_timeout=300.0,
        )
        assert not pp.is_expired
        proc.terminate()
        proc.wait(timeout=5)


class TestProcessPool:
    """子进程连接池"""

    def test_acquire_creates_process(self):
        pool = ProcessPool(max_processes=2, idle_timeout=300.0)
        pp = pool.acquire("test_pool", ["python", "-i"])
        assert pp.is_alive
        assert pp.use_count == 1
        assert pp.adapter_id == "test_pool"
        pool.shutdown()

    def test_release_and_reuse(self):
        pool = ProcessPool(max_processes=2, idle_timeout=300.0)
        pp1 = pool.acquire("test_reuse", ["python", "-i"])
        pool.release(pp1)
        pp2 = pool.acquire("test_reuse", ["python", "-i"])
        assert pp2.use_count == 2  # 复用，计数增加
        pool.shutdown()

    def test_max_processes_limit(self):
        pool = ProcessPool(max_processes=1, idle_timeout=300.0)
        pp1 = pool.acquire("test_limit", ["python", "-i"])
        pool.release(pp1)
        pp2 = pool.acquire("test_limit", ["python", "-i"])
        # 应复用同一进程
        assert pp2.process.pid == pp1.process.pid
        pool.shutdown()

    def test_cleanup(self):
        pool = ProcessPool(max_processes=2, idle_timeout=0.05)  # 极短超时
        pp = pool.acquire("test_cleanup", ["python", "-i"])
        pool.release(pp)
        time.sleep(0.1)  # 等待超时
        cleaned = pool.cleanup()
        assert cleaned >= 1
        pool.shutdown()

    def test_shutdown(self):
        pool = ProcessPool(max_processes=2, idle_timeout=300.0)
        pool.acquire("test_shutdown", ["python", "-i"])
        pool.shutdown()
        stats = pool.stats()
        assert stats["total_active"] == 0

    def test_stats(self):
        pool = ProcessPool(max_processes=4, idle_timeout=300.0)
        pp = pool.acquire("test_stats", ["python", "-i"])
        pool.release(pp)
        stats = pool.stats()
        assert stats["max_processes"] == 4
        assert stats["created"] == 1
        assert stats["reused"] >= 0
        pool.shutdown()

    def test_get_process_pool_singleton(self):
        import yanpub.core.pool as pool_mod
        pool_mod._global_process_pool = None  # 重置
        p1 = get_process_pool()
        p2 = get_process_pool()
        assert p1 is p2
        p1.shutdown()


# ============================================================
# 6. SubprocessAdapter 缓存集成测试
# ============================================================


class TestSubprocessAdapterCacheIntegration:
    """SubprocessAdapter 缓存集成"""

    def setup_method(self):
        """每个测试前重置全局缓存"""
        import yanpub.core.cache as cache_mod
        cache_mod._global_adapter_cache = None

    def test_eval_cache_hit(self):
        adapter = SubprocessAdapter(
            name="测试", lang_id="test_eval_cache", version="1.0",
            extensions=[".tc"], run_command=["python"],
            eval_command=["python", "-c"], eval_mode="arg",
        )
        code = "print(42)"
        result1 = adapter.eval(code)
        assert result1.success

        # 第二次执行应命中缓存
        result2 = adapter.eval(code)
        assert result2.success
        assert result2.stdout == result1.stdout

        # 检查缓存统计
        cache = get_adapter_cache()
        stats = cache.stats()
        assert stats["eval"]["hits"] >= 1

    def test_cache_disabled(self):
        adapter = SubprocessAdapter(
            name="测试", lang_id="test_no_cache", version="1.0",
            extensions=[".tc"], run_command=["python"],
            eval_command=["python", "-c"], eval_mode="arg",
            enable_cache=False,
        )
        code = "print(99)"
        adapter.eval(code)
        # 禁用缓存，不应有缓存条目
        cache = get_adapter_cache()
        # 注意：全局缓存可能被其他适配器使用，检查本适配器无命中
        code_hash = AdapterCache.compute_code_hash(code)
        assert cache.get_eval_result("test_no_cache", code_hash) is None

    def test_invalidate_after_eval(self):
        adapter = SubprocessAdapter(
            name="测试", lang_id="test_invalidate", version="1.0",
            extensions=[".tc"], run_command=["python"],
            eval_command=["python", "-c"], eval_mode="arg",
        )
        code = "print(1)"
        adapter.eval(code)

        cache = get_adapter_cache()
        count = cache.invalidate_adapter("test_invalidate")
        assert count >= 1

        # 失效后应不再命中
        code_hash = AdapterCache.compute_code_hash(code)
        assert cache.get_eval_result("test_invalidate", code_hash) is None
