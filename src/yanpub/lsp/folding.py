"""LSP 代码折叠：块关键字定义与折叠范围计算"""

from __future__ import annotations

from lsprotocol import types as lsp

from yanpub.core.adapter.adapter import LanguageAdapter

# 块开始关键字（这些关键字开启一个新的可折叠区域）
BLOCK_START_KEYWORDS: list[str] = [
    "段落",
    "函数",
    "类",
    "方法",
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
]

# 块结束关键字
BLOCK_END_KEYWORDS: list[str] = [
    "结束",
    "完",
    "完毕",
]

# 保留旧名作为别名（向后兼容）
_BLOCK_START_KEYWORDS = BLOCK_START_KEYWORDS
_BLOCK_END_KEYWORDS = BLOCK_END_KEYWORDS


class FoldingMixin:
    """代码折叠计算逻辑（mixin for YanLanguageServer）"""

    def _compute_folding_ranges(
        self, adapter: LanguageAdapter, code: str
    ) -> list[lsp.FoldingRange]:
        """计算代码折叠区域

        算法：
        1. 扫描每一行，检测块开始/结束关键字
        2. 用栈追踪嵌套的块开始行
        3. 遇到块结束关键字时，弹出栈顶，生成折叠范围
        """
        lines = code.split("\n")
        ranges: list[lsp.FoldingRange] = []

        # 构建适配器特定的块关键字集
        adapter_keywords = set(adapter.keywords) if adapter.keywords else set()
        start_kws = [
            kw
            for kw in BLOCK_START_KEYWORDS
            if kw in adapter_keywords or not adapter_keywords
        ]
        end_kws = [
            kw for kw in BLOCK_END_KEYWORDS if kw in adapter_keywords or not adapter_keywords
        ]

        # 如果适配器没有关键字，使用默认的块关键字集
        if not start_kws:
            start_kws = BLOCK_START_KEYWORDS
        if not end_kws:
            end_kws = BLOCK_END_KEYWORDS

        # 额外从适配器关键字中推断块开始关键字
        # 带有冒号结尾的行通常是块开始
        comment_prefix = adapter.comment_syntax or "#"

        # 栈：每个元素是 (start_line_0based, indent_level)
        stack: list[tuple[int, int]] = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith(comment_prefix):
                continue

            # 计算缩进级别
            indent = len(line) - len(line.lstrip())

            # 检查是否是块开始行
            is_block_start = False
            for kw in start_kws:
                if stripped.startswith(kw) or f" {kw}" in stripped:
                    is_block_start = True
                    break

            # 冒号/中文冒号结尾也视为块开始
            if stripped.endswith((":", "：")):
                is_block_start = True

            if is_block_start:
                stack.append((i, indent))

            # 检查是否是块结束行
            is_block_end = False
            for kw in end_kws:
                if stripped.startswith(kw) or stripped == kw:
                    is_block_end = True
                    break

            if is_block_end and stack:
                start_line, start_indent = stack.pop()
                # 折叠范围：从块开始行到当前行
                # LSP FoldingRange: start_line 和 end_line 都是 0-based
                if i > start_line:
                    ranges.append(
                        lsp.FoldingRange(
                            start_line=start_line,
                            end_line=i,
                            kind=lsp.FoldingRangeKind.Region,
                        )
                    )

        # 处理未闭合的块（缩进恢复到更浅级别时闭合）
        # 简化实现：对于没有显式结束关键字的代码，使用缩进推断
        if stack:
            # 未闭合的块 — 尝试用缩进推断折叠范围
            for start_line, start_indent in stack:
                # 查找下一个缩进回到 start_indent 或更浅的行
                end_line = start_line
                for j in range(start_line + 1, len(lines)):
                    if not lines[j].strip() or lines[j].strip().startswith(comment_prefix):
                        continue
                    current_indent = len(lines[j]) - len(lines[j].lstrip())
                    if current_indent <= start_indent:
                        break
                    end_line = j
                if end_line > start_line:
                    ranges.append(
                        lsp.FoldingRange(
                            start_line=start_line,
                            end_line=end_line,
                            kind=lsp.FoldingRangeKind.Region,
                        )
                    )

        return ranges
