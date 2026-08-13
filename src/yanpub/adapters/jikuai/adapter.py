r"""极快 (Jikuai) 语言适配器

极快项目位于 G:\jikuai
CLI 入口: python -m jikuai.main <file>
REPL: python -m jikuai.main (无参数进入 REPL)
"""

from __future__ import annotations

import os
from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import SubprocessAdapter


# 极快项目根目录
_JIKUAI_PROJECT_DIR = resolve_lang_dir("jikuai")
_JIKUAI_SRC_DIR = os.path.join(_JIKUAI_PROJECT_DIR, "src")


class JikuaiAdapter(SubprocessAdapter):
    """极快适配器 — 通过子进程调用极快后端

    极快 main.py 使用相对导入 (from ._version import ...)，
    必须用 python -m jikuai.main 方式启动，且 cwd 设为 src/ 目录。
    """

    def __init__(self):
        super().__init__(
            name="极快",
            lang_id="jikuai",
            version="0.20.0",
            extensions=[".快", ".jk"],
            run_command=["python", "-m", "jikuai.main"],
            eval_command=None,
            repl_command=["python", "-m", "jikuai.main"],
            keywords_loader=_load_jikuai_keywords,
            primary_color="#00BFA5",
            cwd=_JIKUAI_SRC_DIR,
        )

    @property
    def comment_syntax(self) -> str:
        return "--"

    @property
    def repl_prompt(self) -> str:
        return "极快> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"极快 v{self.version} — 极简 极速 极中国\n"
            "输入代码并回车执行，输入 退出 或 Ctrl+C 退出"
        )


def _load_jikuai_keywords() -> list[str]:
    """加载极快关键字（优先从缓存）"""
    return load_cached_keywords("jikuai", _load_jikuai_keywords_dynamic, _fallback_jikuai_keywords())


def _load_jikuai_keywords_dynamic() -> list[str]:
    """从极快项目的 keywords.py 动态加载关键字列表"""
    keywords_file = Path(_JIKUAI_PROJECT_DIR) / "src" / "jikuai" / "keywords.py"
    if not keywords_file.exists():
        return _fallback_jikuai_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)
        all_kw = ns.get("ALL_KEYWORDS", set())
        return sorted(all_kw)
    except Exception:
        return _fallback_jikuai_keywords()


def _fallback_jikuai_keywords() -> list[str]:
    return [
        "定义", "赋值", "设为", "如果", "那么", "否则如果", "否则",
        "当", "遍历", "于", "从", "到", "重复", "次", "跳出", "跳过",
        "函数", "接收", "返回", "类", "继承", "构造", "方法", "新建",
        "自身", "父类", "尝试", "捕获", "最终", "抛出",
        "导入", "导出", "文件", "作为",
        "真", "假", "空",
    ]
