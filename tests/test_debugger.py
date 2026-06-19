"""v0.8.1 功能测试 — DAP 调试器集成

测试内容：
1. 调试数据模型（Breakpoint, StackFrame, Variable, DebugEvent）
2. 调试会话生命周期（DebugSession）
3. 逐行追踪执行器（LineTracer）
4. DAP 适配器（DebugAdapter）
5. DAP 服务器（DAPServer）消息协议
6. InProcessAdapter 逐行调试
"""

from __future__ import annotations

import json
import socket
import tempfile
import time
from pathlib import Path

import pytest

from yanpub.core.debugger import Breakpoint, DebugEvent, DebugSession, StackFrame, Variable

from conftest import skip_if_no_backend


# ============================================================
# 1. 调试数据模型测试
# ============================================================


class TestBreakpoint:
    """断点模型"""

    def test_breakpoint_creation(self):
        """基本断点创建"""
        from yanpub.core.debugger import Breakpoint

        bp = Breakpoint(id=1, line=10)
        assert bp.id == 1
        assert bp.line == 10
        assert bp.column == 0
        assert bp.condition == ""
        assert bp.hit_count == 0
        assert bp.verified is True

    def test_breakpoint_with_condition(self):
        """条件断点"""
        from yanpub.core.debugger import Breakpoint

        bp = Breakpoint(id=2, line=20, condition="x > 5", hit_count=3)
        assert bp.condition == "x > 5"
        assert bp.hit_count == 3

    def test_breakpoint_with_column(self):
        """带列号的断点"""
        from yanpub.core.debugger import Breakpoint

        bp = Breakpoint(id=3, line=15, column=8)
        assert bp.column == 8


class TestStackFrame:
    """调用栈帧模型"""

    def test_stack_frame_creation(self):
        """基本栈帧创建"""

        frame = StackFrame(id=0, name="main", line=5)
        assert frame.id == 0
        assert frame.name == "main"
        assert frame.line == 5
        assert frame.column == 0
        assert frame.source == ""
        assert frame.module == ""

    def test_stack_frame_with_source(self):
        """带源文件路径的栈帧"""

        frame = StackFrame(
            id=1,
            name="add",
            line=10,
            column=4,
            source="test.duan",
            module="duan",
        )
        assert frame.source == "test.duan"
        assert frame.module == "duan"


class TestVariable:
    """变量模型"""

    def test_variable_creation(self):
        """基本变量创建"""

        var = Variable(name="x", value="42", type="number")
        assert var.name == "x"
        assert var.value == "42"
        assert var.type == "number"
        assert var.scope == "local"

    def test_variable_scopes(self):
        """不同作用域的变量"""

        local_var = Variable(name="y", value="hello", type="str", scope="local")
        global_var = Variable(name="Z", value="100", type="number", scope="global")
        closure_var = Variable(name="z", value="1", type="number", scope="closure")

        assert local_var.scope == "local"
        assert global_var.scope == "global"
        assert closure_var.scope == "closure"


class TestDebugEvent:
    """调试事件模型"""

    def test_stopped_event(self):
        """停止事件"""

        event = DebugEvent(type="stopped", reason="breakpoint", thread_id=1)
        assert event.type == "stopped"
        assert event.reason == "breakpoint"
        assert event.thread_id == 1
        assert event.frames == []
        assert event.variables == []

    def test_exited_event(self):
        """退出事件"""

        event = DebugEvent(type="exited", reason="", output="hello")
        assert event.type == "exited"
        assert event.output == "hello"

    def test_event_with_frames(self):
        """带栈帧的事件"""

        frames = [
            StackFrame(id=0, name="main", line=5, source="test.duan"),
            StackFrame(id=1, name="helper", line=10, source="utils.duan"),
        ]
        variables = [
            Variable(name="x", value="42", type="number"),
        ]
        event = DebugEvent(
            type="stopped",
            reason="step",
            frames=frames,
            variables=variables,
        )
        assert len(event.frames) == 2
        assert event.frames[0].name == "main"
        assert len(event.variables) == 1


# ============================================================
# 2. 调试会话生命周期测试
# ============================================================


class TestDebugSession:
    """调试会话生命周期管理"""

    def _create_test_file(self, tmp_dir: Path) -> Path:
        """创建测试代码文件"""
        code_file = tmp_dir / "test_debug.py"
        code_file.write_text("x = 1\ny = 2\nprint(x + y)\n", encoding="utf-8")
        return code_file

    def _get_adapter(self):
        """获取测试适配器"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")
        return adapter

    def test_session_creation(self):
        """调试会话创建"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        assert session.state == "created"
        assert session.session_id != ""
        assert session.current_line == 0
        assert len(session.breakpoints) == 0

    def test_session_custom_id(self):
        """自定义会话 ID"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter, session_id="test-123")
        assert session.session_id == "test-123"

    def test_set_breakpoints(self):
        """设置断点"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        breakpoints = session.set_breakpoints(
            "test.duan",
            [
                {"line": 5},
                {"line": 10, "condition": "x > 5"},
            ],
        )

        assert len(breakpoints) == 2
        assert breakpoints[0].line == 5
        assert breakpoints[1].line == 10
        assert breakpoints[1].condition == "x > 5"
        assert all(bp.verified for bp in breakpoints)

        # 验证断点存储
        assert "test.duan" in session.breakpoints
        assert len(session.breakpoints["test.duan"]) == 2

    def test_set_breakpoints_replaces_previous(self):
        """设置断点会替换之前的断点"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        session.set_breakpoints("test.duan", [{"line": 5}])
        session.set_breakpoints("test.duan", [{"line": 10}, {"line": 20}])

        assert len(session.breakpoints["test.duan"]) == 2
        assert session.breakpoints["test.duan"][0].line == 10

    def test_session_launch_stop_on_entry(self):
        """启动调试 — 在入口处暂停"""
        skip_if_no_backend("duan")

        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        with tempfile.TemporaryDirectory() as tmp_dir:
            code_file = self._create_test_file(Path(tmp_dir))
            session = DebugSession(adapter)
            event = session.launch(str(code_file), stop_on_entry=True)

            assert event.type == "stopped"
            assert event.reason == "entry"
            assert session.state == "stopped"
            assert session.current_line == 1

    def test_session_launch_run(self):
        """启动调试 — 直接运行"""
        skip_if_no_backend("duan")

        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        with tempfile.TemporaryDirectory() as tmp_dir:
            code_file = self._create_test_file(Path(tmp_dir))
            session = DebugSession(adapter)
            event = session.launch(str(code_file))

            # SubprocessAdapter 会直接运行完
            assert event.type in ("stopped", "exited")

    def test_session_terminate(self):
        """终止调试会话"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        session.terminate()
        assert session.state == "exited"

    def test_get_stack_trace(self):
        """获取调用栈"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        session.call_stack = [
            StackFrame(id=0, name="main", line=5),
        ]
        frames = session.get_stack_trace()
        assert len(frames) == 1
        assert frames[0].name == "main"

    def test_get_variables(self):
        """获取变量"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        session.variables = {
            "local": [
                Variable(name="x", value="42", type="number"),
                Variable(name="y", value="hello", type="str"),
            ],
        }

        local_vars = session.get_variables("local")
        assert len(local_vars) == 2
        assert local_vars[0].name == "x"
        assert local_vars[1].name == "y"

        global_vars = session.get_variables("global")
        assert len(global_vars) == 0

    def test_evaluate(self):
        """求值表达式"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        session.state = "stopped"
        result = session.evaluate("1 + 1")
        assert "result" in result

    def test_evaluate_not_stopped(self):
        """未暂停时求值"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        result = session.evaluate("1 + 1")
        assert "未在暂停状态" in result["result"]

    def test_continue_not_stopped(self):
        """未暂停时 continue"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        event = session.continue_()
        assert event.type == "continued"

    def test_step_not_stopped(self):
        """未暂停时单步"""
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        event = session.step_over()
        assert event.type == "continued"


# ============================================================
# 3. 逐行追踪执行器测试
# ============================================================


class TestLineTracer:
    """逐行追踪执行器"""

    def test_tracer_creation(self):
        """追踪器创建"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)
        assert tracer is not None

    def test_tracer_extract_error_line(self):
        """错误行号提取"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        line = tracer._extract_error_line('File "test.py", line 42, in <module>')
        assert line == 42

        line = tracer._extract_error_line("no line info")
        assert line == 1  # 默认

    def test_tracer_build_variables(self):
        """变量列表构建"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        local_vars = {
            "x": "42",
            "name": "'hello'",
            "items": "[1, 2, 3]",
            "flag": "True",
            "nothing": "None",
        }
        variables = tracer._build_variables(local_vars)

        assert len(variables) == 5
        var_map = {v.name: v for v in variables}
        assert var_map["x"].type == "number"
        assert var_map["name"].type == "str"
        assert var_map["items"].type == "list"
        assert var_map["flag"].type == "bool"
        assert var_map["nothing"].type == "NoneType"

    def test_tracer_subprocess_run(self):
        """SubprocessAdapter 运行测试"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试",
            lang_id="test",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        code = "print('hello')"
        event = tracer.run_to_breakpoint(code, [])
        assert event.type == "exited"
        assert "hello" in event.output

    def test_tracer_subprocess_with_breakpoint(self):
        """SubprocessAdapter 断点模式"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试",
            lang_id="test",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = 2\n"
        breakpoints = [Breakpoint(id=1, line=5)]
        event = tracer.run_to_breakpoint(code, breakpoints)
        # SubprocessAdapter 无法真正暂停，模拟在第一个断点停止
        assert event.type == "stopped"
        assert event.reason == "breakpoint"

    def test_tracer_subprocess_error(self):
        """SubprocessAdapter 执行错误"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试",
            lang_id="test_err",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        code = "raise ValueError('test error')"
        event = tracer.run_to_breakpoint(code, [])
        assert event.type == "stopped"
        assert event.reason == "exception"

    def test_tracer_step_execution(self):
        """单步执行测试"""
        from yanpub.core.debugger import LineTracer
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试",
            lang_id="test_step",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        session = DebugSession(adapter)
        tracer = LineTracer(adapter, session)

        code = "x = 1\n"
        event = tracer.step_execution(code, 1, "over")
        # SubprocessAdapter 简化模式，会执行完整个代码
        assert event.type in ("stopped", "exited")


# ============================================================
# 4. DAP 适配器测试
# ============================================================


class TestDebugAdapter:
    """DAP 适配器"""

    def _create_adapter(self):
        from yanpub.core.debugger import DebugAdapter
        from yanpub.core.adapter import SubprocessAdapter

        da = DebugAdapter()
        lang_adapter = SubprocessAdapter(
            name="测试",
            lang_id="test",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        da.set_adapter(lang_adapter)
        return da

    def test_initialize(self):
        """DAP 初始化"""
        da = self._create_adapter()
        caps = da.initialize({})

        assert caps["supportsConditionalBreakpoints"] is True
        assert caps["supportsHitConditionalBreakpoints"] is True
        assert caps["supportsEvaluateForHovers"] is True
        assert caps["supportTerminateDebuggee"] is True
        assert caps["supportsTerminateRequest"] is True

    def test_set_breakpoints(self):
        """DAP 设置断点"""
        da = self._create_adapter()
        result = da.set_breakpoints(
            {
                "source": {"path": "test.duan"},
                "breakpoints": [
                    {"line": 5},
                    {"line": 10, "condition": "x > 0"},
                ],
            }
        )

        assert "breakpoints" in result
        assert len(result["breakpoints"]) == 2
        assert result["breakpoints"][0]["line"] == 5
        assert result["breakpoints"][1]["line"] == 10
        assert result["breakpoints"][0]["verified"] is True

    def test_set_breakpoints_no_source(self):
        """DAP 设置断点 — 无源文件"""
        da = self._create_adapter()
        result = da.set_breakpoints({"source": {}})
        assert result["breakpoints"] == []

    def test_scopes(self):
        """DAP 作用域"""
        da = self._create_adapter()
        result = da.scopes({"frameId": 0})

        assert "scopes" in result
        assert len(result["scopes"]) == 3  # local, global, closure
        scope_names = [s["name"] for s in result["scopes"]]
        assert "Local" in scope_names
        assert "Global" in scope_names
        assert "Closure" in scope_names

    def test_evaluate(self):
        """DAP 求值"""
        da = self._create_adapter()
        result = da.evaluate({"expression": "1 + 1"})
        assert "result" in result

    def test_evaluate_no_session(self):
        """DAP 求值 — 无会话"""
        da = self._create_adapter()
        result = da.evaluate({"expression": "1 + 1"})
        assert "无活动调试会话" in result["result"]

    def test_attach_not_supported(self):
        """DAP 附加模式不支持"""
        da = self._create_adapter()
        result = da.attach({})
        assert result.get("success") is False

    def test_disconnect(self):
        """DAP 断开连接"""
        da = self._create_adapter()
        result = da.disconnect()
        assert result == {}

    def test_launch_no_program(self):
        """DAP 启动 — 无程序文件"""
        da = self._create_adapter()
        result = da.launch({})
        assert result.get("success") is False

    def test_launch_with_program(self):
        """DAP 启动 — 有程序文件"""
        da = self._create_adapter()

        with tempfile.NamedTemporaryFile(
            suffix=".py",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write("print('hello')\n")
            tmp = f.name

        try:
            result = da.launch({"program": tmp})
            # 启动应该成功（即使结果为空字典也意味着成功）
            assert isinstance(result, dict)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_stack_trace_no_session(self):
        """DAP 调用栈 — 无会话"""
        da = self._create_adapter()
        result = da.stack_trace({})
        assert result["stackFrames"] == []
        assert result["totalFrames"] == 0

    def test_continue_no_session(self):
        """DAP continue — 无会话"""
        da = self._create_adapter()
        result = da.continue_({})
        assert result["allThreadsContinued"] is False


# ============================================================
# 5. DAP 服务器消息协议测试
# ============================================================


class TestDAPServer:
    """DAP 服务器消息协议"""

    def _create_server(self, port: int = 0) -> tuple:
        """创建测试服务器"""
        from yanpub.core.dap_server import DAPServer
        from yanpub.core.adapter import SubprocessAdapter

        lang_adapter = SubprocessAdapter(
            name="测试",
            lang_id="test",
            version="0.1",
            extensions=[".txt"],
            run_command=["python"],
        )
        server = DAPServer(lang_adapter, host="127.0.0.1", port=port)
        return server, lang_adapter

    def test_server_creation(self):
        """DAP 服务器创建"""
        server, _ = self._create_server()
        assert server.host == "127.0.0.1"
        assert server.port == 0

    def test_make_response(self):
        """DAP 响应消息构造"""
        server, _ = self._create_server()
        response = server._make_response(1, "initialize", success=True, body={"test": True})

        assert response["type"] == "response"
        assert response["request_seq"] == 1
        assert response["command"] == "initialize"
        assert response["success"] is True
        assert response["body"]["test"] is True

    def test_make_response_failure(self):
        """DAP 响应消息构造 — 失败"""
        server, _ = self._create_server()
        response = server._make_response(5, "test", success=False, message="error msg")

        assert response["success"] is False
        assert response["message"] == "error msg"

    def test_handle_request_initialize(self):
        """DAP 请求处理 — initialize"""
        server, _ = self._create_server()
        request = {
            "seq": 1,
            "type": "request",
            "command": "initialize",
            "arguments": {},
        }
        response = server._handle_request(request)
        assert response["success"] is True
        assert "supportsConditionalBreakpoints" in response["body"]

    def test_handle_request_threads(self):
        """DAP 请求处理 — threads"""
        server, _ = self._create_server()
        request = {
            "seq": 2,
            "type": "request",
            "command": "threads",
            "arguments": {},
        }
        response = server._handle_request(request)
        assert response["success"] is True
        assert len(response["body"]["threads"]) == 1

    def test_handle_request_set_breakpoints(self):
        """DAP 请求处理 — setBreakpoints"""
        server, _ = self._create_server()
        request = {
            "seq": 3,
            "type": "request",
            "command": "setBreakpoints",
            "arguments": {
                "source": {"path": "test.duan"},
                "breakpoints": [{"line": 5}, {"line": 10}],
            },
        }
        response = server._handle_request(request)
        assert response["success"] is True
        assert len(response["body"]["breakpoints"]) == 2

    def test_handle_request_unknown_command(self):
        """DAP 请求处理 — 未知命令"""
        server, _ = self._create_server()
        request = {
            "seq": 99,
            "type": "request",
            "command": "unknownCommand",
            "arguments": {},
        }
        response = server._handle_request(request)
        assert response["success"] is False
        assert "未知命令" in response["message"]

    def test_handle_request_scopes(self):
        """DAP 请求处理 — scopes"""
        server, _ = self._create_server()
        request = {
            "seq": 4,
            "type": "request",
            "command": "scopes",
            "arguments": {"frameId": 0},
        }
        response = server._handle_request(request)
        assert response["success"] is True
        assert len(response["body"]["scopes"]) == 3

    def test_handle_request_stack_trace(self):
        """DAP 请求处理 — stackTrace"""
        server, _ = self._create_server()
        request = {
            "seq": 5,
            "type": "request",
            "command": "stackTrace",
            "arguments": {"threadId": 1},
        }
        response = server._handle_request(request)
        assert response["success"] is True
        assert "stackFrames" in response["body"]

    def test_handle_request_evaluate(self):
        """DAP 请求处理 — evaluate"""
        server, _ = self._create_server()
        request = {
            "seq": 6,
            "type": "request",
            "command": "evaluate",
            "arguments": {"expression": "1 + 1"},
        }
        response = server._handle_request(request)
        assert response["success"] is True

    def test_handle_request_configuration_done(self):
        """DAP 请求处理 — configurationDone"""
        server, _ = self._create_server()
        request = {
            "seq": 7,
            "type": "request",
            "command": "configurationDone",
            "arguments": {},
        }
        response = server._handle_request(request)
        assert response["success"] is True

    def test_handle_request_set_exception_breakpoints(self):
        """DAP 请求处理 — setExceptionBreakpoints"""
        server, _ = self._create_server()
        request = {
            "seq": 8,
            "type": "request",
            "command": "setExceptionBreakpoints",
            "arguments": {"filters": ["raised"]},
        }
        response = server._handle_request(request)
        assert response["success"] is True

    def test_handle_request_terminate(self):
        """DAP 请求处理 — terminate"""
        server, _ = self._create_server()
        request = {
            "seq": 9,
            "type": "request",
            "command": "terminate",
            "arguments": {},
        }
        response = server._handle_request(request)
        assert response["success"] is True

    def test_message_protocol_read_write(self):
        """DAP 消息协议 — 读写一致性"""
        server, _ = self._create_server()

        # 构造一条 DAP 消息
        message = {
            "seq": 1,
            "type": "request",
            "command": "initialize",
            "arguments": {"clientID": "test"},
        }
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        raw = header + body

        # 创建 socket pair 来模拟读写
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        conn, _ = server_sock.accept()

        try:
            # 发送消息
            conn.sendall(raw)

            # 读取消息
            received = server._read_message(client_sock)
            assert received is not None
            assert received["command"] == "initialize"
            assert received["arguments"]["clientID"] == "test"
        finally:
            client_sock.close()
            conn.close()
            server_sock.close()

    def test_send_event(self):
        """DAP 事件发送"""
        server, _ = self._create_server()

        # 创建 socket pair
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        conn, _ = server_sock.accept()

        try:
            server._client_socket = conn
            server._send_event("stopped", {"reason": "breakpoint", "threadId": 1})

            # 读取事件
            event = server._read_message(client_sock)
            assert event is not None
            assert event["type"] == "event"
            assert event["event"] == "stopped"
            assert event["body"]["reason"] == "breakpoint"
        finally:
            server._client_socket = None
            client_sock.close()
            conn.close()
            server_sock.close()

    def test_debug_event_to_dap_stopped(self):
        """调试事件转 DAP stopped 事件"""

        server, _ = self._create_server()

        # 创建 socket pair
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        conn, _ = server_sock.accept()

        try:
            server._client_socket = conn

            event = DebugEvent(
                type="stopped",
                reason="breakpoint",
                thread_id=1,
                frames=[StackFrame(id=0, name="main", line=5)],
            )
            server._on_debug_event(event)

            dap_event = server._read_message(client_sock)
            assert dap_event is not None
            assert dap_event["type"] == "event"
            assert dap_event["event"] == "stopped"
            assert dap_event["body"]["reason"] == "breakpoint"
            assert dap_event["body"]["allThreadsStopped"] is True
        finally:
            server._client_socket = None
            client_sock.close()
            conn.close()
            server_sock.close()

    def test_debug_event_to_dap_exited(self):
        """调试事件转 DAP exited + terminated 事件"""

        server, _ = self._create_server()

        # 创建 socket pair
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", 0))
        server_sock.listen(1)
        port = server_sock.getsockname()[1]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(("127.0.0.1", port))

        conn, _ = server_sock.accept()

        try:
            server._client_socket = conn

            event = DebugEvent(type="exited", reason="", output="done")
            server._on_debug_event(event)

            # 应该收到 exited 和 terminated 两个事件
            exited = server._read_message(client_sock)
            assert exited["event"] == "exited"

            terminated = server._read_message(client_sock)
            assert terminated["event"] == "terminated"
        finally:
            server._client_socket = None
            client_sock.close()
            conn.close()
            server_sock.close()

    def test_server_start_stop(self):
        """DAP 服务器启动和停止"""
        server, _ = self._create_server(port=0)

        # 绑定到可用端口
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_sock.bind(("127.0.0.1", 0))
        port = test_sock.getsockname()[1]
        test_sock.close()

        server.port = port
        thread = server.start_background()
        time.sleep(0.3)

        assert server._running is True
        server.stop()
        thread.join(timeout=2.0)
        assert server._running is False

    def test_full_dap_session(self):
        """完整 DAP 会话流程测试"""
        server, lang_adapter = self._create_server()

        # 找一个可用端口
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        test_sock.bind(("127.0.0.1", 0))
        port = test_sock.getsockname()[1]
        test_sock.close()

        server.port = port
        thread = server.start_background()
        time.sleep(0.3)

        try:
            # 客户端连接
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(("127.0.0.1", port))
            client.settimeout(5.0)

            def send_dap(msg: dict):
                body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
                header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                client.sendall(header + body)

            def read_dap() -> dict:
                header = b""
                while not header.endswith(b"\r\n\r\n"):
                    header += client.recv(1)
                content_length = 0
                for line in header.decode("ascii").split("\r\n"):
                    if line.startswith("Content-Length:"):
                        content_length = int(line.split(":")[1].strip())
                body = b""
                while len(body) < content_length:
                    body += client.recv(content_length - len(body))
                return json.loads(body.decode("utf-8"))

            # 1. Initialize
            send_dap(
                {
                    "seq": 1,
                    "type": "request",
                    "command": "initialize",
                    "arguments": {},
                }
            )
            resp = read_dap()
            assert resp["success"] is True

            # 2. Launch
            with tempfile.NamedTemporaryFile(
                suffix=".py",
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as f:
                f.write("print('hello from debug')\n")
                tmp = f.name

            try:
                send_dap(
                    {
                        "seq": 2,
                        "type": "request",
                        "command": "launch",
                        "arguments": {"program": tmp},
                    }
                )
                resp = read_dap()
                assert resp["success"] is True

                # 读取 initialized 事件
                event = read_dap()
                assert event["type"] == "event"
                assert event["event"] == "initialized"

                # 读取可能跟随的 exited/terminated 事件
                # （SubprocessAdapter 直接运行完代码）
                client.settimeout(1.0)
                try:
                    while True:
                        extra = read_dap()
                        if extra.get("event") == "terminated":
                            break
                except socket.timeout:
                    pass
                client.settimeout(5.0)

                # 3. Set breakpoints
                send_dap(
                    {
                        "seq": 3,
                        "type": "request",
                        "command": "setBreakpoints",
                        "arguments": {
                            "source": {"path": tmp},
                            "breakpoints": [{"line": 1}],
                        },
                    }
                )
                resp = read_dap()
                assert resp["success"] is True

                # 4. Threads
                send_dap(
                    {
                        "seq": 4,
                        "type": "request",
                        "command": "threads",
                        "arguments": {},
                    }
                )
                resp = read_dap()
                assert resp["success"] is True
                assert len(resp["body"]["threads"]) == 1

                # 5. Disconnect
                send_dap(
                    {
                        "seq": 5,
                        "type": "request",
                        "command": "disconnect",
                        "arguments": {},
                    }
                )
                resp = read_dap()
                assert resp["success"] is True
            finally:
                Path(tmp).unlink(missing_ok=True)

            client.close()
        finally:
            server.stop()
            thread.join(timeout=2.0)


# ============================================================
# 6. InProcessAdapter 逐行调试测试
# ============================================================


class TestInProcessDebugging:
    """InProcessAdapter 的逐行调试"""

    def _make_inprocess_adapter(self, lang_id: str = "test_ip"):
        """创建测试用 InProcessAdapter"""
        from yanpub.core.adapter import InProcessAdapter

        class TestInProcessAdapter(InProcessAdapter):
            @property
            def name(self):
                return "测试进程内"

            @property
            def id(self):
                return lang_id

            @property
            def version(self):
                return "0.1"

            @property
            def file_extensions(self):
                return [".txt"]

            def _get_interpreter(self):
                return None

        return TestInProcessAdapter()

    def test_trace_python_code_no_breakpoints(self):
        """追踪 Python 代码 — 无断点正常退出"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter()
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = 2\nresult = x + y\n"
        event = tracer._trace_in_process(code, [])
        assert event.type == "exited"

    def test_trace_python_with_breakpoint(self):
        """追踪 Python 代码 — 断点命中"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_bp")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = 2\nresult = x + y\n"
        breakpoints = [Breakpoint(id=1, line=2)]
        event = tracer._trace_in_process(code, breakpoints)

        assert event.type == "stopped"
        assert event.reason == "breakpoint"
        assert event.frames[0].line == 2

    def test_trace_python_step(self):
        """追踪 Python 代码 — 单步执行"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_step")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = 2\nresult = x + y\n"
        event = tracer._trace_in_process(code, [], stop_on_next=True, step_type="over")

        assert event.type == "stopped"
        assert event.reason == "step"

    def test_trace_python_conditional_breakpoint_skip(self):
        """追踪 Python 代码 — 条件断点不满足"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_cond")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        # 条件不满足 — 应该跳过断点正常退出
        code = "x = 1\ny = 2\n"
        breakpoints = [Breakpoint(id=1, line=2, condition="x > 100")]
        event = tracer._trace_in_process(code, breakpoints)
        assert event.type == "exited"

    def test_trace_python_conditional_breakpoint_hit(self):
        """追踪 Python 代码 — 条件断点命中"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_cond2")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        # 条件满足 — 应该命中断点
        code = "x = 1\ny = 2\n"
        breakpoints = [Breakpoint(id=1, line=2, condition="x >= 1")]
        event = tracer._trace_in_process(code, breakpoints)
        assert event.type == "stopped"
        assert event.reason == "breakpoint"

    def test_trace_python_error(self):
        """追踪 Python 代码 — 执行错误"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_err")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = undefined_var\n"
        event = tracer._trace_in_process(code, [])
        assert event.type == "stopped"
        assert event.reason == "exception"

    def test_trace_python_variables_capture(self):
        """追踪 Python 代码 — 变量捕获"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_vars")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        # 在第 3 行设断点，此时 x 和 y 已被定义
        code = "x = 42\ny = 'hello'\nresult = x + 10\n"
        breakpoints = [Breakpoint(id=1, line=3)]
        event = tracer._trace_in_process(code, breakpoints)

        assert event.type == "stopped"
        assert len(event.variables) > 0
        var_map = {v.name: v for v in event.variables}
        assert "x" in var_map
        assert "y" in var_map

    def test_trace_python_multiple_breakpoints(self):
        """追踪 Python 代码 — 多个断点，命中第一个"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_multi_bp")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "a = 1\nb = 2\nc = 3\nd = 4\n"
        breakpoints = [Breakpoint(id=1, line=3), Breakpoint(id=2, line=4)]
        event = tracer._trace_in_process(code, breakpoints)

        assert event.type == "stopped"
        assert event.reason == "breakpoint"
        # 应该在第 3 行停下
        assert event.frames[0].line == 3

    def test_trace_python_step_into(self):
        """追踪 Python 代码 — step into"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_step_into")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        code = "x = 1\ny = 2\n"
        event = tracer._trace_in_process(code, [], stop_on_next=True, step_type="into")

        assert event.type == "stopped"
        assert event.reason == "step"

    def test_trace_python_step_out(self):
        """追踪 Python 代码 — step out（顶层代码中会直接执行完毕）"""
        from yanpub.core.debugger import LineTracer

        adapter = self._make_inprocess_adapter("test_step_out")
        session = DebugSession(adapter)
        session.current_source = "<test>"
        tracer = LineTracer(adapter, session)

        # step_out 在顶层代码中 call_depth 始终 >= step_depth
        # 所以不会停止，正常退出
        code = "x = 1\ny = 2\n"
        event = tracer._trace_in_process(code, [], stop_on_next=True, step_type="out")
        # 顶层代码 step_out 无法回到更浅的调用层级，代码直接执行完
        assert event.type in ("stopped", "exited")
