r"""言 (Yan) 语言适配器

言语言项目位于 G:\dumategithub\newlisp\yan
CLI 入口: python main.py <file>
Eval: python main.py -c (从 stdin 读取)
REPL: python main.py
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter.adapter import SubprocessAdapter


# 言语言项目根目录
_YAN_PROJECT_DIR = r"G:\dumategithub\newlisp\yan"
_YAN_CLI = str(Path(_YAN_PROJECT_DIR) / "main.py")


class YanAdapter(SubprocessAdapter):
    """言适配器 — 通过子进程调用言后端"""

    def __init__(self):
        super().__init__(
            name="言",
            lang_id="yan",
            version="3.0.0",
            extensions=[".言", ".yan"],
            run_command=["python", _YAN_CLI],
            eval_command=["python", _YAN_CLI, "-c"],
            eval_mode="stdin",
            repl_command=["python", _YAN_CLI],
            keywords_loader=_load_yan_keywords,
            primary_color="#2980B9",
        )

    @property
    def comment_syntax(self) -> str:
        return "--"

    @property
    def repl_prompt(self) -> str:
        return "言> "

    @property
    def repl_welcome(self) -> str:
        return f"言 v{self.version} — 言编程语言\n输入代码并回车执行，输入 :help 查看帮助"


def _load_yan_keywords() -> list[str]:
    """加载言关键字（优先从缓存）"""
    return load_cached_keywords("yan", _load_yan_keywords_dynamic, _fallback_yan_keywords())


def _load_yan_keywords_dynamic() -> list[str]:
    """从言项目的 lexer.py 动态加载关键字列表"""
    keywords_file = Path(_YAN_PROJECT_DIR) / "lexer.py"
    if not keywords_file.exists():
        return _fallback_yan_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KEYWORDS", set())
        if isinstance(keywords, (set, list, tuple, frozenset)):
            result.update(keywords)

        return sorted(result) if result else _fallback_yan_keywords()
    except Exception:
        return _fallback_yan_keywords()


def _fallback_yan_keywords() -> list[str]:
    return [
        # 定义与赋值
        "定",
        "定义",
        # 控制流
        "若",
        "如果",
        "则",
        "那么",
        "否则",
        "当",
        "每当",
        "时候",
        "遍历",
        "于",
        "于中",
        # 函数
        "函",
        "函数",
        "返回",
        "跳出",
        "继续",
        # 模块
        "导入",
        "来自",
        "导出",
        # 字面量
        "真",
        "假",
        "空",
        # 错误处理
        "试",
        "捕获",
        # 输出
        "印",
        # 注释
        "注",
        # 并发
        "产生",
        # 中文运算
        "加",
        "减",
        "乘",
        "除",
        "大",
        "小",
        "等",
        # 管道
        "皆",
        "只",
        "归",
    ]
