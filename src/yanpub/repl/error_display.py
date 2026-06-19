"""REPL 错误提示 — 解析执行错误并生成友好提示

将原始错误输出（如 Python traceback、Racket 错误等）转换为：
1. 错误类型标识（语法错误/运行时错误/名称错误等）
2. 错误位置提取（行号、列号）
3. 友好中文描述
4. 修复建议（基于关键字和语法规则）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class FriendlyError:
    """友好的错误信息"""

    error_type: str  # 语法错误 / 运行时错误 / 名称错误 / 类型错误 / 导入错误
    message: str  # 友好的中文错误描述
    line: int | None = None
    column: int | None = None
    raw_message: str = ""  # 原始错误信息
    suggestion: str = ""  # 修复建议


# ---- 错误模式匹配规则 ----

# Python 错误类型映射
_PYTHON_ERROR_MAP = {
    "SyntaxError": "语法错误",
    "IndentationError": "缩进错误",
    "NameError": "名称错误",
    "TypeError": "类型错误",
    "ValueError": "值错误",
    "KeyError": "键错误",
    "IndexError": "索引错误",
    "AttributeError": "属性错误",
    "ImportError": "导入错误",
    "ModuleNotFoundError": "模块未找到",
    "ZeroDivisionError": "除零错误",
    "FileNotFoundError": "文件未找到",
    "RecursionError": "递归过深",
    "RuntimeError": "运行时错误",
    "StopIteration": "迭代结束",
    "OverflowError": "溢出错误",
    "MemoryError": "内存不足",
    "TimeoutError": "执行超时",
}

# 修复建议映射
_SUGGESTION_MAP = {
    "语法错误": "请检查语句结构是否完整，关键字拼写是否正确，括号/引号是否配对。",
    "缩进错误": "请检查缩进是否一致，建议使用4个空格缩进。",
    "名称错误": "变量或函数名可能未定义。请检查：1) 是否已声明 2) 拼写是否正确 3) 作用域是否正确。",
    "类型错误": "操作符或函数的参数类型不匹配。请检查参数类型是否符合预期。",
    "值错误": "传入的值不合法。请检查数值范围和格式。",
    "除零错误": "除数不能为零，请检查分母的值。",
    "导入错误": "模块未找到。请检查：1) 模块名是否正确 2) 是否已安装。",
    "递归过深": "递归层数过多，请检查：1) 是否缺少递归终止条件 2) 是否可以改为迭代实现。",
    "运行时错误": "程序运行时发生错误，请检查代码逻辑。",
}

# 中文编程语言常见错误模式
_CHINESE_LANG_PATTERNS = [
    # 未闭合的引号
    (
        r"Unclosed string|EOL while scanning string literal|unterminated string",
        "语法错误",
        "字符串未闭合，请检查引号是否配对。",
    ),
    # 未闭合的括号
    (
        r"Unexpected indent|unmatched|missing closing|unexpected EOF",
        "语法错误",
        "代码结构不完整，请检查括号是否配对、语句块是否闭合。",
    ),
    # 中文标点问题
    (
        r"invalid (character|syntax).*[\u3000\uff1b\uff0c\uff08\uff09]",
        "语法错误",
        "代码中包含全角标点，请使用半角标点（英文括号、逗号等）。",
    ),
]


def parse_error(stderr: str, lang_name: str = "") -> FriendlyError:
    """解析错误输出，返回友好的错误提示

    Args:
        stderr: 原始标准错误输出
        lang_name: 语言名称（用于提示上下文）
    """
    if not stderr or not stderr.strip():
        return FriendlyError(
            error_type="未知错误",
            message="执行失败，但没有错误信息。",
        )

    stderr = stderr.strip()

    # 尝试匹配 Python 错误格式
    error = _parse_python_error(stderr)
    if error is not None:
        return error

    # 尝试匹配中文语言特定错误
    error = _parse_chinese_lang_error(stderr)
    if error is not None:
        return error

    # 通用回退：提取最有用的一行
    return _parse_generic_error(stderr, lang_name)


def _parse_python_error(stderr: str) -> Optional[FriendlyError]:
    """解析 Python 格式的错误输出"""
    # Python traceback 格式: "TypeError: ..." 或 "  File ..., line N"
    # 匹配错误类型
    type_match = re.search(r"^(\w+Error|\w+Warning|\w+Exception):\s*(.+)$", stderr, re.MULTILINE)
    if not type_match:
        # 尝试从最后一行匹配
        last_lines = stderr.strip().split("\n")
        for line in reversed(last_lines):
            type_match = re.match(r"^(\w+Error|\w+Warning|\w+Exception):\s*(.+)$", line.strip())
            if type_match:
                break

    if type_match is None:
        return None

    py_type = type_match.group(1)
    py_msg = type_match.group(2)

    error_type = _PYTHON_ERROR_MAP.get(py_type, "运行时错误")
    suggestion = _SUGGESTION_MAP.get(error_type, "")

    # 提取行号
    line_num = None
    line_match = re.search(r"line\s+(\d+)", stderr)
    if line_match:
        line_num = int(line_match.group(1))

    # 生成友好消息
    friendly_msg = _make_friendly_message(error_type, py_msg, line_num)

    return FriendlyError(
        error_type=error_type,
        message=friendly_msg,
        line=line_num,
        raw_message=py_msg,
        suggestion=suggestion,
    )


def _parse_chinese_lang_error(stderr: str) -> Optional[FriendlyError]:
    """解析中文编程语言特定的错误模式"""
    for pattern, error_type, suggestion in _CHINESE_LANG_PATTERNS:
        if re.search(pattern, stderr, re.IGNORECASE):
            # 提取行号
            line_num = None
            line_match = re.search(r"line\s+(\d+)", stderr)
            if line_match:
                line_num = int(line_match.group(1))

            return FriendlyError(
                error_type=error_type,
                message=suggestion,
                line=line_num,
                raw_message=stderr.split("\n")[-1] if stderr else "",
                suggestion=suggestion,
            )
    return None


def _parse_generic_error(stderr: str, lang_name: str) -> FriendlyError:
    """通用错误解析回退"""
    # 取最相关的行（通常是最后一行非空行）
    lines = [line.strip() for line in stderr.strip().split("\n") if line.strip()]
    relevant_line = lines[-1] if lines else stderr

    # 如果太长，截断
    if len(relevant_line) > 200:
        relevant_line = relevant_line[:200] + "..."

    # 尝试判断是否是语法错误
    error_type = "运行时错误"
    suggestion = ""
    if any(kw in stderr.lower() for kw in ["syntax", "parse", "语法", "unexpected", "invalid"]):
        error_type = "语法错误"
        suggestion = _SUGGESTION_MAP.get("语法错误", "")
    elif any(kw in stderr.lower() for kw in ["name", "undefined", "not defined", "未定义"]):
        error_type = "名称错误"
        suggestion = _SUGGESTION_MAP.get("名称错误", "")

    # 提取行号
    line_num = None
    line_match = re.search(r"line\s+(\d+)", stderr)
    if line_match:
        line_num = int(line_match.group(1))

    return FriendlyError(
        error_type=error_type,
        message=relevant_line,
        line=line_num,
        raw_message=stderr,
        suggestion=suggestion,
    )


def _make_friendly_message(error_type: str, raw_msg: str, line: int | None) -> str:
    """生成友好的中文错误消息"""
    parts = [f"[{error_type}]"]

    if line is not None:
        parts.append(f"第 {line} 行：")

    # 尝试翻译常见的 Python 错误消息
    friendly = raw_msg
    translations = {
        "name": "名称",
        "is not defined": "未定义",
        "cannot be": "不能",
        "unsupported operand": "不支持的操作",
        "invalid syntax": "语法无效",
        "unexpected EOF": "意外的文件结束",
        "missing": "缺少",
        "expected": "期望",
        "division by zero": "除以零",
        "maximum recursion depth": "递归深度超限",
        "module": "模块",
        "No module named": "未找到模块",
        "not found": "未找到",
    }

    # 如果消息包含中文，直接使用
    if re.search(r"[\u4e00-\u9fff]", raw_msg):
        friendly = raw_msg
    else:
        # 对纯英文消息做简单翻译
        for en, zh in translations.items():
            if en.lower() in raw_msg.lower():
                friendly = raw_msg  # 保留原文更准确
                break

    parts.append(friendly)
    return " ".join(parts)


def format_friendly_error(error: FriendlyError, lang_name: str = "") -> str:
    """将 FriendlyError 格式化为终端友好的输出

    使用 ANSI 颜色码高亮关键信息。
    """
    lines = []

    # 错误类型（红色）
    lines.append(f"\033[31m{error.error_type}\033[0m")

    # 错误消息
    if error.line is not None:
        lines.append(
            f"  位置：第 {error.line} 行" + (f"，第 {error.column} 列" if error.column else "")
        )
    lines.append(f"  {error.message}")

    # 修复建议（黄色）
    if error.suggestion:
        lines.append(f"  \033[33m提示：{error.suggestion}\033[0m")

    return "\n".join(lines)
