"""进程级沙箱后端（fallback，无容器依赖）

使用 subprocess + resource limits 实现基本的安全隔离。
适用于无法使用 Docker/Podman/jail 的环境。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from yanpub.core.security.sandbox import SandboxBackend, SandboxConfig, SandboxResult

logger = logging.getLogger("yanpub.sandbox.process")


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

    def execute(self, sandbox_id: str, command: list[str], stdin: str = "") -> SandboxResult:
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
                resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            except (ValueError, OSError):
                pass  # 某些系统不支持 RLIMIT_AS

            # 文件大小限制
            file_size = 10 * 1024 * 1024  # 10MB
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))

            # 进程数限制
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
            except (ValueError, OSError):
                pass  # macOS 上可能不支持

        except ImportError:
            pass  # Windows 没有 resource 模块
