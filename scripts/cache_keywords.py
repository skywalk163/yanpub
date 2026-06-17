#!/usr/bin/env python3
"""关键字预缓存脚本

从各语言项目动态加载关键字列表，写入 adapters/<lang>/keywords.json。
运行一次即可让适配器无需依赖原项目路径。

用法:
    python scripts/cache_keywords.py          # 缓存所有语言
    python scripts/cache_keywords.py duan     # 只缓存段言
    python scripts/cache_keywords.py --force  # 强制覆盖已有缓存
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
ADAPTERS_DIR = ROOT / "src" / "yanpub" / "adapters"


def cache_all(force: bool = False) -> None:
    """缓存所有语言的关键字"""
    # 动态导入，触发 keywords_loader 执行
    sys.path.insert(0, str(ROOT / "src"))

    from yanpub.core.registry import get_registry

    registry = get_registry()
    cached = 0
    skipped = 0

    for adapter in registry:
        lang_id = adapter.id
        cache_file = ADAPTERS_DIR / lang_id / "keywords.json"

        if cache_file.exists() and not force:
            print(f"  跳过 {adapter.name} ({lang_id}): 缓存已存在")
            skipped += 1
            continue

        # 触发关键字加载
        keywords = adapter.keywords
        if not keywords:
            print(f"  跳过 {adapter.name} ({lang_id}): 无关键字")
            skipped += 1
            continue

        # 写入缓存
        cache_file.write_text(
            json.dumps(keywords, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  缓存 {adapter.name} ({lang_id}): {len(keywords)} 个关键字")
        cached += 1

    print(f"\n完成: 缓存 {cached} 个, 跳过 {skipped} 个")


def cache_one(lang_id: str, force: bool = False) -> None:
    """缓存指定语言的关键字"""
    sys.path.insert(0, str(ROOT / "src"))

    from yanpub.core.registry import get_registry

    registry = get_registry()
    adapter = registry.get(lang_id)

    if adapter is None:
        print(f"未知语言: {lang_id}")
        sys.exit(1)

    cache_file = ADAPTERS_DIR / lang_id / "keywords.json"

    if cache_file.exists() and not force:
        print(f"缓存已存在: {cache_file}")
        return

    keywords = adapter.keywords
    if not keywords:
        print(f"{adapter.name} 无关键字")
        return

    cache_file.write_text(
        json.dumps(keywords, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"缓存 {adapter.name} ({lang_id}): {len(keywords)} 个关键字 -> {cache_file}")


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    langs = [a for a in args if a != "--force"]

    print("关键字预缓存")
    print("=" * 40)

    if langs:
        for lang_id in langs:
            cache_one(lang_id, force=force)
    else:
        cache_all(force=force)
