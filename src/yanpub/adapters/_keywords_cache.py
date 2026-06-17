"""关键字缓存工具

为适配器提供优先从本地 JSON 缓存加载关键字的能力，
减少对原项目路径的依赖。

加载顺序:
1. adapters/<lang_id>/keywords.json（预缓存）
2. 从原项目动态加载（回退）
3. 内置 fallback 列表（最终兜底）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


# 适配器目录（_keywords_cache.py 位于 adapters/ 下）
_ADAPTERS_DIR = Path(__file__).resolve().parent


def load_cached_keywords(
    lang_id: str,
    dynamic_loader: Callable[[], list[str]] | None = None,
    fallback: list[str] | None = None,
) -> list[str]:
    """加载关键字（优先缓存）

    Args:
        lang_id: 语言ID，如 "duan"
        dynamic_loader: 从原项目动态加载关键字的函数（可选）
        fallback: 最终兜底列表

    Returns:
        关键字列表
    """
    # 1. 优先从缓存加载
    cache_file = _ADAPTERS_DIR / lang_id / "keywords.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except (json.JSONDecodeError, OSError):
            pass

    # 2. 动态加载
    if dynamic_loader is not None:
        try:
            result = dynamic_loader()
            if result:
                return result
        except Exception:
            pass

    # 3. 兜底
    return fallback or []
