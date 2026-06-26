"""LSP 代码导航处理器：Go to Definition / Find References / Call Hierarchy"""

from __future__ import annotations

from typing import Optional

from lsprotocol import types as lsp


class NavigationMixin:
    """代码导航处理器（mixin for YanLanguageServer）"""

    def _register_navigation_handlers(self, server) -> None:
        """注册代码导航处理器（在 _setup_handlers 中调用）"""
        from yanpub.core.dev.navigator import SymbolNavigator

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
                    code,
                    line,
                    column,
                    uri=params.text_document.uri,
                    documents=self._documents,
                )

            if not result:
                return None

            # 转换为 LSP Location 列表
            locations = []
            for loc in result:
                r = loc["range"]
                locations.append(
                    lsp.Location(
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
                    )
                )

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
                    code,
                    line,
                    column,
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
                locations.append(
                    lsp.Location(
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
                    )
                )

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
                    code,
                    line,
                    column,
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
                func_name,
                uri,
                self._documents,
            )

            if not incoming_defs:
                return None

            calls = []
            for caller in incoming_defs:
                caller_item = self._dict_to_call_hierarchy_item(caller)
                # From ranges：调用发生的位置（简化为调用者定义范围）
                from_ranges = [caller_item.range]
                calls.append(
                    lsp.CallHierarchyIncomingCall(
                        from_=caller_item,
                        from_ranges=from_ranges,
                    )
                )

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
                code,
                func_name,
                func_range,
                uri,
                self._documents,
            )

            if not outgoing_defs:
                return None

            calls = []
            for callee in outgoing_defs:
                callee_item = self._dict_to_call_hierarchy_item(callee)
                # To ranges：调用发生的位置（简化为被调用者定义范围）
                to_ranges = [callee_item.range]
                calls.append(
                    lsp.CallHierarchyOutgoingCall(
                        to=callee_item,
                        from_ranges=to_ranges,
                    )
                )

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
