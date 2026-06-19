"""配置管理"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class YanPubConfig:
    """yanpub 全局配置"""

    # 默认语言
    default_language: str = "duan"

    # Playground 配置
    playground_host: str = "0.0.0.0"
    playground_port: int = 8080

    # LSP 配置
    lsp_host: str = "127.0.0.1"
    lsp_port: int = 2087

    # REPL 配置
    repl_history_size: int = 1000

    # 包管理器配置
    registry_url: str = "https://registry.yanpub.dev"
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".yanpub" / "cache")

    # 执行配置
    execution_timeout: float = 30.0

    @classmethod
    def from_file(cls, path: Path) -> "YanPubConfig":
        """从 YAML 文件加载配置"""
        import yaml

        if not path.exists():
            return cls()

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def find_config(cls) -> "YanPubConfig":
        """查找配置文件（当前目录 → 用户目录）"""
        # 当前目录
        local = Path("yanpub.yaml")
        if local.exists():
            return cls.from_file(local)

        # 用户目录
        global_cfg = Path.home() / ".yanpub" / "config.yaml"
        if global_cfg.exists():
            return cls.from_file(global_cfg)

        return cls()
