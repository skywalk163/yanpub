"""延迟加载 — 适配器代理与延迟注册中心

核心能力：
1. LazyAdapter — 延迟加载适配器代理（首次使用时才实例化真实适配器）
2. LazyRegistry — 延迟加载注册中心（注册时不加载，使用时才加载）

设计要点：
- LazyAdapter 使用 __getattr__ 代理模式，对调用方透明
- LazyRegistry 兼容 LanguageRegistry 的主要接口（get / __iter__ / __len__）
- 预加载支持：preload / preload_all
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from yanpub.core.adapter import LanguageAdapter, ExecutionResult, CompletionItem, Diagnostic


class LazyAdapter(LanguageAdapter):
    """延迟加载适配器代理

    不立即加载适配器，只在第一次使用时才加载。
    加载后所有方法调用委托给真实适配器。

    Args:
        adapter_class: 适配器类
        *args: 传给适配器构造器的位置参数
        **kwargs: 传给适配器构造器的关键字参数
    """

    def __init__(self, adapter_class: type, *args, **kwargs):
        self._adapter_class = adapter_class
        self._adapter_args = args
        self._adapter_kwargs = kwargs
        self._real: LanguageAdapter | None = None
        self._loaded = False
        self._load_time_ms: float | None = None
        self._lock = threading.Lock()

    def _load(self) -> LanguageAdapter:
        """延迟加载真实适配器（线程安全）"""
        if self._loaded and self._real is not None:
            return self._real

        with self._lock:
            # 双重检查
            if self._loaded and self._real is not None:
                return self._real

            start = time.monotonic()
            self._real = self._adapter_class(*self._adapter_args, **self._adapter_kwargs)
            elapsed = (time.monotonic() - start) * 1000
            self._load_time_ms = elapsed
            self._loaded = True
            return self._real

    @property
    def _real_adapter(self) -> LanguageAdapter:
        """获取真实适配器（触发加载）"""
        return self._load()

    @property
    def is_loaded(self) -> bool:
        """适配器是否已加载"""
        return self._loaded

    @property
    def load_time_ms(self) -> float | None:
        """加载耗时（毫秒），未加载时返回 None"""
        return self._load_time_ms

    # ---- 代理 LanguageAdapter 属性 ----

    @property
    def name(self) -> str:
        return self._real_adapter.name

    @property
    def id(self) -> str:
        return self._real_adapter.id

    @property
    def version(self) -> str:
        return self._real_adapter.version

    @property
    def file_extensions(self) -> list[str]:
        return self._real_adapter.file_extensions

    @property
    def description(self) -> str:
        return self._real_adapter.description

    @property
    def primary_color(self) -> str:
        return self._real_adapter.primary_color

    @property
    def secondary_color(self) -> str:
        return self._real_adapter.secondary_color

    @property
    def keywords(self) -> list[str]:
        return self._real_adapter.keywords

    @property
    def comment_syntax(self) -> str:
        return self._real_adapter.comment_syntax

    @property
    def repl_prompt(self) -> str:
        return self._real_adapter.repl_prompt

    @property
    def repl_welcome(self) -> str:
        return self._real_adapter.repl_welcome

    @property
    def capabilities(self) -> dict[str, bool]:
        return self._real_adapter.capabilities

    # ---- 代理 LanguageAdapter 方法 ----

    def eval(self, code: str) -> ExecutionResult:
        return self._real_adapter.eval(code)

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        return self._real_adapter.run(file_path, args)

    def complete(self, code: str, line: int, column: int) -> list[CompletionItem]:
        return self._real_adapter.complete(code, line, column)

    def diagnose(self, code: str) -> list[Diagnostic]:
        return self._real_adapter.diagnose(code)

    def tokenize(self, code: str):
        return self._real_adapter.tokenize(code)

    def parse(self, code: str):
        return self._real_adapter.parse(code)

    def hover(self, code: str, line: int, column: int):
        return self._real_adapter.hover(code, line, column)

    def format(self, code: str) -> str:
        return self._real_adapter.format(code)

    def rename(self, code: str, line: int, column: int, new_name: str):
        return self._real_adapter.rename(code, line, column, new_name)

    def definition(self, code: str, line: int, column: int):
        return self._real_adapter.definition(code, line, column)

    def references(self, code: str, line: int, column: int):
        return self._real_adapter.references(code, line, column)

    def call_hierarchy(self, code: str, line: int, column: int):
        return self._real_adapter.call_hierarchy(code, line, column)

    def extract_function(self, code: str, start_line: int, end_line: int, new_name: str):
        return self._real_adapter.extract_function(code, start_line, end_line, new_name)

    def inline_variable(self, code: str, line: int, column: int):
        return self._real_adapter.inline_variable(code, line, column)

    def list_packages(self) -> list[dict]:
        return self._real_adapter.list_packages()

    def install_package(self, name: str, version: Optional[str] = None) -> bool:
        return self._real_adapter.install_package(name, version)

    def __getattr__(self, name: str):
        """代理未显式定义的属性到真实适配器"""
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._real_adapter, name)


class LazyRegistry:
    """延迟加载注册中心

    注册时不实例化适配器，只在 get() 或迭代时才加载。
    与 LanguageRegistry 接口兼容。

    用法:
        registry = LazyRegistry()
        registry.register_lazy(MyAdapter, foo="bar")
        adapter = registry.get("my_lang")  # 此刻才实例化
    """

    def __init__(self):
        self._lazy_adapters: dict[str, LazyAdapter] = {}
        self._lock = threading.Lock()

    def register_lazy(self, adapter_class: type, *args, **kwargs) -> None:
        """注册延迟加载适配器

        不立即实例化，仅在首次使用时加载。

        Args:
            adapter_class: 适配器类
            *args: 传给适配器构造器的位置参数
            **kwargs: 传给适配器构造器的关键字参数
        """
        # 先创建一个临时实例获取 id（轻量操作）
        # 避免完整初始化，但需要知道 lang_id 以注册
        # 方案：先实例化一个 LazyAdapter，从类属性或临时实例获取 id
        lazy = LazyAdapter(adapter_class, *args, **kwargs)
        # 需要先知道 id，触发一次加载来获取
        lang_id = lazy.id
        with self._lock:
            self._lazy_adapters[lang_id] = lazy

    def register(self, adapter: LanguageAdapter) -> None:
        """注册已实例化的适配器（兼容 LanguageRegistry 接口）

        将已有适配器包装为 LazyAdapter（已加载状态）。
        """
        lazy = LazyAdapter(type(adapter))
        lazy._real = adapter
        lazy._loaded = True
        lazy._load_time_ms = 0.0
        with self._lock:
            self._lazy_adapters[adapter.id] = lazy

    def unregister(self, lang_id: str) -> None:
        """取消注册"""
        with self._lock:
            self._lazy_adapters.pop(lang_id, None)

    def get(self, lang_id: str) -> Optional[LanguageAdapter]:
        """获取适配器（触发加载）"""
        lazy = self._lazy_adapters.get(lang_id)
        if lazy is None:
            return None
        return lazy._real_adapter

    def get_or_raise(self, lang_id: str) -> LanguageAdapter:
        """获取适配器，不存在则抛出 KeyError"""
        adapter = self.get(lang_id)
        if adapter is None:
            available = ", ".join(sorted(self._lazy_adapters.keys())) or "(无)"
            raise KeyError(f"未注册的语言: '{lang_id}'。可用语言: {available}")
        return adapter

    def list_languages(self) -> list[dict]:
        """列出所有语言信息（触发所有适配器加载）"""
        result = []
        for lazy in self._lazy_adapters.values():
            adapter = lazy._real_adapter
            result.append({
                "id": adapter.id,
                "name": adapter.name,
                "version": adapter.version,
                "extensions": adapter.file_extensions,
                "capabilities": adapter.capabilities,
            })
        return result

    @property
    def language_ids(self) -> list[str]:
        """所有已注册语言的 ID 列表（不触发加载）"""
        return sorted(self._lazy_adapters.keys())

    @property
    def loaded_count(self) -> int:
        """已加载的适配器数量"""
        return sum(1 for la in self._lazy_adapters.values() if la.is_loaded)

    @property
    def total_count(self) -> int:
        """注册的适配器总数"""
        return len(self._lazy_adapters)

    def preload(self, lang_id: str) -> None:
        """预加载指定适配器"""
        lazy = self._lazy_adapters.get(lang_id)
        if lazy is not None:
            lazy._load()

    def preload_all(self) -> None:
        """预加载所有适配器"""
        for lazy in self._lazy_adapters.values():
            lazy._load()

    def __len__(self) -> int:
        return len(self._lazy_adapters)

    def __contains__(self, lang_id: str) -> bool:
        return lang_id in self._lazy_adapters

    def __iter__(self):
        """迭代所有适配器（触发加载）"""
        for lazy in self._lazy_adapters.values():
            yield lazy._real_adapter
