"""云端执行沙箱 — 容器化执行、安全隔离与 FreeBSD jail 支持

核心能力：
1. SandboxConfig / SandboxResult — 沙箱配置与结果数据结构
2. SandboxBackend — 沙箱后端抽象基类
3. SandboxManager — 统一沙箱生命周期管理器

后端实现已拆分到 yanpub.core.sandbox_backends：
  DockerSandbox, FreeBSDJailSandbox, ProcessSandbox

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

from yanpub.core.adapter.adapter import LanguageAdapter, SubprocessAdapter

# 延迟 re-export 后端实现，保持向后兼容
# （不能在顶层 import，因为 sandbox_backends 会 import 本模块的数据类）

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

    units = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
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
    def execute(self, sandbox_id: str, command: list[str], stdin: str = "") -> SandboxResult:
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
# 延迟 re-export 后端实现
# ============================================================


def __getattr__(name: str):
    """从 sandbox_backends 子包延迟 re-export，保持向后兼容"""
    _reexports = {"DockerSandbox", "FreeBSDJailSandbox", "ProcessSandbox"}
    if name in _reexports:
        from yanpub.core import sandbox_backends

        return getattr(sandbox_backends, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================
# 沙箱管理器
# ============================================================


# 后端注册表 — 延迟加载避免循环依赖
def _get_backend_classes() -> dict[str, type]:
    """获取后端类注册表"""
    from yanpub.core.sandbox_backends import DockerSandbox, FreeBSDJailSandbox, ProcessSandbox

    return {
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
        self._active_sandboxes: dict[
            str, tuple[str, str]
        ] = {}  # sandbox_id -> (backend_name, backend_sandbox_id)

    def _get_backend(self, name: str) -> SandboxBackend:
        """获取或创建指定后端实例"""
        if name not in self._backends:
            cls = _get_backend_classes().get(name)
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
        from yanpub.core.sandbox_backends import DockerSandbox, FreeBSDJailSandbox

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
        suffix = (
            ".duan"
            if ".duan" in adapter.file_extensions
            else (adapter.file_extensions[-1] if adapter.file_extensions else ".txt")
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
        from yanpub.core.sandbox_backends import DockerSandbox, FreeBSDJailSandbox

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
