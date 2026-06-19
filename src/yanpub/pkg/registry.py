"""包注册中心 — 管理包索引和元数据

包命名规则: lang:package-name
  - duan:web-framework
  - yan:math-utils
  - xinyu:game-engine

本地注册表存储在 ~/.yanpub/registry/ 目录下。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PackageInfo:
    """包元信息"""

    name: str  # 完整名: duan:web-framework
    lang: str  # 语言ID: duan
    package: str  # 包名: web-framework
    version: str = "0.1.0"
    description: str = ""
    authors: list[str] = field(default_factory=list)
    dependencies: dict[str, str] = field(default_factory=dict)  # {包名: 版本约束}
    source_url: str = ""  # Git 仓库地址
    source_type: str = "git"  # git | local | http
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        # 自动解析 lang 和 package
        if ":" in self.name and not self.lang:
            self.lang, self.package = self.name.split(":", 1)
        elif self.lang and self.package and not self.name:
            self.name = f"{self.lang}:{self.package}"

        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PackageInfo":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class PackageRegistry:
    """包注册中心

    管理本地包索引，支持查询、添加、删除包。
    """

    def __init__(self, registry_dir: Optional[Path] = None):
        if registry_dir is None:
            registry_dir = Path.home() / ".yanpub" / "registry"
        self._dir = registry_dir
        self._index: dict[str, PackageInfo] = {}
        self._load()

    @property
    def registry_dir(self) -> Path:
        return self._dir

    def _load(self) -> None:
        """从磁盘加载注册表"""
        index_file = self._dir / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                for pkg_data in data.get("packages", []):
                    pkg = PackageInfo.from_dict(pkg_data)
                    self._index[pkg.name] = pkg
            except (json.JSONDecodeError, KeyError):
                self._index = {}

    def _save(self) -> None:
        """保存注册表到磁盘"""
        self._dir.mkdir(parents=True, exist_ok=True)
        index_file = self._dir / "index.json"
        data = {
            "version": "1",
            "updated_at": datetime.now().isoformat(),
            "packages": [pkg.to_dict() for pkg in self._index.values()],
        }
        index_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, pkg: PackageInfo) -> None:
        """添加或更新包"""
        self._index[pkg.name] = pkg
        self._save()

    def remove(self, name: str) -> bool:
        """删除包"""
        if name in self._index:
            del self._index[name]
            self._save()
            return True
        return False

    def get(self, name: str) -> Optional[PackageInfo]:
        """查询包"""
        return self._index.get(name)

    def search(self, query: str, lang: Optional[str] = None) -> list[PackageInfo]:
        """搜索包

        Args:
            query: 搜索关键词（匹配包名、描述、标签）
            lang: 按语言筛选
        """
        query_lower = query.lower()
        results = []
        for pkg in self._index.values():
            if lang and pkg.lang != lang:
                continue
            if (
                query_lower in pkg.name.lower()
                or query_lower in pkg.description.lower()
                or query_lower in pkg.package.lower()
                or any(query_lower in tag.lower() for tag in pkg.tags)
            ):
                results.append(pkg)
        return results

    def list_by_lang(self, lang: str) -> list[PackageInfo]:
        """列出指定语言的所有包"""
        return [pkg for pkg in self._index.values() if pkg.lang == lang]

    def list_all(self) -> list[PackageInfo]:
        """列出所有包"""
        return list(self._index.values())

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, name: str) -> bool:
        return name in self._index
