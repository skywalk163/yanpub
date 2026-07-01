"""适配器路径解析 — 支持环境变量覆盖

每个语言适配器有一个硬编码的 Windows 路径（开发用），
但可以通过环境变量覆盖（Docker 部署用）。

路径解析优先级（从高到低）：
  1. 单语言环境变量（如 YAN_DIR=/opt/langs/yan）
  2. 基础目录环境变量 YANPUB_LANG_DIR（如 YANPUB_LANG_DIR=/opt/langs → yan 解析为 /opt/langs/yan）
  3. 适配器 default 参数
  4. _LANG_DIR_MAP 中的 Windows 默认路径

环境变量命名规则：
  YANPUB_LANG_DIR -> 基础目录，所有语言在其子目录下
  YAN_DIR     -> 言语言 yan
  ZHIXING_DIR -> 知行
  TRAEYAN_DIR -> 知行语言 traeyan
  YANZHI_DIR  -> 言知
  XINYU_DIR   -> 心语
  MOYAN_DIR   -> 墨言
  YANLV_DIR   -> 言律
  MINGDAO_DIR -> 明道
  HANYU_DIR   -> 翰语
  DUAN_DIR    -> 段言
  HUA_DIR     -> 华语
"""

from __future__ import annotations

import os
from pathlib import Path


# lang_id -> (环境变量名, Windows 默认路径)
_LANG_DIR_MAP: dict[str, tuple[str, str]] = {
    "yan":     ("YAN_DIR",     r"G:\dumategithub\newlisp\yan"),
    "zhixing": ("ZHIXING_DIR", r"G:\zhixing"),
    "traeyan": ("TRAEYAN_DIR", r"G:\traework\traeyan"),
    "yanzhi":  ("YANZHI_DIR",  r"G:\yanzhi"),
    "xinyu":   ("XINYU_DIR",   r"G:\dumategithub\chineseprogram"),
    "moyan":   ("MOYAN_DIR",   r"G:\atomcode\atomyan"),
    "yanlv":   ("YANLV_DIR",   r"G:\dumategithub\yanlv"),
    "mingdao": ("MINGDAO_DIR", r"G:\dumategithub\langbyracket"),
    "hanyu":   ("HANYU_DIR",   r"G:\opencode\hanyu"),
    "duan":    ("DUAN_DIR",    r"G:\dumategithub\duan"),
    "hua":     ("HUA_DIR",     r"G:\mimowork\hua"),
}


def resolve_lang_dir(lang_id: str, default: str | None = None) -> str:
    """解析语言项目目录

    优先级（从高到低）：
    1. 单语言环境变量（如 YAN_DIR）
    2. YANPUB_LANG_DIR 基础目录 + lang_id 子目录
    3. default 参数（适配器硬编码路径）
    4. _LANG_DIR_MAP 中的默认路径

    Returns:
        解析后的绝对路径字符串
    """
    if lang_id in _LANG_DIR_MAP:
        # 优先级 1: 单语言环境变量
        env_name, fallback = _LANG_DIR_MAP[lang_id]
        env_val = os.environ.get(env_name)
        if env_val:
            return env_val

        # 优先级 2: YANPUB_LANG_DIR 基础目录
        base_dir = os.environ.get("YANPUB_LANG_DIR")
        if base_dir:
            return str(Path(base_dir) / lang_id)

    # 优先级 3: default 参数
    if default:
        return default

    # 优先级 4: _LANG_DIR_MAP 默认路径
    if lang_id in _LANG_DIR_MAP:
        return _LANG_DIR_MAP[lang_id][1]

    raise ValueError(f"Unknown lang_id: {lang_id}")


def get_all_lang_dirs() -> dict[str, str]:
    """返回所有语言的解析后路径"""
    return {lang_id: resolve_lang_dir(lang_id) for lang_id in _LANG_DIR_MAP}
