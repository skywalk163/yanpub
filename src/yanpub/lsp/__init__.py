"""YanLSP — 统一 LSP 服务

基于 pygls 实现通用 LSP 协议，通过 LanguageAdapter 获取语言特定数据。

支持的 LSP 功能：
- textDocument/completion    代码补全（基于适配器关键字 + 语义补全）
- textDocument/diagnostic    代码诊断（基于适配器 diagnose 方法）
- textDocument/hover         悬停文档
- textDocument/formatting    代码格式化
- textDocument/didChange     文档变更追踪
"""


def __getattr__(name):
    if name in ("create_lsp_server", "YanLanguageServer"):
        from yanpub.lsp.server import create_lsp_server, YanLanguageServer

        globals()["create_lsp_server"] = create_lsp_server
        globals()["YanLanguageServer"] = YanLanguageServer
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["create_lsp_server", "YanLanguageServer"]
