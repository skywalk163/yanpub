"""语言注册中心 — 管理所有已注册的语言适配器"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from yanpub.core.adapter import LanguageAdapter


class LanguageRegistry:
    """语言注册中心

    负责发现、加载和管理所有语言适配器。
    """

    def __init__(self):
        self._adapters: dict[str, LanguageAdapter] = {}

    def register(self, adapter: LanguageAdapter) -> None:
        """注册一个语言适配器"""
        self._adapters[adapter.id] = adapter

    def unregister(self, lang_id: str) -> None:
        """取消注册"""
        self._adapters.pop(lang_id, None)

    def get(self, lang_id: str) -> Optional[LanguageAdapter]:
        """获取指定语言的适配器"""
        return self._adapters.get(lang_id)

    def get_or_raise(self, lang_id: str) -> LanguageAdapter:
        """获取适配器，不存在则抛出 KeyError"""
        adapter = self.get(lang_id)
        if adapter is None:
            available = ", ".join(sorted(self._adapters.keys())) or "(无)"
            raise KeyError(
                f"未注册的语言: '{lang_id}'。可用语言: {available}"
            )
        return adapter

    def list_languages(self) -> list[dict]:
        """列出所有已注册语言的信息"""
        return [
            {
                "id": a.id,
                "name": a.name,
                "version": a.version,
                "extensions": a.file_extensions,
                "capabilities": a.capabilities,
            }
            for a in self._adapters.values()
        ]

    @property
    def language_ids(self) -> list[str]:
        """所有已注册语言的 ID 列表"""
        return sorted(self._adapters.keys())

    def __len__(self) -> int:
        return len(self._adapters)

    def __contains__(self, lang_id: str) -> bool:
        return lang_id in self._adapters

    def __iter__(self):
        return iter(self._adapters.values())


# ---- 全局注册中心实例 ----

_global_registry: Optional[LanguageRegistry] = None


def get_registry() -> LanguageRegistry:
    """获取全局注册中心（懒加载）"""
    global _global_registry
    if _global_registry is None:
        _global_registry = LanguageRegistry()
        _auto_discover(_global_registry)
    return _global_registry


def _auto_discover(registry: LanguageRegistry) -> None:
    """自动发现并加载内置适配器"""
    adapters_dir = Path(__file__).parent.parent / "adapters"
    if not adapters_dir.exists():
        return

    for adapter_dir in sorted(adapters_dir.iterdir()):
        if not adapter_dir.is_dir():
            continue
        if adapter_dir.name.startswith("_"):
            continue

        # 检查是否有 adapter.yaml
        yaml_path = adapter_dir / "adapter.yaml"
        py_path = adapter_dir / "adapter.py"

        if yaml_path.exists() and py_path.exists():
            try:
                adapter = _load_adapter(adapter_dir)
                if adapter:
                    registry.register(adapter)
            except Exception as e:
                import warnings
                warnings.warn(
                    f"加载适配器 '{adapter_dir.name}' 失败: {e}",
                    stacklevel=2,
                )


def _load_adapter(adapter_dir: Path) -> Optional[LanguageAdapter]:
    """从适配器目录加载适配器"""
    import importlib.util

    yaml_path = adapter_dir / "adapter.yaml"
    py_path = adapter_dir / "adapter.py"

    # 读取 adapter.yaml
    with open(yaml_path, encoding="utf-8") as f:
        yaml.safe_load(f)

    # 动态导入 adapter.py
    spec = importlib.util.spec_from_file_location(
        f"yanpub.adapters.{adapter_dir.name}",
        py_path,
    )
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 查找 LanguageAdapter 子类（排除框架内置基类，只取用户适配器）
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
            # 如果有多个子类，取继承层次最深的那个
            if best is None or (issubclass(attr, best) and attr is not best):
                best = attr

    if best is not None:
        return best()

    return None
