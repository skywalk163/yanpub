r"""华语/华码 (Hua) 语言适配器

华语项目位于 G:\mimowork\hua
CLI 入口: python 华码.py <file>
REPL: python 华码.py
无独立 eval 模式，使用 run + 临时文件实现
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.adapters._path_resolver import resolve_lang_dir
from yanpub.core.adapter.adapter import ExecutionResult, SubprocessAdapter


# 华语项目根目录
_HUA_PROJECT_DIR = resolve_lang_dir("hua")
_HUA_CLI = str(Path(_HUA_PROJECT_DIR) / "华码.py")


class HuaAdapter(SubprocessAdapter):
    """华语适配器 — 通过子进程调用华码后端"""

    def __init__(self):
        super().__init__(
            name="华语",
            lang_id="hua",
            version="0.5.0",
            extensions=[".华", ".hua"],
            run_command=["python", _HUA_CLI],
            eval_command=["python", _HUA_CLI],
            eval_mode="stdin",
            repl_command=["python", _HUA_CLI],
            keywords_loader=_load_hua_keywords,
            primary_color="#E67E22",
        )

    @property
    def comment_syntax(self) -> str:
        """华语使用 // 作为注释语法"""
        return "//"

    @property
    def repl_prompt(self) -> str:
        return "华码> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"华语 v{self.version} — 无括号，无结束，缩进块\n"
            "输入代码并回车执行，输入 退出 退出"
        )

    def eval(self, code: str) -> ExecutionResult:
        """执行代码片段 — 写入临时文件后调用 run"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".hua", encoding="utf-8", delete=False
        ) as f:
            f.write(code)
            tmp_path = f.name
        try:
            return self.run(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def _load_hua_keywords() -> list[str]:
    """加载华语关键字（优先从缓存）"""
    return load_cached_keywords("hua", _load_hua_keywords_dynamic, _fallback_hua_keywords())


def _load_hua_keywords_dynamic() -> list[str]:
    """从华语项目的词法.py 动态加载关键字列表"""
    keywords_file = Path(_HUA_PROJECT_DIR) / "引擎" / "词法.py"
    if not keywords_file.exists():
        return _fallback_hua_keywords()

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)

        result = set()
        keywords = ns.get("KW", {})
        if isinstance(keywords, dict):
            result.update(keywords.keys())

        return sorted(result) if result else _fallback_hua_keywords()
    except Exception:
        return _fallback_hua_keywords()


def _fallback_hua_keywords() -> list[str]:
    return [
        # 声明
        "变量", "常量", "函数", "参数", "返回",
        # 控制流
        "如果", "否则如果", "否则", "对于", "在", "当", "循环",
        "遍历", "每个", "跳出", "继续",
        # 赋值
        "为",
        # 比较
        "等于", "不等于", "大于", "小于", "大于等于", "小于等于",
        # 逻辑
        "并且", "或者", "或", "不",
        # 算术
        "加", "减", "乘", "除", "取余", "幂",
        # 类型名
        "整数", "浮点数", "布尔", "文本", "空值",
        # 字面量
        "真", "假",
        # 映射
        "映射到",
        # 导入
        "导入", "从", "中的",
        # 异常
        "尝试", "捕获", "最终", "抛出",
        # OOP
        "类", "方法", "新", "自己", "结构体", "枚举", "接口", "实现",
        # 模式匹配
        "匹配", "其他",
        # 默认
        "默认",
        # 错误类型
        "错误类型",
        # 异步
        "异步", "等待", "使用", "作为",
        # 重试
        "重试",
        # 生成器
        "产出", "产出自",
        # 范围
        "到", "之间",
    ]
