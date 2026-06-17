"""包管理器工作空间 — monorepo 多包统一管理

核心概念：
- Workspace：一个包含多个包的工作空间，由 workspace.toml 定义
- WorkspaceMember：工作空间成员（子包），每个成员是一个独立的 yanpkg.toml 项目
- WorkspaceResolver：工作空间级别的依赖解析，处理成员间交叉依赖

workspace.toml 格式：
```toml
[workspace]
name = "my-workspace"
members = ["packages/*"]    # glob 模式匹配子包目录

[workspace.dependencies]    # 工作空间共享依赖
"duan:http-core" = ">=1.0.0"
```

每个成员目录下的 yanpkg.toml：
```toml
[package]
name = "web-framework"
lang = "duan"
version = "0.2.0"

[dependencies]
"duan:http-core" = ">=1.0.0"     # 外部依赖
"duan:utils" = "path:../utils"    # 工作空间内部依赖（相对路径）
```
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class WorkspaceMember:
    """工作空间成员（子包）"""
    name: str                  # 包名（不含语言前缀）
    full_name: str             # 完整名：duan:web-framework
    lang: str                  # 语言ID
    version: str = "0.1.0"
    path: Path = Path(".")     # 成员目录路径（相对于工作空间根目录）
    dependencies: dict[str, str] = field(default_factory=dict)
    description: str = ""

    # 内部依赖标记
    is_workspace_dep: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "lang": self.lang,
            "version": self.version,
            "path": str(self.path),
            "dependencies": self.dependencies,
            "description": self.description,
        }


@dataclass
class WorkspaceConfig:
    """工作空间配置"""
    name: str = "default-workspace"
    members: list[str] = field(default_factory=lambda: ["packages/*"])
    shared_dependencies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "members": self.members,
            "shared_dependencies": self.shared_dependencies,
        }


class Workspace:
    """工作空间 — monorepo 多包统一管理

    功能：
    1. 从 workspace.toml 加载工作空间配置
    2. 自动发现成员包（glob 模式匹配）
    3. 解析成员间交叉依赖
    4. 批量操作：构建、测试、发布所有成员
    """

    def __init__(self, root_dir: Path):
        self._root = root_dir.resolve()
        self._config: Optional[WorkspaceConfig] = None
        self._members: dict[str, WorkspaceMember] = {}  # full_name → member

    @property
    def root(self) -> Path:
        """工作空间根目录"""
        return self._root

    @property
    def config(self) -> Optional[WorkspaceConfig]:
        """工作空间配置"""
        return self._config

    @property
    def members(self) -> dict[str, WorkspaceMember]:
        """所有成员包"""
        return dict(self._members)

    @property
    def member_names(self) -> list[str]:
        """所有成员包的完整名列表"""
        return sorted(self._members.keys())

    def is_workspace(self) -> bool:
        """判断当前目录是否是工作空间"""
        return (self._root / "workspace.toml").exists()

    def load(self) -> Workspace:
        """加载工作空间配置和成员"""
        ws_path = self._root / "workspace.toml"
        if not ws_path.exists():
            raise FileNotFoundError(f"未找到 workspace.toml: {ws_path}")

        self._config = self._load_config(ws_path)
        self._members = self._discover_members()
        self._resolve_internal_deps()

        return self

    def _load_config(self, ws_path: Path) -> WorkspaceConfig:
        """加载 workspace.toml"""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        with open(ws_path, "rb") as f:
            data = tomllib.load(f)

        ws_data = data.get("workspace", {})
        return WorkspaceConfig(
            name=ws_data.get("name", "default-workspace"),
            members=ws_data.get("members", ["packages/*"]),
            shared_dependencies=ws_data.get("dependencies", {}),
        )

    def _discover_members(self) -> dict[str, WorkspaceMember]:
        """发现工作空间成员包"""
        if self._config is None:
            return {}

        members: dict[str, WorkspaceMember] = {}

        for pattern in self._config.members:
            # 支持两种模式：
            # 1. glob 模式：packages/* — 匹配目录
            # 2. 精确路径：packages/web-framework
            if "*" in pattern or "?" in pattern:
                # glob 模式
                matched_dirs = sorted(self._root.glob(pattern))
            else:
                # 精确路径
                exact_path = self._root / pattern
                matched_dirs = [exact_path] if exact_path.is_dir() else []

            for member_dir in matched_dirs:
                if not member_dir.is_dir():
                    continue

                toml_path = member_dir / "yanpkg.toml"
                if not toml_path.exists():
                    continue

                try:
                    member = self._load_member(member_dir)
                    if member:
                        members[member.full_name] = member
                except Exception as e:
                    import warnings
                    warnings.warn(
                        f"加载工作空间成员 '{member_dir.name}' 失败: {e}",
                        stacklevel=2,
                    )

        return members

    def _load_member(self, member_dir: Path) -> Optional[WorkspaceMember]:
        """加载单个成员包"""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib

        toml_path = member_dir / "yanpkg.toml"
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        pkg_data = data.get("package", {})
        name = pkg_data.get("name", "")
        lang = pkg_data.get("lang", "")
        version = pkg_data.get("version", "0.1.0")
        description = pkg_data.get("description", "")

        if not name or not lang:
            return None

        full_name = f"{lang}:{name}"
        deps = data.get("dependencies", {})

        # 相对路径计算
        rel_path = member_dir.relative_to(self._root)

        return WorkspaceMember(
            name=name,
            full_name=full_name,
            lang=lang,
            version=version,
            path=rel_path,
            dependencies=deps,
            description=description,
        )

    def _resolve_internal_deps(self) -> None:
        """解析成员间的内部依赖"""
        member_full_names = set(self._members.keys())

        for member in self._members.values():
            for dep_name, version_spec in member.dependencies.items():
                is_internal = dep_name in member_full_names or version_spec.startswith("path:")
                member.is_workspace_dep[dep_name] = is_internal

    def get_member(self, full_name: str) -> Optional[WorkspaceMember]:
        """获取指定成员"""
        return self._members.get(full_name)

    def get_dependency_graph(self) -> dict[str, list[str]]:
        """构建依赖图（拓扑排序用）

        Returns:
            {member_full_name: [依赖的内部成员full_name列表]}
        """
        graph: dict[str, list[str]] = {}
        member_full_names = set(self._members.keys())

        for member in self._members.values():
            internal_deps = [
                dep for dep in member.dependencies
                if dep in member_full_names
            ]
            graph[member.full_name] = internal_deps

        return graph

    def topological_order(self) -> list[str]:
        """计算成员的拓扑排序（依赖在前，被依赖在后）

        Returns:
            按拓扑顺序排列的成员 full_name 列表
        """
        graph = self.get_dependency_graph()
        visited: set[str] = set()
        order: list[str] = []
        visiting: set[str] = set()

        def visit(node: str):
            if node in visited:
                return
            if node in visiting:
                # 检测到循环依赖，跳过
                return
            visiting.add(node)
            for dep in graph.get(node, []):
                visit(dep)
            visiting.discard(node)
            visited.add(node)
            order.append(node)

        for member_name in self._members:
            visit(member_name)

        return order

    def list_internal_deps(self, full_name: str) -> list[str]:
        """列出成员的内部依赖"""
        member = self._members.get(full_name)
        if member is None:
            return []

        member_full_names = set(self._members.keys())
        return [dep for dep in member.dependencies if dep in member_full_names]

    def list_external_deps(self, full_name: str) -> dict[str, str]:
        """列出成员的外部依赖（非工作空间内部）"""
        member = self._members.get(full_name)
        if member is None:
            return {}

        member_full_names = set(self._members.keys())
        return {
            dep: spec
            for dep, spec in member.dependencies.items()
            if dep not in member_full_names and not spec.startswith("path:")
        }

    def create(self, name: str, members_patterns: list[str] | None = None) -> Path:
        """创建工作空间配置文件

        Args:
            name: 工作空间名称
            members_patterns: 成员目录匹配模式

        Returns:
            workspace.toml 的路径
        """
        ws_path = self._root / "workspace.toml"
        if ws_path.exists():
            raise FileExistsError(f"workspace.toml 已存在: {ws_path}")

        patterns = members_patterns or ["packages/*"]

        # 生成 workspace.toml
        lines = [
            '[workspace]',
            f'name = "{name}"',
            f'members = {json.dumps(patterns, ensure_ascii=False)}',
        ]

        # 合并共享依赖
        # 自动扫描已有子包的公共依赖
        shared_deps = self._auto_detect_shared_deps()
        if shared_deps:
            lines.append('')
            lines.append('[workspace.dependencies]')
            for dep, spec in sorted(shared_deps.items()):
                lines.append(f'"{dep}" = "{spec}"')

        ws_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # 重新加载
        self.load()

        return ws_path

    def _auto_detect_shared_deps(self) -> dict[str, str]:
        """自动检测子包的公共依赖"""
        dep_count: dict[str, dict[str, int]] = {}  # dep → {spec → count}

        for member_dir in self._root.iterdir():
            if not member_dir.is_dir():
                continue
            toml_path = member_dir / "yanpkg.toml"
            if not toml_path.exists():
                continue

            try:
                import tomllib
            except ImportError:
                import tomli as tomllib

            try:
                with open(toml_path, "rb") as f:
                    data = tomllib.load(f)
                for dep, spec in data.get("dependencies", {}).items():
                    if dep not in dep_count:
                        dep_count[dep] = {}
                    dep_count[dep][spec] = dep_count[dep].get(spec, 0) + 1
            except Exception:
                continue

        # 选择出现次数最多的版本约束
        shared: dict[str, str] = {}
        for dep, specs in dep_count.items():
            if len(specs) > 1:
                # 多个版本约束，选最低兼容版本
                best_spec = max(specs.items(), key=lambda x: x[1])[0]
                shared[dep] = best_spec
            elif len(specs) == 1:
                spec, count = list(specs.items())[0]
                if count >= 2:  # 至少 2 个子包使用
                    shared[dep] = spec

        return shared

    def add_member(self, member_path: str) -> Optional[WorkspaceMember]:
        """添加成员到工作空间

        Args:
            member_path: 成员目录路径（相对于工作空间根目录）

        Returns:
            新添加的成员，失败返回 None
        """
        abs_path = self._root / member_path
        if not abs_path.is_dir():
            return None

        toml_path = abs_path / "yanpkg.toml"
        if not toml_path.exists():
            return None

        member = self._load_member(abs_path)
        if member is None:
            return None

        self._members[member.full_name] = member

        # 更新 workspace.toml（如果成员路径不在现有模式中）
        if self._config is not None:
            matched = False
            for pattern in self._config.members:
                if "*" in pattern:
                    if abs_path.match(str(self._root / pattern)):
                        matched = True
                        break
                else:
                    if member_path == pattern:
                        matched = True
                        break

            if not matched:
                self._config.members.append(member_path)
                self._save_config()

        self._resolve_internal_deps()
        return member

    def _save_config(self) -> None:
        """保存工作空间配置到 workspace.toml"""
        if self._config is None:
            return

        ws_path = self._root / "workspace.toml"
        lines = [
            '[workspace]',
            f'name = "{self._config.name}"',
            f'members = {json.dumps(self._config.members, ensure_ascii=False)}',
        ]

        if self._config.shared_dependencies:
            lines.append('')
            lines.append('[workspace.dependencies]')
            for dep, spec in sorted(self._config.shared_dependencies.items()):
                lines.append(f'"{dep}" = "{spec}"')

        ws_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def status(self) -> dict:
        """工作空间状态摘要"""
        topo = self.topological_order()

        return {
            "name": self._config.name if self._config else "unknown",
            "root": str(self._root),
            "members_count": len(self._members),
            "members": [
                {
                    "full_name": m.full_name,
                    "version": m.version,
                    "path": str(m.path),
                    "internal_deps": [d for d in m.dependencies if m.is_workspace_dep.get(d, False)],
                    "external_deps": [d for d in m.dependencies if not m.is_workspace_dep.get(d, False)],
                }
                for m in self._members.values()
            ],
            "build_order": topo,
            "shared_dependencies": self._config.shared_dependencies if self._config else {},
            "has_cycles": len(topo) < len(self._members),
        }


def load_workspace(root_dir: Path | str | None = None) -> Optional[Workspace]:
    """加载工作空间

    从指定目录开始，向上查找 workspace.toml。
    如果未指定目录，使用当前工作目录。

    Returns:
        Workspace 实例，如果未找到则返回 None
    """
    if root_dir is None:
        root_dir = Path.cwd()
    else:
        root_dir = Path(root_dir)

    # 向上查找 workspace.toml
    current = root_dir.resolve()
    for _ in range(10):  # 最多向上查找 10 层
        if (current / "workspace.toml").exists():
            ws = Workspace(current)
            ws.load()
            return ws
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None
