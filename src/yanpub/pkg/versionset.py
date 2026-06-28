"""包管理器版本工作集 — 工作空间级别的依赖版本锁定

核心概念：
- VersionConstraint：版本约束解析（支持 >=, ^, ~, 精确, *, 逗号分隔组合）
- ResolvedVersion：已解析的版本记录
- WorkspaceLock：工作空间版本锁定文件（yanworkspace.lock）
- VersionSetManager：版本工作集管理器，负责解析/锁定/检查/升级/应用

yanworkspace.lock 格式（TOML）：
```toml
[workspace]
name = "my-workspace"
created_at = "2026-06-17T12:00:00"

[members]
"duan:utils" = {version = "0.1.0", source = "path"}
"duan:web-framework" = {version = "0.2.0", source = "path"}

[dependencies]
"duan:http-core" = {version = "1.2.0", source = "registry"}
"duan:json-parser" = {version = "2.0.1", source = "registry"}
```
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.pkg.workspace import Workspace
from yanpub.pkg.registry import PackageRegistry

from .version_constraint import VersionConstraint, _VERSION_RE, _parse_version, _same_major, _same_minor  # noqa: F401
from .workspace_lock import ResolvedVersion, WorkspaceLock, _toml_str  # noqa: F401


def __getattr__(name):
    _moved = {
        "VersionConstraint", "_VERSION_RE", "_parse_version", "_same_major", "_same_minor",
        "ResolvedVersion", "WorkspaceLock", "_toml_str",
    }
    if name in _moved:
        import importlib
        if name in {"VersionConstraint", "_VERSION_RE", "_parse_version", "_same_major", "_same_minor"}:
            mod = importlib.import_module(".version_constraint", __name__)
        else:
            mod = importlib.import_module(".workspace_lock", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------
# VersionSetManager — 版本工作集管理器
# ---------------------------------------------------------------------------


class VersionSetManager:
    """版本工作集管理器

    绑定 Workspace 实例，负责：
    1. 解析并锁定所有成员和外部依赖的版本
    2. 加载/保存 yanworkspace.lock
    3. 检查锁定是否过时
    4. 升级指定或全部依赖
    5. 应用锁定版本到各成员
    """

    LOCK_FILENAME = "yanworkspace.lock"

    def __init__(self, workspace: Workspace):
        self._workspace = workspace
        self._lock_path = workspace.root / self.LOCK_FILENAME
        self._registry = PackageRegistry()

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    # ----- 核心操作 -----

    def resolve(self) -> WorkspaceLock:
        """解析并锁定所有版本

        遍历工作空间所有成员，对每个依赖使用 VersionConstraint 匹配。
        - 内部依赖（工作空间成员）：锁定为当前版本
        - 外部依赖：从 PackageRegistry 查询可用版本，选满足约束的最新版本
        """
        ws = self._workspace
        if ws.config is None:
            raise ValueError("工作空间未加载，请先调用 workspace.load()")

        members: dict[str, ResolvedVersion] = {}
        dependencies: dict[str, ResolvedVersion] = {}

        member_full_names = set(ws.members.keys())

        # 1. 锁定所有成员
        for full_name, member in ws.members.items():
            members[full_name] = ResolvedVersion(
                package_name=full_name,
                version=member.version,
                source="path",
            )

        # 2. 收集所有外部依赖及其约束
        #    同一个外部依赖可能被多个成员以不同约束引用，取交集
        dep_constraints: dict[str, list[str]] = {}
        for member in ws.members.values():
            for dep_name, dep_spec in member.dependencies.items():
                # 跳过内部依赖
                if dep_name in member_full_names:
                    continue
                if dep_spec.startswith("path:"):
                    continue
                if dep_name not in dep_constraints:
                    dep_constraints[dep_name] = []
                dep_constraints[dep_name].append(dep_spec)

        # 合并工作空间共享依赖
        if ws.config and ws.config.shared_dependencies:
            for dep_name, dep_spec in ws.config.shared_dependencies.items():
                if dep_name not in dep_constraints:
                    dep_constraints[dep_name] = []
                dep_constraints[dep_name].append(dep_spec)

        # 3. 解析外部依赖
        for dep_name, specs in dep_constraints.items():
            # 构造组合约束
            combined = ",".join(specs)
            constraint = VersionConstraint.parse(combined)

            # 从注册中心查找满足约束的最新版本
            resolved_version = self._find_best_version(dep_name, constraint)
            if resolved_version:
                dependencies[dep_name] = resolved_version
            else:
                # 无法在注册中心找到，记录为 unknown
                dependencies[dep_name] = ResolvedVersion(
                    package_name=dep_name,
                    version="unknown",
                    source="unresolved",
                )

        return WorkspaceLock(
            workspace_name=ws.config.name,
            members=members,
            dependencies=dependencies,
        )

    def load_lock(self) -> Optional[WorkspaceLock]:
        """加载已有的锁定文件"""
        if not self._lock_path.exists():
            return None
        try:
            text = self._lock_path.read_text(encoding="utf-8")
            return WorkspaceLock.from_toml(text)
        except Exception:
            return None

    def save_lock(self, lock: WorkspaceLock) -> Path:
        """保存锁定文件"""
        content = lock.to_toml()
        self._lock_path.write_text(content, encoding="utf-8")
        return self._lock_path

    def check_freshness(self) -> dict:
        """检查锁定是否过时

        Returns:
            {
                "fresh": bool,
                "outdated": [{"name": str, "locked": str, "latest": str}],
                "missing": [str],  # 在 lock 中不存在但 workspace 中声明的依赖
            }
        """
        lock = self.load_lock()

        result: dict = {
            "fresh": True,
            "outdated": [],
            "missing": [],
        }

        if lock is None:
            result["fresh"] = False
            # 没有锁定文件，所有外部依赖都算 missing
            ws = self._workspace
            member_full_names = set(ws.members.keys())
            for member in ws.members.values():
                for dep_name, dep_spec in member.dependencies.items():
                    if dep_name in member_full_names:
                        continue
                    if dep_spec.startswith("path:"):
                        continue
                    if dep_name not in result["missing"]:
                        result["missing"].append(dep_name)
            return result

        # 检查外部依赖是否有过时
        for dep_name, rv in lock.dependencies.items():
            pkg_info = self._registry.get(dep_name)
            if pkg_info is None:
                continue
            if pkg_info.version != rv.version:
                # 检查当前约束是否仍然允许新版本
                result["outdated"].append(
                    {
                        "name": dep_name,
                        "locked": rv.version,
                        "latest": pkg_info.version,
                    }
                )

        # 检查是否有缺失（workspace 中声明但 lock 中没有）
        ws = self._workspace
        member_full_names = set(ws.members.keys())
        for member in ws.members.values():
            for dep_name, dep_spec in member.dependencies.items():
                if dep_name in member_full_names:
                    continue
                if dep_spec.startswith("path:"):
                    continue
                if dep_name not in lock.dependencies:
                    if dep_name not in result["missing"]:
                        result["missing"].append(dep_name)

        if result["outdated"] or result["missing"]:
            result["fresh"] = False

        return result

    def upgrade(self, package_name: str | None = None) -> WorkspaceLock:
        """升级指定包或全部包

        Args:
            package_name: 指定升级的依赖名。None 表示升级全部。

        Returns:
            更新后的 WorkspaceLock
        """
        lock = self.load_lock()
        if lock is None:
            # 没有已有锁定文件，执行完整解析
            lock = self.resolve()
            self.save_lock(lock)
            return lock

        if package_name:
            # 只升级指定包
            rv = lock.dependencies.get(package_name)
            if rv is None:
                # 不在 lock 中，可能是新依赖，执行完整解析
                lock = self.resolve()
            else:
                # 重新解析该依赖
                constraint = self._get_constraint_for_dep(package_name)
                new_rv = self._find_best_version(package_name, constraint)
                if new_rv:
                    lock.dependencies[package_name] = new_rv
                lock.created_at = datetime.now().isoformat()
        else:
            # 升级全部
            lock = self.resolve()

        self.save_lock(lock)
        return lock

    def apply(self) -> None:
        """应用锁定版本（更新各成员的依赖约束）

        将 lock 中锁定的版本写回各成员的 yanpkg.toml。
        对于外部依赖，将约束更新为锁定版本的精确版本号。
        """
        lock = self.load_lock()
        if lock is None:
            raise ValueError("没有可用的锁定文件，请先运行 resolve()")

        ws = self._workspace
        member_full_names = set(ws.members.keys())

        for member in ws.members.values():
            changed = False
            new_deps = dict(member.dependencies)

            for dep_name, dep_spec in member.dependencies.items():
                if dep_name in member_full_names:
                    continue
                if dep_spec.startswith("path:"):
                    continue

                rv = lock.dependencies.get(dep_name)
                if rv and rv.version != "unknown":
                    # 将约束更新为精确版本
                    new_deps[dep_name] = rv.version
                    changed = True

            if changed:
                # 写回成员的 yanpkg.toml
                self._update_member_deps(member, new_deps)

    # ----- 内部方法 -----

    def _find_best_version(
        self, dep_name: str, constraint: VersionConstraint
    ) -> Optional[ResolvedVersion]:
        """从注册中心查找满足约束的最新版本"""
        pkg_info = self._registry.get(dep_name)
        if pkg_info is None:
            return None

        # 当前注册中心只有一个版本，检查是否满足约束
        if constraint.matches(pkg_info.version):
            return ResolvedVersion(
                package_name=dep_name,
                version=pkg_info.version,
                source="registry",
            )

        # 不满足约束
        return None

    def _get_constraint_for_dep(self, dep_name: str) -> VersionConstraint:
        """获取某个依赖在 workspace 中的约束（合并所有成员的声明）"""
        ws = self._workspace
        specs: list[str] = []

        for member in ws.members.values():
            spec = member.dependencies.get(dep_name, "")
            if spec and not spec.startswith("path:"):
                specs.append(spec)

        # 合并共享依赖
        if ws.config and ws.config.shared_dependencies:
            spec = ws.config.shared_dependencies.get(dep_name, "")
            if spec:
                specs.append(spec)

        if not specs:
            return VersionConstraint.parse("*")

        combined = ",".join(specs)
        return VersionConstraint.parse(combined)

    def _update_member_deps(self, member, new_deps: dict[str, str]) -> None:
        """更新成员的 yanpkg.toml 中的依赖声明"""
        member_dir = self._workspace.root / str(member.path)
        toml_path = member_dir / "yanpkg.toml"

        if not toml_path.exists():
            return

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        old_deps = data.get("dependencies", {})
        for dep_name, new_version in new_deps.items():
            if dep_name in old_deps:
                old_deps[dep_name] = new_version

        # 手动重写 toml（保持与 workspace.py _save_config 风格一致）
        self._rewrite_member_toml(toml_path, data, old_deps)

    @staticmethod
    def _rewrite_member_toml(toml_path: Path, data: dict, new_deps: dict[str, str]) -> None:
        """重写成员 yanpkg.toml（手动拼接，不引入 tomlkit）"""
        lines: list[str] = []

        # [package]
        lines.append("[package]")
        pkg_data = data.get("package", {})
        for key in ("name", "lang", "version", "description"):
            if key in pkg_data:
                val = pkg_data[key]
                if isinstance(val, str):
                    lines.append(f'{key} = "{val}"')
                else:
                    lines.append(f"{key} = {val}")

        # [dependencies]
        if new_deps:
            lines.append("")
            lines.append("[dependencies]")
            for dep_name, spec in sorted(new_deps.items()):
                lines.append(f'"{dep_name}" = "{spec}"')

        lines.append("")  # 末尾换行
        toml_path.write_text("\n".join(lines), encoding="utf-8")
