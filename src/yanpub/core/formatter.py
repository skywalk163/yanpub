"""代码格式化器 — 为中文编程语言提供统一的格式化规则

默认规则（LanguageAdapter.format() 使用）：
  1. Tab → 4 空格
  2. 行尾空格清理
  3. 多余空行合并（最多2个连续空行）
  4. 文件末尾确保一个换行

进阶规则（ChineseCodeFormatter）：
  5. 块关键字后自动缩进
  6. 运算符前后空格规范化
  7. 中文标点后空格（可选）

各适配器可覆盖 format() 方法提供语言特定格式化。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class FormatterConfig:
    """格式化器配置"""
    indent_size: int = 4
    use_tabs: bool = False
    max_blank_lines: int = 2
    trim_trailing_whitespace: bool = True
    insert_final_newline: bool = True
    # 块开始关键字（用于自动缩进推断）
    block_start_keywords: list[str] = field(default_factory=lambda: [
        "如果", "若", "当", "遍历", "循环", "对于", "尝试",
        "函数", "段落", "类", "定义",
        "否则", "否则若", "捕获", "最终",
    ])
    # 块结束关键字
    block_end_keywords: list[str] = field(default_factory=lambda: [
        "结束", "完毕", "完",
    ])
    # 冒号关键字（这些关键字后跟冒号表示块开始）
    colon_keywords: list[str] = field(default_factory=lambda: [
        "如果", "若", "当", "遍历", "对于", "尝试",
        "否则", "否则若", "捕获", "最终",
    ])
    # 运算符前后是否加空格
    space_around_operators: bool = True


class ChineseCodeFormatter:
    """中文编程语言代码格式化器

    提供基于规则的格式化，适用于所有中文编程语言。
    适配器可以覆盖 format() 使用此类，或直接继承其规则。
    """

    def __init__(self, config: FormatterConfig | None = None):
        self.config = config or FormatterConfig()

    def format(self, code: str) -> str:
        """格式化代码"""
        lines = code.split("\n")

        # Step 1: Tab → spaces
        indent_str = "\t" if self.config.use_tabs else " " * self.config.indent_size
        lines = [line.replace("\t", indent_str) for line in lines]

        # Step 2: Trim trailing whitespace
        if self.config.trim_trailing_whitespace:
            lines = [line.rstrip() for line in lines]

        # Step 3: Normalize blank lines
        lines = self._normalize_blank_lines(lines)

        # Step 4: Normalize indentation (best-effort for Chinese keywords)
        lines = self._normalize_indentation(lines)

        # Step 5: Normalize operator spacing
        if self.config.space_around_operators:
            lines = [self._normalize_operator_spacing(line) for line in lines]

        # Step 6: Final newline
        while lines and lines[-1] == "":
            lines.pop()
        result = "\n".join(lines)
        if self.config.insert_final_newline and result:
            result += "\n"

        return result

    def _normalize_blank_lines(self, lines: list[str]) -> list[str]:
        """合并多余空行"""
        result: list[str] = []
        blank_count = 0
        for line in lines:
            if line.strip() == "":
                blank_count += 1
                if blank_count <= self.config.max_blank_lines:
                    result.append(line)
            else:
                blank_count = 0
                result.append(line)
        return result

    def _normalize_indentation(self, lines: list[str]) -> list[str]:
        """基于关键字的缩进规范化（best-effort）

        策略：
        - 块开始关键字（如果/当/类等）后的行增加缩进
        - 块结束关键字（结束）减少缩进
        - 保持原有缩进关系不变的情况下修正
        """
        indent_str = "\t" if self.config.use_tabs else " " * self.config.indent_size
        block_starts = set(self.config.block_start_keywords)
        block_ends = set(self.config.block_end_keywords)

        result: list[str] = []
        indent_level = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append("")
                continue

            # 块结束关键字 → 先减缩进
            is_block_end = any(
                stripped.startswith(kw) or stripped == kw
                for kw in block_ends
            )

            current_indent = indent_level
            if is_block_end:
                current_indent = max(0, indent_level - 1)

            # 写入当前行
            result.append(indent_str * current_indent + stripped)

            # 更新缩进级别
            if is_block_end:
                indent_level = max(0, indent_level - 1)

            # 块开始关键字 → 下一行增加缩进
            is_block_start = any(
                stripped.startswith(kw) for kw in block_starts
            )
            # 也检测行尾冒号
            if is_block_start or stripped.endswith("：") or stripped.endswith(":"):
                # 只有冒号关键字或行尾冒号才算
                is_colon_block = stripped.endswith("：") or stripped.endswith(":")
                is_keyword_block = any(
                    stripped.startswith(kw) for kw in self.config.colon_keywords
                )
                if is_colon_block or is_keyword_block:
                    indent_level += 1

        return result

    def _normalize_operator_spacing(self, line: str) -> str:
        """运算符前后空格规范化

        只处理独立的运算符（不在字符串或标识符中的）
        """
        # 跳过字符串行
        if line.strip().startswith('"') or line.strip().startswith("'"):
            return line

        # 在运算符前后添加空格（简化处理，只处理常见的比较和算术运算符）
        # 注意：不处理中文标识符中的运算符
        ops = ["==", "!=", ">=", "<=", ">", "<", "+", "-", "*", "/", "%"]
        result = line
        for op in ops:
            # 跳过单字符运算符在标识符中间的情况
            if len(op) == 1:
                # 如 a+b → a + b，但不影响 a-b（负数）
                pattern = r'([a-zA-Z0-9\u4e00-\u9fff])' + re.escape(op) + r'([a-zA-Z0-9\u4e00-\u9fff])'
                result = re.sub(pattern, r'\1 ' + op + r' \2', result)
            else:
                pattern = r'([a-zA-Z0-9\u4e00-\u9fff])\s*' + re.escape(op) + r'\s*([a-zA-Z0-9\u4e00-\u9fff])'
                result = re.sub(pattern, r'\1 ' + op + r' \2', result)

        return result
