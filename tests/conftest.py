"""测试共享 fixtures 和辅助函数"""

from __future__ import annotations

import pytest


def lang_backend_available(lang_id: str) -> bool:
    """检查指定语言的执行后端是否可用（需要本地项目文件）

    CI 环境中没有本地语言项目，这些测试应自动 skip。
    """
    try:
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return False
        result = adapter.eval('打印("test")')
        return result.exit_code == 0
    except Exception:
        return False


def skip_if_no_backend(lang_id: str):
    """如果后端不可用则跳过测试"""
    if not lang_backend_available(lang_id):
        pytest.skip(f"{lang_id} 后端不可用（需本地项目）")
