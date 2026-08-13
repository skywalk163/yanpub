#!/usr/bin/env python3
"""从 languages.yaml 读取语言仓库 URL，根据镜像策略输出对应 URL。

用法:
  python3 docker/select-mirror.py              # 自动检测镜像
  python3 docker/select-mirror.py gitcode       # 指定 gitcode
  python3 docker/select-mirror.py github        # 指定 github
  python3 docker/select-mirror.py internal      # 指定内网
  python3 docker/select-mirror.py auto          # 自动检测（默认）

输出格式与 docker/lang-repos.conf 兼容:
  lang_id  git_url  subdir
"""

from __future__ import annotations

import sys
import subprocess
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# languages.yaml 路径（项目根目录）
YAML_PATH = Path(__file__).resolve().parent.parent / "languages.yaml"


def load_config() -> dict:
    """加载 languages.yaml"""
    if not YAML_PATH.exists():
        print(f"ERROR: {YAML_PATH} not found", file=sys.stderr)
        sys.exit(1)
    with open(YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def auto_detect_mirror() -> str:
    """自动检测国内/国外环境

    策略: 尝试连接 github.com（3s 超时）
    - 连通 → github（海外）
    - 超时/失败 → gitcode（国内）
    """
    try:
        result = subprocess.run(
            ["curl", "-sf", "--connect-timeout", "3", "--max-time", "5",
             "-o", "/dev/null", "https://github.com"],
            capture_output=True,
            timeout=8,
        )
        if result.returncode == 0:
            return "github"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    return "gitcode"


def select_repo_url(repos: dict, preferred_mirror: str, priority: list[str] | None = None) -> str | None:
    """根据镜像优先级选择可用的仓库 URL

    Args:
        repos: 仓库镜像字典，如 {"gitcode": "...", "github": "...", "internal": "..."}
        preferred_mirror: 首选镜像 ("gitcode" | "github" | "internal")
        priority: 镜像优先级列表（来自 languages.yaml mirror_priority）

    Returns:
        第一个可用的仓库 URL，或 None
    """
    if not repos:
        return None

    # 优先返回首选镜像
    if preferred_mirror in repos:
        return repos[preferred_mirror]

    # 按优先级列表回退
    if priority:
        for mirror in priority:
            if mirror in repos:
                return repos[mirror]

    # 默认回退顺序: gitcode -> github -> internal
    for mirror in ("gitcode", "github", "internal"):
        if mirror in repos:
            return repos[mirror]

    # 最后返回第一个可用的
    return next(iter(repos.values()), None)


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "gitcode"

    if source == "auto":
        source = auto_detect_mirror()
        print(f"# REPO_SOURCE=auto -> detected: {source}", file=sys.stderr)

    config = load_config()
    languages = config.get("languages", {})

    # 根据选中的镜像决定回退优先级
    mirror_priority_cfg = config.get("mirror_priority", {})
    if source in ("internal", "gitcode"):
        priority = mirror_priority_cfg.get("domestic", ["internal", "gitcode", "github"])
    else:
        priority = mirror_priority_cfg.get("overseas", ["github", "gitcode", "internal"])

    for lang_id, lang_info in languages.items():
        repos = lang_info.get("repos", {})
        docker_info = lang_info.get("docker", {})
        subdir = docker_info.get("subdir", ".")

        url = select_repo_url(repos, source, priority)
        if url:
            print(f"{lang_id}\t{url}\t{subdir}")
        else:
            print(f"# WARNING: {lang_id} has no repo URL for mirror '{source}'",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
