"""YanLSP Server — 基于 pygls 的通用 LSP 服务

工作方式：
1. 接收 LSP 客户端请求（VSCode 等）
2. 通过 LanguageAdapter 获取语言特定数据
3. 转换为 LSP 协议格式返回

通用能力（无需适配器实现任何代码）：
- 关键字补全：基于 adapter.keywords 自动提供
- 基本诊断：调用 adapter.diagnose() 获取
- 文档追踪：维护打开文档的内容

语言特定能力（需适配器实现对应方法）：
- 语义补全：adapter.complete()
- 精准诊断：adapter.diagnose()
- 悬停文档：adapter.hover()
- 格式化：adapter.format()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.adapter.registry import get_registry, LanguageRegistry

from yanpub.lsp.handlers_core import CoreHandlersMixin
from yanpub.lsp.handlers_navigation import NavigationMixin
from yanpub.lsp.handlers_code_action import CodeActionMixin
from yanpub.lsp.semantic_tokens import SemanticTokensMixin
from yanpub.lsp.folding import FoldingMixin

# Re-export protocol helpers for backward compatibility
from yanpub.lsp.protocol import (  # noqa: F401
    apply_change,
    completion_item_to_lsp,
    diagnostic_to_lsp,
    _completion_item_to_lsp,
    _diagnostic_to_lsp,
    KIND_MAP as _KIND_MAP,
    SEVERITY_MAP as _SEVERITY_MAP,
)

# Re-export semantic token constants for backward compatibility
from yanpub.lsp.semantic_tokens import (  # noqa: F401
    TOKEN_TYPES as _TOKEN_TYPES,
    TOKEN_MODIFIERS as _TOKEN_MODIFIERS,
    TOKEN_TYPE_INDEX as _TOKEN_TYPE_INDEX,
    TOKEN_MOD_INDEX as _TOKEN_MOD_INDEX,
    DEFINITION_KEYWORDS as _DEFINITION_KEYWORDS,
    OPERATOR_CHARS as _OPERATOR_CHARS,
    CN_OPERATORS as _CN_OPERATORS,
)

# Re-export folding constants for backward compatibility
from yanpub.lsp.folding import (  # noqa: F401
    BLOCK_START_KEYWORDS as _BLOCK_START_KEYWORDS,
    BLOCK_END_KEYWORDS as _BLOCK_END_KEYWORDS,
)

logger = logging.getLogger("yanpub.lsp")


class YanLanguageServer(
    CoreHandlersMixin,
    NavigationMixin,
    CodeActionMixin,
    SemanticTokensMixin,
    FoldingMixin,
):
    """统一 LSP 语言服务器

    管理多个语言的 LSP 功能，通过适配器协议获取语言数据。
    使用 mixin 拆分各功能模块。
    """

    def __init__(self, registry: Optional[LanguageRegistry] = None):
        self.registry = registry or get_registry()
        self.server = LanguageServer("yanlsp", "v1.2.0")
        self._documents: dict[str, str] = {}  # uri → 文档内容
        self._document_versions: dict[str, int] = {}  # uri → 版本号
        self._on_document_change: list[Callable] = []  # 文档变更回调列表
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """注册 LSP 请求处理器"""
        self._register_core_handlers(self.server)
        self._register_navigation_handlers(self.server)
        self._register_code_action(self.server)

    def on_document_change(self, callback: Callable) -> None:
        """注册文档变更回调

        回调签名: callback(uri: str, content: str, version: int)
        用途：触发诊断、签名验证等
        """
        self._on_document_change.append(callback)

    def _check_signature_diagnostics(self, uri: str) -> list[lsp.Diagnostic]:
        """检查文件的签名状态，返回签名相关诊断

        如果文件有 .yanpub-sig 伴随文件，验证签名并添加诊断信息。
        """
        try:
            file_path = uri.replace("file://", "").replace("file:", "")
            sig_path = Path(file_path).with_suffix(Path(file_path).suffix + ".yanpub-sig")
        except Exception:
            return []

        if not sig_path.exists():
            return []

        try:
            from yanpub.core.security.signing import CodeSigner, CodeSignature

            signer = CodeSigner()
            sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
            signature = CodeSignature.from_dict(sig_data)

            content = self._documents.get(uri, "")
            if not content:
                content = Path(file_path).read_text(encoding="utf-8")

            valid, message = signer.verify(content, signature)

            if valid:
                # 签名有效 — 信息级别提示
                severity = lsp.DiagnosticSeverity.Information
                msg = f"签名有效: {message}"
            else:
                # 签名无效 — 警告
                severity = lsp.DiagnosticSeverity.Warning
                msg = f"签名验证失败: {message}"

            return [
                lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=0, character=0),
                    ),
                    severity=severity,
                    message=msg,
                    source="yanlsp-sign",
                )
            ]
        except Exception as e:
            logger.debug("签名检查失败: %s", e)
            return [
                lsp.Diagnostic(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=0, character=0),
                    ),
                    severity=lsp.DiagnosticSeverity.Warning,
                    message=f"签名检查错误: {e}",
                    source="yanlsp-sign",
                )
            ]

    def _run_lint_diagnostics(self, uri: str, code: str) -> list[lsp.Diagnostic]:
        """运行 Lint 规则引擎，返回代码风格诊断"""
        try:
            from yanpub.core.dev.linter import LintRuleEngine

            engine = LintRuleEngine()
            adapter = self._get_adapter_for_uri(uri)
            lang_id = adapter.id if adapter else ""
            results = engine.lint(code, lang_id)
            return [diagnostic_to_lsp(r.to_diagnostic()) for r in results]
        except Exception as e:
            logger.debug("Lint 检查失败: %s", e)
            return []

    def _is_block_definition(self, adapter: LanguageAdapter, line: str) -> bool:
        """判断行是否是块定义（如段落、函数、类）"""
        block_keywords = ["段落", "函数", "类", "方法", "定义", "宏定", "函", "构造"]
        for kw in block_keywords:
            if line.startswith(kw) or f" {kw}" in line:
                return True
        return False

    def _get_adapter_for_uri(self, uri: str) -> Optional[LanguageAdapter]:
        """根据文档 URI 推断语言适配器"""
        # 从 URI 提取文件扩展名
        path = Path(uri.replace("file://", "").replace("file:", ""))
        ext = path.suffix.lower()

        for adapter in self.registry:
            if ext in [e.lower() for e in adapter.file_extensions]:
                return adapter

        # 扩展名不匹配时，尝试用所有适配器的第一个
        # （适用于 untitled 文件等情况）
        return None

    def start(self, host: str = "127.0.0.1", port: int = 2087) -> None:
        """启动 LSP 服务器（TCP 模式）"""
        logger.info("YanLSP 启动: %s:%s", host, port)
        self.server.start_tcp(host, port)

    def start_stdio(self) -> None:
        """启动 LSP 服务器（stdio 模式，适用于 VSCode 扩展）"""
        logger.info("YanLSP 启动 (stdio)")
        self.server.start_io()


def create_lsp_server(
    adapter: Optional[LanguageAdapter] = None,
    host: str = "127.0.0.1",
    port: int = 2087,
    mode: str = "tcp",
) -> YanLanguageServer:
    """创建并启动 LSP 服务器

    Args:
        adapter: 指定语言适配器（可选，不指定则注册所有适配器）
        host: TCP 监听地址
        port: TCP 监听端口
        mode: "tcp" 或 "stdio"
    """
    registry = get_registry()

    # 如果指定了适配器，创建只含该适配器的注册中心
    if adapter is not None:
        single_registry = LanguageRegistry()
        single_registry.register(adapter)
        lsp_server = YanLanguageServer(registry=single_registry)
    else:
        lsp_server = YanLanguageServer(registry=registry)

    if mode == "stdio":
        lsp_server.start_stdio()
    else:
        lsp_server.start(host, port)

    return lsp_server
