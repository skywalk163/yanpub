"""i18n 核心函数：语言设置与翻译查找"""

from __future__ import annotations

import os
from typing import Optional

from yanpub.i18n_pkg.translations import MESSAGES, SUPPORTED_LANGS

# 当前语言
_current_lang: str = "zh"


def get_lang() -> str:
    """获取当前语言设置"""
    return _current_lang


def set_lang(lang: str) -> None:
    """设置当前语言"""
    global _current_lang
    if lang in SUPPORTED_LANGS:
        _current_lang = lang
    else:
        _current_lang = "zh"  # 回退到中文


def init_lang() -> None:
    """从环境变量初始化语言设置"""
    env_lang = os.environ.get("YANPUB_LANG", "").lower()
    if env_lang:
        set_lang(env_lang)
    else:
        # 检测系统语言
        import locale

        try:
            sys_lang = locale.getlocale()[0] or ""
            if sys_lang.startswith("en"):
                set_lang("en")
        except Exception:
            pass


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """翻译消息

    Args:
        key: 消息键（点分格式，如 "error.syntax"）
        lang: 指定语言（默认使用当前语言）
        **kwargs: 格式化参数

    Returns:
        翻译后的消息字符串
    """
    target_lang = lang or _current_lang

    # 查找消息
    messages = MESSAGES.get(target_lang, {})
    msg = messages.get(key)

    # 回退到中文
    if msg is None and target_lang != "zh":
        msg = MESSAGES.get("zh", {}).get(key)

    # 回退到键名本身
    if msg is None:
        msg = key

    # 格式化参数
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return msg


# 启动时初始化语言
init_lang()
