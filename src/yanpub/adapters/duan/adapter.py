r"""段言 (Duan) 语言适配器

段言项目位于 G:\dumategithub\duan
CLI 入口: python cli/duan.py run <file>
"""

from __future__ import annotations

import os
from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter.adapter import SubprocessAdapter


# 段言项目根目录
_DUAN_PROJECT_DIR = r"G:\dumategithub\duan"
_DUAN_CLI = os.path.join(_DUAN_PROJECT_DIR, "cli", "duan.py")


class DuanAdapter(SubprocessAdapter):
    """段言适配器 — 通过子进程调用段言后端"""

    def __init__(self):
        super().__init__(
            name="段言",
            lang_id="duan",
            version="1.3.8",
            extensions=[".段", ".duan"],
            # 段言 CLI: python cli/duan.py run --backend src <file>
            # 使用 --backend src 避免 ANTLR ATN 版本不匹配问题
            run_command=["python", _DUAN_CLI, "run", "--backend", "src"],
            # 段言无 -e 选项，使用临时文件 fallback（父类自动处理）
            eval_command=None,
            repl_command=None,
            keywords_loader=_load_duan_keywords,
            primary_color="#E85D3A",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "段言> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"段言 v{self.version} — 用段落书写的编程语言\n输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_duan_keywords() -> list[str]:
    """加载段言关键字（优先从缓存）"""
    return load_cached_keywords("duan", _load_duan_keywords_dynamic, _fallback_duan_keywords())


def _load_duan_keywords_dynamic() -> list[str]:
    """从段言项目的 keywords.py 动态加载关键字列表

    如果加载失败则返回内置的基础列表。
    """
    keywords_file = Path(_DUAN_PROJECT_DIR) / "src" / "keywords.py"
    if not keywords_file.exists():
        return _fallback_duan_keywords()

    # 动态读取关键字，不 import（避免路径依赖问题）
    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)
        all_kw = ns.get("ALL_KEYWORDS", set())
        builtin_types = ns.get("BUILTIN_TYPES", set())
        verb_arity = ns.get("VERB_ARITY", {})
        # 合并所有关键字、内置类型、动词
        result = sorted(all_kw | builtin_types | set(verb_arity.keys()))
        return result
    except Exception:
        return _fallback_duan_keywords()


def _fallback_duan_keywords() -> list[str]:
    return [
        "设",
        "为",
        "段落",
        "参数",
        "返回",
        "结束",
        "如果",
        "那么",
        "否则",
        "当",
        "遍历",
        "在",
        "类",
        "继承",
        "属性",
        "构造",
        "新建",
        "己",
        "尝试",
        "捕获",
        "抛出",
        "最终",
        "导入",
        "从",
        "导出",
        "真",
        "假",
        "空",
    ]
