r"""翰语 (Hanyu) 语言适配器

翰语项目位于 G:\opencode\hanyu
CLI 入口: hanyu <file> 或 python -m hanyu.compiler <file>
无 REPL（有 Playground HTTP 服务）
特色: LLVM IR 代码生成、Tree-sitter 解析、百家姓标识符、WASM 编译
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter import SubprocessAdapter


_HANYU_PROJECT_DIR = r"G:\opencode\hanyu"


class HanyuAdapter(SubprocessAdapter):
    """翰语适配器 — 通过子进程调用翰语后端

    翰语使用 LLVM IR 进行代码生成，支持 JIT 和子进程两种执行模式。
    无内置 REPL，但可通过 Playground HTTP 服务进行交互。
    """

    def __init__(self):
        super().__init__(
            name="翰语",
            lang_id="hanyu",
            version="0.1.0",
            extensions=[".翰", ".hanyu"],
            run_command=["python", "-m", "hanyu.compiler"],
            eval_command=None,  # 无 eval 选项
            repl_command=None,  # 无 REPL
            keywords_loader=_load_hanyu_keywords,
            primary_color="#D35400",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "repl": False,  # 翰语无 REPL
            "lsp": len(self.keywords) > 0,
            "package_manager": False,
            "debug": False,
            "wasm": True,  # 支持 WASM 编译目标
            "llvm": True,  # 声明使用 LLVM 后端
        }


def _load_hanyu_keywords() -> list[str]:
    """加载翰语关键字（优先从缓存）"""
    return load_cached_keywords("hanyu", _load_hanyu_keywords_dynamic, _fallback_keywords())


def _load_hanyu_keywords_dynamic() -> list[str]:
    """从翰语项目的 lexer.py 动态加载关键字列表"""
    lexer_file = Path(_HANYU_PROJECT_DIR) / "src" / "hanyu" / "lexer.py"
    if not lexer_file.exists():
        return _fallback_keywords()

    try:
        ns: dict = {}
        exec(lexer_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KEYWORDS", {})
        if isinstance(keywords, dict):
            result.update(keywords.keys())
        elif isinstance(keywords, (set, list)):
            result.update(keywords)

        # 单字关键字
        single_cjk = ns.get("SINGLE_CJK_KEYWORDS", set())
        if isinstance(single_cjk, (set, list)):
            result.update(single_cjk)

        # 内置函数
        builtins = ns.get("BUILTIN_FUNCTIONS", {})
        if isinstance(builtins, (dict, set, list)):
            if isinstance(builtins, dict):
                result.update(builtins.keys())
            else:
                result.update(builtins)

        # 操作符
        for op_name in ("OPERATORS_1", "OPERATORS_2", "OPERATORS_3"):
            ops = ns.get(op_name, {})
            if isinstance(ops, dict):
                result.update(ops.keys())
            elif isinstance(ops, (set, list)):
                result.update(ops)

        return sorted(result) if result else _fallback_keywords()
    except Exception:
        return _fallback_keywords()


def _fallback_keywords() -> list[str]:
    return [
        # 定义与控制流
        "定义",
        "函数",
        "返回",
        "如果",
        "那么",
        "否则",
        "循环",
        "当满",
        "对于",
        "跳出",
        "继续",
        "导入",
        # 宏
        "宏用",
        # 结构
        "结构",
        # 类型
        "空值",
        "整数",
        "实数",
        "字符串",
        "布尔",
        "产出",
        # 单字
        "在",
        "真",
        "假",
        "负",
        "为",
        # 运算（3字）
        "小于等于",
        "大于等于",
        # 运算（2字）
        "等于",
        "不等",
        "大于",
        "小于",
        "大于等",
        "小于等",
        "并且",
        "或者",
        "右移",
        "左移",
        # 运算（1字）
        "加",
        "减",
        "乘",
        "除",
        "余",
        "等",
        "负",
        "取",
        # 内置
        "打印",
        "长度",
        "调用",
    ]
