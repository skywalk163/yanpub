"""依赖解析器 — 解析和验证包依赖关系

支持版本约束:
  - ">=0.1.0"   大于等于
  - "^1.0.0"    兼容版本（主版本相同）
  - "~1.2.0"    近似版本（主+次版本相同）
  - "1.0.0"     精确版本
  - "*"         任意版本
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from yanpub.pkg.registry import PackageRegistry


@dataclass
class ResolvedDependency:
    """解析后的依赖项"""

    name: str
    version: str
    resolved_version: str = ""
    source: str = ""  # 来源（registry / local / git）


class DependencyResolver:
    """依赖解析器

    解析包的依赖关系，检测冲突，返回安装顺序。
    """

    def __init__(self, registry: PackageRegistry):
        self.registry = registry

    def resolve(self, package_name: str, version: Optional[str] = None) -> list[ResolvedDependency]:
        """解析指定包的所有依赖（递归）

        返回按安装顺序排列的依赖列表（被依赖的在前）。
        """
        visited: set[str] = set()
        result: list[ResolvedDependency] = []

        self._resolve_recursive(package_name, version, visited, result)
        return result

    def _resolve_recursive(
        self,
        package_name: str,
        version: Optional[str],
        visited: set[str],
        result: list[ResolvedDependency],
    ) -> None:
        """递归解析依赖"""
        if package_name in visited:
            return
        visited.add(package_name)

        pkg = self.registry.get(package_name)
        if pkg is None:
            # 未注册的包，跳过（可能需要从远程获取）
            result.append(
                ResolvedDependency(
                    name=package_name,
                    version=version or "*",
                    resolved_version="unknown",
                    source="missing",
                )
            )
            return

        # 检查版本约束
        if version and not self._version_matches(pkg.version, version):
            result.append(
                ResolvedDependency(
                    name=package_name,
                    version=version,
                    resolved_version=pkg.version,
                    source="version_mismatch",
                )
            )
            return

        # 先解析子依赖
        for dep_name, dep_version in pkg.dependencies.items():
            self._resolve_recursive(dep_name, dep_version, visited, result)

        # 再添加自身
        result.append(
            ResolvedDependency(
                name=package_name,
                version=version or pkg.version,
                resolved_version=pkg.version,
                source="registry",
            )
        )

    @staticmethod
    def _version_matches(available: str, constraint: str) -> bool:
        """检查可用版本是否满足约束

        简化实现，支持常见的版本约束格式。
        """
        if constraint == "*":
            return True

        # 精确版本
        if constraint == available:
            return True

        # ^1.0.0 — 兼容版本（主版本相同）
        if constraint.startswith("^"):
            target = constraint[1:]
            return DependencyResolver._same_major(available, target)

        # ~1.2.0 — 近似版本（主+次版本相同）
        if constraint.startswith("~"):
            target = constraint[1:]
            return DependencyResolver._same_minor(available, target)

        # >=0.1.0 — 大于等于
        if constraint.startswith(">="):
            target = constraint[2:]
            return DependencyResolver._version_gte(available, target)

        # >0.1.0 — 大于
        if constraint.startswith(">") and not constraint.startswith(">="):
            target = constraint[1:]
            return DependencyResolver._version_gt(available, target)

        # <=0.1.0 — 小于等于
        if constraint.startswith("<="):
            target = constraint[2:]
            return DependencyResolver._version_lte(available, target)

        return constraint == available

    @staticmethod
    def _parse_version(v: str) -> tuple[int, ...]:
        """将版本字符串解析为可比较的元组"""
        parts = []
        for p in re.split(r"[.\-]", v):
            try:
                parts.append(int(p))
            except ValueError:
                break
        return tuple(parts) if parts else (0,)

    @staticmethod
    def _same_major(a: str, b: str) -> bool:
        va = DependencyResolver._parse_version(a)
        vb = DependencyResolver._parse_version(b)
        return va[0] == vb[0] if va and vb else False

    @staticmethod
    def _same_minor(a: str, b: str) -> bool:
        va = DependencyResolver._parse_version(a)
        vb = DependencyResolver._parse_version(b)
        return va[:2] == vb[:2] if len(va) >= 2 and len(vb) >= 2 else False

    @staticmethod
    def _version_gte(a: str, b: str) -> bool:
        return DependencyResolver._parse_version(a) >= DependencyResolver._parse_version(b)

    @staticmethod
    def _version_gt(a: str, b: str) -> bool:
        return DependencyResolver._parse_version(a) > DependencyResolver._parse_version(b)

    @staticmethod
    def _version_lte(a: str, b: str) -> bool:
        return DependencyResolver._parse_version(a) <= DependencyResolver._parse_version(b)
