r"""墨言 (Moyan) 语言适配器

墨言项目位于 G:\atomcode\atomyan（与言共享同一后端，使用 --vm 选项）
CLI 入口: python yan.py --vm <file>
Eval: python yan.py --vm -e '代码'
REPL: python yan.py --vm -i
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter import SubprocessAdapter


# 墨言项目根目录（与言共享，使用 VM 后端）
_ATOMYAN_PROJECT_DIR = r"G:\atomcode\atomyan"
_YAN_CLI = str(Path(_ATOMYAN_PROJECT_DIR) / "yan.py")


class MoyanAdapter(SubprocessAdapter):
    """墨言适配器 — 通过子进程调用墨言 VM 后端"""

    def __init__(self):
        super().__init__(
            name="墨言",
            lang_id="moyan",
            version="3.0.0",
            extensions=[".墨", ".moyan"],
            run_command=["python", _YAN_CLI, "--vm"],
            eval_command=["python", _YAN_CLI, "--vm", "-e"],
            eval_mode="arg",
            repl_command=["python", _YAN_CLI, "--vm", "-i"],
            keywords_loader=_load_moyan_keywords,
            primary_color="#8E44AD",
        )

    @property
    def comment_syntax(self) -> str:
        """墨言使用 -- 作为注释语法"""
        return "--"

    @property
    def repl_prompt(self) -> str:
        return "墨言> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"墨言 v{self.version} — 知行编程语言（VM 后端）\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_moyan_keywords() -> list[str]:
    """加载墨言关键字（优先从缓存）"""
    return load_cached_keywords("moyan", _load_moyan_keywords_dynamic, _fallback_moyan_keywords())


def _load_moyan_keywords_dynamic() -> list[str]:
    """从墨言项目的 lexer.py 动态加载关键字列表"""
    keywords_file = Path(_ATOMYAN_PROJECT_DIR) / "lexer.py"
    if not keywords_file.exists():
        return _fallback_moyan_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KEYWORDS", set())
        if isinstance(keywords, (set, list, tuple, frozenset)):
            result.update(keywords)

        return sorted(result) if result else _fallback_moyan_keywords()
    except Exception:
        return _fallback_moyan_keywords()


def _fallback_moyan_keywords() -> list[str]:
    return [
        # 定义与赋值
        "定义", "赋值",
        # 控制流
        "如果", "那么", "否则", "每当", "时候", "遍历", "于中",
        # 函数
        "函数", "宏定",
        # 模块
        "导入", "来自", "导出",
        # 字面量
        "真值", "假值", "空值",
        # 流程控制
        "返回", "跳出", "继续",
        # 错误处理
        "试", "捕获", "则",
        # 调试
        "断点",
        # 并发
        "产生",
    ]
