"""LSP 核心处理器：初始化、文档同步、补全、诊断、悬停、格式化、重命名、CodeLens"""

from __future__ import annotations

import logging
from typing import Optional

from lsprotocol import types as lsp

from yanpub.lsp.protocol import apply_change, completion_item_to_lsp, diagnostic_to_lsp
from yanpub.lsp.semantic_tokens import (
    TOKEN_TYPES,
    TOKEN_MODIFIERS,
)

logger = logging.getLogger("yanpub.lsp")


class CoreHandlersMixin:
    """核心 LSP 处理器（mixin for YanLanguageServer）"""

    def _register_core_handlers(self, server) -> None:
        """注册核心 LSP 请求处理器"""

        # ---- 初始化 ----
        @server.feature(lsp.INITIALIZE)
        def initialize(params: lsp.InitializeParams) -> lsp.InitializeResult:
            """LSP 初始化 — 声明服务器能力"""
            return lsp.InitializeResult(
                capabilities=lsp.ServerCapabilities(
                    text_document_sync=lsp.TextDocumentSyncOptions(
                        open_close=True,
                        change=lsp.TextDocumentSyncKind.Incremental,
                    ),
                ),
            )

        @server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
        def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
            """文档打开"""
            doc = params.text_document
            self._documents[doc.uri] = doc.text
            self._document_versions[doc.uri] = doc.version or 0
            logger.debug("文档打开: %s (v%d)", doc.uri, self._document_versions[doc.uri])

            # 检查签名伴随文件，发布签名诊断
            sig_diags = self._check_signature_diagnostics(doc.uri)
            # Lint 代码风格检查
            lint_diags = self._run_lint_diagnostics(doc.uri, doc.text)
            all_diags = sig_diags + lint_diags
            if all_diags:
                self.server.publish_diagnostics(doc.uri, all_diags)

        @server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
        def did_change(params: lsp.DidChangeTextDocumentParams) -> None:
            """文档变更（增量同步）"""
            uri = params.text_document.uri
            current = self._documents.get(uri, "")
            version = params.text_document.version or 0

            for change in params.content_changes:
                if change.range is None:
                    # 全文替换
                    current = change.text
                else:
                    # 增量变更
                    current = apply_change(current, change)

            self._documents[uri] = current
            self._document_versions[uri] = version
            logger.debug("文档变更: %s (v%d)", uri, version)

            # 触发文档变更回调
            for callback in self._on_document_change:
                try:
                    callback(uri, current, version)
                except Exception as e:
                    logger.warning("文档变更回调异常: %s", e)

        @server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
        def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
            """文档关闭"""
            uri = params.text_document.uri
            self._documents.pop(uri, None)
            self._document_versions.pop(uri, None)

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

            lsp_items = [completion_item_to_lsp(item) for item in items]
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

            lsp_diags = [diagnostic_to_lsp(d) for d in diags]
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
                    end=lsp.Position(
                        line=params.position.line,
                        character=len(code.split("\n")[params.position.line])
                        if params.position.line < len(code.split("\n"))
                        else 0,
                    ),
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
            return [
                lsp.TextEdit(
                    range=lsp.Range(
                        start=lsp.Position(line=0, character=0),
                        end=lsp.Position(line=len(lines) - 1, character=len(lines[-1])),
                    ),
                    new_text=formatted,
                )
            ]

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
                lsp_edits.append(
                    lsp.TextEdit(
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
                    )
                )

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
                    lenses.append(
                        lsp.CodeLens(
                            range=lsp.Range(
                                start=lsp.Position(line=i, character=0),
                                end=lsp.Position(line=i, character=len(line)),
                            ),
                            command=lsp.Command(
                                title="▶ 运行段落",
                                command="yanpub.runBlock",
                                arguments=[params.text_document.uri, i + 1],
                            ),
                            data={
                                "type": "runBlock",
                                "uri": params.text_document.uri,
                                "line": i + 1,
                            },
                        )
                    )

                # 2. 在包含"打印"/"输出"的行显示 📋 查看输出提示
                output_keywords = ["打印", "输出", "显示", "印"]
                for kw in output_keywords:
                    if kw in stripped:
                        lenses.append(
                            lsp.CodeLens(
                                range=lsp.Range(
                                    start=lsp.Position(line=i, character=0),
                                    end=lsp.Position(line=i, character=len(line)),
                                ),
                                command=lsp.Command(
                                    title="📋 输出语句",
                                    command="yanpub.showOutput",
                                    arguments=[params.text_document.uri, i + 1],
                                ),
                                data={
                                    "type": "output",
                                    "uri": params.text_document.uri,
                                    "line": i + 1,
                                },
                            )
                        )
                        break

            # 3. 在文件顶部添加 ▶ 运行文件 按钮
            if lines:
                lenses.insert(
                    0,
                    lsp.CodeLens(
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
                    ),
                )

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
            token_types=TOKEN_TYPES,
            token_modifiers=TOKEN_MODIFIERS,
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
