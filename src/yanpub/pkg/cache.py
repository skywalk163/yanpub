"""包缓存 — 本地已安装包的存储和管理

目录结构:
  ~/.yanpub/cache/
  ├── duan/
  │   ├── web-framework/
  │   │   └── 0.2.0/    # 版本目录，包含包内容
  │   └── math-utils/
  │       └── 1.0.0/
  └── yan/
      └── json-utils/
          └── 0.1.0/
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CachedPackage:
    """已缓存的包信息"""

    name: str  # duan:web-framework
    lang: str  # duan
    package: str  # web-framework
    version: str  # 0.2.0
    install_path: str  # 缓存路径
    installed_at: str = ""

    def __post_init__(self):
        if not self.installed_at:
            self.installed_at = datetime.now().isoformat()


class PackageCache:
    """包缓存管理器

    管理本地已下载和安装的包。
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = Path.home() / ".yanpub" / "cache"
        self._dir = cache_dir
        self._manifest: dict[str, CachedPackage] = {}
        self._load_manifest()

    @property
    def cache_dir(self) -> Path:
        return self._dir

    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    def _load_manifest(self) -> None:
        """加载缓存清单"""
        mp = self._manifest_path()
        if mp.exists():
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                for item in data.get("packages", []):
                    cp = CachedPackage(**item)
                    self._manifest[cp.name] = cp
            except (json.JSONDecodeError, TypeError):
                self._manifest = {}

    def _save_manifest(self) -> None:
        """保存缓存清单"""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1",
            "packages": [
                {
                    "name": cp.name,
                    "lang": cp.lang,
                    "package": cp.package,
                    "version": cp.version,
                    "install_path": cp.install_path,
                    "installed_at": cp.installed_at,
                }
                for cp in self._manifest.values()
            ],
        }
        self._manifest_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_package_dir(self, lang: str, package: str, version: str) -> Path:
        """获取包的缓存目录路径"""
        return self._dir / lang / package / version

    def is_cached(self, name: str, version: Optional[str] = None) -> bool:
        """检查包是否已缓存"""
        cp = self._manifest.get(name)
        if cp is None:
            return False
        if version and cp.version != version:
            return False
        return Path(cp.install_path).exists()

    def add(
        self,
        name: str,
        lang: str,
        package: str,
        version: str,
        source_path: Optional[Path] = None,
    ) -> Path:
        """将包添加到缓存

        如果 source_path 提供，则复制其内容到缓存目录。
        否则只创建目录。
        """
        target = self.get_package_dir(lang, package, version)
        target.mkdir(parents=True, exist_ok=True)

        if source_path and source_path.exists():
            if source_path.is_dir():
                # 复制整个目录内容
                for item in source_path.iterdir():
                    dest = target / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
            else:
                shutil.copy2(source_path, target / source_path.name)

        # 更新清单
        cp = CachedPackage(
            name=name,
            lang=lang,
            package=package,
            version=version,
            install_path=str(target),
        )
        self._manifest[name] = cp
        self._save_manifest()
        return target

    def remove(self, name: str) -> bool:
        """从缓存中移除包"""
        cp = self._manifest.get(name)
        if cp is None:
            return False

        install_path = Path(cp.install_path)
        if install_path.exists():
            shutil.rmtree(install_path, ignore_errors=True)

        del self._manifest[name]
        self._save_manifest()
        return True

    def get(self, name: str) -> Optional[CachedPackage]:
        """获取缓存信息"""
        return self._manifest.get(name)

    def list_all(self) -> list[CachedPackage]:
        """列出所有已缓存的包"""
        return list(self._manifest.values())

    def list_by_lang(self, lang: str) -> list[CachedPackage]:
        """列出指定语言的缓存包"""
        return [cp for cp in self._manifest.values() if cp.lang == lang]

    def clear(self) -> None:
        """清空所有缓存"""
        if self._dir.exists():
            shutil.rmtree(self._dir, ignore_errors=True)
        self._manifest = {}
        self._dir.mkdir(parents=True, exist_ok=True)
