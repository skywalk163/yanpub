r"""言知 (Yanzhi) 语言适配器

言知项目位于 G:\yanzhi
CLI 入口: yanzhi <file> 或 python -m yanzhi.cli <file>
Eval: yanzhi -c '代码'
REPL: yanzhi
特色: 字节码VM、模式匹配、宏系统、双轨转义
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter.adapter import SubprocessAdapter


_YANZHI_PROJECT_DIR = r"G:\yanzhi"


class YanzhiAdapter(SubprocessAdapter):
    """言知适配器 — 通过子进程调用言知后端"""

    def __init__(self):
        super().__init__(
            name="言知",
            lang_id="yanzhi",
            version="0.1.0",
            extensions=[".知", ".yan"],
            run_command=["python", "-m", "yanzhi.cli"],
            eval_command=["python", "-m", "yanzhi.cli", "-c"],
            eval_mode="arg",
            repl_command=["python", "-m", "yanzhi.cli"],
            keywords_loader=_load_yanzhi_keywords,
            primary_color="#16A085",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "言知> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"言知 v{self.version} — 字节码VM驱动的中文编程语言\n"
            "支持模式匹配、宏系统、双轨转义\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_yanzhi_keywords() -> list[str]:
    """加载言知关键字（优先从缓存）"""
    return load_cached_keywords("yanzhi", _load_yanzhi_keywords_dynamic, _fallback_keywords())


def _load_yanzhi_keywords_dynamic() -> list[str]:
    """从言知项目的 pre_tokenizer.py 动态加载关键字列表"""
    keywords_file = Path(_YANZHI_PROJECT_DIR) / "src" / "yanzhi" / "compiler" / "pre_tokenizer.py"
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
        "定义",
        "赋值",
        "函数",
        "结构",
        "方法",
        "宏",
        "模块",
        # 控制流
        "如果",
        "那么",
        "否则",
        "遍历",
        "循环当",
        "对于",
        "每次",
        "算",
        "从",
        "到",
        "每隔",
        "要是",
        "就",
        "不然",
        "是",
        # 逻辑
        "真",
        "假",
        "空",
        # 异常
        "尝试",
        "捕获",
        "结束",
        "完毕",
        "返回",
        "抛出",
        # 模块
        "导入",
        "导出",
        "于",
        # 模式匹配
        "匹配",
        "情况",
        # DSL
        "启用",
        "策略",
        "引用",
        "模板",
        "嵌入",
        "展开嵌入",
        "执行",
        # 运算动词
        "相加",
        "相减",
        "相乘",
        "相除",
        "大于",
        "小于",
        "等于",
        # IO
        "打印",
        "读取",
    ]
