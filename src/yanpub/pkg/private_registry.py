"""私有注册中心 — 基于 Git 仓库的私有包索引服务

核心能力：
1. PrivateRegistry — 私有 Git 仓库作为包索引存储
2. MirrorSync — 与公网 Git 镜像（GitHub/Gitee/GitCode）双向同步
3. PermissionManager — 基于角色的权限管理（owner/maintainer/developer/guest）

仓库结构:
  packages/<lang_id>/<package_name>.json   — 包元数据
  permissions.json                           — 权限配置
  mirrors.json                               — 镜像同步配置
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.pkg.registry import PackageInfo, PackageRegistry


@dataclass
class MirrorConfig:
    """镜像同步配置"""

    name: str  # 镜像名称，如 "github"
    url: str  # 镜像仓库 URL
    enabled: bool = True
    sync_direction: str = "push"  # push | pull | bidirectional
    auth_type: str = ""  # ssh | https | token
    branch: str = "main"
    last_sync: str = ""
    last_sync_status: str = ""  # success | failed | pending


@dataclass
class PermissionEntry:
    """权限条目"""

    user: str  # 用户标识（Git 用户名 / 邮箱）
    role: str  # owner | maintainer | developer | guest
    scope: str = "*"  # "*" 表示全局，"lang:xxx" 表示特定语言
    granted_by: str = ""
    granted_at: str = ""

    def __post_init__(self):
        if not self.granted_at:
            self.granted_at = datetime.now().isoformat()


# 角色权限矩阵
_ROLE_PERMISSIONS = {
    "owner": {"publish", "unpublish", "read", "write", "admin", "manage_permissions", "manage_mirrors"},
    "maintainer": {"publish", "unpublish", "read", "write", "manage_mirrors"},
    "developer": {"publish", "read", "write"},
    "guest": {"read"},
}


class PermissionManager:
    """权限管理器 — 管理私有注册中心的用户权限"""

    def __init__(self, permissions_file: Optional[Path] = None):
        self._file = permissions_file
        self._entries: list[PermissionEntry] = []
        if self._file and self._file.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._entries = [PermissionEntry(**e) for e in data.get("permissions", [])]
        except (json.JSONDecodeError, KeyError):
            self._entries = []

    def _save(self) -> None:
        if not self._file:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1",
            "updated_at": datetime.now().isoformat(),
            "permissions": [asdict(e) for e in self._entries],
        }
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def grant(self, user: str, role: str, scope: str = "*", granted_by: str = "") -> PermissionEntry:
        """授予用户权限"""
        if role not in _ROLE_PERMISSIONS:
            raise ValueError(f"未知角色: {role}，可用角色: {', '.join(_ROLE_PERMISSIONS.keys())}")

        # 检查是否已存在
        for entry in self._entries:
            if entry.user == user and entry.scope == scope:
                entry.role = role
                entry.granted_by = granted_by
                entry.granted_at = datetime.now().isoformat()
                self._save()
                return entry

        entry = PermissionEntry(user=user, role=role, scope=scope, granted_by=granted_by)
        self._entries.append(entry)
        self._save()
        return entry

    def revoke(self, user: str, scope: str = "*") -> bool:
        """撤销用户权限"""
        before = len(self._entries)
        self._entries = [e for e in self._entries if not (e.user == user and e.scope == scope)]
        if len(self._entries) < before:
            self._save()
            return True
        return False

    def check(self, user: str, permission: str, scope: str = "*") -> bool:
        """检查用户是否有指定权限"""
        for entry in self._entries:
            if entry.user != user:
                continue
            # 检查作用域：全局 "*" 匹配一切，否则需要精确匹配
            if entry.scope != "*" and entry.scope != scope:
                continue
            role_perms = _ROLE_PERMISSIONS.get(entry.role, set())
            if permission in role_perms:
                return True
        return False

    def get_user_roles(self, user: str) -> list[PermissionEntry]:
        """获取用户的所有角色"""
        return [e for e in self._entries if e.user == user]

    def list_all(self) -> list[PermissionEntry]:
        """列出所有权限条目"""
        return list(self._entries)


class MirrorSync:
    """镜像同步 — 私有仓库与公网 Git 镜像的双向同步"""

    def __init__(self, mirrors_file: Optional[Path] = None, private_repo_dir: Optional[Path] = None):
        self._file = mirrors_file
        self._repo_dir = private_repo_dir
        self._mirrors: list[MirrorConfig] = []
        if self._file and self._file.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._mirrors = [MirrorConfig(**m) for m in data.get("mirrors", [])]
        except (json.JSONDecodeError, KeyError):
            self._mirrors = []

    def _save(self) -> None:
        if not self._file:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1",
            "updated_at": datetime.now().isoformat(),
            "mirrors": [asdict(m) for m in self._mirrors],
        }
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_mirror(self, name: str, url: str, sync_direction: str = "push",
                   auth_type: str = "https", branch: str = "main") -> MirrorConfig:
        """添加镜像配置"""
        # 检查是否已存在同名镜像
        for m in self._mirrors:
            if m.name == name:
                m.url = url
                m.sync_direction = sync_direction
                m.auth_type = auth_type
                m.branch = branch
                self._save()
                return m

        mirror = MirrorConfig(name=name, url=url, sync_direction=sync_direction,
                              auth_type=auth_type, branch=branch)
        self._mirrors.append(mirror)
        self._save()
        return mirror

    def remove_mirror(self, name: str) -> bool:
        """移除镜像"""
        before = len(self._mirrors)
        self._mirrors = [m for m in self._mirrors if m.name != name]
        if len(self._mirrors) < before:
            self._save()
            return True
        return False

    def list_mirrors(self) -> list[MirrorConfig]:
        """列出所有镜像"""
        return list(self._mirrors)

    def sync_mirror(self, name: str) -> dict:
        """同步指定镜像

        Returns:
            {"success": bool, "mirror": str, "direction": str, "message": str, "duration_ms": int}
        """
        mirror = None
        for m in self._mirrors:
            if m.name == name:
                mirror = m
                break
        if mirror is None:
            return {"success": False, "mirror": name, "direction": "", "message": f"镜像不存在: {name}", "duration_ms": 0}

        if not mirror.enabled:
            return {"success": False, "mirror": name, "direction": "", "message": "镜像已禁用", "duration_ms": 0}

        start = datetime.now()
        results = []

        try:
            if mirror.sync_direction in ("push", "bidirectional"):
                result = self._push_to_mirror(mirror)
                results.append(result)

            if mirror.sync_direction in ("pull", "bidirectional"):
                result = self._pull_from_mirror(mirror)
                results.append(result)

            duration = (datetime.now() - start).total_seconds() * 1000
            all_ok = all(r.get("success", False) for r in results)

            mirror.last_sync = datetime.now().isoformat()
            mirror.last_sync_status = "success" if all_ok else "failed"
            self._save()

            return {
                "success": all_ok,
                "mirror": name,
                "direction": mirror.sync_direction,
                "message": "; ".join(r.get("message", "") for r in results),
                "duration_ms": int(duration),
            }
        except Exception as e:
            mirror.last_sync = datetime.now().isoformat()
            mirror.last_sync_status = "failed"
            self._save()
            return {"success": False, "mirror": name, "direction": mirror.sync_direction,
                    "message": str(e), "duration_ms": 0}

    def sync_all(self) -> list[dict]:
        """同步所有已启用的镜像"""
        results = []
        for mirror in self._mirrors:
            if mirror.enabled:
                results.append(self.sync_mirror(mirror.name))
        return results

    def _push_to_mirror(self, mirror: MirrorConfig) -> dict:
        """将私有仓库推送到镜像"""
        if not self._repo_dir or not self._repo_dir.exists():
            return {"success": False, "message": "私有仓库目录不存在"}

        try:
            # 添加镜像为 remote
            result = subprocess.run(
                ["git", "remote", "get-url", mirror.name],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(self._repo_dir), timeout=10,
            )
            if result.returncode != 0:
                # remote 不存在，添加
                subprocess.run(
                    ["git", "remote", "add", mirror.name, mirror.url],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    cwd=str(self._repo_dir), timeout=10,
                )

            # 推送到镜像
            result = subprocess.run(
                ["git", "push", mirror.name, mirror.branch, "--force-with-lease"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(self._repo_dir), timeout=120,
            )
            if result.returncode == 0:
                return {"success": True, "message": f"推送成功 → {mirror.name}"}
            return {"success": False, "message": f"推送失败: {result.stderr.strip()}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "推送超时（120秒）"}
        except FileNotFoundError:
            return {"success": False, "message": "Git 未安装"}

    def _pull_from_mirror(self, mirror: MirrorConfig) -> dict:
        """从镜像拉取到私有仓库"""
        if not self._repo_dir or not self._repo_dir.exists():
            return {"success": False, "message": "私有仓库目录不存在"}

        try:
            result = subprocess.run(
                ["git", "pull", mirror.url, mirror.branch, "--ff-only"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(self._repo_dir), timeout=120,
            )
            if result.returncode == 0:
                return {"success": True, "message": f"拉取成功 ← {mirror.name}"}
            return {"success": False, "message": f"拉取失败: {result.stderr.strip()}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "拉取超时（120秒）"}
        except FileNotFoundError:
            return {"success": False, "message": "Git 未安装"}


class PrivateRegistry:
    """私有注册中心 — 基于 Git 仓库的包索引服务

    支持功能：
    - 包的发布/撤销（通过 Git 提交）
    - 权限管理（基于角色）
    - 镜像同步（与公网 Git 仓库双向同步）
    """

    def __init__(
        self,
        repo_url: str = "",
        repo_dir: Optional[Path] = None,
        local_registry: Optional[PackageRegistry] = None,
    ):
        self._repo_url = repo_url
        self._repo_dir = repo_dir or Path.home() / ".yanpub" / "private_registry"
        self._local_registry = local_registry or PackageRegistry()
        self._permission_manager = PermissionManager(self._repo_dir / "permissions.json")
        self._mirror_sync = MirrorSync(self._repo_dir / "mirrors.json", self._repo_dir)
        self._initialized = False

    @property
    def repo_url(self) -> str:
        return self._repo_url

    @property
    def repo_dir(self) -> Path:
        return self._repo_dir

    @property
    def permissions(self) -> PermissionManager:
        return self._permission_manager

    @property
    def mirrors(self) -> MirrorSync:
        return self._mirror_sync

    def init_repo(self, url: str = "") -> dict:
        """初始化私有注册中心仓库

        如果 url 非空，clone 远程仓库；否则在本地创建新仓库。
        """
        if url:
            self._repo_url = url

        if self._repo_dir.exists() and (self._repo_dir / ".git").exists():
            return {"success": True, "message": "仓库已存在", "path": str(self._repo_dir)}

        try:
            if self._repo_url:
                # Clone 远程仓库
                result = subprocess.run(
                    ["git", "clone", self._repo_url, str(self._repo_dir)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=120,
                )
                if result.returncode != 0:
                    return {"success": False, "message": f"克隆失败: {result.stderr.strip()}"}
            else:
                # 本地初始化
                self._repo_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "init"],
                    capture_output=True, text=True, cwd=str(self._repo_dir), timeout=10,
                )

                # 创建初始结构
                (self._repo_dir / "packages").mkdir(exist_ok=True)
                index_file = self._repo_dir / "index.json"
                if not index_file.exists():
                    index_file.write_text(
                        json.dumps({"version": "1", "packages": []}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )

                # 初始提交
                subprocess.run(
                    ["git", "add", "."],
                    capture_output=True, cwd=str(self._repo_dir), timeout=10,
                )
                subprocess.run(
                    ["git", "commit", "-m", "init: private registry"],
                    capture_output=True, cwd=str(self._repo_dir), timeout=10,
                )

            # 重新加载权限和镜像
            self._permission_manager = PermissionManager(self._repo_dir / "permissions.json")
            self._mirror_sync = MirrorSync(self._repo_dir / "mirrors.json", self._repo_dir)
            self._initialized = True

            return {"success": True, "message": "初始化成功", "path": str(self._repo_dir)}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "初始化超时"}
        except FileNotFoundError:
            return {"success": False, "message": "Git 未安装"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def publish(self, pkg: PackageInfo, user: str = "", commit_message: str = "") -> dict:
        """发布包到私有注册中心

        通过写入文件 + Git 提交的方式发布。
        """
        # 权限检查
        if user and not self._permission_manager.check(user, "publish", f"lang:{pkg.lang}"):
            return {"success": False, "message": f"用户 '{user}' 无发布权限"}

        try:
            packages_dir = self._repo_dir / "packages" / pkg.lang
            packages_dir.mkdir(parents=True, exist_ok=True)

            # 写入包文件
            pkg_file = packages_dir / f"{pkg.package}.json"
            pkg_file.write_text(
                json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 更新汇总索引
            self._update_index()

            # Git 提交
            msg = commit_message or f"publish: {pkg.name}@{pkg.version}"
            subprocess.run(
                ["git", "add", "."],
                capture_output=True, cwd=str(self._repo_dir), timeout=10,
            )
            result = subprocess.run(
                ["git", "commit", "-m", msg],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(self._repo_dir), timeout=10,
            )
            if result.returncode != 0:
                # 可能没有变更
                return {"success": True, "message": "包已存在，无变更", "package": pkg.name}

            # 同时添加到本地注册中心
            self._local_registry.add(pkg)

            return {"success": True, "message": "发布成功", "package": pkg.name, "version": pkg.version}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def unpublish(self, name: str, user: str = "") -> dict:
        """撤销发布"""
        if user and not self._permission_manager.check(user, "unpublish"):
            return {"success": False, "message": f"用户 '{user}' 无撤销权限"}

        # 解析包名
        if ":" not in name:
            return {"success": False, "message": "包名格式错误，需要 lang:package"}

        lang, package = name.split(":", 1)
        pkg_file = self._repo_dir / "packages" / lang / f"{package}.json"

        if not pkg_file.exists():
            return {"success": False, "message": f"包不存在: {name}"}

        try:
            pkg_file.unlink()
            self._update_index()

            subprocess.run(
                ["git", "add", "."],
                capture_output=True, cwd=str(self._repo_dir), timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", f"unpublish: {name}"],
                capture_output=True, text=True, cwd=str(self._repo_dir), timeout=10,
            )

            self._local_registry.remove(name)

            return {"success": True, "message": "撤销成功", "package": name}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def search(self, query: str, lang: Optional[str] = None, user: str = "") -> list[PackageInfo]:
        """搜索包（合并私有 + 本地索引）"""
        if user and not self._permission_manager.check(user, "read"):
            return []

        # 从私有仓库读取
        private_packages = self._read_packages()

        # 合并本地
        merged = dict(private_packages)
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

    def list_all(self, user: str = "") -> list[PackageInfo]:
        """列出所有包"""
        if user and not self._permission_manager.check(user, "read"):
            return []

        private_packages = self._read_packages()
        merged = dict(private_packages)
        for pkg in self._local_registry.list_all():
            merged[pkg.name] = pkg
        return list(merged.values())

    def _read_packages(self) -> dict[str, PackageInfo]:
        """从私有仓库读取所有包"""
        packages = {}
        packages_dir = self._repo_dir / "packages"
        if not packages_dir.exists():
            return packages

        for lang_dir in packages_dir.iterdir():
            if not lang_dir.is_dir():
                continue
            for pkg_file in lang_dir.glob("*.json"):
                try:
                    data = json.loads(pkg_file.read_text(encoding="utf-8"))
                    pkg = PackageInfo.from_dict(data)
                    packages[pkg.name] = pkg
                except (json.JSONDecodeError, KeyError):
                    continue

        return packages

    def _update_index(self) -> None:
        """更新汇总索引文件"""
        packages = self._read_packages()
        index_file = self._repo_dir / "index.json"
        data = {
            "version": "1",
            "updated_at": datetime.now().isoformat(),
            "packages": [pkg.to_dict() for pkg in packages.values()],
        }
        index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
