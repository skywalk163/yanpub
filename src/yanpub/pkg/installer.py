"""包安装器 — 从 Git/本地/HTTP 源安装包

安装流程:
  1. 解析包名 → 语言:包名
  2. 查询注册中心获取包元信息
  3. 下载包内容（Git clone / 本地复制 / HTTP 下载）
  4. 解析依赖并安装
  5. 缓存到本地
  6. 写入项目 yanpkg.lock
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from yanpub.pkg.registry import PackageRegistry, PackageInfo
from yanpub.pkg.resolver import DependencyResolver
from yanpub.pkg.cache import PackageCache


class Installer:
    """包安装器"""

    def __init__(
        self,
        registry: Optional[PackageRegistry] = None,
        cache: Optional[PackageCache] = None,
    ):
        self.registry = registry or PackageRegistry()
        self.cache = cache or PackageCache()
        self.resolver = DependencyResolver(self.registry)

    def install(
        self,
        package_name: str,
        version: Optional[str] = None,
        project_dir: Optional[Path] = None,
    ) -> bool:
        """安装包

        Args:
            package_name: 包名，格式 "lang:package" 或 "package"
            version: 可选版本号
            project_dir: 项目目录（用于写入 yanpkg.lock）

        Returns:
            是否安装成功
        """
        # 1. 解析包名
        if ":" not in package_name:
            # 尝试在所有语言中搜索
            results = self.registry.search(package_name)
            if not results:
                return False
            if len(results) == 1:
                package_name = results[0].name
            else:
                # 多个结果，优先精确匹配
                for r in results:
                    if r.package == package_name:
                        package_name = r.name
                        break
                else:
                    package_name = results[0].name

        # 2. 检查缓存
        if self.cache.is_cached(package_name, version):
            return True

        # 3. 查询注册中心
        pkg = self.registry.get(package_name)
        if pkg is None:
            return False

        # 4. 解析依赖
        deps = self.resolver.resolve(package_name, version)
        for dep in deps:
            if dep.source == "missing":
                continue
            if self.cache.is_cached(dep.name, dep.resolved_version):
                continue
            dep_pkg = self.registry.get(dep.name)
            if dep_pkg:
                self._download_and_cache(dep_pkg)

        # 5. 下载并缓存主包
        success = self._download_and_cache(pkg)
        if not success:
            return False

        # 6. 写入 lock 文件
        if project_dir:
            self._write_lock(project_dir, package_name, pkg.version)

        return True

    def _download_and_cache(self, pkg: PackageInfo) -> bool:
        """下载包并添加到缓存"""
        if pkg.source_type == "git" and pkg.source_url:
            return self._install_from_git(pkg)
        elif pkg.source_type == "local" and pkg.source_url:
            return self._install_from_local(pkg)
        elif pkg.source_type == "http" and pkg.source_url:
            return self._install_from_http(pkg)
        else:
            # 无源信息，只记录元数据
            self.cache.add(
                name=pkg.name,
                lang=pkg.lang,
                package=pkg.package,
                version=pkg.version,
            )
            return True

    def _install_from_git(self, pkg: PackageInfo) -> bool:
        """从 Git 仓库安装"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / "repo"
                cmd = ["git", "clone", "--depth", "1"]
                if pkg.version and pkg.version != "latest":
                    cmd.extend(["--branch", f"v{pkg.version}"])
                cmd.extend([pkg.source_url, str(target)])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                )
                if result.returncode != 0:
                    return False

                self.cache.add(
                    name=pkg.name,
                    lang=pkg.lang,
                    package=pkg.package,
                    version=pkg.version,
                    source_path=target,
                )
                return True

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _install_from_local(self, pkg: PackageInfo) -> bool:
        """从本地路径安装"""
        source = Path(pkg.source_url)
        if not source.exists():
            return False

        self.cache.add(
            name=pkg.name,
            lang=pkg.lang,
            package=pkg.package,
            version=pkg.version,
            source_path=source,
        )
        return True

    def _install_from_http(self, pkg: PackageInfo) -> bool:
        """从 HTTP 源安装"""
        try:
            import httpx

            resp = httpx.get(pkg.source_url, timeout=30.0)
            if resp.status_code != 200:
                return False

            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / "package.tar.gz"
                target.write_bytes(resp.content)

                self.cache.add(
                    name=pkg.name,
                    lang=pkg.lang,
                    package=pkg.package,
                    version=pkg.version,
                    source_path=Path(tmpdir),
                )
                return True

        except Exception:
            return False

    def _write_lock(self, project_dir: Path, package_name: str, version: str) -> None:
        """写入 yanpkg.lock 文件"""
        import json

        lock_path = project_dir / "yanpkg.lock"
        lock_data: dict = {}

        if lock_path.exists():
            try:
                lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                lock_data = {}

        lock_data.setdefault("dependencies", {})[package_name] = version

        lock_path.write_text(
            json.dumps(lock_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---- 便捷函数 ----

_default_installer: Optional[Installer] = None


def get_installer() -> Installer:
    """获取默认安装器实例"""
    global _default_installer
    if _default_installer is None:
        _default_installer = Installer()
    return _default_installer


def install(package_name: str, version: Optional[str] = None) -> bool:
    """安装包（便捷函数）"""
    installer = get_installer()
    return installer.install(package_name, version)
