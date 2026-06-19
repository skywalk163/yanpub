"""适配器热更新 — 运行时代码替换 + 状态保持 + 版本回退

核心类:
- AdapterState: 适配器运行时状态快照
- VersionRecord: 版本记录
- HotUpdateManager: 热更新管理器（状态保存/恢复、版本链、回退）
"""

from __future__ import annotations

import importlib
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yanpub.core.registry import LanguageRegistry, get_registry


@dataclass
class AdapterState:
    """适配器运行时状态快照"""

    adapter_id: str
    adapter_name: str
    version: str
    module_path: str
    state_data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "version": self.version,
            "module_path": self.module_path,
            "state_data": self.state_data,
            "timestamp": self.timestamp,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AdapterState:
        return cls(
            adapter_id=data["adapter_id"],
            adapter_name=data.get("adapter_name", ""),
            version=data.get("version", ""),
            module_path=data.get("module_path", ""),
            state_data=data.get("state_data", {}),
            timestamp=data.get("timestamp", 0),
            checksum=data.get("checksum", ""),
        )


@dataclass
class VersionRecord:
    """版本记录 — 适配器代码的历史版本"""

    adapter_id: str
    version: int
    adapter_name: str
    code_path: str  # 源码备份路径
    state: AdapterState | None = None
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "version": self.version,
            "adapter_name": self.adapter_name,
            "code_path": self.code_path,
            "state": self.state.to_dict() if self.state else None,
            "timestamp": self.timestamp,
            "success": self.success,
            "error": self.error,
        }


class HotUpdateManager:
    """适配器热更新管理器

    功能:
    - 运行时代码替换: 检测适配器代码变更并热加载
    - 状态保持: 在更新前后保存/恢复适配器运行时状态
    - 版本回退: 维护版本链，支持回退到任意历史版本
    """

    MAX_VERSIONS = 20

    def __init__(
        self, registry: LanguageRegistry | None = None, backup_dir: str | Path | None = None
    ):
        self._registry = registry or get_registry()
        self._backup_dir = (
            Path(backup_dir) if backup_dir else Path.home() / ".yanpub" / "hotupdate_backups"
        )
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._version_chains: dict[str, list[VersionRecord]] = {}
        self._current_versions: dict[str, int] = {}  # adapter_id -> current version number
        self._state_extractors: dict[str, Any] = {}  # adapter_id -> state extractor callback

    # ---- 状态提取/恢复 ----

    def register_state_extractor(self, adapter_id: str, extractor: Any) -> None:
        """注册自定义状态提取器（用于保持运行时状态）"""
        self._state_extractors[adapter_id] = extractor

    def _extract_state(self, adapter_id: str) -> dict:
        """提取适配器当前运行时状态"""
        adapter = self._registry.get(adapter_id)
        if not adapter:
            return {}
        state = {
            "id": adapter.id,
            "name": adapter.name,
            "version": adapter.version,
            "capabilities": adapter.capabilities if hasattr(adapter, "capabilities") else {},
            "keywords": adapter.keywords[:100] if hasattr(adapter, "keywords") else [],
        }
        # 自定义提取器
        extractor = self._state_extractors.get(adapter_id)
        if extractor and callable(extractor):
            try:
                custom_state = extractor(adapter)
                if isinstance(custom_state, dict):
                    state.update(custom_state)
            except Exception:
                pass
        return state

    def _restore_state(self, adapter_id: str, state_data: dict) -> bool:
        """恢复适配器运行时状态（目前仅验证一致性）"""
        adapter = self._registry.get(adapter_id)
        if not adapter:
            return False
        # 验证适配器是否正确加载
        return adapter.id == adapter_id

    # ---- 版本管理 ----

    def _next_version(self, adapter_id: str) -> int:
        current = self._current_versions.get(adapter_id, 0)
        next_v = current + 1
        self._current_versions[adapter_id] = next_v
        return next_v

    def _backup_code(self, adapter_id: str, version: int) -> str:
        """备份适配器源码"""
        adapter = self._registry.get(adapter_id)
        if not adapter:
            return ""
        # 找到适配器模块路径
        module = sys.modules.get(adapter.__class__.__module__)
        if not module or not hasattr(module, "__file__") or not module.__file__:
            return ""
        src_path = Path(module.__file__).parent
        backup_path = self._backup_dir / adapter_id / f"v{version}"
        backup_path.mkdir(parents=True, exist_ok=True)
        # 复制整个适配器目录
        for f in src_path.glob("*"):
            if f.is_file():
                shutil.copy2(f, backup_path / f.name)
        return str(backup_path)

    def _record_version(
        self, adapter_id: str, success: bool = True, error: str = ""
    ) -> VersionRecord:
        """记录一个版本"""
        version = self._next_version(adapter_id)
        adapter = self._registry.get(adapter_id)
        backup_path = ""
        if adapter:
            try:
                backup_path = self._backup_code(adapter_id, version)
            except Exception:
                pass

        state = None
        if adapter:
            state_data = self._extract_state(adapter_id)
            state = AdapterState(
                adapter_id=adapter_id,
                adapter_name=adapter.name,
                version=adapter.version,
                module_path=str(backup_path),
                state_data=state_data,
            )

        record = VersionRecord(
            adapter_id=adapter_id,
            version=version,
            adapter_name=adapter.name if adapter else "",
            code_path=backup_path,
            state=state,
            success=success,
            error=error,
        )

        if adapter_id not in self._version_chains:
            self._version_chains[adapter_id] = []
        self._version_chains[adapter_id].append(record)

        # 限制版本链长度
        if len(self._version_chains[adapter_id]) > self.MAX_VERSIONS:
            self._version_chains[adapter_id] = self._version_chains[adapter_id][
                -self.MAX_VERSIONS :
            ]

        return record

    # ---- 热更新操作 ----

    def update(self, adapter_id: str) -> VersionRecord:
        """执行适配器热更新

        1. 保存当前状态
        2. 备份当前代码
        3. 重新加载适配器
        4. 恢复状态
        """
        adapter = self._registry.get(adapter_id)
        if not adapter:
            return self._record_version(
                adapter_id, success=False, error=f"适配器不存在: {adapter_id}"
            )

        # 1. 提取当前状态
        state_data = self._extract_state(adapter_id)

        # 2. 找到模块并重新加载
        module_name = adapter.__class__.__module__
        try:
            # 清理旧模块缓存
            old_module = sys.modules.get(module_name)
            if old_module:
                # 清理模块及其子模块
                to_remove = [
                    k for k in sys.modules if k == module_name or k.startswith(module_name + ".")
                ]
                for k in to_remove:
                    del sys.modules[k]

                # 重新导入
                new_module = importlib.import_module(module_name)

                # 查找 LanguageAdapter 子类
                from yanpub.core.adapter import (
                    LanguageAdapter as BaseAdapter,
                    SubprocessAdapter,
                    InProcessAdapter,
                    HTTPAdapter,
                )

                _base_classes = {BaseAdapter, SubprocessAdapter, InProcessAdapter, HTTPAdapter}
                best = None
                for attr_name in dir(new_module):
                    attr = getattr(new_module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseAdapter)
                        and attr not in _base_classes
                    ):
                        if best is None or (issubclass(attr, best) and attr is not best):
                            best = attr
                new_adapter = best() if best else None
                if new_adapter:
                    # 注销旧的，注册新的
                    self._registry.unregister(adapter_id)
                    self._registry.register(new_adapter)

                    # 恢复状态
                    self._restore_state(adapter_id, state_data)

                    return self._record_version(adapter_id, success=True)
                else:
                    return self._record_version(
                        adapter_id, success=False, error="重新加载后未找到适配器类"
                    )
            else:
                return self._record_version(
                    adapter_id, success=False, error="模块不在 sys.modules 中"
                )
        except Exception as e:
            return self._record_version(adapter_id, success=False, error=str(e))

    def rollback(self, adapter_id: str, target_version: int | None = None) -> VersionRecord:
        """回退到指定版本（默认回退到上一个版本）"""
        chain = self._version_chains.get(adapter_id, [])
        if not chain:
            return self._record_version(adapter_id, success=False, error="无版本历史")

        if target_version is None:
            # 回退到上一个版本
            if len(chain) < 2:
                return self._record_version(adapter_id, success=False, error="无更早版本可回退")
            target = chain[-2]
        else:
            target = None
            for rec in chain:
                if rec.version == target_version:
                    target = rec
                    break
            if not target:
                return self._record_version(
                    adapter_id, success=False, error=f"版本 {target_version} 不存在"
                )

        if not target.code_path or not Path(target.code_path).exists():
            return self._record_version(
                adapter_id, success=False, error=f"版本 {target.version} 代码备份不存在"
            )

        # 从备份恢复代码
        try:
            backup_dir = Path(target.code_path)
            adapter = self._registry.get(adapter_id)
            if not adapter:
                return self._record_version(adapter_id, success=False, error="适配器不存在")

            module = sys.modules.get(adapter.__class__.__module__)
            if module and hasattr(module, "__file__") and module.__file__:
                current_dir = Path(module.__file__).parent
                # 用备份覆盖当前代码
                for f in backup_dir.glob("*"):
                    if f.is_file():
                        shutil.copy2(f, current_dir / f.name)

                # 重新加载
                return self.update(adapter_id)
            else:
                return self._record_version(adapter_id, success=False, error="无法定位当前模块路径")
        except Exception as e:
            return self._record_version(adapter_id, success=False, error=str(e))

    # ---- 查询 ----

    def list_versions(self, adapter_id: str) -> list[dict]:
        """列出适配器的版本历史"""
        chain = self._version_chains.get(adapter_id, [])
        return [rec.to_dict() for rec in chain]

    def get_current_version(self, adapter_id: str) -> int:
        return self._current_versions.get(adapter_id, 0)

    def get_version_record(self, adapter_id: str, version: int) -> VersionRecord | None:
        for rec in self._version_chains.get(adapter_id, []):
            if rec.version == version:
                return rec
        return None

    def list_all(self) -> dict:
        """列出所有适配器的版本状态"""
        result = {}
        for adapter in self._registry:
            aid = adapter.id
            result[aid] = {
                "name": adapter.name,
                "current_version": self._current_versions.get(aid, 0),
                "version_count": len(self._version_chains.get(aid, [])),
            }
        return result

    def check_for_updates(self) -> list[dict]:
        """检查所有适配器是否有代码变更"""
        from yanpub.core.hotreload import HotReloader

        reloader = HotReloader(self._registry)
        events = reloader.check_and_reload()
        return [
            {
                "adapter_id": e.adapter_id,
                "event_type": e.event_type,
                "success": e.success,
                "error": e.error,
            }
            for e in events
        ]
