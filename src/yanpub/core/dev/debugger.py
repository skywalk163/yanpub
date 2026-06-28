"""DAP 调试器框架 — Debug Adapter Protocol 调试会话与执行追踪

基于 DAP (Debug Adapter Protocol) 协议，为中文编程语言提供统一调试能力。
支持断点管理、逐行追踪、变量查看、调用栈追踪等调试功能。

拆分模块：
- yanpub.core.dev.line_tracer — LineTracer 逐行追踪执行器
- yanpub.core.dev.dap_adapter — DebugAdapter DAP 协议适配器
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from yanpub.core.adapter.adapter import InProcessAdapter, LanguageAdapter

if TYPE_CHECKING:
    from yanpub.core.dev.dap_adapter import DebugAdapter as DebugAdapter
    from yanpub.core.dev.line_tracer import LineTracer as LineTracer


__all__ = [
    "Breakpoint",
    "StackFrame",
    "Variable",
    "DebugEvent",
    "LineTracer",
    "_DebugStopException",
    "DebugSession",
    "DebugAdapter",
]


# ---- 延迟 re-export 避免循环依赖 ----


def __getattr__(name: str):
    """从子模块延迟 re-export，保持向后兼容"""
    if name in ("LineTracer", "_DebugStopException"):
        from yanpub.core.dev import line_tracer

        return getattr(line_tracer, name)
    if name == "DebugAdapter":
        from yanpub.core.dev import dap_adapter

        return getattr(dap_adapter, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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

        from yanpub.core.dev.line_tracer import LineTracer

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
            event = self._tracer.step_execution(self._code, self.current_line, step_type)
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
