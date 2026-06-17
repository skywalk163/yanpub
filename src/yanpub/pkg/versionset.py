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

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.pkg.workspace import Workspace
from yanpub.pkg.registry import PackageRegistry


# ---------------------------------------------------------------------------
# VersionConstraint — 版本约束解析
# ---------------------------------------------------------------------------

@dataclass
class VersionConstraint:
    """版本约束

    支持格式：
      ">=1.0.0"       大于等于
      "^1.0.0"        兼容版本（主版本相同）
      "~1.0.0"        近似版本（主+次版本相同）
      "1.0.0"         精确版本
      "*"             任意版本
      ">=1.0.0,<2.0.0" 逗号分隔的与（AND）约束
    """

    raw: str
    parts: list[tuple[str, str]] = field(default_factory=list)
    """每个元素为 (operator, target_version)"""

    @classmethod
    def parse(cls, spec: str) -> VersionConstraint:
        """解析版本约束字符串"""
        spec = spec.strip()
        if not spec:
            spec = "*"

        parts: list[tuple[str, str]] = []

        if spec == "*":
            parts.append(("*", "*"))
        elif "," in spec:
            # 组合约束：">=1.0.0,<2.0.0"
            for segment in spec.split(","):
                segment = segment.strip()
                parts.append(cls._parse_single(segment))
        else:
            parts.append(cls._parse_single(spec))

        return cls(raw=spec, parts=parts)

    @staticmethod
    def _parse_single(segment: str) -> tuple[str, str]:
        """解析单条约束，返回 (operator, target)"""
        segment = segment.strip()
        if segment == "*":
            return ("*", "*")
        if segment.startswith(">="):
            return (">=", segment[2:].strip())
        if segment.startswith(">"):
            return (">", segment[1:].strip())
        if segment.startswith("<="):
            return ("<=", segment[2:].strip())
        if segment.startswith("<"):
            return ("<", segment[1:].strip())
        if segment.startswith("^"):
            return ("^", segment[1:].strip())
        if segment.startswith("~"):
            return ("~", segment[1:].strip())
        # 精确版本
        return ("==", segment)

    def matches(self, version: str) -> bool:
        """检查版本是否满足约束"""
        return all(self._match_single(op, target, version) for op, target in self.parts)

    @staticmethod
    def _match_single(op: str, target: str, version: str) -> bool:
        """匹配单条约束"""
        if op == "*":
            return True
        if op == "==":
            return _parse_version(version) == _parse_version(target)
        if op == ">=":
            return _parse_version(version) >= _parse_version(target)
        if op == ">":
            return _parse_version(version) > _parse_version(target)
        if op == "<=":
            return _parse_version(version) <= _parse_version(target)
        if op == "<":
            return _parse_version(version) < _parse_version(target)
        if op == "^":
            # 兼容版本：主版本相同且 version >= target
            vv = _parse_version(version)
            tv = _parse_version(target)
            return vv >= tv and _same_major(version, target)
        if op == "~":
            # 近似版本：主+次版本相同且 version >= target
            vv = _parse_version(version)
            tv = _parse_version(target)
            return vv >= tv and _same_minor(version, target)
        return False


# ---------------------------------------------------------------------------
# 辅助函数（简单字符串分割 + 整数比较）
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?.*$")


def _parse_version(v: str) -> tuple[int, ...]:
    """将版本字符串解析为可比较的整数元组"""
    m = _VERSION_RE.match(v.strip())
    if not m:
        return (0,)
    parts = []
    for i in range(1, 4):
        group = m.group(i)
        parts.append(int(group) if group is not None else 0)
    return tuple(parts)


def _same_major(a: str, b: str) -> bool:
    va = _parse_version(a)
    vb = _parse_version(b)
    return va[0] == vb[0] if va and vb else False


def _same_minor(a: str, b: str) -> bool:
    va = _parse_version(a)
    vb = _parse_version(b)
    return va[:2] == vb[:2] if len(va) >= 2 and len(vb) >= 2 else False


# ---------------------------------------------------------------------------
# ResolvedVersion — 已解析版本
# ---------------------------------------------------------------------------

@dataclass
class ResolvedVersion:
    """已解析的版本记录"""

    package_name: str
    version: str
    source: str = "registry"  # registry / path / git
    resolved_at: float = 0.0  # 解析时间戳
    checksum: str = ""        # 校验和（可选）

    def __post_init__(self):
        if self.resolved_at == 0.0:
            self.resolved_at = time.time()

    def to_dict(self) -> dict:
        d: dict[str, str | float] = {
            "package_name": self.package_name,
            "version": self.version,
            "source": self.source,
            "resolved_at": self.resolved_at,
        }
        if self.checksum:
            d["checksum"] = self.checksum
        return d


# ---------------------------------------------------------------------------
# WorkspaceLock — 工作空间版本锁定
# ---------------------------------------------------------------------------

@dataclass
class WorkspaceLock:
    """工作空间版本锁定文件"""

    workspace_name: str
    created_at: str = ""
    members: dict[str, ResolvedVersion] = field(default_factory=dict)
    dependencies: dict[str, ResolvedVersion] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "workspace": {
                "name": self.workspace_name,
                "created_at": self.created_at,
            },
            "members": {
                name: rv.to_dict() for name, rv in self.members.items()
            },
            "dependencies": {
                name: rv.to_dict() for name, rv in self.dependencies.items()
            },
        }

    def to_toml(self) -> str:
        """生成人类可读的 TOML 格式锁定文件"""
        lines: list[str] = []

        # [workspace]
        lines.append("[workspace]")
        lines.append(f'name = {_toml_str(self.workspace_name)}')
        lines.append(f'created_at = {_toml_str(self.created_at)}')

        # [members]
        if self.members:
            lines.append("")
            lines.append("[members]")
            for name in sorted(self.members):
                rv = self.members[name]
                lines.append(
                    f'{_toml_str(name)} = {{version = {_toml_str(rv.version)}, '
                    f'source = {_toml_str(rv.source)}}}'
                )

        # [dependencies]
        if self.dependencies:
            lines.append("")
            lines.append("[dependencies]")
            for name in sorted(self.dependencies):
                rv = self.dependencies[name]
                lines.append(
                    f'{_toml_str(name)} = {{version = {_toml_str(rv.version)}, '
                    f'source = {_toml_str(rv.source)}}}'
                )

        lines.append("")  # 末尾换行
        return "\n".join(lines)

    @classmethod
    def from_toml(cls, text: str) -> WorkspaceLock:
        """从 TOML 文本加载锁定文件"""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        data = tomllib.loads(text)

        ws_data = data.get("workspace", {})
        name = ws_data.get("name", "unknown")
        created_at = ws_data.get("created_at", "")

        members: dict[str, ResolvedVersion] = {}
        for pkg_name, info in data.get("members", {}).items():
            members[pkg_name] = ResolvedVersion(
                package_name=pkg_name,
                version=info.get("version", "0.0.0"),
                source=info.get("source", "path"),
                resolved_at=0.0,
                checksum=info.get("checksum", ""),
            )

        dependencies: dict[str, ResolvedVersion] = {}
        for pkg_name, info in data.get("dependencies", {}).items():
            dependencies[pkg_name] = ResolvedVersion(
                package_name=pkg_name,
                version=info.get("version", "0.0.0"),
                source=info.get("source", "registry"),
                resolved_at=0.0,
                checksum=info.get("checksum", ""),
            )

        lock = cls(
            workspace_name=name,
            created_at=created_at,
            members=members,
            dependencies=dependencies,
        )
        return lock


def _toml_str(s: str) -> str:
    """生成 TOML 带引号的字符串值"""
    # 简单转义：处理内部引号和反斜杠
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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
                result["outdated"].append({
                    "name": dep_name,
                    "locked": rv.version,
                    "latest": pkg_info.version,
                })

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

    def _find_best_version(self, dep_name: str, constraint: VersionConstraint) -> Optional[ResolvedVersion]:
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
