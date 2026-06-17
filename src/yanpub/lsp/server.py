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

# ---- 语义高亮（Semantic Tokens）类型定义 ----

_TOKEN_TYPES: list[str] = [
    "keyword", "function", "variable", "type", "module",
    "number", "string", "operator", "comment", "parameter",
    "property", "namespace", "class", "method", "constant",
    "controlFlow", "punctuation",
]

_TOKEN_MODIFIERS: list[str] = [
    "declaration", "definition", "readonly", "static", "deprecated",
    "abstract", "async", "modification", "documentation", "defaultLibrary",
]

# token type 字符串 → 索引映射
_TOKEN_TYPE_INDEX: dict[str, int] = {t: i for i, t in enumerate(_TOKEN_TYPES)}
_TOKEN_MOD_INDEX: dict[str, int] = {m: i for i, m in enumerate(_TOKEN_MODIFIERS)}

# 定义类关键字：这些关键字后面跟着的名称标记为对应的类型
_DEFINITION_KEYWORDS: dict[str, str] = {
    "段落": "function",
    "函数": "function",
    "函": "function",
    "方法": "method",
    "类": "class",
    "定义": "function",
    "宏定": "function",
    "构造": "method",
}

# 运算符集合（中文 + ASCII）
_OPERATOR_CHARS = set("+-*/%=<>!&|^~")
_CN_OPERATORS = {"加", "减", "乘", "除", "取余", "等于", "不等于", "大于", "小于", "且", "或", "非"}


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

            # 检查签名伴随文件，发布签名诊断
            sig_diags = self._check_signature_diagnostics(doc.uri)
            if sig_diags:
                self.server.publish_diagnostics(doc.uri, sig_diags)

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

        # ---- 语义高亮 ----
        _sem_legend = lsp.SemanticTokensLegend(
            token_types=_TOKEN_TYPES,
            token_modifiers=_TOKEN_MODIFIERS,
        )

        @server.feature(
            lsp.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL,
            lsp.SemanticTokensOptions(legend=_sem_legend, full=True),
        )
        def semantic_tokens(
            params: lsp.SemanticTokensParams,
        ) -> lsp.SemanticTokens:
            """语义高亮 — 返回全量语义 token"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            code = self._documents.get(params.text_document.uri, "")
            if adapter is None or not code:
                return lsp.SemanticTokens(data=[])
            data = self._compute_semantic_tokens(adapter, code)
            return lsp.SemanticTokens(data=data)

        # ---- 代码导航 ----
        self._register_navigation_handlers(server)

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

    # ---- 语义高亮逻辑 ----

    def _compute_semantic_tokens(
        self, adapter: LanguageAdapter, code: str
    ) -> list[int]:
        """计算语义 token 数据

        优先使用 adapter.tokenize()；若返回空列表则 fallback 到
        基于关键字和正则的逐行扫描。
        """
        # 尝试适配器词法分析
        try:
            tokens = adapter.tokenize(code)
        except Exception:
            tokens = []

        if tokens:
            return self._tokens_from_adapter(tokens)

        # Fallback：基于关键字和正则的扫描
        return self._tokens_fallback(adapter, code)

    def _tokens_from_adapter(self, tokens: list) -> list[int]:
        """从 adapter.tokenize() 结果生成 SemanticTokens.data"""
        # 内部 token type → LSP token type 索引
        _TYPE_MAP = {
            "keyword": "keyword",
            "identifier": "variable",
            "number": "number",
            "string": "string",
            "operator": "operator",
            "comment": "comment",
            "punctuation": "punctuation",
            "function": "function",
            "class": "class",
            "method": "method",
            "parameter": "parameter",
            "property": "property",
            "type": "type",
            "module": "module",
            "constant": "constant",
            "namespace": "namespace",
            "controlFlow": "controlFlow",
        }

        data: list[int] = []
        prev_line = 0
        prev_char = 0

        for tok in tokens:
            # tok 来自 adapter.TokenInfo 或兼容对象
            tok_type_str = getattr(tok, "type", "variable")
            value = getattr(tok, "value", "")
            line = getattr(tok, "line", 0) - 1  # 0-based
            col = getattr(tok, "column", 0) - 1  # 0-based

            if line < 0:
                line = 0
            if col < 0:
                col = 0

            mapped = _TYPE_MAP.get(tok_type_str, "variable")
            token_type = _TOKEN_TYPE_INDEX.get(mapped, 0)
            length = len(value)

            delta_line = line - prev_line
            delta_char = col if delta_line > 0 else (col - prev_char)

            data.extend([delta_line, delta_char, length, token_type, 0])

            prev_line = line
            prev_char = col

        return data

    def _tokens_fallback(self, adapter: LanguageAdapter, code: str) -> list[int]:
        """基于关键字和正则的 fallback 语义 token 扫描"""
        lines = code.split("\n")
        keyword_set = set(adapter.keywords) if adapter.keywords else set()
        comment_prefix = adapter.comment_syntax or "#"

        # 构建中文关键字正则：按长度降序排列以优先匹配长关键字
        sorted_keywords = sorted(keyword_set, key=len, reverse=True)

        # 中文字符范围（用于标识符识别）
        _CJK = r"\u4e00-\u9fff\u3400-\u4dbf"

        data: list[int] = []
        prev_line = 0
        prev_char = 0

        for line_idx, line in enumerate(lines):
            pos = 0
            line_len = len(line)

            while pos < line_len:
                # 跳过空白
                if line[pos] in " \t\r\n":
                    pos += 1
                    continue

                # 1. 注释行
                if line[pos:].startswith(comment_prefix):
                    length = line_len - pos
                    self._emit_token(data, line_idx, pos, length, "comment", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    break  # 注释后不再扫描此行

                # 2. 字符串字面量
                if line[pos] in ('"', "'", "\u201c", "\u2018"):
                    quote = line[pos]
                    end_quote = quote
                    # 中文引号配对
                    if quote == "\u201c":
                        end_quote = "\u201d"
                    elif quote == "\u2018":
                        end_quote = "\u2019"
                    end_pos = line.find(end_quote, pos + 1)
                    if end_pos == -1:
                        end_pos = line_len  # 未闭合
                    else:
                        end_pos += 1  # 包含结束引号
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "string", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 3. 中文关键字匹配
                matched_kw = False
                for kw in sorted_keywords:
                    if line[pos:].startswith(kw):
                        # 检查关键字后是否是非标识符字符或行尾
                        after_pos = pos + len(kw)
                        if after_pos >= line_len or not (
                            line[after_pos].isalnum()
                            or line[after_pos] == "_"
                            or "\u4e00" <= line[after_pos] <= "\u9fff"
                        ):
                            kw_type = _DEFINITION_KEYWORDS.get(kw, "keyword")
                            self._emit_token(data, line_idx, pos, len(kw), kw_type, prev_line, prev_char)
                            prev_line = line_idx
                            prev_char = pos

                            # 如果是定义类关键字，尝试提取后面的名称
                            if kw in _DEFINITION_KEYWORDS:
                                name_start = after_pos
                                # 跳过空白
                                while name_start < line_len and line[name_start] in " \t":
                                    name_start += 1
                                if name_start < line_len:
                                    name_end = name_start
                                    while name_end < line_len and (
                                        line[name_end].isalnum()
                                        or line[name_end] == "_"
                                        or "\u4e00" <= line[name_end] <= "\u9fff"
                                    ):
                                        name_end += 1
                                    if name_end > name_start:
                                        name_type = _DEFINITION_KEYWORDS[kw]
                                        self._emit_token(data, line_idx, name_start, name_end - name_start, name_type, prev_line, prev_char)
                                        prev_line = line_idx
                                        prev_char = name_start

                            pos = after_pos
                            matched_kw = True
                            break
                if matched_kw:
                    continue

                # 4. 数字字面量
                if line[pos].isdigit():
                    end_pos = pos + 1
                    # 支持小数
                    has_dot = False
                    while end_pos < line_len:
                        ch = line[end_pos]
                        if ch.isdigit():
                            end_pos += 1
                        elif ch == "." and not has_dot:
                            has_dot = True
                            end_pos += 1
                        else:
                            break
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "number", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 5. 运算符
                if line[pos] in _OPERATOR_CHARS:
                    end_pos = pos + 1
                    # 多字符运算符（==, !=, <=, >=, &&, ||）
                    if end_pos < line_len and line[end_pos] in "=&|":
                        end_pos += 1
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "operator", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 6. 中文运算符
                cn_op_matched = False
                for cn_op in sorted(_CN_OPERATORS, key=len, reverse=True):
                    if line[pos:].startswith(cn_op):
                        self._emit_token(data, line_idx, pos, len(cn_op), "operator", prev_line, prev_char)
                        prev_line = line_idx
                        prev_char = pos
                        pos += len(cn_op)
                        cn_op_matched = True
                        break
                if cn_op_matched:
                    continue

                # 7. 标识符（ASCII + 中文）
                if line[pos].isalpha() or line[pos] == "_" or "\u4e00" <= line[pos] <= "\u9fff":
                    end_pos = pos + 1
                    while end_pos < line_len and (
                        line[end_pos].isalnum()
                        or line[end_pos] == "_"
                        or "\u4e00" <= line[end_pos] <= "\u9fff"
                    ):
                        end_pos += 1
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "variable", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 8. 标点和其他字符
                pos += 1

        return data

    @staticmethod
    def _emit_token(
        data: list[int],
        line: int,
        char: int,
        length: int,
        token_type: str,
        prev_line: int,
        prev_char: int,
    ) -> None:
        """向 data 列表追加一个语义 token（5 整数一组）"""
        delta_line = line - prev_line
        delta_char = char if delta_line > 0 else (char - prev_char)
        type_idx = _TOKEN_TYPE_INDEX.get(token_type, 0)
        data.extend([delta_line, delta_char, length, type_idx, 0])

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

            # 4. 签名操作 — 对文件进行签名
            actions.append(lsp.CodeAction(
                title="签名文件 (yanpub/sign)",
                kind=lsp.CodeActionKind.Source,
                data={"uri": params.text_document.uri, "action": "sign"},
            ))

            # 5. 验证签名
            actions.append(lsp.CodeAction(
                title="验证签名",
                kind=lsp.CodeActionKind.Source,
                data={"uri": params.text_document.uri, "action": "verify-signature"},
            ))

            return actions

    # ---- 代码导航逻辑 ----

    def _register_navigation_handlers(self, server) -> None:
        """注册代码导航处理器（在 _setup_handlers 中调用）"""
        from yanpub.core.navigator import SymbolNavigator

        # ---- Go to Definition ----
        @server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
        def definition(params: lsp.DefinitionParams) -> Optional[lsp.Definition]:
            """跳转到定义"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            line = params.position.line + 1
            column = params.position.character + 1

            # 优先使用适配器实现
            try:
                result = adapter.definition(code, line, column)
            except Exception:
                result = None

            # Fallback：使用 SymbolNavigator
            if result is None:
                navigator = SymbolNavigator(keywords=adapter.keywords)
                result = navigator.find_definition(
                    code, line, column,
                    uri=params.text_document.uri,
                    documents=self._documents,
                )

            if not result:
                return None

            # 转换为 LSP Location 列表
            locations = []
            for loc in result:
                r = loc["range"]
                locations.append(lsp.Location(
                    uri=loc["uri"],
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
                ))

            if len(locations) == 1:
                return locations[0]
            return locations

        # ---- Find All References ----
        @server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
        def references(params: lsp.ReferenceParams) -> Optional[list[lsp.Location]]:
            """查找所有引用"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            line = params.position.line + 1
            column = params.position.character + 1

            # 优先使用适配器实现
            try:
                result = adapter.references(code, line, column)
            except Exception:
                result = None

            # Fallback：使用 SymbolNavigator
            if result is None:
                navigator = SymbolNavigator(keywords=adapter.keywords)
                result = navigator.find_references(
                    code, line, column,
                    uri=params.text_document.uri,
                    documents=self._documents,
                    include_declaration=params.context.include_declaration,
                )

            if not result:
                return None

            # 转换为 LSP Location 列表
            locations = []
            for loc in result:
                r = loc["range"]
                locations.append(lsp.Location(
                    uri=loc["uri"],
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
                ))

            return locations

        # ---- Call Hierarchy ----
        @server.feature(
            lsp.TEXT_DOCUMENT_PREPARE_CALL_HIERARCHY,
            lsp.CallHierarchyOptions(),
        )
        def call_hierarchy_prepare(
            params: lsp.CallHierarchyPrepareParams,
        ) -> Optional[list[lsp.CallHierarchyItem]]:
            """准备调用层次"""
            adapter = self._get_adapter_for_uri(params.text_document.uri)
            if adapter is None:
                return None

            code = self._documents.get(params.text_document.uri, "")
            line = params.position.line + 1
            column = params.position.character + 1

            # 优先使用适配器实现
            try:
                result = adapter.call_hierarchy(code, line, column)
            except Exception:
                result = None

            # Fallback：使用 SymbolNavigator
            if result is None:
                navigator = SymbolNavigator(keywords=adapter.keywords)
                result = navigator.find_call_hierarchy(
                    code, line, column,
                    uri=params.text_document.uri,
                    documents=self._documents,
                )

            if not result or "items" not in result:
                return None

            # 转换为 LSP CallHierarchyItem 列表
            items = []
            for item in result["items"]:
                items.append(self._dict_to_call_hierarchy_item(item))

            return items

        @server.feature(lsp.CALL_HIERARCHY_INCOMING_CALLS)
        def call_hierarchy_incoming(
            params: lsp.CallHierarchyIncomingCallsParams,
        ) -> Optional[list[lsp.CallHierarchyIncomingCall]]:
            """调用层次 — 入调用（谁调用了此函数）"""
            item = params.item
            func_name = item.name
            uri = item.uri

            # 从所有文档中搜索调用此函数的函数
            navigator = SymbolNavigator()
            incoming_defs = navigator._find_incoming_calls(
                func_name, uri, self._documents,
            )

            if not incoming_defs:
                return None

            calls = []
            for caller in incoming_defs:
                caller_item = self._dict_to_call_hierarchy_item(caller)
                # From ranges：调用发生的位置（简化为调用者定义范围）
                from_ranges = [caller_item.range]
                calls.append(lsp.CallHierarchyIncomingCall(
                    from_=caller_item,
                    from_ranges=from_ranges,
                ))

            return calls

        @server.feature(lsp.CALL_HIERARCHY_OUTGOING_CALLS)
        def call_hierarchy_outgoing(
            params: lsp.CallHierarchyOutgoingCallsParams,
        ) -> Optional[list[lsp.CallHierarchyOutgoingCall]]:
            """调用层次 — 出调用（此函数调用了谁）"""
            item = params.item
            func_name = item.name
            uri = item.uri

            code = self._documents.get(uri, "")
            if not code:
                return None

            # 构建函数体范围
            func_range = {
                "start": {"line": item.range.start.line, "character": item.range.start.character},
                "end": {"line": item.range.end.line, "character": item.range.end.character},
            }

            navigator = SymbolNavigator()
            outgoing_defs = navigator._find_outgoing_calls(
                code, func_name, func_range, uri, self._documents,
            )

            if not outgoing_defs:
                return None

            calls = []
            for callee in outgoing_defs:
                callee_item = self._dict_to_call_hierarchy_item(callee)
                # To ranges：调用发生的位置（简化为被调用者定义范围）
                to_ranges = [callee_item.range]
                calls.append(lsp.CallHierarchyOutgoingCall(
                    to=callee_item,
                    from_ranges=to_ranges,
                ))

            return calls

    def _dict_to_call_hierarchy_item(self, d: dict) -> lsp.CallHierarchyItem:
        """将字典转为 LSP CallHierarchyItem"""
        r = d["range"]
        sel_range = d.get("selectionRange", r)
        return lsp.CallHierarchyItem(
            name=d["name"],
            kind=d.get("kind", lsp.SymbolKind.Function),
            uri=d["uri"],
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
            selection_range=lsp.Range(
                start=lsp.Position(
                    line=sel_range["start"]["line"],
                    character=sel_range["start"]["character"],
                ),
                end=lsp.Position(
                    line=sel_range["end"]["line"],
                    character=sel_range["end"]["character"],
                ),
            ),
        )

    def _check_signature_diagnostics(self, uri: str) -> list[lsp.Diagnostic]:
        """检查文件的签名状态，返回签名相关诊断

        如果文件有 .yanpub-sig 伴随文件，验证签名并添加诊断信息。
        """
        try:
            file_path = uri.replace("file://", "").replace("file:", "")
            sig_path = Path(file_path).with_suffix(
                Path(file_path).suffix + ".yanpub-sig"
            )
        except Exception:
            return []

        if not sig_path.exists():
            return []

        try:
            from yanpub.core.signing import CodeSigner, CodeSignature

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

            return [lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=0, character=0),
                ),
                severity=severity,
                message=msg,
                source="yanlsp-sign",
            )]
        except Exception as e:
            logger.debug("签名检查失败: %s", e)
            return [lsp.Diagnostic(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=0, character=0),
                ),
                severity=lsp.DiagnosticSeverity.Warning,
                message=f"签名检查错误: {e}",
                source="yanlsp-sign",
            )]

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
