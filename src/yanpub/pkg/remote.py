"""远程注册中心 — 基于 Git 仓库的包索引

远程注册中心使用 Git 仓库存储包索引：
  - 仓库结构: packages/<lang_id>/<package_name>.json
  - 索引文件: index.json（汇总所有包的元信息）

工作流程:
  1. pkg sync    — 从远程拉取最新索引到本地缓存
  2. pkg search  — 搜索本地 + 远程索引
  3. pkg install — 从远程安装包
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.pkg.registry import PackageInfo, PackageRegistry


# 默认远程注册中心仓库
DEFAULT_REMOTE_URL = "https://github.com/yanpub/registry.git"

# 本地缓存目录
_REMOTE_CACHE_DIR = Path.home() / ".yanpub" / "remote_registry"


class RemoteRegistry:
    """远程注册中心

    从 Git 仓库同步包索引到本地缓存，然后与本地注册中心合并。
    """

    def __init__(
        self,
        remote_url: str = DEFAULT_REMOTE_URL,
        cache_dir: Path | None = None,
        local_registry: PackageRegistry | None = None,
    ):
        self.remote_url = remote_url
        self._cache_dir = cache_dir or _REMOTE_CACHE_DIR
        self._local_registry = local_registry or PackageRegistry()
        self._remote_packages: dict[str, PackageInfo] = {}
        self._last_sync: str = ""

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def last_sync(self) -> str:
        return self._last_sync

    def sync(self, branch: str = "main") -> dict:
        """从远程仓库同步包索引

        Returns:
            同步结果统计: {synced: N, added: N, updated: N, removed: N, errors: [...]}
        """
        stats = {"synced": 0, "added": 0, "updated": 0, "removed": 0, "errors": []}

        # Clone 或 pull 远程仓库
        tmp_dir = None
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="yanpub_sync_"))
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, self.remote_url, str(tmp_dir)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            if result.returncode != 0:
                # 如果 clone 失败，尝试 git pull（已有缓存）
                if self._cache_dir.exists():
                    result = subprocess.run(
                        ["git", "pull", "--ff-only"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                        cwd=str(self._cache_dir),
                    )
                    if result.returncode != 0:
                        stats["errors"].append(f"同步失败: {result.stderr.strip()}")
                        return stats
                else:
                    stats["errors"].append(f"克隆仓库失败: {result.stderr.strip()}")
                    return stats
            else:
                # 将克隆的内容复制到缓存目录
                if self._cache_dir.exists():
                    shutil.rmtree(self._cache_dir)
                shutil.copytree(tmp_dir, self._cache_dir)

            # 读取索引
            old_packages = dict(self._remote_packages)
            self._remote_packages.clear()

            # 方法1: 读取汇总索引文件
            index_file = self._cache_dir / "index.json"
            if index_file.exists():
                try:
                    data = json.loads(index_file.read_text(encoding="utf-8"))
                    for pkg_data in data.get("packages", []):
                        pkg = PackageInfo.from_dict(pkg_data)
                        self._remote_packages[pkg.name] = pkg
                except (json.JSONDecodeError, KeyError) as e:
                    stats["errors"].append(f"索引文件解析失败: {e}")

            # 方法2: 扫描 packages/ 目录下的 JSON 文件
            packages_dir = self._cache_dir / "packages"
            if packages_dir.exists():
                for lang_dir in packages_dir.iterdir():
                    if not lang_dir.is_dir():
                        continue
                    for pkg_file in lang_dir.glob("*.json"):
                        try:
                            pkg_data = json.loads(pkg_file.read_text(encoding="utf-8"))
                            pkg = PackageInfo.from_dict(pkg_data)
                            self._remote_packages[pkg.name] = pkg
                        except (json.JSONDecodeError, KeyError) as e:
                            stats["errors"].append(f"包文件解析失败 {pkg_file}: {e}")

            # 计算变更统计
            new_keys = set(self._remote_packages.keys())
            old_keys = set(old_packages.keys())

            stats["added"] = len(new_keys - old_keys)
            stats["removed"] = len(old_keys - new_keys)
            stats["updated"] = sum(
                1 for k in new_keys & old_keys
                if self._remote_packages[k].version != old_packages[k].version
            )
            stats["synced"] = len(self._remote_packages)
            self._last_sync = datetime.now().isoformat()

        except subprocess.TimeoutExpired:
            stats["errors"].append("同步超时（60秒）")
        except FileNotFoundError:
            stats["errors"].append("Git 未安装，无法同步远程索引")
        except Exception as e:
            stats["errors"].append(f"同步失败: {e}")
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return stats

    def search(self, query: str, lang: str | None = None) -> list[PackageInfo]:
        """搜索远程 + 本地包

        合并远程和本地索引，本地优先。
        """
        merged = dict(self._remote_packages)

        # 本地注册中心的包覆盖远程的（本地优先）
        for pkg in self._local_registry.list_all():
            merged[pkg.name] = pkg

        query_lower = query.lower()
        results = []
        for pkg in merged.values():
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

    def get(self, name: str) -> Optional[PackageInfo]:
        """获取包信息（本地优先，然后远程）"""
        local = self._local_registry.get(name)
        if local:
            return local
        return self._remote_packages.get(name)

    def list_all(self) -> list[PackageInfo]:
        """列出所有包（本地 + 远程）"""
        merged = dict(self._remote_packages)
        for pkg in self._local_registry.list_all():
            merged[pkg.name] = pkg
        return list(merged.values())

    def list_by_lang(self, lang: str) -> list[PackageInfo]:
        """列出指定语言的所有包"""
        return [pkg for pkg in self.list_all() if pkg.lang == lang]

    def is_synced(self) -> bool:
        """是否已同步过远程索引"""
        return bool(self._remote_packages) or self._cache_dir.exists()
