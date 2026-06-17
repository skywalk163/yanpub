r"""言律 (YanLv) 语言适配器

言律项目位于 G:\dumategithub\yanlv
CLI 入口: python -m yanlv 运行 <file>
REPL: python -m yanlv 交互
依赖: jieba（中文分词）
"""

from __future__ import annotations

from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter import SubprocessAdapter


_YANLV_PROJECT_DIR = r"G:\dumategithub\yanlv"


class YanlvAdapter(SubprocessAdapter):
    """言律适配器 — 通过子进程调用言律后端"""

    def __init__(self):
        super().__init__(
            name="言律",
            lang_id="yanlv",
            version="2.0.0",
            extensions=[".律", ".yan"],
            run_command=["python", "-m", "yanlv", "运行"],
            eval_command=None,  # 言律无 -c 选项，使用临时文件 fallback
            repl_command=["python", "-m", "yanlv", "交互"],
            keywords_loader=_load_yanlv_keywords,
            primary_color="#C0392B",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "言律> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"言律 v{self.version} — 意合式中文编程语言\n"
            "支持因果链、语境省略、状态流、意合式调用\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


def _load_yanlv_keywords() -> list[str]:
    """加载言律关键字（优先从缓存）"""
    return load_cached_keywords("yanlv", _load_yanlv_keywords_dynamic, _fallback_keywords())


def _load_yanlv_keywords_dynamic() -> list[str]:
    """从言律项目的 constants.py 动态加载关键字列表"""
    keywords_file = Path(_YANLV_PROJECT_DIR) / "src" / "yanlv" / "lexer" / "constants.py"
    if not keywords_file.exists():
        return _fallback_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KEYWORDS", {})
        if isinstance(keywords, dict):
            result.update(keywords.keys())
        elif isinstance(keywords, (set, list)):
            result.update(keywords)

        # 动词分类
        verb_categories = ns.get("VERB_CATEGORIES", {})
        if isinstance(verb_categories, dict):
            for cat_verbs in verb_categories.values():
                if isinstance(cat_verbs, (set, list, dict)):
                    result.update(cat_verbs.keys() if isinstance(cat_verbs, dict) else cat_verbs)

        return sorted(result) if result else _fallback_keywords()
    except Exception:
        return _fallback_keywords()


def _fallback_keywords() -> list[str]:
    return [
        # 定义与赋值
        "定", "定义", "设", "设置", "变量",
        # 控制流
        "如果", "要是", "否则", "不然", "否则如果", "否则要是",
        "当", "一直", "对于", "遍历", "每个", "直到",
        # 函数
        "函数", "参数", "调用", "返回", "结束", "循环",
        # 输入输出
        "输出", "打印", "显示",
        # 异常
        "尝试", "捕获", "抛出", "异常", "最终",
        # 模块
        "定义模块", "导入", "导出", "从", "作为", "命名空间", "结束模块",
        # 运算
        "加", "减", "乘", "除", "余",
        "等于", "大于", "小于", "大于等于", "小于等于", "不等于",
        # 内置数学
        "绝对值", "平方根", "幂", "正弦", "余弦", "正切", "自然对数", "阶乘",
        # 文件
        "读取文件", "写入文件", "追加文件", "文件存在", "文件大小",
    ]
