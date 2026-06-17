"""DAP 调试器框架 — Debug Adapter Protocol 调试会话与执行追踪

基于 DAP (Debug Adapter Protocol) 协议，为中文编程语言提供统一调试能力。
支持断点管理、逐行追踪、变量查看、调用栈追踪等调试功能。
"""

from __future__ import annotations

import asyncio
import sys
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from yanpub.core.adapter import InProcessAdapter, LanguageAdapter


# ============================================================
# 数据模型
# ============================================================


@dataclass
class Breakpoint:
    """断点"""

    id: int
    line: int
    column: int = 0
    condition: str = ""  # 条件断点表达式
    hit_count: int = 0  # 命中次数
    verified: bool = True


@dataclass
class StackFrame:
    """调用栈帧"""

    id: int
    name: str
    line: int
    column: int = 0
    source: str = ""  # 文件路径
    module: str = ""


@dataclass
class Variable:
    """变量"""

    name: str
    value: str
    type: str = ""
    scope: str = "local"  # local | global | closure


@dataclass
class DebugEvent:
    """调试事件"""

    type: str  # "stopped" | "continued" | "exited" | "output" | "breakpoint"
    reason: str  # "breakpoint" | "step" | "exception" | "entry"
    thread_id: int = 1
    frames: list[StackFrame] = field(default_factory=list)
    output: str = ""
    variables: list[Variable] = field(default_factory=list)


# ============================================================
# 逐行追踪执行器
# ============================================================


class LineTracer:
    """逐行追踪执行器

    原理：
    1. 将源代码按行分割
    2. 逐行调用适配器的 eval 或使用 Python exec 模式
    3. 在每行执行前检查断点
    4. 在断点处暂停，返回 DebugEvent

    对于 SubprocessAdapter：无法真正逐行执行，使用"运行到断点"模式
    对于 InProcessAdapter：使用 Python 的 sys.settrace 实现真正的逐行调试
    """

    def __init__(self, adapter: LanguageAdapter, session: DebugSession):
        self.adapter = adapter
        self.session = session
        self._stop_on_next: bool = False
        self._step_type: str = ""  # "over" | "into" | "out"
        self._call_depth: int = 0
        self._step_depth: int = 0

    def run_to_breakpoint(self, code: str, breakpoints: list[Breakpoint]) -> DebugEvent:
        """运行到下一个断点

        对 SubprocessAdapter：执行完整代码，无法真正暂停，返回执行结果
        对 InProcessAdapter：使用 sys.settrace 逐行追踪
        """
        if isinstance(self.adapter, InProcessAdapter):
            return self._trace_in_process(code, breakpoints)
        else:
            return self._run_subprocess(code, breakpoints)

    def step_execution(self, code: str, current_line: int, step_type: str) -> DebugEvent:
        """单步执行

        Args:
            code: 源代码
            current_line: 当前行号（1-based）
            step_type: "over" | "into" | "out"
        """
        self._step_type = step_type
        self._stop_on_next = True

        if isinstance(self.adapter, InProcessAdapter):
            return self._trace_in_process(code, [], stop_on_next=True, step_type=step_type)
        else:
            return self._run_subprocess(code, [])

    def _run_subprocess(self, code: str, breakpoints: list[Breakpoint]) -> DebugEvent:
        """SubprocessAdapter 的简化调试模式

        执行完整代码，捕获输出和错误行号，模拟断点命中
        """
        result = self.adapter.eval(code)

        if result.success:
            # 检查是否有断点命中（简化：如果输出包含行号信息则模拟）
            bp_lines = {bp.line for bp in breakpoints}
            if bp_lines:
                # 模拟在第一个断点处停止
                first_bp = min(bp_lines)
                return DebugEvent(
                    type="stopped",
                    reason="breakpoint",
                    thread_id=1,
                    frames=[
                        StackFrame(
                            id=0,
                            name=f"{self.adapter.name}:<module>",
                            line=first_bp,
                            source=self.session.current_source,
                            module=self.adapter.id,
                        )
                    ],
                    output=result.stdout,
                )

            return DebugEvent(
                type="exited",
                reason="",
                thread_id=1,
                output=result.stdout,
            )
        else:
            # 执行错误 — 从 stderr 提取行号
            error_line = self._extract_error_line(result.stderr)
            return DebugEvent(
                type="stopped",
                reason="exception",
                thread_id=1,
                frames=[
                    StackFrame(
                        id=0,
                        name=f"{self.adapter.name}:<module>",
                        line=error_line or 1,
                        source=self.session.current_source,
                        module=self.adapter.id,
                    )
                ],
                output=result.stderr,
            )

    def _trace_in_process(
        self,
        code: str,
        breakpoints: list[Breakpoint],
        stop_on_next: bool = False,
        step_type: str = "",
    ) -> DebugEvent:
        """InProcessAdapter 的逐行追踪模式

        使用 Python sys.settrace 实现真正的逐行调试
        """
        bp_lines = {bp.line for bp in breakpoints}
        bp_conditions = {bp.line: bp.condition for bp in breakpoints if bp.condition}
        output_lines: list[str] = []
        stopped_event: Optional[DebugEvent] = None
        local_vars: dict = {}
        call_stack: list[tuple[str, int, str]] = []  # (name, line, source)

        # 追踪状态
        tracer_state = {
            "stopped": False,
            "stop_reason": "",
            "stop_line": 0,
            "call_depth": 0,
            "step_depth": 0,
            "output_lines": output_lines,
            "local_vars": local_vars,
            "call_stack": call_stack,
        }

        if stop_on_next:
            tracer_state["stopped"] = False  # 会在第一行停止
            # exec() 本身是一个 call，会使 call_depth 从 1 开始
            if step_type == "over":
                tracer_state["step_depth"] = 1  # 在 exec 的同一层级停止
            elif step_type == "into":
                tracer_state["step_depth"] = 0  # 允许进入更深的调用
            elif step_type == "out":
                tracer_state["step_depth"] = 0  # 需要回到更浅的调用深度

        def _trace_calls(frame, event, arg):
            """sys.settrace 的 call 回调"""
            if event == "call":
                tracer_state["call_depth"] += 1
                co = frame.f_code
                func_name = co.co_name
                func_line = frame.f_lineno
                filename = co.co_filename
                tracer_state["call_stack"].append((func_name, func_line, filename))
            elif event == "return":
                tracer_state["call_depth"] -= 1
                if tracer_state["call_stack"]:
                    tracer_state["call_stack"].pop()
            return _trace_lines

        def _trace_lines(frame, event, arg):
            """sys.settrace 的 line 回调"""
            if event != "line":
                return _trace_lines

            line_no = frame.f_lineno

            # 收集局部变量（安全模式，避免某些对象 repr 失败）
            safe_vars = {}
            for k, v in frame.f_locals.items():
                if k.startswith("__"):
                    continue
                try:
                    safe_vars[k] = repr(v)
                except Exception:
                    safe_vars[k] = f"<{type(v).__name__}>"
            tracer_state["local_vars"] = safe_vars

            # 条件断点检查
            if line_no in bp_conditions:
                try:
                    condition_result = eval(
                        bp_conditions[line_no],
                        frame.f_globals,
                        frame.f_locals,
                    )
                    if not condition_result:
                        return _trace_lines  # 条件不满足，继续
                except Exception:
                    pass  # 条件求值失败，当作无条件断点

            # 断点命中检查
            if line_no in bp_lines:
                tracer_state["stopped"] = True
                tracer_state["stop_reason"] = "breakpoint"
                tracer_state["stop_line"] = line_no
                # 请求停止 — 通过抛出异常中断执行
                raise _DebugStopException(line_no, "breakpoint")

            # 单步执行检查
            if stop_on_next:
                current_depth = tracer_state["call_depth"]
                target_depth = tracer_state.get("step_depth", 1)

                if step_type == "into":
                    # step into: 在下一行代码处停止，无论调用深度
                    tracer_state["stopped"] = True
                    tracer_state["stop_reason"] = "step"
                    tracer_state["stop_line"] = line_no
                    raise _DebugStopException(line_no, "step")
                elif step_type == "over":
                    # step over: 在同一调用深度停止
                    if current_depth <= target_depth:
                        tracer_state["stopped"] = True
                        tracer_state["stop_reason"] = "step"
                        tracer_state["stop_line"] = line_no
                        raise _DebugStopException(line_no, "step")
                elif step_type == "out":
                    # step out: 在更浅的调用深度停止
                    if current_depth < target_depth:
                        tracer_state["stopped"] = True
                        tracer_state["stop_reason"] = "step"
                        tracer_state["stop_line"] = line_no
                        raise _DebugStopException(line_no, "step")

            return _trace_lines

        # 执行代码并追踪
        import io

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            sys.settrace(_trace_calls)
            try:
                # 编译代码
                source_file = self.session.current_source or "<debug>"
                compiled = compile(code, source_file, "exec")
                exec(compiled)
            except _DebugStopException as e:
                # 断点或单步命中
                frames = self._build_stack_frames(
                    tracer_state, e.line, source_file
                )
                variables = self._build_variables(tracer_state["local_vars"])
                stopped_event = DebugEvent(
                    type="stopped",
                    reason=e.reason,
                    thread_id=1,
                    frames=frames,
                    output=captured_stdout.getvalue(),
                    variables=variables,
                )
            except Exception:
                # 执行错误
                tb = traceback.format_exc()
                error_line = self._extract_error_line(tb)
                frames = [
                    StackFrame(
                        id=0,
                        name=f"{self.adapter.name}:<module>",
                        line=error_line or 1,
                        source=source_file,
                        module=self.adapter.id,
                    )
                ]
                stopped_event = DebugEvent(
                    type="stopped",
                    reason="exception",
                    thread_id=1,
                    frames=frames,
                    output=tb,
                )
            finally:
                sys.settrace(None)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        if stopped_event:
            return stopped_event

        # 正常执行完成
        return DebugEvent(
            type="exited",
            reason="",
            thread_id=1,
            output=captured_stdout.getvalue(),
            variables=self._build_variables(tracer_state["local_vars"]),
        )

    def _build_stack_frames(
        self, tracer_state: dict, current_line: int, source_file: str
    ) -> list[StackFrame]:
        """构建调用栈帧列表"""
        frames = []
        call_stack = tracer_state.get("call_stack", [])

        # 当前帧
        if call_stack:
            func_name, func_line, filename = call_stack[-1]
            frames.append(
                StackFrame(
                    id=0,
                    name=func_name,
                    line=current_line,
                    source=filename,
                    module=self.adapter.id,
                )
            )
        else:
            frames.append(
                StackFrame(
                    id=0,
                    name=f"{self.adapter.name}:<module>",
                    line=current_line,
                    source=source_file,
                    module=self.adapter.id,
                )
            )

        # 上层帧
        for i, (func_name, func_line, filename) in enumerate(reversed(call_stack[:-1]), 1):
            frames.append(
                StackFrame(
                    id=i,
                    name=func_name,
                    line=func_line,
                    source=filename,
                    module=self.adapter.id,
                )
            )

        return frames

    def _build_variables(self, local_vars: dict) -> list[Variable]:
        """构建变量列表"""
        variables = []
        for name, value_repr in local_vars.items():
            var_type = ""
            # 从 repr 推断类型
            if value_repr.startswith("'") or value_repr.startswith('"'):
                var_type = "str"
            elif value_repr.startswith("["):
                var_type = "list"
            elif value_repr.startswith("{"):
                var_type = "dict"
            elif value_repr in ("True", "False"):
                var_type = "bool"
            elif value_repr == "None":
                var_type = "NoneType"
            else:
                try:
                    float(value_repr)
                    var_type = "number"
                except (ValueError, TypeError):
                    var_type = "object"

            variables.append(
                Variable(
                    name=name,
                    value=value_repr,
                    type=var_type,
                    scope="local",
                )
            )
        return variables

    def _extract_error_line(self, error_text: str) -> int:
        """从错误信息中提取行号"""
        import re

        # Python traceback 格式: File "...", line N
        match = re.search(r'line\s+(\d+)', error_text)
        if match:
            return int(match.group(1))
        return 1


class _DebugStopException(Exception):
    """调试暂停异常 — 用于中断执行并在断点/单步处停止"""

    def __init__(self, line: int, reason: str):
        self.line = line
        self.reason = reason
        super().__init__(f"Debug stop at line {line}: {reason}")


# ============================================================
# 调试会话
# ============================================================


class DebugSession:
    """调试会话 — 管理单次调试的生命周期

    状态转换: created → running → stopped → running → ... → exited
    """

    def __init__(self, adapter: LanguageAdapter, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.adapter = adapter
        self.breakpoints: dict[str, list[Breakpoint]] = {}  # source → breakpoints
        self.state: str = "created"  # created | running | stopped | exited
        self.current_line: int = 0
        self.current_source: str = ""
        self.call_stack: list[StackFrame] = []
        self.variables: dict[str, list[Variable]] = {}  # scope → variables
        self.output_buffer: list[str] = []
        self._tracer: LineTracer | None = None
        self._event_queue: asyncio.Queue[DebugEvent] = asyncio.Queue()
        self._next_bp_id: int = 1
        self._code: str = ""  # 当前调试的代码
        self._lock = threading.Lock()

    def launch(
        self,
        file_path: str,
        args: list[str] | None = None,
        stop_on_entry: bool = False,
    ) -> DebugEvent:
        """启动调试会话"""
        from pathlib import Path

        self.current_source = file_path
        self._code = Path(file_path).read_text(encoding="utf-8")
        self.state = "running"
        self._tracer = LineTracer(self.adapter, self)

        if stop_on_entry:
            self.state = "stopped"
            self.current_line = 1
            return DebugEvent(
                type="stopped",
                reason="entry",
                thread_id=1,
                frames=[
                    StackFrame(
                        id=0,
                        name=f"{self.adapter.name}:<module>",
                        line=1,
                        source=file_path,
                        module=self.adapter.id,
                    )
                ],
            )

        # 获取所有断点
        all_breakpoints = self.breakpoints.get(file_path, [])
        event = self._tracer.run_to_breakpoint(self._code, all_breakpoints)

        if event.type == "stopped":
            self.state = "stopped"
            self.current_line = event.frames[0].line if event.frames else 0
            self.call_stack = event.frames
            self.variables = {"local": event.variables} if event.variables else {}
        elif event.type == "exited":
            self.state = "exited"

        if event.output:
            self.output_buffer.append(event.output)

        return event

    def set_breakpoints(self, source: str, breakpoints: list[dict]) -> list[Breakpoint]:
        """设置断点

        Args:
            source: 文件路径
            breakpoints: [{"line": int, "condition": str?, "hitCount": int?}]
        """
        result = []
        bp_list = []

        for bp_info in breakpoints:
            bp_id = self._next_bp_id
            self._next_bp_id += 1

            bp = Breakpoint(
                id=bp_id,
                line=bp_info["line"],
                column=bp_info.get("column", 0),
                condition=bp_info.get("condition", ""),
                hit_count=bp_info.get("hitCount", 0),
                verified=True,
            )
            bp_list.append(bp)
            result.append(bp)

        self.breakpoints[source] = bp_list
        return result

    def continue_(self) -> DebugEvent:
        """继续执行"""
        if self.state != "stopped":
            return DebugEvent(type="continued", reason="", thread_id=1)

        self.state = "running"
        all_breakpoints = self.breakpoints.get(self.current_source, [])

        if self._tracer:
            event = self._tracer.run_to_breakpoint(self._code, all_breakpoints)
        else:
            # fallback：直接执行
            result = self.adapter.eval(self._code)
            event = DebugEvent(
                type="exited" if result.success else "stopped",
                reason="" if result.success else "exception",
                output=result.stdout or result.stderr,
            )

        if event.type == "stopped":
            self.state = "stopped"
            self.current_line = event.frames[0].line if event.frames else self.current_line
            self.call_stack = event.frames
            self.variables = {"local": event.variables} if event.variables else {}
        elif event.type == "exited":
            self.state = "exited"

        if event.output:
            self.output_buffer.append(event.output)

        return event

    def step_over(self) -> DebugEvent:
        """步过"""
        return self._do_step("over")

    def step_into(self) -> DebugEvent:
        """步入"""
        return self._do_step("into")

    def step_out(self) -> DebugEvent:
        """步出"""
        return self._do_step("out")

    def _do_step(self, step_type: str) -> DebugEvent:
        """执行单步操作"""
        if self.state != "stopped":
            return DebugEvent(type="continued", reason="", thread_id=1)

        self.state = "running"

        if self._tracer:
            event = self._tracer.step_execution(
                self._code, self.current_line, step_type
            )
        else:
            result = self.adapter.eval(self._code)
            event = DebugEvent(
                type="exited" if result.success else "stopped",
                reason="step" if result.success else "exception",
                output=result.stdout or result.stderr,
            )

        if event.type == "stopped":
            self.state = "stopped"
            self.current_line = event.frames[0].line if event.frames else self.current_line
            self.call_stack = event.frames
            self.variables = {"local": event.variables} if event.variables else {}
        elif event.type == "exited":
            self.state = "exited"

        if event.output:
            self.output_buffer.append(event.output)

        return event

    def get_stack_trace(self) -> list[StackFrame]:
        """获取调用栈"""
        return list(self.call_stack)

    def get_variables(self, scope: str = "local") -> list[Variable]:
        """获取变量"""
        return self.variables.get(scope, [])

    def evaluate(self, expression: str) -> dict:
        """在当前调试上下文中求值表达式"""
        result = {"result": "", "variablesReference": 0}

        if self.state != "stopped":
            result["result"] = "(程序未在暂停状态)"
            return result

        # 尝试使用适配器求值
        try:
            eval_result = self.adapter.eval(expression)
            if eval_result.success:
                output = eval_result.stdout.strip()
                result["result"] = output or "(无输出)"
            else:
                result["result"] = eval_result.stderr.strip() or "(求值错误)"
        except Exception as e:
            result["result"] = f"错误: {e}"

        return result

    def terminate(self) -> None:
        """终止调试会话"""
        self.state = "exited"
        self._tracer = None


# ============================================================
# DAP 适配器 — 桥接 yanpub 调试器和 DAP 客户端
# ============================================================


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
