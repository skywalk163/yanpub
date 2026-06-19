"""包依赖锁定 — yanpkg.lock 文件管理

yanpkg.lock 文件结构:
  {
    "version": "1",
    "generated_at": "2026-06-17T10:00:00",
    "platform": "win32",
    "python_version": "3.12.9",
    "packages": {
      "duan:web-framework": {
        "version": "0.2.0",
        "source": "git+https://github.com/example/web-framework.git@v0.2.0",
        "hash": "sha256:abc123...",
        "dependencies": {
          "duan:http-core": ">=0.1.0"
        }
      }
    }
  }

命令:
  yanpub pkg lock     — 生成/更新 lock 文件
  yanpub pkg verify   — 验证 lock 文件完整性
  yanpub pkg unlock   — 删除 lock 文件
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.pkg.registry import PackageRegistry, PackageInfo
from yanpub.pkg.resolver import DependencyResolver
from yanpub.pkg.cache import PackageCache


LOCK_VERSION = "1"


@dataclass
class LockedPackage:
    """锁定的包信息"""

    version: str
    source: str = ""
    hash: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LockedPackage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LockFile:
    """依赖锁定文件"""

    version: str = LOCK_VERSION
    generated_at: str = ""
    platform: str = ""
    python_version: str = ""
    packages: dict[str, LockedPackage] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "platform": self.platform,
            "python_version": self.python_version,
            "packages": {name: pkg.to_dict() for name, pkg in self.packages.items()},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "LockFile":
        lf = cls(
            version=data.get("version", LOCK_VERSION),
            generated_at=data.get("generated_at", ""),
            platform=data.get("platform", ""),
            python_version=data.get("python_version", ""),
        )
        for name, pkg_data in data.get("packages", {}).items():
            lf.packages[name] = LockedPackage.from_dict(pkg_data)
        return lf

    @classmethod
    def from_file(cls, path: Path) -> "LockFile":
        """从文件加载 lock 文件"""
        if not path.exists():
            raise FileNotFoundError(f"Lock 文件不存在: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def save(self, path: Path) -> None:
        """保存 lock 文件"""
        self.generated_at = datetime.now().isoformat()
        self.platform = platform.system().lower()
        self.python_version = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        path.write_text(self.to_json(), encoding="utf-8")


class LockManager:
    """依赖锁定管理器

    负责 lock 文件的生成、验证和更新。
    """

    def __init__(
        self,
        project_dir: Path,
        registry: Optional[PackageRegistry] = None,
        cache: Optional[PackageCache] = None,
    ):
        self.project_dir = project_dir
        self.lock_path = project_dir / "yanpkg.lock"
        self._registry = registry or PackageRegistry()
        self._cache = cache or PackageCache()
        self._resolver = DependencyResolver(self._registry)

    @property
    def is_locked(self) -> bool:
        """是否已有 lock 文件"""
        return self.lock_path.exists()

    def load_lock(self) -> Optional[LockFile]:
        """加载现有 lock 文件"""
        if not self.is_locked:
            return None
        try:
            return LockFile.from_file(self.lock_path)
        except (json.JSONDecodeError, KeyError):
            return None

    def generate(self) -> LockFile:
        """生成 lock 文件

        从 yanpkg.toml 读取依赖，解析完整依赖树，
        计算每个包的哈希，生成 lock 文件。
        """
        lock = LockFile()

        # 读取项目 yanpkg.toml
        toml_path = self.project_dir / "yanpkg.toml"
        project_deps = self._read_project_deps(toml_path)

        # 解析所有依赖
        all_packages = {}
        for dep_name, dep_version in project_deps.items():
            resolved = self._resolver.resolve(dep_name, dep_version)
            for r in resolved:
                if r.source == "missing":
                    continue
                if r.name not in all_packages:
                    pkg = self._registry.get(r.name)
                    if pkg:
                        pkg_hash = self._compute_package_hash(pkg)
                        all_packages[r.name] = LockedPackage(
                            version=r.resolved_version or pkg.version,
                            source=self._get_source_url(pkg),
                            hash=pkg_hash,
                            dependencies=pkg.dependencies,
                        )

        lock.packages = all_packages
        lock.save(self.lock_path)
        return lock

    def verify(self) -> dict:
        """验证 lock 文件完整性

        Returns:
            验证结果: {
                valid: bool,
                errors: [str],
                warnings: [str],
                checked: int,
            }
        """
        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "checked": 0,
        }

        if not self.is_locked:
            result["valid"] = False
            result["errors"].append("Lock 文件不存在")
            return result

        lock = self.load_lock()
        if lock is None:
            result["valid"] = False
            result["errors"].append("Lock 文件格式错误")
            return result

        # 检查版本兼容
        if lock.version != LOCK_VERSION:
            result["warnings"].append(
                f"Lock 文件版本 {lock.version} 与当前版本 {LOCK_VERSION} 不匹配"
            )

        # 检查每个包
        for name, locked_pkg in lock.packages.items():
            result["checked"] += 1

            # 检查包是否仍在注册中心
            pkg = self._registry.get(name)
            if pkg is None:
                result["warnings"].append(f"包 {name} 不在注册中心中")
                continue

            # 检查版本是否匹配
            if pkg.version != locked_pkg.version:
                result["warnings"].append(
                    f"包 {name} 版本不匹配: lock={locked_pkg.version}, registry={pkg.version}"
                )

            # 检查哈希
            if locked_pkg.hash:
                current_hash = self._compute_package_hash(pkg)
                if current_hash and current_hash != locked_pkg.hash:
                    result["errors"].append(f"包 {name} 哈希不匹配: 可能已被修改")
                    result["valid"] = False

            # 检查缓存
            if not self._cache.is_cached(name, locked_pkg.version):
                result["warnings"].append(f"包 {name} v{locked_pkg.version} 未缓存")

        # 检查 yanpkg.toml 中的依赖是否都被锁定
        toml_path = self.project_dir / "yanpkg.toml"
        project_deps = self._read_project_deps(toml_path)
        for dep_name in project_deps:
            if dep_name not in lock.packages:
                result["errors"].append(f"依赖 {dep_name} 未被锁定")
                result["valid"] = False

        return result

    def unlock(self) -> bool:
        """删除 lock 文件"""
        if self.lock_path.exists():
            self.lock_path.unlink()
            return True
        return False

    def update(self, package_name: str | None = None) -> LockFile:
        """更新 lock 文件（全部或指定包）

        Args:
            package_name: 指定更新的包名，None 表示全部更新
        """
        if package_name:
            # 只更新指定包
            lock = self.load_lock() or LockFile()
            pkg = self._registry.get(package_name)
            if pkg:
                lock.packages[package_name] = LockedPackage(
                    version=pkg.version,
                    source=self._get_source_url(pkg),
                    hash=self._compute_package_hash(pkg),
                    dependencies=pkg.dependencies,
                )
            lock.save(self.lock_path)
            return lock
        else:
            # 全部更新
            return self.generate()

    def _read_project_deps(self, toml_path: Path) -> dict[str, str]:
        """读取项目的依赖声明"""
        if not toml_path.exists():
            return {}

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        return config.get("dependencies", {})

    def _compute_package_hash(self, pkg: PackageInfo) -> str:
        """计算包的完整性哈希

        基于: 包名 + 版本 + 排序后的依赖列表
        """
        hash_input = f"{pkg.name}@{pkg.version}"
        if pkg.dependencies:
            sorted_deps = sorted(pkg.dependencies.items())
            hash_input += ":" + ",".join(f"{k}={v}" for k, v in sorted_deps)
        return "sha256:" + hashlib.sha256(hash_input.encode("utf-8")).hexdigest()[:16]

    def _get_source_url(self, pkg: PackageInfo) -> str:
        """获取包的源地址"""
        if pkg.source_url:
            if pkg.source_type == "git":
                return f"git+{pkg.source_url}@v{pkg.version}"
            return pkg.source_url
        return ""
