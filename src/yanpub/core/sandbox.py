"""云端执行沙箱 — 容器化执行、安全隔离与 FreeBSD jail 支持

核心能力：
1. SandboxConfig / SandboxResult — 沙箱配置与结果数据结构
2. SandboxBackend — 沙箱后端抽象基类
3. DockerSandbox — Docker/Podman 容器沙箱（命令行调用）
4. FreeBSDJailSandbox — FreeBSD jail 沙箱
5. ProcessSandbox — 进程级沙箱（fallback，无容器依赖）
6. SandboxManager — 统一沙箱生命周期管理器

命令:
  yanpub sandbox <lang_id> <file>       — 在沙箱中安全执行代码
  yanpub sandbox check                  — 检测可用的沙箱后端

设计原则:
  - 不引入新的第三方依赖，所有后端通过命令行调用
  - Docker/Podman 通过 subprocess 调用 docker run / podman run
  - FreeBSD jail 通过 subprocess 调用 jail / jexec
  - ProcessSandbox 使用 Python 标准库 resource + subprocess
  - 所有后端均实现超时、内存限制
  - 路径处理跨平台（Windows/FreeBSD/Linux）
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from yanpub.core.adapter import LanguageAdapter, SubprocessAdapter

logger = logging.getLogger("yanpub.sandbox")


# ============================================================
# 数据结构
# ============================================================


@dataclass
class SandboxConfig:
    """沙箱配置"""

    backend: str = "auto"  # "auto" | "docker" | "podman" | "freebsd_jail" | "nsjail" | "process"
    timeout: float = 30.0
    memory_limit: str = "512m"
    cpu_limit: float = 1.0  # CPU 核数
    network: bool = False  # 是否允许网络
    max_file_size: str = "10m"
    max_processes: int = 10
    workdir: str = "/workspace"
    read_only_paths: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    # Docker/Podman 专用
    image: str = "yanpub/runner:latest"
    # FreeBSD jail 专用
    jail_path: str = "/jail/yanpub"
    jail_ip: str = "127.0.0.2"

    def memory_limit_bytes(self) -> int:
        """将内存限制字符串转换为字节数"""
        return _parse_size(self.memory_limit)

    def max_file_size_bytes(self) -> int:
        """将文件大小限制字符串转换为字节数"""
        return _parse_size(self.max_file_size)


@dataclass
class SandboxResult:
    """沙箱执行结果"""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    memory_used_mb: float = 0.0
    sandbox_id: str = ""
    backend: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "memoryUsedMb": self.memory_used_mb,
            "sandboxId": self.sandbox_id,
            "backend": self.backend,
        }


# ============================================================
# 工具函数
# ============================================================


def _parse_size(size_str: str) -> int:
    """将大小字符串（如 '512m', '1g', '10k'）解析为字节数"""
    size_str = size_str.strip().lower()
    if not size_str:
        return 0

    units = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}
    if size_str[-1] in units:
        return int(float(size_str[:-1]) * units[size_str[-1]])
    return int(size_str)


def _which(cmd: str) -> Optional[str]:
    """查找命令的完整路径，找不到返回 None"""
    return shutil.which(cmd)


def _is_freebsd() -> bool:
    """检测当前系统是否为 FreeBSD"""
    return sys.platform == "freebsd" or platform.system().lower() == "freebsd"


# ============================================================
# 沙箱后端抽象基类
# ============================================================


class SandboxBackend(ABC):
    """沙箱后端抽象基类"""

    @abstractmethod
    def create(self, config: SandboxConfig) -> str:
        """创建沙箱实例，返回 sandbox_id"""
        ...

    @abstractmethod
    def execute(
        self, sandbox_id: str, command: list[str], stdin: str = ""
    ) -> SandboxResult:
        """在沙箱中执行命令"""
        ...

    @abstractmethod
    def destroy(self, sandbox_id: str) -> None:
        """销毁沙箱实例"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检测后端是否可用"""
        ...


# ============================================================
# Docker/Podman 沙箱后端
# ============================================================


class DockerSandbox(SandboxBackend):
    """Docker/Podman 沙箱后端

    通过命令行调用 docker run / podman run 创建容器执行代码。
    自动检测 docker 或 podman 可用性。
    """

    def __init__(self):
        self._runtime: Optional[str] = None
        self._sandboxes: dict[str, dict] = {}  # sandbox_id -> metadata

    def _detect_runtime(self) -> Optional[str]:
        """检测可用的容器运行时（docker 或 podman）"""
        for runtime in ("docker", "podman"):
            if _which(runtime):
                # 验证运行时能正常工作
                try:
                    result = subprocess.run(
                        [runtime, "info"],
                        capture_output=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        self._runtime = runtime
                        return runtime
                except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                    continue
        return None

    def is_available(self) -> bool:
        return self._detect_runtime() is not None

    @property
    def runtime(self) -> Optional[str]:
        if self._runtime is None:
            self._detect_runtime()
        return self._runtime

    def create(self, config: SandboxConfig) -> str:
        runtime = self.runtime
        if runtime is None:
            raise RuntimeError("无可用的容器运行时（docker/podman）")

        sandbox_id = f"yanpub-{uuid.uuid4().hex[:12]}"

        # 构建容器名称
        container_name = sandbox_id

        # 保存元数据
        self._sandboxes[sandbox_id] = {
            "container_name": container_name,
            "runtime": runtime,
            "config": config,
            "created_at": time.time(),
        }

        return sandbox_id

    def execute(
        self, sandbox_id: str, command: list[str], stdin: str = ""
    ) -> SandboxResult:
        meta = self._sandboxes.get(sandbox_id)
        if meta is None:
            return SandboxResult(
                stderr=f"沙箱实例不存在: {sandbox_id}",
                exit_code=-1,
                sandbox_id=sandbox_id,
                backend=self.runtime or "docker",
            )

        runtime = meta["runtime"]
        config: SandboxConfig = meta["config"]
        container_name = meta["container_name"]

        # 构建 docker/podman run 命令
        cmd = [runtime, "run", "--rm", "--name", container_name]

        # 内存限制
        cmd.extend(["--memory", config.memory_limit])

        # CPU 限制
        cmd.extend(["--cpus", str(config.cpu_limit)])

        # 网络隔离
        if not config.network:
            cmd.extend(["--network", "none"])

        # 进程数限制
        cmd.extend(["--pids-limit", str(config.max_processes)])

        # 工作目录
        cmd.extend(["--workdir", config.workdir])

        # 只读路径挂载
        for ro_path in config.read_only_paths:
            p = Path(ro_path)
            if p.exists():
                cmd.extend(["-v", f"{p}:{p}:ro"])

        # 环境变量
        for key, value in config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # 设置 PYTHONIOENCODING
        cmd.extend(["-e", "PYTHONIOENCODING=utf-8"])

        # 镜像
        cmd.append(config.image)

        # 执行命令
        cmd.extend(command)

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout,
            )
            elapsed = (time.monotonic() - start) * 1000

            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend=runtime,
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            # 尝试杀掉超时容器
            try:
                subprocess.run(
                    [runtime, "kill", container_name],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass
            return SandboxResult(
                stderr=f"执行超时（{config.timeout}秒）",
                exit_code=-1,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend=runtime,
            )
        except FileNotFoundError:
            return SandboxResult(
                stderr=f"容器运行时未找到: {runtime}",
                exit_code=-2,
                sandbox_id=sandbox_id,
                backend=runtime or "docker",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"沙箱执行错误: {e}",
                exit_code=-3,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend=runtime or "docker",
            )

    def destroy(self, sandbox_id: str) -> None:
        meta = self._sandboxes.pop(sandbox_id, None)
        if meta is None:
            return

        runtime = meta["runtime"]
        container_name = meta["container_name"]

        # 尝试停止并移除容器
        try:
            subprocess.run(
                [runtime, "rm", "-f", container_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass


# ============================================================
# FreeBSD jail 沙箱后端
# ============================================================


class FreeBSDJailSandbox(SandboxBackend):
    """FreeBSD jail 沙箱后端

    通过 jail/jexec 命令创建和管理 FreeBSD jail 实例。
    需要在 FreeBSD 系统上运行，且需要 root 权限。
    """

    def __init__(self):
        self._jails: dict[str, dict] = {}  # sandbox_id -> metadata
        self._jail_counter = 0

    def is_available(self) -> bool:
        """检测 FreeBSD jail 是否可用"""
        if not _is_freebsd():
            return False
        # 检查 jail 命令是否存在
        if _which("jail") is None:
            return False
        # 检查是否有 root 权限
        try:
            return os.geteuid() == 0
        except AttributeError:
            return False

    def create(self, config: SandboxConfig) -> str:
        if not self.is_available():
            raise RuntimeError("FreeBSD jail 不可用（需要 FreeBSD 系统和 root 权限）")

        self._jail_counter += 1
        jail_id = self._jail_counter
        sandbox_id = f"yanpub-jail-{jail_id}"
        jail_name = f"yanpub_{jail_id}"

        # jail 根目录
        jail_root = Path(config.jail_path) / jail_name
        jail_root.mkdir(parents=True, exist_ok=True)

        # 创建基本目录结构
        (jail_root / "workspace").mkdir(exist_ok=True)
        (jail_root / "tmp").mkdir(exist_ok=True)
        (jail_root / "dev").mkdir(exist_ok=True)

        # 创建 jail.conf 配置
        jail_conf = jail_root / "jail.conf"
        conf_content = (
            f'{jail_name} {{\n'
            f'    path = "{jail_root}";\n'
            f'    host.hostname = "{jail_name}.yanpub";\n'
            f'    ip4.addr = {config.jail_ip};\n'
            f'    mount.devfs;\n'
            f'    exec.stop = "/bin/sh -c \'umount /dev 2>/dev/null; true\'";\n'
            f'    persist;\n'
            f'}}\n'
        )
        jail_conf.write_text(conf_content, encoding="utf-8")

        # 创建 jail
        try:
            result = subprocess.run(
                ["jail", "-c", jail_name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode != 0:
                # jail 创建失败，清理目录
                shutil.rmtree(jail_root, ignore_errors=True)
                raise RuntimeError(f"创建 jail 失败: {result.stderr}")
        except FileNotFoundError:
            shutil.rmtree(jail_root, ignore_errors=True)
            raise RuntimeError("jail 命令未找到")

        # 保存元数据
        self._jails[sandbox_id] = {
            "jail_name": jail_name,
            "jail_root": str(jail_root),
            "config": config,
            "created_at": time.time(),
        }

        return sandbox_id

    def execute(
        self, sandbox_id: str, command: list[str], stdin: str = ""
    ) -> SandboxResult:
        meta = self._jails.get(sandbox_id)
        if meta is None:
            return SandboxResult(
                stderr=f"沙箱实例不存在: {sandbox_id}",
                exit_code=-1,
                sandbox_id=sandbox_id,
                backend="freebsd_jail",
            )

        jail_name = meta["jail_name"]
        config: SandboxConfig = meta["config"]

        # 使用 jexec 在 jail 中执行命令
        cmd = ["jexec", jail_name] + command

        start = time.monotonic()
        try:
            env = os.environ.copy()
            env.update(config.env_vars)
            env.setdefault("PYTHONIOENCODING", "utf-8")

            result = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout,
                env=env,
            )
            elapsed = (time.monotonic() - start) * 1000

            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="freebsd_jail",
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"执行超时（{config.timeout}秒）",
                exit_code=-1,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="freebsd_jail",
            )
        except FileNotFoundError:
            return SandboxResult(
                stderr="jexec 命令未找到",
                exit_code=-2,
                sandbox_id=sandbox_id,
                backend="freebsd_jail",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"jail 执行错误: {e}",
                exit_code=-3,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="freebsd_jail",
            )

    def destroy(self, sandbox_id: str) -> None:
        meta = self._jails.pop(sandbox_id, None)
        if meta is None:
            return

        jail_name = meta["jail_name"]
        jail_root = meta["jail_root"]

        # 停止 jail
        try:
            subprocess.run(
                ["jail", "-r", jail_name],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

        # 清理 jail 根目录
        try:
            shutil.rmtree(jail_root, ignore_errors=True)
        except Exception:
            pass


# ============================================================
# 进程级沙箱（fallback）
# ============================================================


class ProcessSandbox(SandboxBackend):
    """进程级沙箱（fallback，无容器）

    使用 subprocess + resource limits 实现基本的安全隔离。
    适用于无法使用 Docker/Podman/jail 的环境。
    """

    def __init__(self):
        self._sandboxes: dict[str, dict] = {}  # sandbox_id -> metadata

    def is_available(self) -> bool:
        """进程级沙箱始终可用"""
        return True

    def create(self, config: SandboxConfig) -> str:
        sandbox_id = f"yanpub-proc-{uuid.uuid4().hex[:12]}"

        # 创建临时工作目录
        work_dir = Path(tempfile.mkdtemp(prefix="yanpub_sandbox_"))
        workspace = work_dir / "workspace"
        workspace.mkdir(exist_ok=True)

        self._sandboxes[sandbox_id] = {
            "work_dir": str(work_dir),
            "config": config,
            "created_at": time.time(),
        }

        return sandbox_id

    def execute(
        self, sandbox_id: str, command: list[str], stdin: str = ""
    ) -> SandboxResult:
        meta = self._sandboxes.get(sandbox_id)
        if meta is None:
            return SandboxResult(
                stderr=f"沙箱实例不存在: {sandbox_id}",
                exit_code=-1,
                sandbox_id=sandbox_id,
                backend="process",
            )

        config: SandboxConfig = meta["config"]
        work_dir = meta["work_dir"]

        start = time.monotonic()

        # 构建环境变量
        env = os.environ.copy()
        env.update(config.env_vars)
        env.setdefault("PYTHONIOENCODING", "utf-8")

        # 在非 Windows 系统上设置资源限制
        preexec_fn = None
        if sys.platform != "win32":
            preexec_fn = self._set_resource_limits

        try:
            result = subprocess.run(
                command,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout,
                cwd=work_dir,
                env=env,
                preexec_fn=preexec_fn,
            )
            elapsed = (time.monotonic() - start) * 1000

            # 尝试获取内存使用信息
            memory_mb = 0.0
            if sys.platform != "win32":
                try:
                    import resource as res_module
                    # ru_maxrss 在 Linux 上是 KB，在 macOS/BSD 上是 bytes
                    usage = res_module.getrusage(res_module.RUSAGE_CHILDREN)
                    if sys.platform == "darwin":
                        memory_mb = usage.ru_maxrss / (1024 * 1024)
                    else:
                        memory_mb = usage.ru_maxrss / 1024
                except Exception:
                    pass

            return SandboxResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=elapsed,
                memory_used_mb=memory_mb,
                sandbox_id=sandbox_id,
                backend="process",
            )

        except subprocess.TimeoutExpired:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"执行超时（{config.timeout}秒）",
                exit_code=-1,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="process",
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"命令未找到: {command[0] if command else ''}",
                exit_code=-2,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="process",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                stderr=f"沙箱执行错误: {e}",
                exit_code=-3,
                duration_ms=elapsed,
                sandbox_id=sandbox_id,
                backend="process",
            )

    def destroy(self, sandbox_id: str) -> None:
        meta = self._sandboxes.pop(sandbox_id, None)
        if meta is None:
            return

        work_dir = meta["work_dir"]
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _set_resource_limits():
        """设置进程资源限制（preexec_fn 回调）"""
        try:
            import resource

            # CPU 时间限制（秒）— 设为 2 倍超时作为安全上限
            resource.setrlimit(resource.RLIMIT_CPU, (60, 60))

            # 内存限制（字节）
            memory_bytes = 512 * 1024 * 1024  # 默认 512MB
            try:
                resource.setrlimit(
                    resource.RLIMIT_AS, (memory_bytes, memory_bytes)
                )
            except (ValueError, OSError):
                pass  # 某些系统不支持 RLIMIT_AS

            # 文件大小限制
            file_size = 10 * 1024 * 1024  # 10MB
            resource.setrlimit(
                resource.RLIMIT_FSIZE, (file_size, file_size)
            )

            # 进程数限制
            try:
                resource.setrlimit(
                    resource.RLIMIT_NPROC, (10, 10)
                )
            except (ValueError, OSError):
                pass  # macOS 上可能不支持

        except ImportError:
            pass  # Windows 没有 resource 模块


# ============================================================
# 沙箱管理器
# ============================================================


# 后端注册表
_BACKEND_CLASSES: dict[str, type[SandboxBackend]] = {
    "docker": DockerSandbox,
    "podman": DockerSandbox,  # DockerSandbox 自动检测 docker/podman
    "freebsd_jail": FreeBSDJailSandbox,
    "process": ProcessSandbox,
}

# 后端检测优先级
_BACKEND_PRIORITY = ["docker", "podman", "freebsd_jail", "nsjail", "process"]


class SandboxManager:
    """沙箱管理器 — 统一管理沙箱生命周期"""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._backends: dict[str, SandboxBackend] = {}
        self._active_sandboxes: dict[str, tuple[str, str]] = {}  # sandbox_id -> (backend_name, backend_sandbox_id)

    def _get_backend(self, name: str) -> SandboxBackend:
        """获取或创建指定后端实例"""
        if name not in self._backends:
            cls = _BACKEND_CLASSES.get(name)
            if cls is None:
                raise ValueError(f"未知的沙箱后端: {name}")
            self._backends[name] = cls()
        return self._backends[name]

    def detect_backend(self) -> str:
        """自动检测可用的沙箱后端"""
        backends = self.detect_available_backends()
        if backends:
            return backends[0]
        return "process"  # 始终 fallback 到 process

    @staticmethod
    def detect_available_backends() -> list[str]:
        """检测所有可用的沙箱后端（按优先级排序）"""
        available = []

        # 检测 Docker/Podman
        docker_sandbox = DockerSandbox()
        if docker_sandbox.is_available():
            runtime = docker_sandbox.runtime
            if runtime:
                available.append(runtime)

        # 检测 FreeBSD jail
        jail_sandbox = FreeBSDJailSandbox()
        if jail_sandbox.is_available():
            available.append("freebsd_jail")

        # 检测 nsjail
        if _which("nsjail"):
            available.append("nsjail")

        # Process 始终可用
        available.append("process")

        return available

    def _resolve_backend_name(self) -> str:
        """根据配置解析实际使用的后端名称"""
        if self.config.backend == "auto":
            return self.detect_backend()
        return self.config.backend

    def execute_code(self, adapter: LanguageAdapter, code: str) -> SandboxResult:
        """在沙箱中执行代码片段"""
        backend_name = self._resolve_backend_name()
        backend = self._get_backend(backend_name)

        # 创建沙箱实例
        sandbox_id = backend.create(self.config)

        # 准备代码文件
        # 优先使用 ASCII 扩展名，避免 Windows 上中文文件名编码问题
        suffix = ".duan" if ".duan" in adapter.file_extensions else (
            adapter.file_extensions[-1] if adapter.file_extensions else ".txt"
        )

        # 写临时文件
        tmp_dir = Path(tempfile.mkdtemp(prefix="yanpub_sandbox_code_"))
        code_file = tmp_dir / f"main{suffix}"
        code_file.write_text(code, encoding="utf-8")

        try:
            # 构建执行命令
            command = self._build_exec_command(adapter, code_file, backend_name)

            # 在沙箱中执行
            result = backend.execute(sandbox_id, command)

            # 销毁沙箱
            try:
                backend.destroy(sandbox_id)
            except Exception:
                pass

            return result

        finally:
            # 清理临时文件
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def execute_file(self, adapter: LanguageAdapter, file_path: str) -> SandboxResult:
        """在沙箱中执行代码文件"""
        backend_name = self._resolve_backend_name()
        backend = self._get_backend(backend_name)

        # 创建沙箱实例
        sandbox_id = backend.create(self.config)

        try:
            # 构建执行命令
            command = self._build_exec_command(adapter, Path(file_path), backend_name)

            # 在沙箱中执行
            result = backend.execute(sandbox_id, command)

            # 销毁沙箱
            try:
                backend.destroy(sandbox_id)
            except Exception:
                pass

            return result

        except Exception as e:
            try:
                backend.destroy(sandbox_id)
            except Exception:
                pass
            return SandboxResult(
                stderr=f"沙箱执行失败: {e}",
                exit_code=-3,
                sandbox_id=sandbox_id,
                backend=backend_name,
            )

    def _build_exec_command(
        self, adapter: LanguageAdapter, code_path: Path, backend_name: str
    ) -> list[str]:
        """构建适配器的执行命令

        对于容器后端（docker/podman），代码文件需要通过卷挂载方式传入。
        命令中的文件路径应该是容器内的路径。
        对于 process 后端，直接使用本地路径。
        """
        if backend_name in ("docker", "podman"):
            # 容器后端：代码路径映射到容器内的 /workspace/
            container_code_path = f"/workspace/{code_path.name}"
            # 需要在 create 阶段已挂载卷，这里只构建容器内命令
            # 使用适配器的 run_command，将文件路径替换为容器内路径
            if isinstance(adapter, SubprocessAdapter):
                cmd = adapter._run_command + [container_code_path]
            else:
                # 通用方式：使用 python 执行
                cmd = ["python3", str(container_code_path)]
            return cmd
        elif backend_name == "freebsd_jail":
            # jail 后端：代码路径映射到 jail 内
            jail_code_path = f"/workspace/{code_path.name}"
            if isinstance(adapter, SubprocessAdapter):
                cmd = adapter._run_command + [jail_code_path]
            else:
                cmd = ["python3", str(jail_code_path)]
            return cmd
        else:
            # 进程后端：直接使用本地路径
            if isinstance(adapter, SubprocessAdapter):
                cmd = adapter._run_command + [str(code_path)]
            else:
                cmd = ["python3", str(code_path)]
            return cmd

    def cleanup(self) -> None:
        """清理所有沙箱实例"""
        for backend_name, backend in self._backends.items():
            # 各后端自行管理实例销毁
            # 这里只清理已知活跃的沙箱
            pass
        self._active_sandboxes.clear()

    @staticmethod
    def get_backend_status() -> dict[str, dict]:
        """获取所有后端的状态信息"""
        status = {}

        # Docker/Podman
        docker_sandbox = DockerSandbox()
        docker_available = docker_sandbox.is_available()
        docker_runtime = docker_sandbox.runtime
        status["docker"] = {
            "available": docker_available and docker_runtime == "docker",
            "runtime": docker_runtime or "",
            "description": "Docker 容器沙箱",
        }
        status["podman"] = {
            "available": docker_available and docker_runtime == "podman",
            "runtime": docker_runtime or "",
            "description": "Podman 容器沙箱",
        }

        # FreeBSD jail
        jail_sandbox = FreeBSDJailSandbox()
        status["freebsd_jail"] = {
            "available": jail_sandbox.is_available(),
            "description": "FreeBSD jail 沙箱",
        }

        # nsjail
        status["nsjail"] = {
            "available": _which("nsjail") is not None,
            "description": "nsjail 沙箱（Linux 命名空间隔离）",
        }

        # Process（始终可用）
        status["process"] = {
            "available": True,
            "description": "进程级沙箱（fallback，无容器隔离）",
        }

        return status



