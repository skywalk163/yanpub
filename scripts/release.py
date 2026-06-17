#!/usr/bin/env python3
"""发布脚本

用法:
    python scripts/release.py          # 干跑（只构建，不上传）
    python scripts/release.py --upload # 构建并上传到 PyPI
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  > {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=ROOT, check=check)


def main() -> None:
    upload = "--upload" in sys.argv

    print("== 言埠 YanPub 发布 ==")
    print()

    # 1. 检查版本号
    import tomllib
    with open(ROOT / "pyproject.toml", "rb") as f:
        config = tomllib.load(f)
    version = config["project"]["version"]
    print(f"版本: {version}")
    print()

    # 2. 运行 lint
    print("1. Lint 检查...")
    result = run(["ruff", "check", "src/"], check=False)
    if result.returncode != 0:
        print("  Lint 有错误，请先修复。")
        sys.exit(1)
    print("  OK")
    print()

    # 3. 运行测试
    print("2. 运行测试...")
    result = run(["pytest", "tests/", "-q", "--tb=short"], check=False)
    if result.returncode != 0:
        print("  测试失败，请先修复。")
        sys.exit(1)
    print("  OK")
    print()

    # 4. 清理旧构建
    print("3. 清理旧构建...")
    import shutil
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    print("  OK")
    print()

    # 5. 构建
    print("4. 构建...")
    run(["python", "-m", "build"])
    print("  OK")
    print()

    # 6. 检查包
    print("5. 检查包...")
    run(["twine", "check", "dist/*"])
    print("  OK")
    print()

    if upload:
        print("6. 上传到 PyPI...")
        run(["twine", "upload", "dist/*"])
        print("  OK - 已发布到 PyPI!")
    else:
        print("6. 干跑模式（未上传）。使用 --upload 上传到 PyPI。")
        print(f"  构建产物: {dist}")


if __name__ == "__main__":
    main()
