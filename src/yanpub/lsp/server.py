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

import logging
from pathlib import Path
from typing import Optional

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer

from yanpub.core.adapter import LanguageAdapter, CompletionItem, Diagnostic
from yanpub.core.registry import get_registry, LanguageRegistry

logger = logging.getLogger("yanpub.lsp")


# ---- 适配器数据 → LSP 类型转换 ----

_KIND_MAP = {
    "keyword": lsp.CompletionItemKind.Keyword,
    "function": lsp.CompletionItemKind.Function,
    "variable": lsp.CompletionItemKind.Variable,
    "type": lsp.CompletionItemKind.Class,
    "module": lsp.CompletionItemKind.Module,
    "constant": lsp.CompletionItemKind.Constant,
    "snippet": lsp.CompletionItemKind.Snippet,
}

_SEVERITY_MAP = {
    "error": lsp.DiagnosticSeverity.Error,
    "warning": lsp.DiagnosticSeverity.Warning,
    "info": lsp.DiagnosticSeverity.Information,
    "hint": lsp.DiagnosticSeverity.Hint,
}


def _completion_item_to_lsp(item: CompletionItem) -> lsp.CompletionItem:
    """将适配器 CompletionItem 转为 LSP CompletionItem"""
    return lsp.CompletionItem(
        label=item.label,
        kind=_KIND_MAP.get(item.kind, lsp.CompletionItemKind.Text),
        detail=item.detail or None,
        documentation=item.documentation or None,
        insert_text=item.insert_text or item.label,
        insert_text_format=lsp.InsertTextFormat.PlainText,
    )


def _diagnostic_to_lsp(diag: Diagnostic) -> lsp.Diagnostic:
    """将适配器 Diagnostic 转为 LSP Diagnostic"""
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=diag.line - 1, character=diag.column - 1),
            end=lsp.Position(line=diag.line - 1, character=diag.column - 1 + 10),
        ),
        severity=_SEVERITY_MAP.get(diag.severity, lsp.DiagnosticSeverity.Error),
        message=diag.message,
        source=diag.source or "yanlsp",
    )


class YanLanguageServer:
    """统一 LSP 语言服务器

    管理多个语言的 LSP 功能，通过适配器协议获取语言数据。
    """

    def __init__(self, registry: Optional[LanguageRegistry] = None):
        self.registry = registry or get_registry()
        self.server = LanguageServer("yanlsp", "v0.1.0")
        self._documents: dict[str, str] = {}  # uri → 文档内容
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """注册 LSP 请求处理器"""
        server = self.server

        # ---- 初始化 ----
        @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
        def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
            """文档打开"""
            doc = params.text_document
            self._documents[doc.uri] = doc.text
            logger.debug("文档打开: %s", doc.uri)

        @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
            """文档变更"""
            # 取最后一个变更作为当前内容
            if params.content_changes:
                # 如果是全文更新
                change = params.content_changes[-1]
                if change.range is None:
                    self._documents[params.text_document.uri] = change.text
                else:
                    # 增量更新（简化处理：直接用最新全文）
                    # 实际生产中应该做增量计算
                    self._documents[params.text_document.uri] = change.text

        @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
        def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
            """文档关闭"""
            self._documents.pop(params.text_document.uri, None)

        # ---- 补全 ----
        @server.feature(
            lsp.TEXT_DOCUMENT_COMPLETION,
            lsp.CompletionOptions(trigger_characters=[" ", ".", "（"]),
        )
        def completions(params: lsp.CompletionParams) -> lsp.CompletionList:
            """代码补全"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return lsp.CompletionList(is_incomplete=False, items=[])

            code = self._documents.get(params.text_document.uri, "")
            line = params.position.line + 1
            column = params.position.character + 1

            try:
                items = adapter.complete(code, line, column)
            except Exception as e:
                logger.warning("补全失败: %s", e)
                items = []

            lsp_items = [_completion_item_to_lsp(item) for item in items]
            return lsp.CompletionList(is_incomplete=False, items=lsp_items)

        # ---- 诊断 ----
        @server.feature(lsp.TEXT_DOCUMENT_DIAGNOSTIC)
        def diagnostics(params: lsp.DocumentDiagnosticParams) -> lsp.DocumentDiagnosticReport:
            """代码诊断"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return lsp.DocumentDiagnosticReport(
                    kind=lsp.DocumentDiagnosticReportKind.Full,
                    items=[],
                )

            code = self._documents.get(params.text_document.uri, "")
            try:
                diags = adapter.diagnose(code)
            except Exception as e:
                logger.warning("诊断失败: %s", e)
                diags = []

            lsp_diags = [_diagnostic_to_lsp(d) for d in diags]
            return lsp.DocumentDiagnosticReport(
                kind=lsp.DocumentDiagnosticReportKind.Full,
                items=lsp_diags,
            )

        # ---- 悬停 ----
        @server.feature(lsp.TEXT_DOCUMENT_HOVER)
        def hover(params: lsp.HoverParams) -> Optional[lsp.Hover]:
            """悬停文档"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            line = params.position.line + 1
            column = params.position.character + 1

            try:
                doc = adapter.hover(code, line, column)
            except Exception:
                doc = None

            if doc is None:
                return None

            return lsp.Hover(
                contents=lsp.MarkupContent(
                    kind=lsp.MarkupKind.Markdown,
                    value=doc,
                ),
                range=lsp.Range(
                    start=lsp.Position(line=params.position.line, character=0),
                    end=lsp.Position(line=params.position.line, character=len(code.split("\n")[params.position.line]) if params.position.line < len(code.split("\n")) else 0),
                ),
            )

        # ---- 格式化 ----
        @server.feature(lsp.TEXT_DOCUMENT_FORMATTING)
        def formatting(params: lsp.DocumentFormattingParams) -> Optional[list[lsp.TextEdit]]:
            """代码格式化"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            try:
                formatted = adapter.format(code)
            except Exception:
                return None

            if formatted == code:
                return None

            # 替换整个文档
            lines = code.split("\n")
            return [lsp.TextEdit(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=len(lines) - 1, character=len(lines[-1])),
                ),
                new_text=formatted,
            )]

        # ---- 重命名 ----
        @server.feature(lsp.TEXT_DOCUMENT_RENAME)
        def rename(params: lsp.RenameParams) -> Optional[lsp.WorkspaceEdit]:
            """符号重命名"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            try:
                edits = adapter.rename(
                    code,
                    params.position.line + 1,
                    params.position.character + 1,
                    params.new_name,
                )
            except Exception:
                return None

            if not edits:
                return None

            # 转换为 LSP TextEdit 列表
            lsp_edits = []
            for edit in edits:
                r = edit["range"]
                lsp_edits.append(lsp.TextEdit(
                    range=lsp.Range(
                        start=lsp.Position(
                            line=r["start"]["line"],
                            character=r["start"]["character"],
                        ),
                        end=lsp.Position(
                            line=r["end"]["line"],
                            character=r["end"]["character"],
                        ),
                    ),
                    new_text=edit["newText"],
                ))

            return lsp.WorkspaceEdit(
                changes={params.text_document.uri: lsp_edits},
            )

        # ---- 代码透镜（Code Lens）----
        @server.feature(
            lsp.TEXT_DOCUMENT_CODE_LENS,
            lsp.CodeLensOptions(resolve_provider=True),
        )
        def code_lens(params: lsp.CodeLensParams) -> Optional[list[lsp.CodeLens]]:
            """代码透镜：在编辑器中显示行内提示和操作按钮"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            if not code:
                return None

            lenses = []
            lines = code.split("\n")

            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue

                # 跳过纯注释行
                comment_prefix = adapter.comment_syntax or "#"
                if stripped.startswith(comment_prefix):
                    continue

                # 1. 在段言的"段落"定义行显示 ▶ 运行按钮
                if self._is_block_definition(adapter, stripped):
                    lenses.append(lsp.CodeLens(
                        range=lsp.Range(
                            start=lsp.Position(line=i, character=0),
                            end=lsp.Position(line=i, character=len(line)),
                        ),
                        command=lsp.Command(
                            title="▶ 运行段落",
                            command="yanpub.runBlock",
                            arguments=[params.text_document.uri, i + 1],
                        ),
                        data={"type": "runBlock", "uri": params.text_document.uri, "line": i + 1},
                    ))

                # 2. 在包含"打印"/"输出"的行显示 📋 查看输出提示
                output_keywords = ["打印", "输出", "显示", "印"]
                for kw in output_keywords:
                    if kw in stripped:
                        lenses.append(lsp.CodeLens(
                            range=lsp.Range(
                                start=lsp.Position(line=i, character=0),
                                end=lsp.Position(line=i, character=len(line)),
                            ),
                            command=lsp.Command(
                                title="📋 输出语句",
                                command="yanpub.showOutput",
                                arguments=[params.text_document.uri, i + 1],
                            ),
                            data={"type": "output", "uri": params.text_document.uri, "line": i + 1},
                        ))
                        break

            # 3. 在文件顶部添加 ▶ 运行文件 按钮
            if lines:
                lenses.insert(0, lsp.CodeLens(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=0, character=0),
                    ),
                    command=lsp.Command(
                        title="▶ 运行文件",
                        command="yanpub.runFile",
                        arguments=[params.text_document.uri],
                    ),
                    data={"type": "runFile", "uri": params.text_document.uri},
                ))

            return lenses

        @server.feature(lsp.CODE_LENS_RESOLVE)
        def code_lens_resolve(params: lsp.CodeLens) -> lsp.CodeLens:
            """解析代码透镜（为未解析的 CodeLens 补充信息）"""
            # 当前所有 CodeLens 在创建时已包含 command，无需额外解析
            return params

        # ---- 代码折叠 ----
        @server.feature(
            lsp.TEXT_DOCUMENT_FOLDING_RANGE,
            lsp.FoldingRangeOptions(),
        )
        def folding_range(params: lsp.FoldingRangeParams) -> Optional[list[lsp.FoldingRange]]:
            """代码折叠 — 基于块关键字识别折叠区域"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            if not code:
                return None

            return self._compute_folding_ranges(adapter, code)

        # ---- 代码操作 ----
        self._register_code_action(server)

    # ---- 代码折叠逻辑 ----

    # 块开始关键字（这些关键字开启一个新的可折叠区域）
    _BLOCK_START_KEYWORDS: list[str] = [
        "段落", "函数", "类", "方法", "定义", "宏定", "构造",
        "当", "遍历", "循环", "对于", "如果", "若", "尝试",
        "否则", "否则若", "否则如果", "捕获", "最终",
    ]

    # 块结束关键字
    _BLOCK_END_KEYWORDS: list[str] = [
        "结束", "完", "完毕",
    ]

    def _compute_folding_ranges(
        self, adapter: LanguageAdapter, code: str
    ) -> list[lsp.FoldingRange]:
        """计算代码折叠区域

        算法：
        1. 扫描每一行，检测块开始/结束关键字
        2. 用栈追踪嵌套的块开始行
        3. 遇到块结束关键字时，弹出栈顶，生成折叠范围
        """
        lines = code.split("\n")
        ranges: list[lsp.FoldingRange] = []

        # 构建适配器特定的块关键字集
        adapter_keywords = set(adapter.keywords) if adapter.keywords else set()
        start_kws = [kw for kw in self._BLOCK_START_KEYWORDS if kw in adapter_keywords or not adapter_keywords]
        end_kws = [kw for kw in self._BLOCK_END_KEYWORDS if kw in adapter_keywords or not adapter_keywords]

        # 如果适配器没有关键字，使用默认的块关键字集
        if not start_kws:
            start_kws = self._BLOCK_START_KEYWORDS
        if not end_kws:
            end_kws = self._BLOCK_END_KEYWORDS

        # 额外从适配器关键字中推断块开始关键字
        # 带有冒号结尾的行通常是块开始
        comment_prefix = adapter.comment_syntax or "#"

        # 栈：每个元素是 (start_line_0based, indent_level)
        stack: list[tuple[int, int]] = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith(comment_prefix):
                continue

            # 计算缩进级别
            indent = len(line) - len(line.lstrip())

            # 检查是否是块开始行
            is_block_start = False
            for kw in start_kws:
                if stripped.startswith(kw) or f" {kw}" in stripped:
                    is_block_start = True
                    break

            # 冒号/中文冒号结尾也视为块开始
            if stripped.endswith((":", "：")):
                is_block_start = True

            if is_block_start:
                stack.append((i, indent))

            # 检查是否是块结束行
            is_block_end = False
            for kw in end_kws:
                if stripped.startswith(kw) or stripped == kw:
                    is_block_end = True
                    break

            if is_block_end and stack:
                start_line, start_indent = stack.pop()
                # 折叠范围：从块开始行到当前行
                # LSP FoldingRange: start_line 和 end_line 都是 0-based
                if i > start_line:
                    ranges.append(lsp.FoldingRange(
                        start_line=start_line,
                        end_line=i,
                        kind=lsp.FoldingRangeKind.Region,
                    ))

        # 处理未闭合的块（缩进恢复到更浅级别时闭合）
        # 简化实现：对于没有显式结束关键字的代码，使用缩进推断
        if stack:
            # 未闭合的块 — 尝试用缩进推断折叠范围
            for start_line, start_indent in stack:
                # 查找下一个缩进回到 start_indent 或更浅的行
                end_line = start_line
                for j in range(start_line + 1, len(lines)):
                    if not lines[j].strip() or lines[j].strip().startswith(comment_prefix):
                        continue
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent <= start_indent:
                        break
                    end_line = j
                if end_line > start_line:
                    ranges.append(lsp.FoldingRange(
                        start_line=start_line,
                        end_line=end_line,
                        kind=lsp.FoldingRangeKind.Region,
                    ))

        return ranges

    # ---- 代码操作 ----

    def _register_code_action(self, server) -> None:
        """注册代码操作处理器（在 _setup_handlers 中调用）"""
        @server.feature(lsp.TEXT_DOCUMENT_CODE_ACTION)
        def code_action(params: lsp.CodeActionParams) -> Optional[list[lsp.CodeAction]]:
            """代码操作（快速修复、重构等）"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return []

            actions = []
            code = self._documents.get(params.text_document.uri, "")

            # 1. 格式化操作（始终提供）
            actions.append(lsp.CodeAction(
                title="格式化代码",
                kind=lsp.CodeActionKind.SourceOrganizeImports,
                data={"uri": params.text_document.uri, "action": "format"},
            ))

            # 2. 如果有诊断错误，提供快速修复
            for diag in params.context.diagnostics:
                actions.append(lsp.CodeAction(
                    title=f"忽略: {diag.message[:50]}",
                    kind=lsp.CodeActionKind.QuickFix,
                    data={"uri": params.text_document.uri, "action": "suppress", "diagnostic": diag.message},
                ))

            # 3. 如果光标在标识符上，提供重命名提示
            line = params.range.start.line + 1
            column = params.range.start.character + 1
            if adapter.rename(code, line, column, "placeholder") is not None:
                actions.append(lsp.CodeAction(
                    title="重命名符号",
                    kind=lsp.CodeActionKind.RefactorRename,
                    data={"uri": params.text_document.uri, "action": "rename"},
                ))

            return actions

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
        from yanpub.core.registry import LanguageRegistry
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
