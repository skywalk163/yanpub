"""标识符工具函数与常量 — navigator / refactor 共享

提供 CJK 感知的标识符判断、单词边界检测，以及中文编程语言的关键字与运算符常量。
"""

from __future__ import annotations


# ---- 标识符工具函数 ----


def _is_ident_char(ch: str) -> bool:
    """判断字符是否属于标识符（ASCII + CJK）"""
    return ch.isalnum() or ch == "_" or "\u4e00" <= ch <= "\u9fff"


def _is_cjk(ch: str) -> bool:
    """判断字符是否为 CJK 统一汉字"""
    return "\u4e00" <= ch <= "\u9fff"


def _is_word_boundary(text: str, idx: int, length: int) -> bool:
    """检查位置 idx 处长度为 length 的匹配是否具有单词边界

    用于引用搜索时排除子串匹配。
    """
    before_ok = idx == 0 or not _is_ident_char(text[idx - 1])
    after_ok = idx + length >= len(text) or not _is_ident_char(text[idx + length])
    return before_ok and after_ok


# ---- 定义类关键字 → 符号类型映射 ----

_DEFINITION_KEYWORDS: dict[str, str] = {
    "段落": "function",
    "函数": "function",
    "函": "function",
    "方法": "method",
    "类": "class",
    "定义": "function",
    "宏定": "function",
    "构造": "method",
}

# 符号类型 → SymbolKind 数值（LSP 协议）
_SYMBOL_KIND_MAP: dict[str, int] = {
    "function": 12,  # Function
    "method": 6,  # Method
    "class": 5,  # Class
    "variable": 13,  # Variable
}


# ---- 中文编程语言关键字集合 ----
# 用于 safe_rename 检测新名称是否是关键字

_CN_KEYWORDS: set[str] = {
    "段落",
    "函数",
    "函",
    "方法",
    "类",
    "定义",
    "宏定",
    "构造",
    "当",
    "遍历",
    "循环",
    "对于",
    "如果",
    "若",
    "尝试",
    "否则",
    "否则若",
    "否则如果",
    "捕获",
    "最终",
    "结束",
    "完",
    "完毕",
    "返回",
    "设",
    "为",
    "参数",
    "导入",
    "从",
    "导出",
    "继承",
    "属性",
    "己",
    "新建",
    "抛出",
    "空",
    "真",
    "假",
    "打印",
    "输出",
    "显示",
}

# 中文运算符集合（不作为标识符）
_CN_OPERATORS: set[str] = {
    "加",
    "减",
    "乘",
    "除",
    "取余",
    "等于",
    "不等于",
    "大于",
    "小于",
    "且",
    "或",
    "非",
}
