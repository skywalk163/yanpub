r"""知行 (Zhixing) 语言适配器

知行项目位于 G:\zhixing
CLI 入口: zhixing <file> 或 python -m yan.cli <file>
Eval: zhixing -c '代码'
REPL: zhixing -i
"""

from __future__ import annotations

import os
from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import SubprocessAdapter


_ZHIXING_PROJECT_DIR = resolve_lang_dir("zhixing")
_ZHIXING_CLI = os.path.join(_ZHIXING_PROJECT_DIR, "src", "zhixing", "cli.py")


class ZhixingAdapter(SubprocessAdapter):
    """知行适配器 — 通过子进程调用知行后端"""

    def __init__(self):
        super().__init__(
            name="知行",
            lang_id="zhixing",
            version="0.9.0",
            extensions=[".行", ".yan"],
            run_command=["python", _ZHIXING_CLI],
            eval_command=["python", _ZHIXING_CLI, "-c"],
            eval_mode="arg",
            repl_command=["python", _ZHIXING_CLI, "-i"],
            keywords_loader=_load_zhixing_keywords,
            primary_color="#E67E22",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "知行> "

    @property
    def repl_welcome(self) -> str:
        return f"知行 v{self.version} — 管道式中文编程语言\n输入代码并回车执行，输入 :help 查看帮助"


def _load_zhixing_keywords() -> list[str]:
    """加载知行关键字（优先从缓存）"""
    return load_cached_keywords("zhixing", _load_zhixing_keywords_dynamic, _fallback_keywords())


def _load_zhixing_keywords_dynamic() -> list[str]:
    """从知行项目的 pre_tokenizer.py 动态加载关键字列表"""
    keywords_file = Path(_ZHIXING_PROJECT_DIR) / "src" / "zhixing" / "compiler" / "pre_tokenizer.py"
    if not keywords_file.exists():
        return _fallback_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KEYWORDS", set())
        if isinstance(keywords, (set, list, tuple)):
            result.update(keywords)

        verbs = ns.get("VERBS", set())
        if isinstance(verbs, (set, list, tuple)):
            result.update(verbs)

        return sorted(result) if result else _fallback_keywords()
    except Exception:
        return _fallback_keywords()


def _fallback_keywords() -> list[str]:
    return [
        # 定义与赋值
        "定",
        "设",
        "函",
        # 控制流
        "若",
        "则",
        "否则",
        "当",
        "遍历",
        "入",
        "于",
        # 逻辑
        "真",
        "假",
        "空",
        # 异常
        "尝试",
        "捕获",
        "结束",
        "完毕",
        # 模块
        "导入",
        "导出",
        "模块",
        "从",
        "为",
        # 运算
        "加",
        "减",
        "乘",
        "除",
        "模",
        "幂",
        "大",
        "小",
        "等",
        "不等",
        # 函数式
        "皆",
        "只",
        "归",
        "并",
        # 返回
        "返回",
    ]
