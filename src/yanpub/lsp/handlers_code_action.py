"""LSP 代码操作处理器：Quick Fix / Refactor / 签名"""

from __future__ import annotations

from typing import Optional

from lsprotocol import types as lsp


class CodeActionMixin:
    """代码操作处理器（mixin for YanLanguageServer）"""

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
            actions.append(
                lsp.CodeAction(
                    title="格式化代码",
                    kind=lsp.CodeActionKind.SourceOrganizeImports,
                    data={"uri": params.text_document.uri, "action": "format"},
                )
            )

            # 2. 如果有诊断错误，提供快速修复
            for diag in params.context.diagnostics:
                actions.append(
                    lsp.CodeAction(
                        title=f"忽略: {diag.message[:50]}",
                        kind=lsp.CodeActionKind.QuickFix,
                        data={
                            "uri": params.text_document.uri,
                            "action": "suppress",
                            "diagnostic": diag.message,
                        },
                    )
                )

            # 3. 如果光标在标识符上，提供重命名提示
            line = params.range.start.line + 1
            column = params.range.start.character + 1
            if adapter.rename(code, line, column, "placeholder") is not None:
                actions.append(
                    lsp.CodeAction(
                        title="重命名符号",
                        kind=lsp.CodeActionKind.RefactorRename,
                        data={"uri": params.text_document.uri, "action": "rename"},
                    )
                )

            # 4. 签名操作 — 对文件进行签名
            actions.append(
                lsp.CodeAction(
                    title="签名文件 (yanpub/sign)",
                    kind=lsp.CodeActionKind.Source,
                    data={"uri": params.text_document.uri, "action": "sign"},
                )
            )

            # 5. 验证签名
            actions.append(
                lsp.CodeAction(
                    title="验证签名",
                    kind=lsp.CodeActionKind.Source,
                    data={"uri": params.text_document.uri, "action": "verify-signature"},
                )
            )

            # 6. Extract Function — 当有选中文本时可用
            if params.range.start != params.range.end:
                actions.append(
                    lsp.CodeAction(
                        title="提取为函数 (Extract Function)",
                        kind=lsp.CodeActionKind.RefactorExtract,
                        data={
                            "uri": params.text_document.uri,
                            "action": "extract-function",
                            "start_line": params.range.start.line + 1,
                            "end_line": params.range.end.line + 1,
                        },
                    )
                )

            # 7. Inline Variable — 当光标在变量上时可用
            from yanpub.core.dev.refactor import RefactoringEngine

            engine = RefactoringEngine(adapter)
            ident = engine._is_identifier_at(code, line, column)
            if ident is not None:
                # 检查是否是变量声明（"设X为Y"模式）
                decl = engine._find_variable_declaration(code, ident)
                if decl is not None:
                    actions.append(
                        lsp.CodeAction(
                            title="内联变量 (Inline Variable)",
                            kind=lsp.CodeActionKind.RefactorInline,
                            data={
                                "uri": params.text_document.uri,
                                "action": "inline-variable",
                                "line": line,
                                "column": column,
                            },
                        )
                    )

            return actions

        @server.feature(lsp.CODE_ACTION_RESOLVE)
        def code_action_resolve(params: lsp.CodeAction) -> lsp.CodeAction:
            """解析代码操作 — 执行重构并返回 WorkspaceEdit"""
            data = params.data
            if data is None:
                return params

            action = data.get("action", "")
            uri = data.get("uri", "")
            code = self._documents.get(uri, "")

            if action == "extract-function":
                from yanpub.core.dev.refactor import RefactoringEngine

                engine = RefactoringEngine(self._get_adapter_for_uri(uri))
                start_line = data.get("start_line", 1)
                end_line = data.get("end_line", start_line)

                # 使用默认函数名（可通过后续交互修改）
                new_name = "提取的函数"
                result = engine.extract_function(code, start_line, end_line, new_name)

                # 构造 WorkspaceEdit
                lines = code.split("\n")
                edits = []

                # 1. 在选中代码块之前插入新函数
                # 找到合适的位置：函数定义之前的空行
                insert_pos = 0
                for i in range(start_line - 2, -1, -1):
                    if i < len(lines) and lines[i].strip() == "":
                        insert_pos = i
                        break
                    elif i < len(lines):
                        insert_pos = i
                        break

                # 插入新函数 + 空行
                new_func_text = result["new_function"] + "\n\n"
                edits.append(
                    lsp.TextEdit(
                        range=lsp.Range(
                            start=lsp.Position(line=insert_pos, character=0),
                            end=lsp.Position(line=insert_pos, character=0),
                        ),
                        new_text=new_func_text,
                    )
                )

                # 2. 替换选中代码块为函数调用
                block_start_line = result["range"]["start"]
                block_end_line = result["range"]["end"]
                replacement = result["replacement"]

                # 需要调整行号（因为前面插入了新函数）
                lines_inserted = result["new_function"].count("\n") + 2  # +2 for two newlines
                adjusted_start = block_start_line + lines_inserted
                adjusted_end = block_end_line + lines_inserted

                start_char = 0
                end_char = len(lines[block_end_line]) if block_end_line < len(lines) else 0

                edits.append(
                    lsp.TextEdit(
                        range=lsp.Range(
                            start=lsp.Position(line=adjusted_start, character=start_char),
                            end=lsp.Position(line=adjusted_end, character=end_char),
                        ),
                        new_text=replacement,
                    )
                )

                params.edit = lsp.WorkspaceEdit(changes={uri: edits})

            elif action == "inline-variable":
                from yanpub.core.dev.refactor import RefactoringEngine

                engine = RefactoringEngine(self._get_adapter_for_uri(uri))
                line = data.get("line", 1)
                column = data.get("column", 1)

                result = engine.inline_variable(code, line, column)

                if not result["value"]:
                    return params

                edits = []

                # 1. 删除变量声明行
                decl_range = result["declaration_range"]
                edits.append(
                    lsp.TextEdit(
                        range=lsp.Range(
                            start=lsp.Position(
                                line=decl_range["start"]["line"],
                                character=decl_range["start"]["character"],
                            ),
                            end=lsp.Position(
                                line=decl_range["end"]["line"],
                                character=decl_range["end"]["character"],
                            ),
                        ),
                        new_text="",  # 删除声明
                    )
                )

                # 2. 替换所有使用处为变量值
                value = result["value"]
                for usage in result["usage_ranges"]:
                    edits.append(
                        lsp.TextEdit(
                            range=lsp.Range(
                                start=lsp.Position(
                                    line=usage["start"]["line"],
                                    character=usage["start"]["character"],
                                ),
                                end=lsp.Position(
                                    line=usage["end"]["line"],
                                    character=usage["end"]["character"],
                                ),
                            ),
                            new_text=value,
                        )
                    )

                params.edit = lsp.WorkspaceEdit(changes={uri: edits})

            return params
