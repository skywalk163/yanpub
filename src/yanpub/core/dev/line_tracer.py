"""逐行追踪执行器 — 调试器的代码执行追踪引擎

基于 Python sys.settrace (InProcessAdapter) 或简化模式 (SubprocessAdapter)
实现断点命中检测、单步执行和调用栈追踪。
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass
from typing import Optional

from yanpub.core.adapter.adapter import InProcessAdapter, LanguageAdapter

# 延迟导入避免循环依赖：DebugSession 在运行时才需要
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yanpub.core.dev.debugger import DebugSession


class _DebugStopException(Exception):
    """调试暂停异常 — 用于中断执行并在断点/单步处停止"""

    def __init__(self, line: int, reason: str):
        self.line = line
        self.reason = reason
        super().__init__(f"Debug stop at line {line}: {reason}")


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

    def __init__(self, adapter: LanguageAdapter, session: "DebugSession"):
        self.adapter = adapter
        self.session = session
        self._stop_on_next: bool = False
        self._step_type: str = ""  # "over" | "into" | "out"
        self._call_depth: int = 0
        self._step_depth: int = 0

    def run_to_breakpoint(self, code: str, breakpoints: list) -> "object":
        """运行到下一个断点

        对 SubprocessAdapter：执行完整代码，无法真正暂停，返回执行结果
        对 InProcessAdapter：使用 sys.settrace 逐行追踪
        """
        from yanpub.core.dev.debugger import Breakpoint, DebugEvent, StackFrame

        if isinstance(self.adapter, InProcessAdapter):
            return self._trace_in_process(code, breakpoints)
        else:
            return self._run_subprocess(code, breakpoints)

    def step_execution(self, code: str, current_line: int, step_type: str) -> "object":
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

    def _run_subprocess(self, code: str, breakpoints: list) -> "object":
        """SubprocessAdapter 的简化调试模式

        执行完整代码，捕获输出和错误行号，模拟断点命中
        """
        from yanpub.core.dev.debugger import Breakpoint, DebugEvent, StackFrame

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
        breakpoints: list,
        stop_on_next: bool = False,
        step_type: str = "",
    ) -> "object":
        """InProcessAdapter 的逐行追踪模式

        使用 Python sys.settrace 实现真正的逐行调试
        """
        from yanpub.core.dev.debugger import Breakpoint, DebugEvent, StackFrame, Variable

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
                frames = self._build_stack_frames(tracer_state, e.line, source_file)
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
    ) -> list:
        """构建调用栈帧列表"""
        from yanpub.core.dev.debugger import StackFrame

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

    def _build_variables(self, local_vars: dict) -> list:
        """构建变量列表"""
        from yanpub.core.dev.debugger import Variable

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
        match = re.search(r"line\s+(\d+)", error_text)
        if match:
            return int(match.group(1))
        return 1
