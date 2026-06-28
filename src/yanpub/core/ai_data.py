"""AI 辅助数据定义 — 配置、模板与常量

本模块存放 AIAssistEngine 所需的纯数据常量，不包含业务逻辑。
由 yanpub.core.ai_assist 导入使用。
"""

from __future__ import annotations

from dataclasses import dataclass


# ============================================================
# 配置
# ============================================================


@dataclass
class AIAssistConfig:
    """AI 辅助配置"""

    provider: str = "local"  # "local" | "openai" | "custom"
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    max_tokens: int = 1024
    temperature: float = 0.7


# ============================================================
# 自然语言意图模板
# ============================================================


_NL_TEMPLATES: dict[str, dict] = {
    "print": {
        "patterns": ["打印", "输出", "显示", "印"],
        "templates": {
            "duan": '打印("{text}")。',
            "yan": '打印("{text}")',
            "default": '打印("{text}")',
        },
    },
    "variable": {
        "patterns": ["设", "定义变量", "声明变量", "赋值"],
        "templates": {
            "duan": "设{name}为{value}。",
            "default": "设{name}为{value}",
        },
    },
    "function": {
        "patterns": ["定义函数", "写个函数", "创建函数", "定义段落", "写个段落"],
        "templates": {
            "duan": '段落 {name}。\n  打印("{name}")。\n结束。',
            "default": '段落 {name}。\n  打印("{name}")。\n结束。',
        },
    },
    "loop": {
        "patterns": ["循环", "遍历", "重复"],
        "templates": {
            "duan": "当 {condition}：\n  {body}\n结束。",
            "default": "当 {condition}：\n  {body}\n结束。",
        },
    },
    "condition": {
        "patterns": ["如果", "判断", "条件"],
        "templates": {
            "duan": "如果 {condition}：\n  {body}\n结束。",
            "default": "如果 {condition}：\n  {body}\n结束。",
        },
    },
    "class": {
        "patterns": ["定义类", "写个类", "创建类"],
        "templates": {
            "duan": "类 {name}。\n  属性 {attr}。\n  构造 参数 {param}。\n    己{attr} 为 {param}。\n  结束。\n结束。",
            "default": "类 {name}。\n  属性 {attr}。\n结束。",
        },
    },
    "return": {
        "patterns": ["返回", "返回值"],
        "templates": {
            "duan": "返回 {value}。",
            "default": "返回 {value}",
        },
    },
    "import": {
        "patterns": ["导入", "引入", "引用模块"],
        "templates": {
            "duan": "导入《{module}》。",
            "default": "导入 {module}",
        },
    },
}


# ============================================================
# 错误修复规则
# ============================================================


_FIX_RULES: list[dict] = [
    # 未闭合的块
    {
        "pattern": r"缺少.*结束|未闭合|unclosed|unexpected.*EOF|IndentationError",
        "fix": "add_end_marker",
        "confidence": 0.9,
    },
    # 拼写错误 / 未定义变量
    {
        "pattern": r"未定义|undefined|NameError|not defined",
        "fix": "suggest_similar",
        "confidence": 0.7,
    },
    # 语法错误
    {
        "pattern": r"语法错误|SyntaxError|syntax|invalid syntax",
        "fix": "suggest_syntax_fix",
        "confidence": 0.6,
    },
]


# ============================================================
# 模式匹配规则（智能补全用）
# ============================================================

# 块关键字 → 期望的结束标记
_BLOCK_KEYWORDS: dict[str, str] = {
    "如果": "结束",
    "当": "结束",
    "遍历": "结束",
    "段落": "结束",
    "类": "结束",
    "尝试": "结束",
    "否则": None,  # 否则不需要独立结束
}

# 关键字后期望的补全片段
_KEYWORD_SNIPPETS: dict[str, dict] = {
    "如果": {
        "insert_text": "如果 {condition}：\n  {body}\n结束。",
        "detail": "条件语句",
    },
    "当": {
        "insert_text": "当 {condition}：\n  {body}\n结束。",
        "detail": "当循环",
    },
    "遍历": {
        "insert_text": "遍历 {list} 中的 {item}：\n  {body}\n结束。",
        "detail": "遍历循环",
    },
    "段落": {
        "insert_text": "段落 {name}。\n  {body}\n结束。",
        "detail": "段落/函数定义",
    },
    "设": {
        "insert_text": "设{name}为{value}。",
        "detail": "变量声明",
    },
    "类": {
        "insert_text": "类 {name}。\n  {body}\n结束。",
        "detail": "类定义",
    },
    "尝试": {
        "insert_text": "尝试：\n  {body}\n捕获 e：\n  {handler}\n结束。",
        "detail": "异常处理",
    },
    "打印": {
        "insert_text": '打印("")。',
        "detail": "打印输出",
    },
    "返回": {
        "insert_text": "返回 {value}。",
        "detail": "返回值",
    },
}
