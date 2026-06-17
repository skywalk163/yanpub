r"""言 (Yan) 语言适配器

言/墨言项目位于 G:\atomcode\atomyan
CLI 入口: python yan.py <file>
Eval: python yan.py -e '代码'
REPL: python yan.py -i
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter import SubprocessAdapter


# 言/墨言项目根目录
_ATOMYAN_PROJECT_DIR = r"G:\atomcode\atomyan"
_YAN_CLI = str(Path(_ATOMYAN_PROJECT_DIR) / "yan.py")
_YANREPL = str(Path(_ATOMYAN_PROJECT_DIR) / "yanrepl.py")


class YanAdapter(SubprocessAdapter):
    """言适配器 — 通过子进程调用言后端"""

    def __init__(self):
        super().__init__(
            name="言",
            lang_id="yan",
            version="3.0.0",
            extensions=[".言", ".yan"],
            run_command=["python", _YAN_CLI],
            eval_command=["python", _YAN_CLI, "-e"],
            eval_mode="arg",
            repl_command=["python", _YAN_CLI, "-i"],
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
        return (
            f"言 v{self.version} — 墨言编程语言\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_yan_keywords() -> list[str]:
    """加载言关键字（优先从缓存）"""
    return load_cached_keywords("yan", _load_yan_keywords_dynamic, _fallback_yan_keywords())


def _load_yan_keywords_dynamic() -> list[str]:
    """从言项目的 lexer.py 动态加载关键字列表"""
    keywords_file = Path(_ATOMYAN_PROJECT_DIR) / "lexer.py"
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
        # 定义
        "定义", "赋值",
        # 控制流
        "如果", "那么", "否则", "每当", "时候", "遍历", "于中",
        # 函数与结构
        "函数", "宏定", "返回", "跳出", "继续",
        # 模块
        "导入", "来自", "导出",
        # 字面量
        "真值", "假值", "空值",
        # 错误处理
        "试", "捕获", "则",
        # 调试
        "断点",
        # 并发
        "产生",
    ]
