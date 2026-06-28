"""DAP 适配器 — 桥接 yanpub 调试器和 DAP 客户端

实现 DAP 协议的请求/响应/事件机制。
"""

from __future__ import annotations

from typing import Callable, Optional

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.dev.debugger import Breakpoint, DebugEvent, DebugSession, Variable


class DebugAdapter:
    """DAP 适配器 — 桥接 yanpub 调试器和 DAP 客户端

    实现 DAP 协议的请求/响应/事件机制。
    """

    def __init__(self):
        self._session: Optional[DebugSession] = None
        self._adapter: Optional[LanguageAdapter] = None
        self._seq: int = 1
        self._frame_variables: dict[int, dict[str, list[Variable]]] = {}
        self._var_ref_counter: int = 1000
        self._var_refs: dict[int, list[Variable]] = {}
        self._pending_event: Optional[DebugEvent] = None

    def set_adapter(self, adapter: LanguageAdapter) -> None:
        """设置语言适配器"""
        self._adapter = adapter

    # ---- DAP 生命周期 ----

    def initialize(self, params: dict) -> dict:
        """初始化 DAP 会话"""
        return {
            "supportsConfigurationDoneRequest": True,
            "supportsFunctionBreakpoints": False,
            "supportsConditionalBreakpoints": True,
            "supportsHitConditionalBreakpoints": True,
            "supportsEvaluateForHovers": True,
            "supportsStepBack": False,
            "supportsSetVariable": False,
            "supportsRestartFrame": False,
            "supportsGotoTargetsRequest": False,
            "supportsStepInTargetsRequest": False,
            "supportsCompletionsRequest": False,
            "supportsModulesRequest": False,
            "supportsExceptionOptions": True,
            "supportsValueFormattingOptions": False,
            "supportsExceptionInfoRequest": False,
            "supportTerminateDebuggee": True,
            "supportsDelayedStackTraceLoading": False,
            "supportsLoadedSourcesRequest": False,
            "supportsLogPoints": False,
            "supportsTerminateThreadsRequest": False,
            "supportsSetExpression": False,
            "supportsTerminateRequest": True,
            "supportsDataBreakpoints": False,
            "supportsReadMemoryRequest": False,
            "supportsWriteMemoryRequest": False,
            "supportsDisassembleRequest": False,
            "exceptionBreakpointFilters": [
                {
                    "filter": "raised",
                    "label": "Raised Exceptions",
                    "default": True,
                },
                {
                    "filter": "uncaught",
                    "label": "Uncaught Exceptions",
                    "default": True,
                },
            ],
        }

    def launch(self, params: dict) -> dict:
        """启动调试"""
        if self._adapter is None:
            return {"success": False, "message": "未设置语言适配器"}

        self._session = DebugSession(self._adapter)
        file_path = params.get("program", "")
        args = params.get("args", [])
        stop_on_entry = params.get("stopOnEntry", False)

        if not file_path:
            return {"success": False, "message": "未指定程序文件"}

        event = self._session.launch(file_path, args, stop_on_entry)
        # 不在此处发送事件，由调用方（DAP 服务器）在发送响应后处理
        self._pending_event = event

        return {}

    def attach(self, params: dict) -> dict:
        """附加到运行中的进程（暂不支持）"""
        return {"success": False, "message": "attach 模式暂不支持"}

    def disconnect(self) -> dict:
        """断开调试连接"""
        if self._session:
            self._session.terminate()
            self._session = None
        return {}

    # ---- DAP 请求 ----

    def set_breakpoints(self, params: dict) -> dict:
        """设置断点"""
        if self._session is None:
            self._session = DebugSession(self._adapter)

        source = params.get("source", {}).get("path", "")
        if not source:
            return {"breakpoints": []}

        bp_list = params.get("breakpoints", [])
        breakpoints = self._session.set_breakpoints(source, bp_list)

        return {
            "breakpoints": [
                {
                    "id": bp.id,
                    "verified": bp.verified,
                    "line": bp.line,
                    "column": bp.column,
                }
                for bp in breakpoints
            ]
        }

    def continue_(self, params: dict) -> dict:
        """继续执行"""
        if self._session is None:
            return {"allThreadsContinued": False}

        event = self._session.continue_()
        self._pending_event = event

        return {"allThreadsContinued": True}

    def next_(self, params: dict) -> dict:
        """步过"""
        if self._session is None:
            return {}

        event = self._session.step_over()
        self._pending_event = event

        return {}

    def step_in(self, params: dict) -> dict:
        """步入"""
        if self._session is None:
            return {}

        event = self._session.step_into()
        self._pending_event = event

        return {}

    def step_out(self, params: dict) -> dict:
        """步出"""
        if self._session is None:
            return {}

        event = self._session.step_out()
        self._pending_event = event

        return {}

    def stack_trace(self, params: dict) -> dict:
        """获取调用栈"""
        if self._session is None:
            return {"stackFrames": [], "totalFrames": 0}

        frames = self._session.get_stack_trace()
        start_frame = params.get("startFrame", 0)
        levels = params.get("levels", len(frames))

        sliced = frames[start_frame : start_frame + levels]

        dap_frames = []
        for f in sliced:
            dap_frames.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "line": f.line,
                    "column": f.column + 1,  # DAP 列号 1-based
                    "source": {
                        "name": f.module,
                        "path": f.source,
                    },
                }
            )

        return {
            "stackFrames": dap_frames,
            "totalFrames": len(frames),
        }

    def scopes(self, params: dict) -> dict:
        """获取变量作用域"""

        scopes = []
        for scope_name in ("local", "global", "closure"):
            var_ref = self._var_ref_counter
            self._var_ref_counter += 1

            if self._session:
                variables = self._session.get_variables(scope_name)
            else:
                variables = []

            self._var_refs[var_ref] = variables

            scopes.append(
                {
                    "name": scope_name.capitalize(),
                    "variablesReference": var_ref,
                    "namedVariables": len(variables),
                    "indexedVariables": 0,
                    "expensive": scope_name == "global",
                }
            )

        return {"scopes": scopes}

    def variables(self, params: dict) -> dict:
        """获取变量"""
        var_ref = params.get("variablesReference", 0)
        variables = self._var_refs.get(var_ref, [])

        dap_vars = []
        for v in variables:
            var_entry = {
                "name": v.name,
                "value": v.value,
                "variablesReference": 0,
            }
            if v.type:
                var_entry["type"] = v.type
            dap_vars.append(var_entry)

        return {"variables": dap_vars}

    def evaluate(self, params: dict) -> dict:
        """求值表达式"""
        if self._session is None:
            return {"result": "(无活动调试会话)", "variablesReference": 0}

        expression = params.get("expression", "")
        result = self._session.evaluate(expression)

        return {
            "result": result.get("result", ""),
            "variablesReference": result.get("variablesReference", 0),
        }

    # ---- 事件发送 ----

    def _emit_event(self, event: DebugEvent) -> None:
        """发送调试事件"""
        if self.on_event is not None:
            self.on_event(event)

    on_event: Callable[[DebugEvent], None] | None = None
