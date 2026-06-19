"""适配器热重载 — 监控适配器文件变更，自动重新加载

核心组件：
- AdapterWatcher：基于 watchdog 的文件监控器，检测适配器目录变更
- HotReloader：管理适配器热重载生命周期（卸载旧适配器 → 重新加载 → 注册）
- reload 事件回调：通知 LSP/REPL/Playground 等模块适配器已更新

使用方式：
  1. CLI: yanpub adapter watch
  2. 编程: watcher = AdapterWatcher(registry); watcher.start()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from yanpub.core.adapter import LanguageAdapter
from yanpub.core.registry import LanguageRegistry, get_registry

logger = logging.getLogger("yanpub.adapter.hotreload")


@dataclass
class ReloadEvent:
    """重载事件"""

    adapter_id: str
    adapter_name: str
    event_type: str  # "created" | "modified" | "deleted"
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: str = ""


# 回调类型：重载事件通知
ReloadCallback = Callable[[ReloadEvent], None]


class HotReloader:
    """适配器热重载管理器

    负责卸载旧适配器、重新加载新适配器、注册到注册中心。
    支持注册回调函数，在重载完成后通知其他模块。
    """

    def __init__(self, registry: Optional[LanguageRegistry] = None):
        self._registry = registry or get_registry()
        self._callbacks: list[ReloadCallback] = []
        self._history: list[ReloadEvent] = []
        self._adapter_dirs: dict[str, Path] = {}  # adapter_id → 目录路径
        self._adapter_mtimes: dict[str, float] = {}  # adapter_id → 上次修改时间

        # 初始化：记录当前适配器的目录和修改时间
        self._snapshot_current_adapters()

    def _snapshot_current_adapters(self) -> None:
        """快照当前适配器状态"""
        adapters_dir = Path(__file__).parent.parent / "adapters"
        if not adapters_dir.exists():
            return

        for adapter_dir in adapters_dir.iterdir():
            if not adapter_dir.is_dir() or adapter_dir.name.startswith("_"):
                continue

            py_path = adapter_dir / "adapter.py"
            if py_path.exists():
                self._adapter_mtimes[adapter_dir.name] = py_path.stat().st_mtime
                self._adapter_dirs[adapter_dir.name] = adapter_dir

    def on_reload(self, callback: ReloadCallback) -> None:
        """注册重载回调"""
        self._callbacks.append(callback)

    def _notify(self, event: ReloadEvent) -> None:
        """通知所有回调"""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning("重载回调执行失败: %s", e)

    def check_and_reload(self) -> list[ReloadEvent]:
        """检查适配器文件变更并重载

        Returns:
            本轮检查中发生的重载事件列表
        """
        events: list[ReloadEvent] = []
        adapters_dir = Path(__file__).parent.parent / "adapters"
        if not adapters_dir.exists():
            return events

        for adapter_dir in adapters_dir.iterdir():
            if not adapter_dir.is_dir() or adapter_dir.name.startswith("_"):
                continue

            py_path = adapter_dir / "adapter.py"
            yaml_path = adapter_dir / "adapter.yaml"

            if not py_path.exists():
                continue

            current_mtime = py_path.stat().st_mtime
            if yaml_path.exists():
                yaml_mtime = yaml_path.stat().st_mtime
                current_mtime = max(current_mtime, yaml_mtime)

            prev_mtime = self._adapter_mtimes.get(adapter_dir.name, 0)

            if current_mtime > prev_mtime:
                # 文件已变更，重新加载
                event = self._reload_adapter(adapter_dir, "modified")
                events.append(event)
                self._adapter_mtimes[adapter_dir.name] = current_mtime
                self._adapter_dirs[adapter_dir.name] = adapter_dir

        return events

    def _reload_adapter(self, adapter_dir: Path, event_type: str) -> ReloadEvent:
        """重新加载单个适配器"""
        import importlib.util

        py_path = adapter_dir / "adapter.py"

        try:
            # 1. 识别旧适配器
            old_adapter: Optional[LanguageAdapter] = None
            for adapter in self._registry:
                # 通过目录名匹配旧适配器
                if adapter_dir.name in str(getattr(adapter, "__module__", "")):
                    old_adapter = adapter
                    break

            old_id = old_adapter.id if old_adapter else adapter_dir.name
            old_name = old_adapter.name if old_adapter else adapter_dir.name

            # 2. 卸载旧适配器
            if old_adapter:
                self._registry.unregister(old_id)
                logger.info("卸载适配器: %s (%s)", old_name, old_id)

            # 3. 重新加载
            # 清除模块缓存以强制重新导入
            module_name = f"yanpub.adapters.{adapter_dir.name}"
            if module_name in importlib.util._bootstrap._modules:  # type: ignore[attr-defined]
                del importlib.util._bootstrap._modules[module_name]  # type: ignore[attr-defined]

            # 清除 sys.modules 中的缓存
            import sys

            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, py_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载适配器: {py_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 查找适配器子类
            from yanpub.core.adapter import (
                LanguageAdapter as BaseAdapter,
                SubprocessAdapter,
                InProcessAdapter,
                HTTPAdapter,
            )

            _base_classes = {BaseAdapter, SubprocessAdapter, InProcessAdapter, HTTPAdapter}

            best = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAdapter)
                    and attr not in _base_classes
                ):
                    if best is None or (issubclass(attr, best) and attr is not best):
                        best = attr

            if best is None:
                raise ImportError(f"适配器目录中未找到 LanguageAdapter 子类: {adapter_dir.name}")

            # 4. 注册新适配器
            new_adapter = best()
            self._registry.register(new_adapter)
            logger.info(
                "重载适配器: %s (%s) v%s", new_adapter.name, new_adapter.id, new_adapter.version
            )

            event = ReloadEvent(
                adapter_id=new_adapter.id,
                adapter_name=new_adapter.name,
                event_type=event_type,
                success=True,
            )

        except Exception as e:
            logger.error("重载适配器失败 %s: %s", adapter_dir.name, e)
            event = ReloadEvent(
                adapter_id=adapter_dir.name,
                adapter_name=adapter_dir.name,
                event_type=event_type,
                success=False,
                error=str(e),
            )

        self._history.append(event)
        self._notify(event)
        return event

    @property
    def history(self) -> list[ReloadEvent]:
        """重载历史"""
        return list(self._history)


class AdapterWatcher:
    """适配器文件监控器

    使用 watchdog 库监控适配器目录变更，触发热重载。
    如果 watchdog 不可用，回退到轮询模式。
    """

    def __init__(
        self,
        registry: Optional[LanguageRegistry] = None,
        poll_interval: float = 2.0,
    ):
        self._registry = registry or get_registry()
        self._reloader = HotReloader(self._registry)
        self._poll_interval = poll_interval
        self._running = False
        self._observer = None

    @property
    def reloader(self) -> HotReloader:
        """获取热重载管理器"""
        return self._reloader

    def on_reload(self, callback: ReloadCallback) -> None:
        """注册重载回调"""
        self._reloader.on_reload(callback)

    def start(self) -> None:
        """启动适配器文件监控"""
        self._running = True

        # 尝试使用 watchdog
        try:
            import watchdog.observers
            import watchdog.events

            adapters_dir = Path(__file__).parent.parent / "adapters"

            class AdapterEventHandler(watchdog.events.FileSystemEventHandler):
                def __init__(self, watcher: AdapterWatcher):
                    self._watcher = watcher
                    self._last_check = 0.0

                def on_modified(self, event):
                    # 防抖：1秒内不重复触发
                    now = time.time()
                    if now - self._last_check < 1.0:
                        return
                    self._last_check = now

                    if event.src_path.endswith((".py", ".yaml", ".json")):
                        self._watcher._reloader.check_and_reload()

                def on_created(self, event):
                    self.on_modified(event)

            observer = watchdog.observers.Observer()
            handler = AdapterEventHandler(self)
            observer.schedule(handler, str(adapters_dir), recursive=True)
            observer.start()
            self._observer = observer

            logger.info("适配器热重载已启动 (watchdog 模式): %s", adapters_dir)

        except ImportError:
            # watchdog 不可用，使用轮询模式
            logger.info("watchdog 不可用，使用轮询模式 (间隔 %.1fs)", self._poll_interval)
            import threading

            def _poll_loop():
                while self._running:
                    time.sleep(self._poll_interval)
                    if self._running:
                        self._reloader.check_and_reload()

            thread = threading.Thread(target=_poll_loop, daemon=True)
            thread.start()

    def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
        logger.info("适配器热重载已停止")

    def check_now(self) -> list[ReloadEvent]:
        """立即检查并重载变更的适配器"""
        return self._reloader.check_and_reload()
