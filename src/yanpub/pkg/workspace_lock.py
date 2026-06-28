"""工作空间版本锁定 — yanworkspace.lock 文件管理

核心类：
- ResolvedVersion: 已解析的版本记录
- WorkspaceLock: 工作空间版本锁定文件

锁定文件格式（TOML）：
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

import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ResolvedVersion:
    """已解析的版本记录"""

    package_name: str
    version: str
    source: str = "registry"  # registry / path / git
    resolved_at: float = 0.0  # 解析时间戳
    checksum: str = ""  # 校验和（可选）

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
            "members": {name: rv.to_dict() for name, rv in self.members.items()},
            "dependencies": {name: rv.to_dict() for name, rv in self.dependencies.items()},
        }

    def to_toml(self) -> str:
        """生成人类可读的 TOML 格式锁定文件"""
        lines: list[str] = []

        # [workspace]
        lines.append("[workspace]")
        lines.append(f"name = {_toml_str(self.workspace_name)}")
        lines.append(f"created_at = {_toml_str(self.created_at)}")

        # [members]
        if self.members:
            lines.append("")
            lines.append("[members]")
            for name in sorted(self.members):
                rv = self.members[name]
                lines.append(
                    f"{_toml_str(name)} = {{version = {_toml_str(rv.version)}, "
                    f"source = {_toml_str(rv.source)}}}"
                )

        # [dependencies]
        if self.dependencies:
            lines.append("")
            lines.append("[dependencies]")
            for name in sorted(self.dependencies):
                rv = self.dependencies[name]
                lines.append(
                    f"{_toml_str(name)} = {{version = {_toml_str(rv.version)}, "
                    f"source = {_toml_str(rv.source)}}}"
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
