r"""翰语 (Hanyu) 语言适配器

翰语项目位于 G:\opencode\hanyu
CLI 入口: hanyu <file> 或 python -m hanyu.compiler <file.翰>
REPL 入口: python -m hanyu.repl
特色: LLVM IR 代码生成、百家姓标识符（406姓）、类型检查、JIT执行、
      WASM编译、结构体、导入系统、自举编译器、GC内存管理
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import SubprocessAdapter


_HANYU_PROJECT_DIR = resolve_lang_dir("hanyu")


class HanyuAdapter(SubprocessAdapter):
    """翰语适配器 — 通过子进程调用翰语后端

    翰语使用 LLVM IR 进行代码生成，支持 JIT 和子进程两种执行模式。
    v0.2.2 移除 Lark/Tree-sitter 后端（统一使用 Python 解析器），
    新增结构体、导入系统、GC内存管理、自举编译器。
    """

    def __init__(self):
        super().__init__(
            name="翰语",
            lang_id="hanyu",
            version="0.2.2",
            extensions=[".翰", ".hanyu"],
            run_command=["python", "-m", "hanyu.compiler"],
            eval_command=None,  # 编译型语言，无单行 eval
            repl_command=["python", "-m", "hanyu.repl"],
            keywords_loader=_load_hanyu_keywords,
            primary_color="#D35400",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "repl": True,
            "lsp": len(self.keywords) > 0,
            "package_manager": False,
            "debug": False,
            "wasm": True,
            "llvm": True,
            "type_checker": True,
            "struct": True,       # v0.2.1 结构体
            "import": True,       # v0.2.1 导入系统
            "gc": True,           # v0.2.1 GC内存管理
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
        # 宏与结构
        "宏用",
        "结构",
        "Python",
        # 类型与值
        "空值",
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
        # 内置函数
        "打印",
        "打印字符串",
        "调用",
        "不等于",
        "写JSON",
    ]
