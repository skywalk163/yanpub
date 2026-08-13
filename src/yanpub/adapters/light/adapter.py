r"""光明 (Light) 语言适配器

光明项目位于 G:\github\light
CLI 入口: python cli/light.py run <file>
REPL: python cli/light.py repl
"""

from __future__ import annotations

import os
from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import SubprocessAdapter


# 光明项目根目录
_LIGHT_PROJECT_DIR = resolve_lang_dir("light")
_LIGHT_CLI = os.path.join(_LIGHT_PROJECT_DIR, "cli", "light.py")


class LightAdapter(SubprocessAdapter):
    """光明适配器 — 通过子进程调用光明后端"""

    def __init__(self):
        super().__init__(
            name="光明",
            lang_id="light",
            version="6.0.0",
            extensions=[".明", ".light"],
            run_command=["python", _LIGHT_CLI, "run"],
            eval_command=None,
            repl_command=["python", _LIGHT_CLI, "repl"],
            keywords_loader=_load_light_keywords,
            primary_color="#FFD600",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "光明> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"光明 v{self.version} — 像中文一样的中文编程语言\n"
            "输入代码并回车执行，输入 退出 退出"
        )


def _load_light_keywords() -> list[str]:
    """加载光明关键字（优先从缓存）"""
    return load_cached_keywords("light", _load_light_keywords_dynamic, _fallback_light_keywords())


def _load_light_keywords_dynamic() -> list[str]:
    """从光明项目的 keywords.py 动态加载关键字列表"""
    keywords_file = Path(_LIGHT_PROJECT_DIR) / "src" / "keywords.py"
    if not keywords_file.exists():
        return _fallback_light_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)
        all_kw = ns.get("ALL_KEYWORDS", set())
        return sorted(all_kw)
    except Exception:
        return _fallback_light_keywords()


def _fallback_light_keywords() -> list[str]:
    return [
        "若", "否", "当", "遍", "跳", "过", "返", "设", "段", "类",
        "承", "接", "配", "试", "捕", "抛", "终", "自", "之", "并",
        "从", "是", "且", "或", "非", "真", "假", "空", "导", "出",
        "定义", "常量", "类型", "导入", "导出", "为", "如果", "那么",
        "否则", "否则若", "则", "遍历", "跳出", "跳过", "在", "对",
        "中的", "于", "函数", "段落", "接收", "返回", "严格", "松散",
        "尝试", "捕获", "抛出", "最终", "继承", "属性", "构造", "新建",
        "接口", "实现", "私属性", "私段落", "私有", "公有", "保护",
        "静态", "静态方法", "类方法", "特性", "模块", "标准库",
        "异步", "等待", "作用域", "匹配", "情况", "使用", "标注",
        "嵌入", "结束嵌入", "引", "结束引", "外部", "外部错误",
        "加载库", "包含", "位域", "回调", "函数指针", "变长参数",
        "宏", "结构体", "联合体", "枚举", "类型别名", "调试", "步", "至",
    ]
