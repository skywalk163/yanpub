"""DAP 服务器 — 实现 Debug Adapter Protocol 通信

基于 DAP 协议规范，使用原生 socket + json 实现 JSON-RPC over TCP 通信。
消息格式: Content-Length: {len}\r\n\r\n{json_body}

DAP 协议要点:
- 请求: {"seq": N, "type": "request", "command": "...", "arguments": {...}}
- 响应: {"seq": N, "type": "response", "request_seq": M, "success": true, "body": {...}}
- 事件: {"seq": N, "type": "event", "event": "...", "body": {...}}
"""

from __future__ import annotations

import json
import logging
import socket
import threading
from typing import Optional

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.dev.debugger import DebugAdapter, DebugEvent

logger = logging.getLogger(__name__)


class DAPServer:
    """DAP 服务器 — 实现 Debug Adapter Protocol 通信

    启动 TCP 服务器监听 DAP 客户端连接，
    解析 DAP 消息并路由到 DebugAdapter 处理。
    """

    def __init__(
        self,
        adapter: LanguageAdapter,
        host: str = "127.0.0.1",
        port: int = 4711,
    ):
        self.adapter = adapter
        self.host = host
        self.port = port
        self._debug_adapter = DebugAdapter()
        self._debug_adapter.set_adapter(adapter)
        self._debug_adapter.on_event = self._on_debug_event
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._running = False
        self._seq: int = 1
        self._lock = threading.Lock()

    def start(self) -> None:
        """启动 DAP 服务器（阻塞式）"""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        self._running = True

        logger.info(f"DAP 服务器启动: {self.host}:{self.port}")

        try:
            while self._running:
                self._server_socket.settimeout(1.0)
                try:
                    client, addr = self._server_socket.accept()
                    logger.info(f"DAP 客户端连接: {addr}")
                    self._handle_client(client)
                except socket.timeout:
                    continue
                except OSError:
                    break
        finally:
            self.stop()

    def start_background(self) -> threading.Thread:
        """在后台线程启动 DAP 服务器"""
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        """停止 DAP 服务器"""
        self._running = False
        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
            self._client_socket = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        logger.info("DAP 服务器已停止")

    def _handle_client(self, client: socket.socket) -> None:
        """处理客户端连接"""
        self._client_socket = client
        try:
            while self._running:
                message = self._read_message(client)
                if message is None:
                    break

                response = self._handle_request(message)

                if response is not None:
                    self._send_message(client, response)

                # 发送响应后处理待发送的调试事件
                self._flush_pending_events()
        except (ConnectionResetError, BrokenPipeError, OSError):
            logger.info("DAP 客户端断开连接")
        finally:
            try:
                client.close()
            except Exception:
                pass
            self._client_socket = None

    def _flush_pending_events(self) -> None:
        """发送响应后刷新待发送的调试事件"""
        if self._debug_adapter is None:
            return
        pending = getattr(self._debug_adapter, "_pending_event", None)
        if pending is not None:
            self._debug_adapter._pending_event = None
            # 先发送 initialized 事件（launch 成功后）
            if self._client_socket:
                self._send_event("initialized", {})
            # 再发送调试事件（stopped/exited）
            self._on_debug_event(pending)

    # ---- DAP 消息处理 ----

    def _handle_request(self, request: dict) -> Optional[dict]:
        """处理 DAP 请求，返回响应"""
        command = request.get("command", "")
        args = request.get("arguments", {})
        seq = request.get("seq", 0)

        handler = {
            "initialize": self._cmd_initialize,
            "launch": self._cmd_launch,
            "attach": self._cmd_attach,
            "disconnect": self._cmd_disconnect,
            "setBreakpoints": self._cmd_set_breakpoints,
            "setFunctionBreakpoints": self._cmd_not_supported,
            "setExceptionBreakpoints": self._cmd_set_exception_breakpoints,
            "configurationDone": self._cmd_configuration_done,
            "continue": self._cmd_continue,
            "next": self._cmd_next,
            "stepIn": self._cmd_step_in,
            "stepOut": self._cmd_step_out,
            "threads": self._cmd_threads,
            "stackTrace": self._cmd_stack_trace,
            "scopes": self._cmd_scopes,
            "variables": self._cmd_variables,
            "evaluate": self._cmd_evaluate,
            "terminate": self._cmd_terminate,
        }.get(command)

        if handler is None:
            return self._make_response(seq, command, success=False, message=f"未知命令: {command}")

        try:
            body = handler(args)
            if body is None:
                body = {}
            # launch 和 continue 不立即返回成功响应，先发送事件
            if command == "launch":
                # 先发送 response，再发送 initialized 事件
                return self._make_response(seq, command, success=True, body=body)
            return self._make_response(seq, command, success=True, body=body)
        except Exception as e:
            logger.error(f"处理 DAP 命令 '{command}' 失败: {e}")
            return self._make_response(seq, command, success=False, message=str(e))

    def _on_debug_event(self, event: DebugEvent) -> None:
        """调试事件回调 — 转换为 DAP 事件并发送给客户端"""
        if self._client_socket is None:
            return

        if event.type == "stopped":
            dap_event = {
                "reason": event.reason,
                "threadId": event.thread_id,
                "allThreadsStopped": True,
            }
            self._send_event("stopped", dap_event)

        elif event.type == "continued":
            dap_event = {
                "threadId": event.thread_id,
                "allThreadsContinued": True,
            }
            self._send_event("continued", dap_event)

        elif event.type == "exited":
            dap_event = {
                "exitCode": 0,
            }
            self._send_event("exited", dap_event)
            # 同时发送 terminated 事件
            self._send_event("terminated", {})

        elif event.type == "output":
            dap_event = {
                "category": "stdout",
                "output": event.output,
            }
            self._send_event("output", dap_event)

        elif event.type == "breakpoint":
            dap_event = {
                "reason": event.reason,
                "breakpoint": {
                    "verified": True,
                    "line": event.frames[0].line if event.frames else 0,
                },
            }
            self._send_event("breakpoint", dap_event)

    # ---- DAP 命令实现 ----

    def _cmd_initialize(self, args: dict) -> dict:
        return self._debug_adapter.initialize(args)

    def _cmd_launch(self, args: dict) -> dict:
        result = self._debug_adapter.launch(args)
        # initialized 事件在 _flush_pending_events 中发送
        return result

    def _cmd_attach(self, args: dict) -> dict:
        return self._debug_adapter.attach(args)

    def _cmd_disconnect(self, args: dict) -> dict:
        return self._debug_adapter.disconnect()

    def _cmd_set_breakpoints(self, args: dict) -> dict:
        return self._debug_adapter.set_breakpoints(args)

    def _cmd_set_exception_breakpoints(self, args: dict) -> dict:
        # 接受但不处理异常断点过滤器
        return {}

    def _cmd_configuration_done(self, args: dict) -> dict:
        return {}

    def _cmd_continue(self, args: dict) -> dict:
        return self._debug_adapter.continue_(args)

    def _cmd_next(self, args: dict) -> dict:
        return self._debug_adapter.next_(args)

    def _cmd_step_in(self, args: dict) -> dict:
        return self._debug_adapter.step_in(args)

    def _cmd_step_out(self, args: dict) -> dict:
        return self._debug_adapter.step_out(args)

    def _cmd_threads(self, args: dict) -> dict:
        return {
            "threads": [
                {
                    "id": 1,
                    "name": f"{self.adapter.name} Main Thread",
                }
            ]
        }

    def _cmd_stack_trace(self, args: dict) -> dict:
        return self._debug_adapter.stack_trace(args)

    def _cmd_scopes(self, args: dict) -> dict:
        return self._debug_adapter.scopes(args)

    def _cmd_variables(self, args: dict) -> dict:
        return self._debug_adapter.variables(args)

    def _cmd_evaluate(self, args: dict) -> dict:
        return self._debug_adapter.evaluate(args)

    def _cmd_terminate(self, args: dict) -> dict:
        self._debug_adapter.disconnect()
        return {}

    def _cmd_not_supported(self, args: dict) -> dict:
        return {}

    # ---- DAP 消息协议 ----

    def _read_message(self, sock: socket.socket) -> Optional[dict]:
        """从 socket 读取一条 DAP 消息"""
        # 读取消息头
        header = b""
        while True:
            try:
                byte = sock.recv(1)
                if not byte:
                    return None
                header += byte
                if header.endswith(b"\r\n\r\n"):
                    break
            except (ConnectionResetError, OSError):
                return None

        # 解析 Content-Length
        header_str = header.decode("ascii")
        content_length = 0
        for line in header_str.split("\r\n"):
            if line.startswith("Content-Length:"):
                content_length = int(line.split(":")[1].strip())
                break

        if content_length == 0:
            return None

        # 读取消息体
        body = b""
        while len(body) < content_length:
            chunk = sock.recv(content_length - len(body))
            if not chunk:
                return None
            body += chunk

        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("DAP 消息 JSON 解析失败")
            return None

    def _send_message(self, sock: socket.socket, message: dict) -> None:
        """发送一条 DAP 消息"""
        with self._lock:
            body = json.dumps(message, ensure_ascii=False).encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            try:
                sock.sendall(header + body)
            except (BrokenPipeError, OSError):
                logger.error("DAP 消息发送失败")

    def _make_response(
        self,
        request_seq: int,
        command: str,
        success: bool = True,
        body: dict | None = None,
        message: str = "",
    ) -> dict:
        """构造 DAP 响应"""
        with self._lock:
            seq = self._seq
            self._seq += 1

        response = {
            "seq": seq,
            "type": "response",
            "request_seq": request_seq,
            "command": command,
            "success": success,
        }
        if body:
            response["body"] = body
        if message:
            response["message"] = message
        return response

    def _send_event(self, event_name: str, body: dict) -> None:
        """发送 DAP 事件"""
        if self._client_socket is None:
            return

        with self._lock:
            seq = self._seq
            self._seq += 1

        event = {
            "seq": seq,
            "type": "event",
            "event": event_name,
            "body": body,
        }
        self._send_message(self._client_socket, event)
