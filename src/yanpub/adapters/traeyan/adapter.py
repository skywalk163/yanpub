"""趣言 (traeyan) 适配器

趣言项目位于 G:\traework\traeyan
CLI 入口: python -m traeyan.main <file>
REPL: python -m traeyan.main
特色: THULAC分词、动词吞噬解析、复合赋值、百家姓标识符
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import SubprocessAdapter


_TRAEYAN_PROJECT_DIR = resolve_lang_dir("traeyan")


class TraeyanAdapter(SubprocessAdapter):
    """趣言适配器 — 通过子进程调用趣言后端"""

    def __init__(self):
        super().__init__(
            name="趣言",
            lang_id="traeyan",
            version="0.8.0",
            extensions=[".行", ".yan"],
            run_command=["python", "-m", "traeyan.main"],
            eval_command=None,  # 无 -c 选项，使用临时文件 fallback
            repl_command=["python", "-m", "traeyan.main"],
            keywords_loader=_load_traeyan_keywords,
            primary_color="#2C3E50",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return ">>> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"趣言 v{self.version} — THULAC 分词驱动的中文编程语言\n"
            "支持动词吞噬解析、复合赋值、渐近类型系统\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_traeyan_keywords() -> list[str]:
    """加载趣言关键字（优先从缓存）"""
    return load_cached_keywords("traeyan", _load_traeyan_keywords_dynamic, _fallback_keywords())


def _load_traeyan_keywords_dynamic() -> list[str]:
    """从趣言项目的 parser.py 和 lexer.py 动态加载关键字列表"""
    parser_file = Path(_TRAEYAN_PROJECT_DIR) / "traeyan" / "parser.py"
    lexer_file = Path(_TRAEYAN_PROJECT_DIR) / "traeyan" / "lexer.py"

    result = set()

    # 从 parser.py 的 TokenType 字典提取
    if parser_file.exists():
        try:
            ns: dict = {}
            exec(parser_file.read_text(encoding="utf-8"), ns)
            token_type = ns.get("TokenType", {})
            if isinstance(token_type, dict):
                result.update(token_type.keys())
        except Exception:
            pass

    # 从 lexer.py 的 VERB_ARITY 提取
    if lexer_file.exists():
        try:
            ns: dict = {}
            exec(lexer_file.read_text(encoding="utf-8"), ns)
            verb_arity = ns.get("VERB_ARITY", {})
            if isinstance(verb_arity, dict):
                result.update(verb_arity.keys())
            verbs = ns.get("VERBS", {})
            if isinstance(verbs, dict):
                result.update(verbs.keys())
        except Exception:
            pass

    return sorted(result) if result else _fallback_keywords()


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
        "否则若",
        "当",
        "每",
        "遍历",
        "重复",
        "从",
        "到",
        # 逻辑
        "真",
        "假",
        "空",
        # 异常
        "尝试",
        "捕获",
        "最终",
        "抛出",
        "异常",
        # 模块
        "导入",
        # 模式匹配
        "匹配",
        "例",
        "其他",
        # 流程
        "返回",
        "断",
        "继",
        "结束",
        "完",
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
        "不等于",
        "且",
        "或",
        "非",
        "负",
        # 复合赋值
        "加等于",
        "减等于",
        "乘等于",
        "除等于",
        "模等于",
        "幂等于",
        # 类型
        "数",
        "符",
        "串",
        "布",
        "列",
        "集",
        # IO
        "印",
        # 结构体
        "结构体",
    ]
