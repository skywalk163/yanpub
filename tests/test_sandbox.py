"""v0.8.0 功能测试 — 云端执行沙箱

测试覆盖：
1. SandboxConfig / SandboxResult 数据结构
2. _parse_size 工具函数
3. ProcessSandbox 生命周期（create/execute/destroy）
4. FreeBSDJailSandbox 可用性检测
5. DockerSandbox 可用性检测
6. SandboxManager 自动后端检测与执行
7. SandboxManager 集成适配器执行
8. Playground 沙箱路由注册
9. 后端抽象接口测试
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest


# ============================================================
# 1. 数据结构测试
# ============================================================


class TestSandboxConfig:
    """SandboxConfig 配置数据结构"""

    def test_default_config(self):
        """默认配置值"""
        from yanpub.core.sandbox import SandboxConfig

        config = SandboxConfig()
        assert config.backend == "auto"
        assert config.timeout == 30.0
        assert config.memory_limit == "512m"
        assert config.cpu_limit == 1.0
        assert config.network is False
        assert config.max_file_size == "10m"
        assert config.max_processes == 10
        assert config.workdir == "/workspace"
        assert config.read_only_paths == []
        assert config.env_vars == {}

    def test_custom_config(self):
        """自定义配置"""
        from yanpub.core.sandbox import SandboxConfig

        config = SandboxConfig(
            backend="docker",
            timeout=60.0,
            memory_limit="1g",
            cpu_limit=2.0,
            network=True,
            max_processes=20,
            image="custom/runner:v2",
        )
        assert config.backend == "docker"
        assert config.timeout == 60.0
        assert config.memory_limit == "1g"
        assert config.cpu_limit == 2.0
        assert config.network is True
        assert config.max_processes == 20
        assert config.image == "custom/runner:v2"

    def test_memory_limit_bytes(self):
        """内存限制转换为字节数"""
        from yanpub.core.sandbox import SandboxConfig

        assert SandboxConfig(memory_limit="512m").memory_limit_bytes() == 512 * 1024 ** 2
        assert SandboxConfig(memory_limit="1g").memory_limit_bytes() == 1024 ** 3
        assert SandboxConfig(memory_limit="256k").memory_limit_bytes() == 256 * 1024

    def test_max_file_size_bytes(self):
        """文件大小限制转换为字节数"""
        from yanpub.core.sandbox import SandboxConfig

        assert SandboxConfig(max_file_size="10m").max_file_size_bytes() == 10 * 1024 ** 2
        assert SandboxConfig(max_file_size="100k").max_file_size_bytes() == 100 * 1024


class TestSandboxResult:
    """SandboxResult 结果数据结构"""

    def test_success_result(self):
        from yanpub.core.sandbox import SandboxResult

        result = SandboxResult(
            stdout="hello\n",
            exit_code=0,
            duration_ms=100.0,
            sandbox_id="test-123",
            backend="process",
        )
        assert result.success
        assert result.stdout == "hello\n"
        assert result.exit_code == 0

    def test_failure_result(self):
        from yanpub.core.sandbox import SandboxResult

        result = SandboxResult(
            stderr="error",
            exit_code=1,
            sandbox_id="test-456",
            backend="docker",
        )
        assert not result.success

    def test_to_dict(self):
        from yanpub.core.sandbox import SandboxResult

        result = SandboxResult(
            stdout="out",
            stderr="err",
            exit_code=0,
            duration_ms=50.0,
            memory_used_mb=32.0,
            sandbox_id="sid",
            backend="process",
        )
        d = result.to_dict()
        assert d["stdout"] == "out"
        assert d["stderr"] == "err"
        assert d["exitCode"] == 0
        assert d["durationMs"] == 50.0
        assert d["memoryUsedMb"] == 32.0
        assert d["sandboxId"] == "sid"
        assert d["backend"] == "process"


# ============================================================
# 2. 工具函数测试
# ============================================================


class TestParseSize:
    """_parse_size 大小解析函数"""

    def test_kilobytes(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("10k") == 10 * 1024
        assert _parse_size("10K") == 10 * 1024

    def test_megabytes(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("512m") == 512 * 1024 ** 2
        assert _parse_size("1M") == 1024 ** 2

    def test_gigabytes(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("2g") == 2 * 1024 ** 3
        assert _parse_size("1G") == 1024 ** 3

    def test_terabytes(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("1t") == 1024 ** 4

    def test_plain_number(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("1024") == 1024

    def test_empty_string(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size("") == 0

    def test_whitespace(self):
        from yanpub.core.sandbox import _parse_size
        assert _parse_size(" 512m ") == 512 * 1024 ** 2


# ============================================================
# 3. ProcessSandbox 测试
# ============================================================


class TestProcessSandbox:
    """ProcessSandbox 进程级沙箱"""

    @pytest.fixture
    def sandbox(self):
        from yanpub.core.sandbox import ProcessSandbox
        return ProcessSandbox()

    @pytest.fixture
    def config(self):
        from yanpub.core.sandbox import SandboxConfig
        return SandboxConfig(backend="process", timeout=10.0)

    def test_is_available(self, sandbox):
        """ProcessSandbox 始终可用"""
        assert sandbox.is_available()

    def test_create_returns_id(self, sandbox, config):
        """创建沙箱返回 ID"""
        sid = sandbox.create(config)
        assert sid.startswith("yanpub-proc-")

    def test_execute_simple(self, sandbox, config):
        """执行简单命令"""
        sid = sandbox.create(config)
        py = "python" if sys.platform == "win32" else "python3"
        result = sandbox.execute(sid, [py, "-c", "print('hello')"])
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.backend == "process"
        sandbox.destroy(sid)

    def test_execute_with_stdin(self, sandbox, config):
        """通过 stdin 传递数据"""
        sid = sandbox.create(config)
        py = "python" if sys.platform == "win32" else "python3"
        result = sandbox.execute(
            sid,
            [py, "-c", "import sys; print(sys.stdin.read().strip().upper())"],
            stdin="hello world",
        )
        assert result.exit_code == 0
        assert "HELLO WORLD" in result.stdout
        sandbox.destroy(sid)

    def test_execute_timeout(self, sandbox):
        """超时终止执行"""
        from yanpub.core.sandbox import SandboxConfig
        short_config = SandboxConfig(backend="process", timeout=2.0)
        sid = sandbox.create(short_config)
        py = "python" if sys.platform == "win32" else "python3"
        result = sandbox.execute(sid, [py, "-c", "import time; time.sleep(60)"])
        assert result.exit_code == -1
        assert "超时" in result.stderr
        sandbox.destroy(sid)

    def test_execute_command_not_found(self, sandbox, config):
        """命令不存在"""
        sid = sandbox.create(config)
        result = sandbox.execute(sid, ["nonexistent_cmd_xyz_12345"])
        assert result.exit_code == -2
        sandbox.destroy(sid)

    def test_destroy_nonexistent(self, sandbox):
        """销毁不存在的沙箱不报错"""
        sandbox.destroy("nonexistent-sandbox-id")

    def test_execute_nonexistent_sandbox(self, sandbox):
        """执行不存在的沙箱返回错误"""
        result = sandbox.execute("nonexistent", ["echo", "test"])
        assert result.exit_code == -1
        assert "不存在" in result.stderr

    def test_destroy_cleans_workdir(self, sandbox, config):
        """销毁沙箱时清理临时目录"""
        sid = sandbox.create(config)
        work_dir = sandbox._sandboxes[sid]["work_dir"]
        assert Path(work_dir).exists()
        sandbox.destroy(sid)
        assert not Path(work_dir).exists()


# ============================================================
# 4. FreeBSDJailSandbox 测试
# ============================================================


class TestFreeBSDJailSandbox:
    """FreeBSD jail 沙箱"""

    def test_not_available_on_non_freebsd(self):
        """非 FreeBSD 系统不可用"""
        if sys.platform == "freebsd":
            pytest.skip("Running on FreeBSD")
        from yanpub.core.sandbox import FreeBSDJailSandbox
        jail = FreeBSDJailSandbox()
        assert not jail.is_available()


# ============================================================
# 5. DockerSandbox 测试
# ============================================================


class TestDockerSandbox:
    """Docker/Podman 沙箱"""

    def test_is_available_check(self):
        """检测 Docker/Podman 可用性（不依赖实际安装）"""
        from yanpub.core.sandbox import DockerSandbox
        ds = DockerSandbox()
        result = ds.is_available()
        assert isinstance(result, bool)


# ============================================================
# 6. SandboxManager 测试
# ============================================================


class TestSandboxManager:
    """SandboxManager 沙箱管理器"""

    def test_detect_available_backends(self):
        """检测可用后端"""
        from yanpub.core.sandbox import SandboxManager
        backends = SandboxManager.detect_available_backends()
        assert isinstance(backends, list)
        assert "process" in backends  # 始终可用

    def test_detect_backend(self):
        """自动检测后端"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        mgr = SandboxManager(SandboxConfig(backend="auto"))
        backend = mgr.detect_backend()
        assert isinstance(backend, str)
        assert len(backend) > 0

    def test_resolve_backend_auto(self):
        """auto 模式解析后端"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        mgr = SandboxManager(SandboxConfig(backend="auto"))
        resolved = mgr._resolve_backend_name()
        assert resolved != "auto"

    def test_resolve_backend_explicit(self):
        """显式指定后端"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        mgr = SandboxManager(SandboxConfig(backend="process"))
        resolved = mgr._resolve_backend_name()
        assert resolved == "process"

    def test_get_backend_status(self):
        """获取后端状态"""
        from yanpub.core.sandbox import SandboxManager
        status = SandboxManager.get_backend_status()
        assert isinstance(status, dict)
        assert "process" in status
        assert status["process"]["available"] is True
        assert "docker" in status
        assert "freebsd_jail" in status

    def test_execute_code_with_process(self):
        """使用 ProcessSandbox 执行代码"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试语言",
            lang_id="test_lang",
            version="0.1.0",
            extensions=[".tl"],
            run_command=["python"] if sys.platform == "win32" else ["python3"],
        )

        config = SandboxConfig(backend="process", timeout=10.0)
        mgr = SandboxManager(config)

        code = "print('sandbox test')"
        result = mgr.execute_code(adapter, code)
        assert result.backend == "process"

    def test_execute_file_with_process(self):
        """使用 ProcessSandbox 执行文件"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试语言",
            lang_id="test_lang2",
            version="0.1.0",
            extensions=[".py"],
            run_command=["python"] if sys.platform == "win32" else ["python3"],
        )

        # 创建临时代码文件
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("print('file sandbox test')\n")
            tmp_path = f.name

        try:
            config = SandboxConfig(backend="process", timeout=10.0)
            mgr = SandboxManager(config)
            result = mgr.execute_file(adapter, tmp_path)
            assert result.backend == "process"
            if result.exit_code == 0:
                assert "file sandbox test" in result.stdout
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_cleanup(self):
        """清理管理器"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        mgr = SandboxManager(SandboxConfig(backend="process"))
        mgr.cleanup()  # 应该不崩溃


# ============================================================
# 7. 适配器集成测试
# ============================================================


class TestSandboxAdapterIntegration:
    """沙箱与语言适配器集成"""

    def test_duan_adapter_sandbox_execute(self):
        """段言适配器沙箱执行"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        from yanpub.core.registry import LanguageRegistry

        try:
            from yanpub.adapters.duan.adapter import DuanAdapter
        except ImportError:
            pytest.skip("段言适配器不可用")

        registry = LanguageRegistry()
        registry.register(DuanAdapter())
        adapter = registry.get("duan")

        config = SandboxConfig(backend="process", timeout=30.0)
        mgr = SandboxManager(config)

        result = mgr.execute_code(adapter, '打印("沙箱测试")。')
        assert result.exit_code == 0
        assert "沙箱测试" in result.stdout
        assert result.backend == "process"

    def test_duan_adapter_sandbox_file(self):
        """段言适配器沙箱文件执行"""
        from yanpub.core.sandbox import SandboxManager, SandboxConfig
        from yanpub.core.registry import LanguageRegistry

        try:
            from yanpub.adapters.duan.adapter import DuanAdapter
        except ImportError:
            pytest.skip("段言适配器不可用")

        registry = LanguageRegistry()
        registry.register(DuanAdapter())
        adapter = registry.get("duan")

        # 创建临时代码文件
        with tempfile.NamedTemporaryFile(
            suffix=".duan", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write('打印("文件沙箱测试")。\n')
            tmp_path = f.name

        try:
            config = SandboxConfig(backend="process", timeout=30.0)
            mgr = SandboxManager(config)
            result = mgr.execute_file(adapter, tmp_path)
            assert result.exit_code == 0
            assert "文件沙箱测试" in result.stdout
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ============================================================
# 8. Playground 沙箱路由测试
# ============================================================


class TestPlaygroundSandboxRoutes:
    """Playground 沙箱路由"""

    def test_sandbox_routes_registered(self):
        """沙箱路由已注册"""
        from yanpub.playground.server import create_app

        app = create_app()
        routes = [r.path for r in app.routes]
        assert "/api/sandbox/run" in routes
        assert "/api/sandbox/status" in routes

    def test_sandbox_status_endpoint(self):
        """沙箱状态端点"""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from yanpub.playground.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/sandbox/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "backends" in data
        assert "available" in data
        assert "recommended" in data
        assert "process" in data["backends"]
        assert data["backends"]["process"]["available"] is True

    def test_sandbox_run_endpoint(self):
        """沙箱执行端点"""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from yanpub.playground.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.post("/api/sandbox/run", json={
            "lang": "duan",
            "code": '打印("playground sandbox")。',
            "backend": "process",
            "timeout": 10.0,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "sandbox_result"
        assert data["backend"] == "process"
        assert data["exitCode"] == 0
        assert "playground sandbox" in data["stdout"]

    def test_sandbox_run_unknown_language(self):
        """沙箱执行未知语言"""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from yanpub.playground.server import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.post("/api/sandbox/run", json={
            "lang": "nonexistent_lang",
            "code": "test",
        })
        assert resp.status_code == 400


# ============================================================
# 9. 后端抽象接口测试
# ============================================================


class TestSandboxBackendABC:
    """SandboxBackend 抽象基类"""

    def test_abstract_methods(self):
        """验证抽象方法必须实现"""
        from yanpub.core.sandbox import SandboxBackend

        with pytest.raises(TypeError):
            SandboxBackend()  # type: ignore

    def test_concrete_implementation(self):
        """验证具体实现可实例化"""
        from yanpub.core.sandbox import SandboxBackend, SandboxConfig, SandboxResult

        class TestBackend(SandboxBackend):
            def create(self, config: SandboxConfig) -> str:
                return "test-sid"
            def execute(self, sandbox_id: str, command: list[str], stdin: str = "") -> SandboxResult:
                return SandboxResult(sandbox_id=sandbox_id, backend="test")
            def destroy(self, sandbox_id: str) -> None:
                pass
            def is_available(self) -> bool:
                return True

        backend = TestBackend()
        assert backend.is_available()
        sid = backend.create(SandboxConfig())
        assert sid == "test-sid"
        result = backend.execute(sid, ["echo", "test"])
        assert result.sandbox_id == sid
