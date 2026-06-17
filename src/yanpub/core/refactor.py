"""代码重构引擎 — 基于文本分析的默认重构实现

提供 Extract Function、Inline Variable、Safe Rename 三项核心重构能力。
无需适配器覆盖即可工作；适配器可通过 LanguageAdapter.extract_function/inline_variable
提供更精确的实现。
"""

from __future__ import annotations

import re
from typing import Optional

from yanpub.core.adapter import LanguageAdapter


# ---- 标识符工具函数 ----


def _is_ident_char(ch: str) -> bool:
    """判断字符是否属于标识符（ASCII + CJK）"""
    return ch.isalnum() or ch == "_" or "\u4e00" <= ch <= "\u9fff"


def _is_cjk(ch: str) -> bool:
    """判断字符是否为 CJK 统一汉字"""
    return "\u4e00" <= ch <= "\u9fff"


def _is_word_boundary(text: str, idx: int, length: int) -> bool:
    """检查位置 idx 处长度为 length 的匹配是否具有单词边界"""
    before_ok = idx == 0 or not _is_ident_char(text[idx - 1])
    after_ok = idx + length >= len(text) or not _is_ident_char(text[idx + length])
    return before_ok and after_ok


# ---- 中文编程语言关键字集合 ----
# 用于 safe_rename 检测新名称是否是关键字
_CN_KEYWORDS: set[str] = {
    "段落", "函数", "函", "方法", "类", "定义", "宏定", "构造",
    "当", "遍历", "循环", "对于", "如果", "若", "尝试",
    "否则", "否则若", "否则如果", "捕获", "最终",
    "结束", "完", "完毕",
    "返回", "设", "为", "参数", "导入", "从", "导出",
    "继承", "属性", "己", "新建",
    "抛出", "空", "真", "假",
    "打印", "输出", "显示",
}

# 中文运算符集合（不作为标识符）
_CN_OPERATORS: set[str] = {
    "加", "减", "乘", "除", "取余",
    "等于", "不等于", "大于", "小于",
    "且", "或", "非",
}


class RefactoringEngine:
    """代码重构引擎 — 基于文本分析的默认重构实现

    功能：
    - Extract Function：将选中代码块提取为新的段落/函数
    - Inline Variable：将变量使用处替换为变量值，并删除变量声明
    - Safe Rename：增强版重命名，检查关键字冲突和标识符冲突

    设计原则：
    - 使用文本模式分析，不需要 AST
    - 中文编程语言特定：识别"设X为Y"模式、中文标识符
    - 支持适配器覆盖以提供更精确的实现
    """

    def __init__(self, adapter: Optional[LanguageAdapter] = None):
        """
        Args:
            adapter: 语言适配器（可选，用于获取关键字列表等）
        """
        self.adapter = adapter

    # ---- Extract Function ----

    def extract_function(self, code: str, start_line: int, end_line: int, new_name: str) -> dict:
        """提取函数重构

        算法：
        1. 提取 start_line 到 end_line 的代码块
        2. 分析代码块中的变量：
           - 输入变量：代码块中使用但未在块内定义的变量（"设X为" → X 是定义，使用但未定义 → 输入）
           - 输出变量：代码块中定义的变量（可能被外部使用）
        3. 生成新函数：
           - 参数 = 输入变量
           - 函数体 = 代码块
           - 返回语句 = 输出变量（如果有）
        4. 生成替换代码：调用新函数的代码

        中文编程语言特定：
        - 函数定义用 "段落 新名。参数 输入1 输入2。...结束。"
        - 变量声明用 "设X为Y"
        - 返回用 "返回 Z"

        Args:
            code: 源代码
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based, inclusive）
            new_name: 新函数名

        Returns:
            {
                "new_function": str,           # 新函数代码
                "replacement": str,            # 替换选中代码的调用
                "range": {"start": int, "end": int}  # 替换范围（0-based 行号）
            }
        """
        lines = code.split("\n")

        # 边界检查
        if start_line < 1:
            start_line = 1
        if end_line > len(lines):
            end_line = len(lines)
        if start_line > end_line:
            return {
                "new_function": "",
                "replacement": "",
                "range": {"start": start_line - 1, "end": start_line - 1},
            }

        # 1. 提取代码块
        block_lines = lines[start_line - 1:end_line]
        block = "\n".join(block_lines)

        # 2. 分析变量
        var_info = self._extract_block_variables(block)
        input_vars = var_info["inputs"]
        output_vars = var_info["outputs"]

        # 3. 生成新函数
        # 计算缩进
        base_indent = ""
        if block_lines:
            first_line = block_lines[0]
            base_indent = first_line[:len(first_line) - len(first_line.lstrip())]

        # 函数体：调整缩进（增加一级）
        body_lines = []
        for ln in block_lines:
            stripped = ln.lstrip()
            if stripped:
                body_lines.append(base_indent + "    " + stripped)
            else:
                body_lines.append("")
        body = "\n".join(body_lines)

        # 参数列表
        params_str = ""
        if input_vars:
            params_str = "参数 " + " ".join(input_vars) + "。"

        # 返回语句
        return_str = ""
        if output_vars:
            if len(output_vars) == 1:
                return_str = f"{base_indent}    返回 {output_vars[0]}。"
            else:
                return_str = f"{base_indent}    返回 {' '.join(output_vars)}。"

        # 构建新函数
        new_func_parts = [f"{base_indent}段落 {new_name}。"]
        if params_str:
            new_func_parts.append(f"{base_indent}    {params_str}")
        new_func_parts.append(body)
        if return_str:
            new_func_parts.append(return_str)
        new_func_parts.append(f"{base_indent}结束。")

        new_function = "\n".join(new_func_parts)

        # 4. 生成替换代码
        args_str = " ".join(input_vars) if input_vars else ""
        if output_vars:
            # 输出变量需要接收返回值
            if len(output_vars) == 1:
                replacement = f"{base_indent}设 {output_vars[0]} 为 {new_name}({args_str})。"
            else:
                replacement = f"{base_indent}设 ({' '.join(output_vars)}) 为 {new_name}({args_str})。"
        else:
            replacement = f"{base_indent}{new_name}({args_str})。"

        return {
            "new_function": new_function,
            "replacement": replacement,
            "range": {"start": start_line - 1, "end": end_line - 1},
        }

    # ---- Inline Variable ----

    def inline_variable(self, code: str, line: int, column: int) -> dict:
        """内联变量重构

        算法：
        1. 找到光标位置的变量名
        2. 找到该变量的声明（"设变量名 为 值"）
        3. 收集所有使用该变量的位置
        4. 返回声明范围、变量值、使用位置

        Args:
            code: 源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）

        Returns:
            {
                "declaration_range": {"start": {"line": int, "character": int}, "end": {"line": int, "character": int}},
                "value": str,
                "usage_ranges": [{"start": {"line": int, "character": int}, "end": {"line": int, "character": int}}],
            }
        """
        # 1. 获取光标位置的标识符
        var_name = self._is_identifier_at(code, line, column)
        if var_name is None:
            return {
                "declaration_range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                "value": "",
                "usage_ranges": [],
            }

        # 2. 查找变量声明
        decl = self._find_variable_declaration(code, var_name)
        if decl is None:
            return {
                "declaration_range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                "value": "",
                "usage_ranges": [],
            }

        # 3. 收集所有使用位置
        usages = self._find_variable_usages(code, var_name)

        # 排除声明本身
        decl_line = decl["line"]
        decl_start = decl["name_start"]
        decl_end = decl["name_end"]
        filtered_usages = []
        for u in usages:
            if u["line"] == decl_line and u["start"] == decl_start and u["end"] == decl_end:
                continue
            filtered_usages.append(u)

        return {
            "declaration_range": {
                "start": {"line": decl_line, "character": decl["line_start"]},
                "end": {"line": decl_line, "character": decl["line_end"]},
            },
            "value": decl["value"],
            "usage_ranges": [
                {
                    "start": {"line": u["line"], "character": u["start"]},
                    "end": {"line": u["line"], "character": u["end"]},
                }
                for u in filtered_usages
            ],
        }

    # ---- Safe Rename ----

    def safe_rename(self, code: str, line: int, column: int, new_name: str, documents: Optional[dict[str, str]] = None) -> dict:
        """安全重命名

        增强版重命名，检查：
        1. 新名称是否与现有标识符冲突
        2. 新名称是否是关键字
        3. 跨文件引用（使用 SymbolNavigator）

        Args:
            code: 源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）
            new_name: 新名称
            documents: 其他打开文档 {uri: code}（用于跨文件检查）

        Returns:
            {
                "safe": bool,
                "conflicts": list[str],
                "changes": [{"uri": str, "range": {"start": {"line":..., "character":...},
                                                    "end": {"line":..., "character":...}},
                              "new_text": str}]
            }
        """
        conflicts: list[str] = []

        # 1. 检查新名称是否是关键字
        all_keywords = _CN_KEYWORDS.copy()
        all_keywords.update(_CN_OPERATORS)
        if self.adapter and self.adapter.keywords:
            all_keywords.update(self.adapter.keywords)

        if new_name in all_keywords:
            conflicts.append(f"'{new_name}' 是语言关键字")

        # 2. 检查新名称是否是有效的标识符
        if new_name and not all(_is_ident_char(ch) for ch in new_name):
            conflicts.append(f"'{new_name}' 包含无效的标识符字符")

        # 3. 获取旧名称
        old_name = self._is_identifier_at(code, line, column)
        if old_name is None:
            return {
                "safe": False,
                "conflicts": ["光标位置没有标识符"],
                "changes": [],
            }

        if old_name == new_name:
            return {
                "safe": False,
                "conflicts": ["新名称与旧名称相同"],
                "changes": [],
            }

        # 4. 检查新名称是否与现有标识符冲突
        # 在所有文档中搜索新名称是否已存在
        search_docs: dict[str, str] = {}
        if documents:
            search_docs.update(documents)
        search_docs["__current__"] = code

        for doc_uri, doc_code in search_docs.items():
            doc_lines = doc_code.split("\n")
            for i, ln in enumerate(doc_lines):
                search_pos = 0
                while True:
                    idx = ln.find(new_name, search_pos)
                    if idx == -1:
                        break
                    # 边界检查
                    is_cjk_name = len(new_name) == 1 and _is_cjk(new_name)
                    if is_cjk_name:
                        match_ok = True
                    else:
                        match_ok = _is_word_boundary(ln, idx, len(new_name))

                    if match_ok:
                        conflicts.append(f"'{new_name}' 已存在于 {doc_uri}:{i + 1}")
                        break
                    search_pos = idx + 1
                if conflicts and conflicts[-1].startswith(f"'{new_name}' 已存在"):
                    break
            if conflicts and any(c.startswith(f"'{new_name}' 已存在") for c in conflicts):
                break

        # 5. 计算所有需要修改的位置
        changes: list[dict] = []

        for doc_uri, doc_code in search_docs.items():
            actual_uri = doc_uri if doc_uri != "__current__" else ""
            doc_lines = doc_code.split("\n")
            is_cjk_name = len(old_name) == 1 and _is_cjk(old_name)

            for i, ln in enumerate(doc_lines):
                search_pos = 0
                while True:
                    idx = ln.find(old_name, search_pos)
                    if idx == -1:
                        break

                    if is_cjk_name:
                        match_ok = True
                    else:
                        match_ok = _is_word_boundary(ln, idx, len(old_name))

                    if match_ok:
                        changes.append({
                            "uri": actual_uri,
                            "range": {
                                "start": {"line": i, "character": idx},
                                "end": {"line": i, "character": idx + len(old_name)},
                            },
                            "new_text": new_name,
                        })

                    search_pos = idx + 1

        # 6. 如果使用 SymbolNavigator 可用，检查跨文件引用
        try:
            from yanpub.core.navigator import SymbolNavigator

            navigator = SymbolNavigator(keywords=self.adapter.keywords if self.adapter else None)
            # 使用 navigator 的引用搜索验证完整性
            refs = navigator.find_references(
                code, line, column,
                uri="",
                documents=documents or {},
                include_declaration=True,
            )
            # 如果找到的引用数量与我们的 changes 数量不匹配，添加警告
            if refs and len(refs) != len(changes):
                conflicts.append(
                    f"跨文件引用检查：找到 {len(refs)} 个引用，"
                    f"但本地文本匹配 {len(changes)} 个位置"
                )
        except Exception:
            pass  # SymbolNavigator 不可用时跳过

        safe = len(conflicts) == 0

        return {
            "safe": safe,
            "conflicts": conflicts,
            "changes": changes,
        }

    # ---- 辅助方法 ----

    def _find_variable_declaration(self, code: str, var_name: str) -> Optional[dict]:
        """查找变量声明位置和值

        匹配模式："设 <变量名> 为 <值>。"

        Returns:
            {
                "line": int,          # 0-based 行号
                "name_start": int,    # 变量名起始列（0-based）
                "name_end": int,      # 变量名结束列（0-based）
                "line_start": int,    # 整行声明起始列（0-based）
                "line_end": int,      # 整行声明结束列（0-based）
                "value": str,         # 变量值
            }
            或 None
        """
        lines = code.split("\n")

        for i, ln in enumerate(lines):
            stripped = ln.strip()

            # 匹配 "设 <名称> 为 <值>" 模式
            m = re.search(r"设\s+(\S+)\s+为\s*(.+?)[。;；]?\s*$", stripped)
            if m:
                found_name = m.group(1)
                # 清理尾部标点
                found_name = found_name.rstrip("。，；：,;:")

                if found_name == var_name:
                    value = m.group(2).rstrip("。，；：,;:").strip()
                    # 计算在原始行中的位置
                    original_m = re.search(r"设\s+(\S+)\s+为\s*(.+?)[。;；]?\s*$", ln)
                    if original_m:
                        name_start = original_m.start(1)
                        name_end = original_m.end(1)
                        # 清理尾部标点后的 end
                        while name_end > name_start and ln[name_end - 1] in "。，；：,;:":
                            name_end -= 1

                        # 整个声明行的范围
                        line_start = ln.find("设")
                        line_end = original_m.end(0)
                        # 清理尾部空白
                        while line_end > line_start and ln[line_end - 1] in " \t":
                            line_end -= 1

                        return {
                            "line": i,
                            "name_start": name_start,
                            "name_end": name_end,
                            "line_start": line_start,
                            "line_end": line_end,
                            "value": value,
                        }

        return None

    def _find_variable_usages(self, code: str, var_name: str) -> list[dict]:
        """查找变量使用位置

        Returns:
            [{"line": int, "start": int, "end": int}, ...]
            行号和列号都是 0-based
        """
        lines = code.split("\n")
        usages = []
        is_cjk_name = len(var_name) == 1 and _is_cjk(var_name)

        for i, ln in enumerate(lines):
            search_pos = 0
            while True:
                idx = ln.find(var_name, search_pos)
                if idx == -1:
                    break

                # 边界检查
                if is_cjk_name:
                    match_ok = True
                else:
                    match_ok = _is_word_boundary(ln, idx, len(var_name))

                if match_ok:
                    usages.append({
                        "line": i,
                        "start": idx,
                        "end": idx + len(var_name),
                    })

                search_pos = idx + 1

        return usages

    def _extract_block_variables(self, block: str) -> dict:
        """分析代码块的输入/输出变量

        算法：
        1. 扫描代码块中所有标识符
        2. "设X为Y" 模式 → X 是定义（输出变量）
        3. 使用但未在块内定义的标识符 → 输入变量
        4. 输出变量 = 块中定义的变量（可能被外部使用）

        Returns:
            {"inputs": list[str], "outputs": list[str]}
        """
        lines = block.split("\n")
        defined_vars: list[str] = []  # 保持定义顺序
        defined_set: set[str] = set()
        used_vars: set[str] = set()

        # 获取关键字集合
        keywords = _CN_KEYWORDS.copy()
        keywords.update(_CN_OPERATORS)
        if self.adapter and self.adapter.keywords:
            keywords.update(self.adapter.keywords)

        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue

            # 检查 "设 <名称> 为 <值>" 模式
            m = re.search(r"设\s+(\S+)\s+为\s*(.+?)[。;；]?\s*$", stripped)
            if m:
                var_name = m.group(1).rstrip("。，；：,;:")
                if var_name not in defined_set:
                    defined_vars.append(var_name)
                    defined_set.add(var_name)
                # 也提取值表达式中的标识符
                value_expr = m.group(2).rstrip("。，；：,;:").strip()
                value_idents = self._extract_identifiers(value_expr, keywords)
                used_vars.update(value_idents)
                continue

            # 提取行中的所有标识符
            identifiers = self._extract_identifiers(stripped, keywords)
            used_vars.update(identifiers)

        # 输入变量 = 使用但未定义的（排除关键字和纯数字）
        inputs = [v for v in sorted(used_vars - defined_set - keywords) if v]
        # 输出变量 = 定义的所有变量（保持定义顺序）
        outputs = [v for v in defined_vars if v]

        return {"inputs": inputs, "outputs": outputs}

    def _extract_identifiers(self, line: str, keywords: set[str]) -> set[str]:
        """从一行代码中提取所有标识符

        跳过关键字、字符串字面量和纯数字字面量。
        """
        identifiers: set[str] = set()
        pos = 0
        line_len = len(line)

        # 先跳过字符串
        in_string = False
        string_char = ""

        while pos < line_len:
            ch = line[pos]

            # 跳过字符串
            if ch in ('"', "'", "\u201c", "\u2018") and not in_string:
                in_string = True
                string_char = ch
                pos += 1
                continue
            if in_string:
                if ch == string_char or (
                    string_char == "\u201c" and ch == "\u201d"
                ) or (
                    string_char == "\u2018" and ch == "\u2019"
                ):
                    in_string = False
                pos += 1
                continue

            # 跳过空白和标点
            if not _is_ident_char(ch):
                pos += 1
                continue

            # 提取标识符
            start = pos
            while pos < line_len and _is_ident_char(line[pos]):
                pos += 1

            ident = line[start:pos]
            if ident and ident not in keywords:
                # 跳过纯数字字面量（含小数点）
                if ident.replace(".", "").isdigit():
                    continue
                # 跳过中文运算符
                if ident in _CN_OPERATORS:
                    continue
                identifiers.add(ident)

        return identifiers

    def _is_identifier_at(self, code: str, line: int, column: int) -> Optional[str]:
        """获取光标位置的标识符

        Args:
            code: 源代码
            line: 行号（1-based）
            column: 列号（1-based）

        Returns:
            标识符文本或 None
        """
        lines = code.split("\n")
        if line < 1 or line > len(lines):
            return None

        code_line = lines[line - 1]
        if column < 1 or column > len(code_line) + 1:
            return None

        pos = column - 1  # 0-based
        if pos >= len(code_line):
            return None

        if _is_cjk(code_line[pos]):
            # CJK 字符：向左右扩展连续的标识符字符
            start = pos
            end = pos + 1
            while start > 0 and _is_ident_char(code_line[start - 1]):
                start -= 1
            while end < len(code_line) and _is_ident_char(code_line[end]):
                end += 1
            return code_line[start:end]
        elif code_line[pos].isalnum() or code_line[pos] == "_":
            # ASCII 标识符：向左右扩展
            start = pos
            end = pos
            while start > 0 and _is_ident_char(code_line[start - 1]) and not _is_cjk(code_line[start - 1]):
                start -= 1
            while end < len(code_line) and _is_ident_char(code_line[end]) and not _is_cjk(code_line[end]):
                end += 1
            if start < end:
                return code_line[start:end]
            return None
        else:
            return None
