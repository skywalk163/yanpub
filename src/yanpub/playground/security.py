"""Playground 安全中间件

提供 CORS、请求限流、代码长度限制、WebSocket origin 校验等安全防护。
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("yanpub.playground.security")

# ---------------------------------------------------------------------------
# 配置（可通过环境变量覆盖）
# ---------------------------------------------------------------------------

# 代码最大长度（字符数）
MAX_CODE_LENGTH = int(os.environ.get("YANPUB_MAX_CODE_LENGTH", "65536"))

# 请求体最大长度（字节）
MAX_BODY_SIZE = int(os.environ.get("YANPUB_MAX_BODY_SIZE", str(512 * 1024)))

# 限流：每 IP 每分钟最大请求数
RATE_LIMIT_PER_MINUTE = int(os.environ.get("YANPUB_RATE_LIMIT", "60"))

# 限流：执行类端点每 IP 每分钟最大请求数（更严格）
EXEC_RATE_LIMIT_PER_MINUTE = int(os.environ.get("YANPUB_EXEC_RATE_LIMIT", "10"))

# 执行类端点
EXEC_ENDPOINTS = {"/api/run", "/api/sandbox/run", "/ws/run"}

# WebSocket 允许的 origin（逗号分隔，空表示允许所有）
_ws_origins_env = os.environ.get("YANPUB_WS_ORIGINS", "")
ALLOWED_WS_ORIGINS: list[str] = [o.strip() for o in _ws_origins_env.split(",") if o.strip()]

# CORS 允许的 origins（逗号分隔，空表示允许所有即 *）
_cors_origins_env = os.environ.get("YANPUB_CORS_ORIGINS", "")
CORS_ORIGINS: list[str] = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]

# sandbox 参数安全限制
SANDBOX_MAX_TIMEOUT = float(os.environ.get("YANPUB_SANDBOX_MAX_TIMEOUT", "120"))
SANDBOX_ALLOWED_BACKENDS = {"auto", "process", "docker", "podman"}
SANDBOX_MAX_MEMORY_MB = int(os.environ.get("YANPUB_SANDBOX_MAX_MEMORY_MB", "2048"))


# ---------------------------------------------------------------------------
# CORS 中间件
# ---------------------------------------------------------------------------


def _add_cors_middleware(app: FastAPI) -> None:
    """添加 CORS 中间件"""
    origins = CORS_ORIGINS if CORS_ORIGINS else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,
    )


# ---------------------------------------------------------------------------
# 请求限流
# ---------------------------------------------------------------------------


@dataclass
class _RateBucket:
    """简易令牌桶：每分钟重置"""

    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 IP 的请求限流中间件

    对普通 API 限流 RATE_LIMIT_PER_MINUTE 次/分钟，
    对执行类端点限流 EXEC_RATE_LIMIT_PER_MINUTE 次/分钟。
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._general: dict[str, _RateBucket] = defaultdict(_RateBucket)
        self._exec: dict[str, _RateBucket] = defaultdict(_RateBucket)

    def _check_and_count(self, ip: str, path: str) -> tuple[bool, int]:
        """返回 (是否放行, 当前窗口计数)"""
        now = time.monotonic()
        is_exec = path in EXEC_ENDPOINTS
        store = self._exec if is_exec else self._general
        limit = EXEC_RATE_LIMIT_PER_MINUTE if is_exec else RATE_LIMIT_PER_MINUTE

        bucket = store[ip]
        if now - bucket.window_start >= 60.0:
            bucket.count = 0
            bucket.window_start = now

        bucket.count += 1
        if bucket.count > limit:
            return False, bucket.count
        return True, bucket.count

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # WebSocket 由 ASGI 层处理，不经过此中间件
        if path.startswith("/ws/"):
            return await call_next(request)

        allowed, count = self._check_and_count(ip, path)
        if not allowed:
            logger.warning("限流触发: ip=%s path=%s count=%d", ip, path, count)
            return JSONResponse(
                {"error": "请求过于频繁，请稍后再试"},
                status_code=429,
                headers={"Retry-After": "60"},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# 请求体大小 + 代码长度限制
# ---------------------------------------------------------------------------


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """限制请求体大小，并对执行类端点校验代码长度"""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path

        # 只检查 POST 请求
        if request.method != "POST":
            return await call_next(request)

        # 读取请求体
        body = await request.body()
        if len(body) > MAX_BODY_SIZE:
            logger.warning("请求体过大: path=%s size=%d", path, len(body))
            return JSONResponse(
                {"error": f"请求体过大，最大允许 {MAX_BODY_SIZE // 1024}KB"},
                status_code=413,
            )

        # 对执行类端点校验代码长度
        if path in EXEC_ENDPOINTS and body:
            try:
                import json

                data = json.loads(body)
                code = data.get("code", "")
                if len(code) > MAX_CODE_LENGTH:
                    logger.warning("代码过长: path=%s len=%d", path, len(code))
                    return JSONResponse(
                        {"error": f"代码过长，最大允许 {MAX_CODE_LENGTH} 字符"},
                        status_code=413,
                    )
            except (json.JSONDecodeError, AttributeError):
                pass  # 非 JSON 请求，跳过

        return await call_next(request)


# ---------------------------------------------------------------------------
# WebSocket Origin 校验（ASGI 中间件层）
# ---------------------------------------------------------------------------


class WSOriginValidator:
    """ASGI 中间件：校验 WebSocket 握手的 Origin 头

    仅在 ALLOWED_WS_ORIGINS 非空时生效。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket" and ALLOWED_WS_ORIGINS:
            origin = None
            for header_name, header_value in scope.get("headers", []):
                if header_name == b"origin":
                    origin = header_value.decode("latin-1")
                    break

            if origin and origin not in ALLOWED_WS_ORIGINS:
                logger.warning("WebSocket origin 拒绝: origin=%s", origin)
                await send({"type": "websocket.close", "code": 1008, "reason": "Origin not allowed"})
                return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# WebSocket 连接数限制
# ---------------------------------------------------------------------------

MAX_WS_CONNECTIONS = int(os.environ.get("YANPUB_MAX_WS_CONNECTIONS", "50"))
_active_ws: set[int] = set()


def acquire_ws_slot() -> bool:
    """获取 WebSocket 连接槽位，返回是否成功"""
    if len(_active_ws) >= MAX_WS_CONNECTIONS:
        return False
    _active_ws.add(id(object()))  # 使用临时 id，实际由调用方管理
    return True


def release_ws_slot(slot_id: int) -> None:
    """释放 WebSocket 连接槽位"""
    _active_ws.discard(slot_id)


class WSConnectionLimiter:
    """ASGI 中间件：限制 WebSocket 并发连接数"""

    def __init__(self, app: ASGIApp, max_connections: int = MAX_WS_CONNECTIONS) -> None:
        self.app = app
        self.max_connections = max_connections
        self._active: set[int] = set()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            if len(self._active) >= self.max_connections:
                logger.warning(
                    "WebSocket 连接数超限: current=%d max=%d",
                    len(self._active),
                    self.max_connections,
                )
                await send({"type": "websocket.close", "code": 1013, "reason": "Too many connections"})
                return

            conn_id = id(scope)
            self._active.add(conn_id)
            try:
                await self.app(scope, receive, send)
            finally:
                self._active.discard(conn_id)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# sandbox 参数安全校验
# ---------------------------------------------------------------------------


def validate_sandbox_params(body: dict) -> str | None:
    """校验 sandbox 执行参数安全性，返回错误信息或 None"""

    # backend 白名单
    backend = body.get("backend", "auto")
    if backend not in SANDBOX_ALLOWED_BACKENDS:
        return f"不支持的沙箱后端: {backend}，允许: {', '.join(sorted(SANDBOX_ALLOWED_BACKENDS))}"

    # timeout 上限
    timeout = body.get("timeout", 30.0)
    try:
        timeout_val = float(timeout)
        if timeout_val <= 0 or timeout_val > SANDBOX_MAX_TIMEOUT:
            return f"超时时间超出范围 (0, {SANDBOX_MAX_TIMEOUT}]"
    except (TypeError, ValueError):
        return "超时时间格式无效"

    # memory 上限
    memory = body.get("memory", "512m")
    try:
        mem_str = str(memory).lower().strip()
        if mem_str.endswith("m"):
            mem_val = int(mem_str[:-1])
        elif mem_str.endswith("g"):
            mem_val = int(mem_str[:-1]) * 1024
        else:
            mem_val = int(mem_str)

        if mem_val <= 0 or mem_val > SANDBOX_MAX_MEMORY_MB:
            return f"内存限制超出范围 (0, {SANDBOX_MAX_MEMORY_MB}MB]"
    except (TypeError, ValueError):
        return "内存限制格式无效"

    # network 必须为 bool 且默认 False
    network = body.get("network", False)
    if not isinstance(network, bool):
        return "network 参数必须为布尔值"

    return None


# ---------------------------------------------------------------------------
# 一键安装所有安全中间件
# ---------------------------------------------------------------------------


def install_security_middleware(app: FastAPI) -> None:
    """为 Playground 应用安装全部安全中间件

    Starlette 中间件栈：最后添加的最先执行。
    实际请求处理顺序：
      1. WSOriginValidator + WSConnectionLimiter (ASGI 层)
      2. RateLimitMiddleware (HTTP 层)
      3. BodySizeLimitMiddleware (HTTP 层)
      4. CORSMiddleware (HTTP 层，最外层处理预检)
    """
    # HTTP 中间件（注意添加顺序与执行顺序相反）
    _add_cors_middleware(app)  # CORS 最外层
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ASGI 层中间件：WebSocket origin 校验 + 连接数限制
    # 需要包裹整个 app，通过 build_asgi_app 集成
    app.add_middleware(WSOriginValidator)  # type: ignore[arg-type]
    app.add_middleware(WSConnectionLimiter)  # type: ignore[arg-type]

    logger.info(
        "安全中间件已安装: CORS(%s), 限流(%d/min, 执行%d/min), "
        "代码长度%d, body%dKB, WS origin校验, WS连接数上限%d",
        "custom" if CORS_ORIGINS else "*",
        RATE_LIMIT_PER_MINUTE,
        EXEC_RATE_LIMIT_PER_MINUTE,
        MAX_CODE_LENGTH,
        MAX_BODY_SIZE // 1024,
        MAX_WS_CONNECTIONS,
    )
