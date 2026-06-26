"""言埠 YanPub — 中文编程语言统一基础设施

核心概念：语言即插件。每种中文编程语言只需实现一个轻量适配器，
即可获得完整工具链（Playground / REPL / LSP / 包管理 / 文档站 / VSCode 扩展）。
"""

__version__ = "1.5.0"

from yanpub.core.adapter.adapter import (
    LanguageAdapter,
    SubprocessAdapter,
    InProcessAdapter,
    HTTPAdapter,
    ExecutionResult,
    CompletionItem,
    Diagnostic,
)
from yanpub.core.adapter.registry import LanguageRegistry, get_registry
from yanpub.i18n import t, get_lang, set_lang

__all__ = [
    "__version__",
    # 核心抽象
    "LanguageAdapter",
    "SubprocessAdapter",
    "InProcessAdapter",
    "HTTPAdapter",
    # 数据类
    "ExecutionResult",
    "CompletionItem",
    "Diagnostic",
    # 注册中心
    "LanguageRegistry",
    "get_registry",
    # 国际化
    "t",
    "get_lang",
    "set_lang",
]
