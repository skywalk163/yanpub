"""FreeBSD jail 沙箱后端

通过 jail/jexec 命令创建和管理 FreeBSD jail 实例。
需要在 FreeBSD 系统上运行，且需要 root 权限。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from yanpub.core.security.sandbox import SandboxBackend, SandboxConfig, SandboxResult

logger = logging.getLogger("yanpub.sandbox.freebsd")


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
        if not (sys.platform == "freebsd" or platform.system().lower() == "freebsd"):
            return False
        # 检查 jail 命令是否存在
        if shutil.which("jail") is None:
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
            f"{jail_name} {{\n"
            f'    path = "{jail_root}";\n'
            f'    host.hostname = "{jail_name}.yanpub";\n'
            f"    ip4.addr = {config.jail_ip};\n"
            f"    mount.devfs;\n"
            f"    exec.stop = \"/bin/sh -c 'umount /dev 2>/dev/null; true'\";\n"
            f"    persist;\n"
            f"}}\n"
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

    def execute(self, sandbox_id: str, command: list[str], stdin: str = "") -> SandboxResult:
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
