"""YanPkg — 统一包管理器

支持：
- 语言隔离的命名空间: duan:web-framework, yan:math-utils
- 跨语言依赖解析
- Git 源优先安装
- 本地缓存
- yanpkg.toml 包描述文件
"""

from yanpub.pkg.registry import PackageRegistry
from yanpub.pkg.resolver import DependencyResolver
from yanpub.pkg.installer import Installer
from yanpub.pkg.cache import PackageCache

__all__ = ["PackageRegistry", "DependencyResolver", "Installer", "PackageCache"]
