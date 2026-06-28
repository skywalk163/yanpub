"""沙箱后端实现 — 从 core.sandbox_backends 统一导出

后端是执行实现，不属于安全关注点，因此放在 core/ 层级而非 core/security/ 下。
"""

from yanpub.core.sandbox_backends.docker import DockerSandbox
from yanpub.core.sandbox_backends.freebsd import FreeBSDJailSandbox
from yanpub.core.sandbox_backends.process import ProcessSandbox

__all__ = [
    "DockerSandbox",
    "FreeBSDJailSandbox",
    "ProcessSandbox",
]
