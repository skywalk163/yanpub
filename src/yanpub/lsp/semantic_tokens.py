"""LSP 语义高亮：token 类型定义与计算逻辑"""

from __future__ import annotations

from yanpub.core.adapter.adapter import LanguageAdapter

# ---- 语义高亮（Semantic Tokens）类型定义 ----

TOKEN_TYPES: list[str] = [
    "keyword",
    "function",
    "variable",
    "type",
    "module",
    "number",
    "string",
    "operator",
    "comment",
    "parameter",
    "property",
    "namespace",
    "class",
    "method",
    "constant",
    "controlFlow",
    "punctuation",
]

TOKEN_MODIFIERS: list[str] = [
    "declaration",
    "definition",
    "readonly",
    "static",
    "deprecated",
    "abstract",
    "async",
    "modification",
    "documentation",
    "defaultLibrary",
]

# token type 字符串 → 索引映射
TOKEN_TYPE_INDEX: dict[str, int] = {t: i for i, t in enumerate(TOKEN_TYPES)}
TOKEN_MOD_INDEX: dict[str, int] = {m: i for i, m in enumerate(TOKEN_MODIFIERS)}

# 定义类关键字：这些关键字后面跟着的名称标记为对应的类型
DEFINITION_KEYWORDS: dict[str, str] = {
    "段落": "function",
    "函数": "function",
    "函": "function",
    "方法": "method",
    "类": "class",
    "定义": "function",
    "宏定": "function",
    "构造": "method",
}

# 运算符集合（中文 + ASCII）
OPERATOR_CHARS = set("+-*/%=<>!&|^~")
CN_OPERATORS = {"加", "减", "乘", "除", "取余", "等于", "不等于", "大于", "小于", "且", "或", "非"}


# 保留旧名作为别名（向后兼容）
_TOKEN_TYPES = TOKEN_TYPES
_TOKEN_MODIFIERS = TOKEN_MODIFIERS
_TOKEN_TYPE_INDEX = TOKEN_TYPE_INDEX
_TOKEN_MOD_INDEX = TOKEN_MOD_INDEX
_DEFINITION_KEYWORDS = DEFINITION_KEYWORDS
_OPERATOR_CHARS = OPERATOR_CHARS
_CN_OPERATORS = CN_OPERATORS


class SemanticTokensMixin:
    """语义高亮计算逻辑（mixin for YanLanguageServer）"""

    def _compute_semantic_tokens(self, adapter: LanguageAdapter, code: str) -> list[int]:
        """计算语义 token 数据

        优先使用 adapter.tokenize()；若返回空列表则 fallback 到
        基于关键字和正则的逐行扫描。
        """
        # 尝试适配器词法分析
        try:
            tokens = adapter.tokenize(code)
        except Exception:
            tokens = []

        if tokens:
            return self._tokens_from_adapter(tokens)

        # Fallback：基于关键字和正则的扫描
        return self._tokens_fallback(adapter, code)

    def _tokens_from_adapter(self, tokens: list) -> list[int]:
        """从 adapter.tokenize() 结果生成 SemanticTokens.data"""
        # 内部 token type → LSP token type 索引
        _TYPE_MAP = {
            "keyword": "keyword",
            "identifier": "variable",
            "number": "number",
            "string": "string",
            "operator": "operator",
            "comment": "comment",
            "punctuation": "punctuation",
            "function": "function",
            "class": "class",
            "method": "method",
            "parameter": "parameter",
            "property": "property",
            "type": "type",
            "module": "module",
            "constant": "constant",
            "namespace": "namespace",
            "controlFlow": "controlFlow",
        }

        data: list[int] = []
        prev_line = 0
        prev_char = 0

        for tok in tokens:
            # tok 来自 adapter.TokenInfo 或兼容对象
            tok_type_str = getattr(tok, "type", "variable")
            value = getattr(tok, "value", "")
            line = getattr(tok, "line", 0) - 1  # 0-based
            col = getattr(tok, "column", 0) - 1  # 0-based

            if line < 0:
                line = 0
            if col < 0:
                col = 0

            mapped = _TYPE_MAP.get(tok_type_str, "variable")
            token_type = TOKEN_TYPE_INDEX.get(mapped, 0)
            length = len(value)

            delta_line = line - prev_line
            delta_char = col if delta_line > 0 else (col - prev_char)

            data.extend([delta_line, delta_char, length, token_type, 0])

            prev_line = line
            prev_char = col

        return data

    def _tokens_fallback(self, adapter: LanguageAdapter, code: str) -> list[int]:
        """基于关键字和正则的 fallback 语义 token 扫描"""
        lines = code.split("\n")
        keyword_set = set(adapter.keywords) if adapter.keywords else set()
        comment_prefix = adapter.comment_syntax or "#"

        # 构建中文关键字正则：按长度降序排列以优先匹配长关键字
        sorted_keywords = sorted(keyword_set, key=len, reverse=True)

        data: list[int] = []
        prev_line = 0
        prev_char = 0

        for line_idx, line in enumerate(lines):
            pos = 0
            line_len = len(line)

            while pos < line_len:
                # 跳过空白
                if line[pos] in " \t\r\n":
                    pos += 1
                    continue

                # 1. 注释行
                if line[pos:].startswith(comment_prefix):
                    length = line_len - pos
                    self._emit_token(data, line_idx, pos, length, "comment", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    break  # 注释后不再扫描此行

                # 2. 字符串字面量
                if line[pos] in ('"', "'", "\u201c", "\u2018"):
                    quote = line[pos]
                    end_quote = quote
                    # 中文引号配对
                    if quote == "\u201c":
                        end_quote = "\u201d"
                    elif quote == "\u2018":
                        end_quote = "\u2019"
                    end_pos = line.find(end_quote, pos + 1)
                    if end_pos == -1:
                        end_pos = line_len  # 未闭合
                    else:
                        end_pos += 1  # 包含结束引号
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "string", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 3. 中文关键字匹配
                matched_kw = False
                for kw in sorted_keywords:
                    if line[pos:].startswith(kw):
                        # 检查关键字后是否是非标识符字符或行尾
                        after_pos = pos + len(kw)
                        if after_pos >= line_len or not (
                            line[after_pos].isalnum()
                            or line[after_pos] == "_"
                            or "\u4e00" <= line[after_pos] <= "\u9fff"
                        ):
                            kw_type = DEFINITION_KEYWORDS.get(kw, "keyword")
                            self._emit_token(
                                data, line_idx, pos, len(kw), kw_type, prev_line, prev_char
                            )
                            prev_line = line_idx
                            prev_char = pos

                            # 如果是定义类关键字，尝试提取后面的名称
                            if kw in DEFINITION_KEYWORDS:
                                name_start = after_pos
                                # 跳过空白
                                while name_start < line_len and line[name_start] in " \t":
                                    name_start += 1
                                if name_start < line_len:
                                    name_end = name_start
                                    while name_end < line_len and (
                                        line[name_end].isalnum()
                                        or line[name_end] == "_"
                                        or "\u4e00" <= line[name_end] <= "\u9fff"
                                    ):
                                        name_end += 1
                                    if name_end > name_start:
                                        name_type = DEFINITION_KEYWORDS[kw]
                                        self._emit_token(
                                            data,
                                            line_idx,
                                            name_start,
                                            name_end - name_start,
                                            name_type,
                                            prev_line,
                                            prev_char,
                                        )
                                        prev_line = line_idx
                                        prev_char = name_start

                            pos = after_pos
                            matched_kw = True
                            break
                if matched_kw:
                    continue

                # 4. 数字字面量
                if line[pos].isdigit():
                    end_pos = pos + 1
                    # 支持小数
                    has_dot = False
                    while end_pos < line_len:
                        ch = line[end_pos]
                        if ch.isdigit():
                            end_pos += 1
                        elif ch == "." and not has_dot:
                            has_dot = True
                            end_pos += 1
                        else:
                            break
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "number", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 5. 运算符
                if line[pos] in OPERATOR_CHARS:
                    end_pos = pos + 1
                    # 多字符运算符（==, !=, <=, >=, &&, ||）
                    if end_pos < line_len and line[end_pos] in "=&|":
                        end_pos += 1
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "operator", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 6. 中文运算符
                cn_op_matched = False
                for cn_op in sorted(CN_OPERATORS, key=len, reverse=True):
                    if line[pos:].startswith(cn_op):
                        self._emit_token(
                            data, line_idx, pos, len(cn_op), "operator", prev_line, prev_char
                        )
                        prev_line = line_idx
                        prev_char = pos
                        pos += len(cn_op)
                        cn_op_matched = True
                        break
                if cn_op_matched:
                    continue

                # 7. 标识符（ASCII + 中文）
                if line[pos].isalpha() or line[pos] == "_" or "\u4e00" <= line[pos] <= "\u9fff":
                    end_pos = pos + 1
                    while end_pos < line_len and (
                        line[end_pos].isalnum()
                        or line[end_pos] == "_"
                        or "\u4e00" <= line[end_pos] <= "\u9fff"
                    ):
                        end_pos += 1
                    length = end_pos - pos
                    self._emit_token(data, line_idx, pos, length, "variable", prev_line, prev_char)
                    prev_line = line_idx
                    prev_char = pos
                    pos = end_pos
                    continue

                # 8. 标点和其他字符
                pos += 1

        return data

    @staticmethod
    def _emit_token(
        data: list[int],
        line: int,
        char: int,
        length: int,
        token_type: str,
        prev_line: int,
        prev_char: int,
    ) -> None:
        """向 data 列表追加一个语义 token（5 整数一组）"""
        delta_line = line - prev_line
        delta_char = char if delta_line > 0 else (char - prev_char)
        type_idx = TOKEN_TYPE_INDEX.get(token_type, 0)
        data.extend([delta_line, delta_char, length, type_idx, 0])
