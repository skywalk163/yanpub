r"""心语 (XinYu) 语言适配器

心语项目位于 G:\dumategithub\chineseprogram
CLI 入口: python src/main.py <file>
Eval: python src/main.py -c '代码'
REPL: python src/main.py
"""

from __future__ import annotations

import os
from pathlib import Path

from yanpub.core.adapter.adapter import SubprocessAdapter


_XINYU_PROJECT_DIR = r"G:\dumategithub\chineseprogram"
_XINYU_CLI = os.path.join(_XINYU_PROJECT_DIR, "src", "main.py")


class XinyuAdapter(SubprocessAdapter):
    """心语适配器 — 通过子进程调用心语后端"""

    def __init__(self):
        super().__init__(
            name="心语",
            lang_id="xinyu",
            version="0.1.0",
            extensions=[".心", ".xinyu"],
            run_command=["python", _XINYU_CLI],
            eval_command=["python", _XINYU_CLI, "-c"],
            eval_mode="arg",
            repl_command=["python", _XINYU_CLI],
            keywords_loader=_load_xinyu_keywords,
            primary_color="#27AE60",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "心语> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"心语 v{self.version} — 安全、简洁的中文编程语言\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_xinyu_keywords() -> list[str]:
    """从心语项目的 keywords.py 加载关键字列表"""
    keywords_file = Path(_XINYU_PROJECT_DIR) / "src" / "lexer" / "keywords.py"
    if not keywords_file.exists():
        return _fallback_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        # 心语有双字关键字和单字关键字两套
        for attr in ("KEYWORDS", "CORE_KEYWORDS", "SYNTAX_MARKERS"):
            val = ns.get(attr, {})
            if isinstance(val, dict):
                result.update(val.keys())
            elif isinstance(val, (set, list)):
                result.update(val)

        # 内置函数
        builtin_funcs = ns.get("BUILTIN_FUNCTIONS", {})
        if isinstance(builtin_funcs, dict):
            result.update(builtin_funcs.keys())

        # 动词
        verbs = ns.get("VERBS", {})
        if isinstance(verbs, dict):
            result.update(verbs.keys())

        return sorted(result) if result else _fallback_keywords()
    except Exception:
        return _fallback_keywords()


def _fallback_keywords() -> list[str]:
    return [
        # 双字关键字
        "定义",
        "函数",
        "如果",
        "那么",
        "否则",
        "可选",
        "循环",
        "当满足",
        "遍历",
        "返回",
        "继续",
        "跳出",
        "结束",
        "尝试",
        "捕获",
        "最终",
        "抛出",
        "导入",
        "从",
        "真值",
        "假值",
        # 单字关键字
        "定",
        "函",
        "若",
        "真",
        "假",
        # 函数式
        "皆",
        "只",
        "归",
        # 运算
        "相加",
        "加",
        "相减",
        "减",
        "相乘",
        "乘",
        "相除",
        "除",
        "等于",
        "等",
        "大于",
        "大",
        "小于",
        "小",
        "且",
        "或",
        "非",
    ]
