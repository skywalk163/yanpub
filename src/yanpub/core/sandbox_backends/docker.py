"""Docker/Podman 沙箱后端

通过命令行调用 docker run / podman run 创建容器执行代码。
自动检测 docker 或 podman 可用性。
"""

from __future__ import annotations

import logging
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from yanpub.core.security.sandbox import SandboxBackend, SandboxConfig, SandboxResult

logger = logging.getLogger("yanpub.sandbox.docker")


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
        import shutil

        for runtime in ("docker", "podman"):
            if shutil.which(runtime):
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

    def execute(self, sandbox_id: str, command: list[str], stdin: str = "") -> SandboxResult:
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
