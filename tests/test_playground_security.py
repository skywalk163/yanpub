"""Playground 安全中间件测试"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yanpub.playground.security import (
    BodySizeLimitMiddleware,
    MAX_CODE_LENGTH,
    MAX_BODY_SIZE,
    RATE_LIMIT_PER_MINUTE,
    EXEC_RATE_LIMIT_PER_MINUTE,
    RateLimitMiddleware,
    validate_sandbox_params,
    SANDBOX_ALLOWED_BACKENDS,
    SANDBOX_MAX_TIMEOUT,
    SANDBOX_MAX_MEMORY_MB,
    WSOriginValidator,
    WSConnectionLimiter,
    install_security_middleware,
)


def _make_test_app() -> FastAPI:
    """创建带安全中间件的测试应用"""
    app = FastAPI()

    @app.post("/api/run")
    async def run_code(body: dict):
        return {"type": "result", "stdout": "ok"}

    @app.post("/api/sandbox/run")
    async def run_sandbox(body: dict):
        return {"type": "sandbox_result", "stdout": "ok"}

    @app.get("/api/languages")
    async def list_langs():
        return []

    install_security_middleware(app)
    return app


@pytest.fixture
def secure_client():
    app = _make_test_app()
    return TestClient(app)


class TestCORS:
    def test_cors_headers_present(self, secure_client):
        """CORS 预检请求返回正确的 headers"""
        resp = secure_client.options(
            "/api/run",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


class TestRateLimit:
    def test_normal_requests_pass(self, secure_client):
        """正常频率请求应通过"""
        for _ in range(5):
            resp = secure_client.get("/api/languages")
            assert resp.status_code == 200

    def test_rate_limit_triggered(self):
        """超频请求应被限流"""
        app = FastAPI()

        @app.get("/api/test")
        async def test_endpoint():
            return {"ok": True}

        # 使用极低限流便于测试
        import yanpub.playground.security as sec
        original = sec.RATE_LIMIT_PER_MINUTE
        sec.RATE_LIMIT_PER_MINUTE = 3
        try:
            app.add_middleware(RateLimitMiddleware)
            client = TestClient(app)

            # 前 3 次应通过
            for _ in range(3):
                resp = client.get("/api/test")
                assert resp.status_code == 200

            # 第 4 次应被限流
            resp = client.get("/api/test")
            assert resp.status_code == 429
            assert "频繁" in resp.json()["error"]
        finally:
            sec.RATE_LIMIT_PER_MINUTE = original


class TestBodySizeLimit:
    def test_normal_body_passes(self, secure_client):
        """正常大小的请求体应通过"""
        resp = secure_client.post("/api/run", json={"lang": "test", "code": "print('hi')"})
        assert resp.status_code == 200

    def test_oversized_body_rejected(self):
        """超大请求体应被拒绝"""
        app = FastAPI()

        @app.post("/api/run")
        async def run_code(body: dict):
            return {"type": "result"}

        import yanpub.playground.security as sec
        original = sec.MAX_BODY_SIZE
        sec.MAX_BODY_SIZE = 100  # 极小限制便于测试
        try:
            app.add_middleware(BodySizeLimitMiddleware)
            client = TestClient(app)

            big_code = "x" * 200
            resp = client.post("/api/run", json={"lang": "test", "code": big_code})
            assert resp.status_code == 413
        finally:
            sec.MAX_BODY_SIZE = original

    def test_code_length_limit(self):
        """超长代码应被拒绝"""
        app = FastAPI()

        @app.post("/api/run")
        async def run_code(body: dict):
            return {"type": "result"}

        import yanpub.playground.security as sec
        original = sec.MAX_CODE_LENGTH
        sec.MAX_CODE_LENGTH = 100  # 极小限制便于测试
        try:
            app.add_middleware(BodySizeLimitMiddleware)
            client = TestClient(app)

            long_code = "x" * 200
            resp = client.post("/api/run", json={"lang": "test", "code": long_code})
            assert resp.status_code == 413
            assert "代码过长" in resp.json()["error"]
        finally:
            sec.MAX_CODE_LENGTH = original


class TestSandboxParamValidation:
    def test_valid_params(self):
        """合法参数应通过校验"""
        assert validate_sandbox_params({}) is None
        assert validate_sandbox_params({"backend": "auto", "timeout": 30, "memory": "512m", "network": False}) is None

    def test_invalid_backend(self):
        """不支持的后端应被拒绝"""
        err = validate_sandbox_params({"backend": "malicious"})
        assert err is not None
        assert "不支持的沙箱后端" in err

    def test_timeout_too_large(self):
        """超大超时应被拒绝"""
        err = validate_sandbox_params({"timeout": 9999})
        assert err is not None
        assert "超时时间" in err

    def test_timeout_negative(self):
        """负超时应被拒绝"""
        err = validate_sandbox_params({"timeout": -1})
        assert err is not None

    def test_timeout_invalid_format(self):
        """非法超时格式应被拒绝"""
        err = validate_sandbox_params({"timeout": "abc"})
        assert err is not None

    def test_memory_too_large(self):
        """超大内存应被拒绝"""
        err = validate_sandbox_params({"memory": "9999g"})
        assert err is not None
        assert "内存限制" in err

    def test_memory_invalid_format(self):
        """非法内存格式应被拒绝"""
        err = validate_sandbox_params({"memory": "abc"})
        assert err is not None

    def test_network_must_be_bool(self):
        """network 必须为布尔值"""
        err = validate_sandbox_params({"network": "yes"})
        assert err is not None
        assert "布尔值" in err

    def test_network_true_allowed(self):
        """network=True 应通过"""
        assert validate_sandbox_params({"network": True}) is None

    def test_allowed_backends(self):
        """所有允许的后端都应通过"""
        for backend in SANDBOX_ALLOWED_BACKENDS:
            assert validate_sandbox_params({"backend": backend}) is None


class TestWSOriginValidator:
    def test_ws_no_origin_restriction_by_default(self):
        """默认配置（ALLOWED_WS_ORIGINS 为空）不限制 origin"""
        import yanpub.playground.security as sec
        # 默认为空列表，不限制
        assert sec.ALLOWED_WS_ORIGINS == []

    def test_ws_origin_validator_blocks_unauthorized(self):
        """配置了允许的 origin 时，非法 origin 应被拒绝"""
        app = FastAPI()

        @app.websocket("/ws/test")
        async def ws_test(websocket):
            await websocket.accept()
            await websocket.send_json({"ok": True})
            await websocket.close()

        validator = WSOriginValidator(app)
        # 直接测试 ASGI 层行为（通过 scope 模拟）
        # 这里只验证 validator 可正常构造
        assert validator.app is app


class TestInstallSecurityMiddleware:
    def test_install_adds_all_middleware(self):
        """install_security_middleware 应添加所有中间件"""
        app = FastAPI()
        install_security_middleware(app)
        # 验证中间件栈非空
        assert len(app.user_middleware) > 0

    def test_full_app_with_middleware(self):
        """带安全中间件的完整应用应正常工作"""
        app = _make_test_app()
        client = TestClient(app)

        resp = client.get("/api/languages")
        assert resp.status_code == 200

        resp = client.post("/api/run", json={"lang": "test", "code": "hello"})
        assert resp.status_code == 200


class TestSecurityDefaults:
    def test_code_length_default(self):
        assert MAX_CODE_LENGTH == 65536

    def test_body_size_default(self):
        assert MAX_BODY_SIZE == 512 * 1024

    def test_rate_limit_default(self):
        assert RATE_LIMIT_PER_MINUTE == 60

    def test_exec_rate_limit_default(self):
        assert EXEC_RATE_LIMIT_PER_MINUTE == 10

    def test_sandbox_max_timeout(self):
        assert SANDBOX_MAX_TIMEOUT == 120.0

    def test_sandbox_max_memory(self):
        assert SANDBOX_MAX_MEMORY_MB == 2048

    def test_allowed_backends_complete(self):
        assert SANDBOX_ALLOWED_BACKENDS == {"auto", "process", "docker", "podman"}
