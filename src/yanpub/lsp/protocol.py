"""LSP 协议辅助：类型映射、转换函数、增量同步"""

from __future__ import annotations

from typing import Union

from lsprotocol import types as lsp

from yanpub.core.adapter.adapter import CompletionItem, Diagnostic


# ---- 补全项类型映射 ----

KIND_MAP = {
    "keyword": lsp.CompletionItemKind.Keyword,
    "function": lsp.CompletionItemKind.Function,
    "variable": lsp.CompletionItemKind.Variable,
    "type": lsp.CompletionItemKind.Class,
    "module": lsp.CompletionItemKind.Module,
    "constant": lsp.CompletionItemKind.Constant,
    "snippet": lsp.CompletionItemKind.Snippet,
}

# ---- 诊断严重度映射 ----

SEVERITY_MAP = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
    "info": lsp.DiagnosticSeverity.Information,
    "hint": lsp.DiagnosticSeverity.Hint,
}


# ---- 增量同步辅助函数 ----


def apply_change(
    text: str,
    change: Union[
        lsp.TextDocumentContentChangePartial,
        lsp.TextDocumentContentChangeWholeDocument,
    ],
) -> str:
    """将增量变更应用到文档文本

    Args:
        text: 原始文档文本
        change: LSP ContentChangeEvent（含 range 和 text）

    Returns:
        应用变更后的新文档文本

    算法：
    1. 将文本按行分割
    2. 根据 range.start 和 range.end 计算删除范围
    3. 删除范围内的文本
    4. 插入 change.text
    5. 合并回完整文本
    """
    rng = getattr(change, "range", None)
    if rng is None:
        # 无 range 表示全文替换（TextDocumentContentChangeWholeDocument）
        return change.text

    lines = text.split("\n")
    start_line = rng.start.line
    start_char = rng.start.character
    end_line = rng.end.line
    end_char = rng.end.character

    # 边界检查：空文档
    if not lines:
        return change.text

    # 确保 start 不超出范围
    start_line = min(start_line, len(lines) - 1)
    end_line = min(end_line, len(lines) - 1)

    # 取 start 位置之前的文本
    prefix = lines[start_line][:start_char] if start_line < len(lines) else ""

    # 取 end 位置之后的文本
    suffix = lines[end_line][end_char:] if end_line < len(lines) else ""

    # 拼接：前缀 + 新文本 + 后缀
    new_content = prefix + change.text + suffix

    # 重建行列表
    new_lines = new_content.split("\n")

    # 保留 start_line 之前的行和 end_line 之后的行
    result_lines = lines[:start_line] + new_lines + lines[end_line + 1 :]

    return "\n".join(result_lines)


# ---- 适配器数据 → LSP 类型转换 ----


def completion_item_to_lsp(item: CompletionItem) -> lsp.CompletionItem:
    """将适配器 CompletionItem 转为 LSP CompletionItem"""
    return lsp.CompletionItem(
        label=item.label,
        kind=KIND_MAP.get(item.kind, lsp.CompletionItemKind.Text),
        detail=item.detail or None,
        documentation=item.documentation or None,
        insert_text=item.insert_text or item.label,
        insert_text_format=lsp.InsertTextFormat.PlainText,
    )


# 保留旧名作为别名（向后兼容）
_completion_item_to_lsp = completion_item_to_lsp


def diagnostic_to_lsp(diag: Diagnostic) -> lsp.Diagnostic:
    """将适配器 Diagnostic 转为 LSP Diagnostic"""
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=diag.line - 1, character=diag.column - 1),
            end=lsp.Position(line=diag.line - 1, character=diag.column - 1 + 10),
        ),
        severity=SEVERITY_MAP.get(diag.severity, lsp.DiagnosticSeverity.Error),
        message=diag.message,
        source=diag.source or "yanlsp",
    )


# 保留旧名作为别名（向后兼容）
_diagnostic_to_lsp = diagnostic_to_lsp
