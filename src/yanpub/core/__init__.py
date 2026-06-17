"""核心抽象 — 语言适配器协议与注册中心"""

from yanpub.core.adapter import (
    LanguageAdapter,
    ExecutionResult,
    CompletionItem,
    Diagnostic,
    SubprocessAdapter,
    InProcessAdapter,
    HTTPAdapter,
)
from yanpub.core.registry import LanguageRegistry
from yanpub.core.config import YanPubConfig
from yanpub.core.cache import LRUCache, AdapterCache, CacheEntry, get_adapter_cache
from yanpub.core.lazy_loader import LazyAdapter, LazyRegistry
from yanpub.core.pool import ProcessPool, PooledProcess, get_process_pool
from yanpub.core.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxBackend,
    DockerSandbox,
    FreeBSDJailSandbox,
    ProcessSandbox,
    SandboxManager,
)
from yanpub.core.debugger import (
    Breakpoint,
    StackFrame,
    Variable,
    DebugEvent,
    DebugSession,
    DebugAdapter,
    LineTracer,
)
from yanpub.core.dap_server import DAPServer
from yanpub.core.signing import SigningKey, CodeSignature, TrustStore, CodeSigner
from yanpub.core.audit import AuditEntry, AuditLog

__all__ = [
    "LanguageAdapter",
    "ExecutionResult",
    "CompletionItem",
    "Diagnostic",
    "SubprocessAdapter",
    "InProcessAdapter",
    "HTTPAdapter",
    "LanguageRegistry",
    "YanPubConfig",
    "LRUCache",
    "AdapterCache",
    "CacheEntry",
    "get_adapter_cache",
    "LazyAdapter",
    "LazyRegistry",
    "ProcessPool",
    "PooledProcess",
    "get_process_pool",
    "SandboxConfig",
    "SandboxResult",
    "SandboxBackend",
    "DockerSandbox",
    "FreeBSDJailSandbox",
    "ProcessSandbox",
    "SandboxManager",
    "Breakpoint",
    "StackFrame",
    "Variable",
    "DebugEvent",
    "DebugSession",
    "DebugAdapter",
    "LineTracer",
    "DAPServer",
    "SigningKey",
    "CodeSignature",
    "TrustStore",
    "CodeSigner",
    "AuditEntry",
    "AuditLog",
]
