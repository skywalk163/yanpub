"""符号导航引擎 — 基于文本分析的默认导航实现

提供 Go to Definition、Find All References、Call Hierarchy 三项核心导航能力。
无需适配器覆盖即可工作；适配器可通过 LanguageAdapter.definition/references/call_hierarchy
提供更精确的实现。
"""

from __future__ import annotations

import re
from typing import Optional

from yanpub.core.dev._ident_utils import (
    _CN_KEYWORDS,
    _DEFINITION_KEYWORDS,
    _SYMBOL_KIND_MAP,
    _is_cjk,
    _is_ident_char,
    _is_word_boundary,
)


def _extract_identifier_at(
    code: str, line: int, column: int, keywords: Optional[set[str]] = None
) -> Optional[tuple[str, int, int]]:
    """提取光标位置的标识符

    对于 CJK 字符，尝试扩展为完整的多字符标识符（如"加法"、"乘法"）。
    排除已知关键字（如"段落"、"返回"等不被视为标识符）。

    Args:
        code: 源代码
        line: 行号（1-based）
        column: 列号（1-based）
        keywords: 语言关键字集合（用于排除关键字误识别）

    Returns:
        (标识符文本, 起始列_0based, 结束列_0based) 或 None
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

    kw_set = keywords or set()

    if _is_cjk(code_line[pos]):
        # CJK 标识符：向左右扩展连续的 CJK+alnum 字符
        start = pos
        end = pos + 1

        # 向左扩展
        while start > 0 and _is_ident_char(code_line[start - 1]):
            start -= 1
        # 向右扩展
        while end < len(code_line) and _is_ident_char(code_line[end]):
            end += 1

        candidate = code_line[start:end]

        # 如果候选是关键字，尝试缩小范围
        # 例如光标在"段落"的"落"上，应该返回"段落"整个关键字还是单字符？
        # 对于导航目的，如果候选以关键字开头，尝试剥离关键字后取标识符
        # 例如 "段落加法" 中关键字是"段落"，标识符是"加法"
        if candidate in kw_set:
            # 光标在整个关键字上，返回关键字本身
            # 调用方应处理关键字导航
            return (candidate, start, end)

        # 尝试剥离前缀关键字
        stripped = candidate
        stripped_start = start
        for kw in sorted(kw_set, key=len, reverse=True):
            if stripped.startswith(kw) and len(stripped) > len(kw):
                stripped = stripped[len(kw) :]
                stripped_start = start + len(kw)
                break

        # 如果剥离后仍有内容，使用剥离后的标识符
        if stripped and stripped not in kw_set:
            # 验证光标是否在剥离后的范围内
            if stripped_start <= pos < stripped_start + len(stripped):
                return (stripped, stripped_start, stripped_start + len(stripped))

        return (candidate, start, end)
    else:
        # ASCII 标识符：向左右扩展（alnum/_，不含 CJK）
        start = pos
        end = pos
        while (
            start > 0 and _is_ident_char(code_line[start - 1]) and not _is_cjk(code_line[start - 1])
        ):
            start -= 1
        while (
            end < len(code_line) and _is_ident_char(code_line[end]) and not _is_cjk(code_line[end])
        ):
            end += 1

        if start == end:
            return None

        return (code_line[start:end], start, end)


class SymbolNavigator:
    """基于文本分析的符号导航引擎

    功能：
    - Go to Definition：扫描文档，识别段落/函数/类/方法/设 等定义位置
    - Find All References：在多文档中搜索同名标识符
    - Call Hierarchy：从函数定义出发，扫描函数体中的调用关系

    设计原则：
    - 使用 LanguageAdapter.keywords 和已知模式识别定义和引用
    - 支持多文档（通过 documents 字典传入）
    - 标识符边界检测：CJK 单字符 + ASCII 标识符都正确匹配
    """

    def __init__(self, keywords: Optional[list[str]] = None):
        """
        Args:
            keywords: 语言关键字列表（用于定义模式识别）
        """
        self._keywords = set(keywords or [])
        # 构建定义关键字的正则，按长度降序排列优先匹配长关键字
        self._def_kw_sorted = sorted(_DEFINITION_KEYWORDS.keys(), key=len, reverse=True)

    # ---- Go to Definition ----

    def find_definition(
        self,
        code: str,
        line: int,
        column: int,
        uri: str = "",
        documents: Optional[dict[str, str]] = None,
    ) -> list[dict]:
        """跳转到定义

        算法：
        1. 提取光标位置的标识符
        2. 在当前文档和所有打开的文档中搜索定义位置
        3. 定义模式：段落 X、函数 X、类 X、方法 X、设 X 为 … 等

        Args:
            code: 当前文档源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）
            uri: 当前文档 URI
            documents: 所有打开文档 {uri: code}

        Returns:
            定义位置列表 [{"uri": str, "range": {"start": {"line": int, "character": int}, "end": {...}}}]
        """
        ident = _extract_identifier_at(code, line, column, keywords=self._keywords)
        if ident is None:
            return []

        symbol_name, _, _ = ident

        # 构建搜索文档集：当前文档 + 其他文档
        search_docs: dict[str, str] = {}
        if documents:
            search_docs.update(documents)
        if uri and uri not in search_docs:
            search_docs[uri] = code

        results = []
        for doc_uri, doc_code in search_docs.items():
            defs = self._scan_definitions(doc_code, symbol_name, doc_uri)
            results.extend(defs)

        return results

    def _scan_definitions(self, code: str, symbol_name: str, uri: str) -> list[dict]:
        """扫描文档中指定符号的定义位置"""
        lines = code.split("\n")
        results = []

        for i, ln in enumerate(lines):
            stripped = ln.strip()
            if not stripped:
                continue

            # 模式 1：段落/函数/类/方法/定义/宏定 <名称>
            for kw in self._def_kw_sorted:
                if kw not in stripped:
                    continue
                # 在行中找到 kw 的位置
                search_pos = 0
                while True:
                    kw_idx = stripped.find(kw, search_pos)
                    if kw_idx == -1:
                        break
                    # 检查关键字后面是否跟着目标名称
                    after_pos = kw_idx + len(kw)
                    # 跳过空白
                    while after_pos < len(stripped) and stripped[after_pos] in " \t":
                        after_pos += 1
                    if after_pos < len(stripped):
                        # 提取定义的名称
                        name_end = after_pos
                        while name_end < len(stripped) and _is_ident_char(stripped[name_end]):
                            name_end += 1
                        defined_name = stripped[after_pos:name_end]
                        if defined_name == symbol_name:
                            # 计算在原始行中的位置
                            original_after = ln.find(kw, 0) + len(kw)
                            while original_after < len(ln) and ln[original_after] in " \t":
                                original_after += 1
                            original_name_end = original_after
                            while original_name_end < len(ln) and _is_ident_char(
                                ln[original_name_end]
                            ):
                                original_name_end += 1

                            results.append(
                                {
                                    "uri": uri,
                                    "range": {
                                        "start": {"line": i, "character": original_after},
                                        "end": {"line": i, "character": original_name_end},
                                    },
                                }
                            )
                    search_pos = kw_idx + 1

            # 模式 2：设 <名称> 为 …（变量定义）
            if "设" in stripped and "为" in stripped:
                # 匹配 "设 <名称> 为" 模式
                m = re.search(r"设\s+(\S+)\s+为", stripped)
                if m:
                    var_name = m.group(1)
                    # 清理可能的标点
                    var_name = var_name.rstrip("。，；：,;:")
                    if var_name == symbol_name:
                        # 计算在原始行中的位置
                        original_m = re.search(r"设\s+(\S+)\s+为", ln)
                        if original_m:
                            name_start = original_m.start(1)
                            name_end = original_m.end(1)
                            # 清理尾部标点后的 end
                            while name_end > name_start and ln[name_end - 1] in "。，；：,;:":
                                name_end -= 1
                            results.append(
                                {
                                    "uri": uri,
                                    "range": {
                                        "start": {"line": i, "character": name_start},
                                        "end": {"line": i, "character": name_end},
                                    },
                                }
                            )

        return results

    # ---- Find All References ----

    def find_references(
        self,
        code: str,
        line: int,
        column: int,
        uri: str = "",
        documents: Optional[dict[str, str]] = None,
        include_declaration: bool = True,
    ) -> list[dict]:
        """查找所有引用

        算法：
        1. 提取光标位置的标识符
        2. 在所有打开的文档中搜索同名标识符（含定义和引用）
        3. 根据标识符类型应用边界检测

        Args:
            code: 当前文档源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）
            uri: 当前文档 URI
            documents: 所有打开文档 {uri: code}
            include_declaration: 是否包含定义本身

        Returns:
            引用位置列表 [{"uri": str, "range": {"start": {"line": int, "character": int}, "end": {...}}}]
        """
        ident = _extract_identifier_at(code, line, column, keywords=self._keywords)
        if ident is None:
            return []

        symbol_name, _, _ = ident

        # 构建搜索文档集
        search_docs: dict[str, str] = {}
        if documents:
            search_docs.update(documents)
        if uri and uri not in search_docs:
            search_docs[uri] = code

        # 定义位置集合（用于 include_declaration 过滤）
        definitions: set[tuple[str, int, int]] = set()
        if not include_declaration:
            for doc_uri, doc_code in search_docs.items():
                for defn in self._scan_definitions(doc_code, symbol_name, doc_uri):
                    r = defn["range"]
                    definitions.add(
                        (
                            defn["uri"],
                            r["start"]["line"],
                            r["start"]["character"],
                        )
                    )

        results = []
        is_cjk_symbol = len(symbol_name) == 1 and _is_cjk(symbol_name)

        for doc_uri, doc_code in search_docs.items():
            lines = doc_code.split("\n")
            for i, ln in enumerate(lines):
                search_start = 0
                while True:
                    idx = ln.find(symbol_name, search_start)
                    if idx == -1:
                        break

                    # 边界检查
                    if is_cjk_symbol:
                        # CJK 单字符：不做严格边界检查
                        # （中文 token 间无分隔符，无法仅凭文本判断边界）
                        match_ok = True
                    else:
                        match_ok = _is_word_boundary(ln, idx, len(symbol_name))

                    if match_ok:
                        loc_key = (doc_uri, i, idx)
                        if include_declaration or loc_key not in definitions:
                            results.append(
                                {
                                    "uri": doc_uri,
                                    "range": {
                                        "start": {"line": i, "character": idx},
                                        "end": {"line": i, "character": idx + len(symbol_name)},
                                    },
                                }
                            )

                    search_start = idx + 1

        return results

    # ---- Call Hierarchy ----

    def find_call_hierarchy(
        self,
        code: str,
        line: int,
        column: int,
        uri: str = "",
        documents: Optional[dict[str, str]] = None,
    ) -> Optional[dict]:
        """调用层次

        算法：
        1. 确定光标所在的函数定义
        2. 扫描函数体中调用的其他函数（outgoing calls）
        3. 扫描所有文档中调用此函数的位置（incoming calls）

        Args:
            code: 当前文档源代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）
            uri: 当前文档 URI
            documents: 所有打开文档 {uri: code}

        Returns:
            {"items": [{"name": str, "kind": str, "uri": str, "range": {...},
                         "selectionRange": {...}, "children": [...]}]}
        """
        # 构建搜索文档集
        search_docs: dict[str, str] = {}
        if documents:
            search_docs.update(documents)
        if uri and uri not in search_docs:
            search_docs[uri] = code

        # 找到光标所在的函数定义
        func_def = self._find_enclosing_function(code, line, column, uri)
        if func_def is None:
            return None

        func_name = func_def["name"]
        func_range = func_def["range"]
        func_kind = func_def["kind"]

        # 扫描 outgoing calls（此函数调用了哪些函数）
        outgoing = self._find_outgoing_calls(
            code,
            func_name,
            func_range,
            uri,
            search_docs,
        )

        # 扫描 incoming calls（哪些函数调用了此函数）
        incoming = self._find_incoming_calls(
            func_name,
            uri,
            search_docs,
        )

        # 构建调用层次结构
        item = {
            "name": func_name,
            "kind": func_kind,
            "uri": uri,
            "range": func_range,
            "selectionRange": func_range,
            "children": outgoing,
            "callers": incoming,
        }

        return {"items": [item]}

    def _find_enclosing_function(
        self,
        code: str,
        line: int,
        column: int,
        uri: str,
    ) -> Optional[dict]:
        """找到光标所在的函数/段落定义

        Returns:
            {"name": str, "kind": str, "range": {...}} 或 None
        """
        lines = code.split("\n")
        target_line_0 = line - 1  # 0-based

        # 从光标位置向上搜索，找到最近的函数定义
        for i in range(target_line_0, -1, -1):
            ln = lines[i]
            stripped = ln.strip()
            if not stripped:
                continue

            for kw in self._def_kw_sorted:
                if not stripped.startswith(kw) and f" {kw}" not in stripped:
                    continue
                # 找到 kw 在行中的位置
                kw_pos = stripped.find(kw)
                after_pos = kw_pos + len(kw)
                # 跳过空白
                while after_pos < len(stripped) and stripped[after_pos] in " \t":
                    after_pos += 1
                if after_pos < len(stripped):
                    # 提取函数名
                    name_end = after_pos
                    while name_end < len(stripped) and _is_ident_char(stripped[name_end]):
                        name_end += 1
                    func_name = stripped[after_pos:name_end]

                    if func_name:
                        kind = _DEFINITION_KEYWORDS.get(kw, "function")

                        # 计算在原始行中的位置
                        original_kw_pos = ln.find(kw)
                        original_after = original_kw_pos + len(kw)
                        while original_after < len(ln) and ln[original_after] in " \t":
                            original_after += 1
                        original_name_end = original_after
                        while original_name_end < len(ln) and _is_ident_char(ln[original_name_end]):
                            original_name_end += 1

                        # 检查此函数是否包含光标位置
                        # 简化：如果光标行 >= 定义行，且定义行在光标行之前
                        # 更精确的判断需要检查函数结束位置
                        if i <= target_line_0:
                            # 进一步验证：确保光标在此函数体内
                            # 扫描定义行之后的缩进块
                            func_end = self._find_block_end(lines, i)
                            if target_line_0 <= func_end:
                                return {
                                    "name": func_name,
                                    "kind": _SYMBOL_KIND_MAP.get(kind, 12),
                                    "range": {
                                        "start": {"line": i, "character": original_after},
                                        "end": {"line": i, "character": original_name_end},
                                    },
                                }

        return None

    def _find_block_end(self, lines: list[str], start_line: int) -> int:
        """找到块的结束行（0-based）

        查找 "结束"、"完"、"完毕" 等结束关键字，或通过缩进推断。
        """
        # 获取定义行的缩进级别
        if start_line >= len(lines):
            return start_line

        base_indent = len(lines[start_line]) - len(lines[start_line].lstrip())
        end_keywords = {"结束", "完", "完毕"}

        for i in range(start_line + 1, len(lines)):
            stripped = lines[i].strip()
            if not stripped:
                continue

            # 检查结束关键字
            for ek in end_keywords:
                if stripped.startswith(ek) or stripped == ek:
                    return i

            # 缩进回到基础级别或更浅 → 块结束
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            if current_indent <= base_indent and stripped:
                return i - 1

        # 未找到显式结束，到文件末尾
        return len(lines) - 1

    def _find_outgoing_calls(
        self,
        code: str,
        func_name: str,
        func_range: dict,
        uri: str,
        documents: dict[str, str],
    ) -> list[dict]:
        """查找函数体中调用的其他函数

        匹配模式：
        - 中文函数调用：段落名( 或 段落名（
        - ASCII 函数调用：funcName( 或 func_name(
        """
        lines = code.split("\n")
        func_start = func_range["start"]["line"]  # 0-based
        func_end = self._find_block_end(lines, func_start)

        # 收集所有定义的函数名，用于验证调用
        defined_names = self._collect_all_definitions(documents)

        outgoing = []
        seen = set()

        for i in range(func_start + 1, func_end + 1):
            if i >= len(lines):
                break
            ln = lines[i]
            stripped = ln.strip()
            if not stripped:
                continue

            # 跳过注释行
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # 查找调用模式：标识符后面跟着 ( 或 （
            self._scan_calls_in_line(ln, i, uri, defined_names, outgoing, seen, func_name)

        return outgoing

    def _scan_calls_in_line(
        self,
        ln: str,
        line_idx: int,
        uri: str,
        defined_names: dict[str, list[dict]],
        outgoing: list[dict],
        seen: set[str],
        exclude_name: str,
    ) -> None:
        """扫描一行代码中的函数调用"""
        pos = 0
        line_len = len(ln)

        while pos < line_len:
            ch = ln[pos]

            # 跳过空白和标点
            if ch in " \t\r\n" or ch in "#{}[];，。：；":
                pos += 1
                continue

            # 跳过字符串
            if ch in ('"', "'", "\u201c", "\u2018"):
                end_ch = ch
                if ch == "\u201c":
                    end_ch = "\u201d"
                elif ch == "\u2018":
                    end_ch = "\u2019"
                end_pos = ln.find(end_ch, pos + 1)
                pos = (end_pos + 1) if end_pos != -1 else line_len
                continue

            # 提取标识符
            ident_start = pos
            if _is_cjk(ch):
                # CJK 标识符：向右扩展连续的 CJK+alnum 字符
                ident_end = pos + 1
                while ident_end < line_len and _is_ident_char(ln[ident_end]):
                    ident_end += 1
                ident = ln[ident_start:ident_end]
                pos = ident_end

                # 如果标识符以关键字开头，剥离关键字
                for kw in self._def_kw_sorted:
                    if ident.startswith(kw) and len(ident) > len(kw):
                        stripped = ident[len(kw) :]
                        # 检查剥离后是否跟括号
                        if pos < line_len and ln[pos] in "(（":
                            ident = stripped
                            ident_start = ident_start + len(kw)
                        break

            elif ch.isalpha() or ch == "_":
                # ASCII 标识符：多字符后跟括号
                ident_end = pos + 1
                while (
                    ident_end < line_len
                    and (ln[ident_end].isalnum() or ln[ident_end] == "_")
                    and not _is_cjk(ln[ident_end])
                ):
                    ident_end += 1
                ident = ln[ident_start:ident_end]
                pos = ident_end
            else:
                pos += 1
                continue

            # 检查标识符后是否跟括号
            if pos < line_len and ln[pos] in "(（":
                # 这是一个函数调用
                if ident != exclude_name and ident not in seen:
                    # 验证是否是已定义的函数
                    if ident in defined_names:
                        seen.add(ident)
                        # 取第一个定义的位置
                        first_def = defined_names[ident][0]
                        outgoing.append(
                            {
                                "name": ident,
                                "kind": first_def["kind"],
                                "uri": first_def["uri"],
                                "range": first_def["range"],
                                "selectionRange": first_def["range"],
                            }
                        )

    def _find_incoming_calls(
        self,
        func_name: str,
        current_uri: str,
        documents: dict[str, str],
    ) -> list[dict]:
        """查找调用了指定函数的所有函数"""
        incoming = []

        for doc_uri, doc_code in documents.items():
            lines = doc_code.split("\n")

            # 找到此文档中的所有函数定义
            func_defs = []
            for i, ln in enumerate(lines):
                stripped = ln.strip()
                if not stripped:
                    continue
                for kw in self._def_kw_sorted:
                    if not stripped.startswith(kw) and f" {kw}" not in stripped:
                        continue
                    kw_pos = stripped.find(kw)
                    after_pos = kw_pos + len(kw)
                    while after_pos < len(stripped) and stripped[after_pos] in " \t":
                        after_pos += 1
                    if after_pos < len(stripped):
                        name_end = after_pos
                        while name_end < len(stripped) and _is_ident_char(stripped[name_end]):
                            name_end += 1
                        def_name = stripped[after_pos:name_end]
                        if def_name:
                            # 计算原始行中的位置
                            orig_kw_pos = ln.find(kw)
                            orig_after = orig_kw_pos + len(kw)
                            while orig_after < len(ln) and ln[orig_after] in " \t":
                                orig_after += 1
                            orig_name_end = orig_after
                            while orig_name_end < len(ln) and _is_ident_char(ln[orig_name_end]):
                                orig_name_end += 1

                            func_end = self._find_block_end(lines, i)
                            kind = _DEFINITION_KEYWORDS.get(kw, "function")
                            func_defs.append(
                                {
                                    "name": def_name,
                                    "kind": _SYMBOL_KIND_MAP.get(kind, 12),
                                    "uri": doc_uri,
                                    "range": {
                                        "start": {"line": i, "character": orig_after},
                                        "end": {"line": i, "character": orig_name_end},
                                    },
                                    "body_start": i,
                                    "body_end": func_end,
                                }
                            )

            # 在每个函数体中搜索对目标函数的调用
            for fd in func_defs:
                if fd["name"] == func_name:
                    continue  # 跳过自身

                found_call = False
                for j in range(fd["body_start"] + 1, fd["body_end"] + 1):
                    if j >= len(lines):
                        break
                    ln = lines[j]
                    # 搜索 func_name 后跟 ( 或 （
                    search_pos = 0
                    while not found_call:
                        idx = ln.find(func_name, search_pos)
                        if idx == -1:
                            break

                        # 边界检查
                        if len(func_name) == 1 and _is_cjk(func_name):
                            boundary_ok = True
                        else:
                            boundary_ok = _is_word_boundary(ln, idx, len(func_name))

                        if boundary_ok:
                            after = idx + len(func_name)
                            if after < len(ln) and ln[after] in "(（":
                                found_call = True
                                break

                        search_pos = idx + 1

                    if found_call:
                        break

                if found_call:
                    incoming.append(
                        {
                            "name": fd["name"],
                            "kind": fd["kind"],
                            "uri": fd["uri"],
                            "range": fd["range"],
                            "selectionRange": fd["range"],
                        }
                    )

        return incoming

    def _collect_all_definitions(self, documents: dict[str, str]) -> dict[str, list[dict]]:
        """收集所有文档中的定义

        Returns:
            {符号名: [{"kind": int, "uri": str, "range": {...}}, ...]}
        """
        all_defs: dict[str, list[dict]] = {}

        for doc_uri, doc_code in documents.items():
            lines = doc_code.split("\n")
            for i, ln in enumerate(lines):
                stripped = ln.strip()
                if not stripped:
                    continue

                for kw in self._def_kw_sorted:
                    if not stripped.startswith(kw) and f" {kw}" not in stripped:
                        continue
                    kw_pos = stripped.find(kw)
                    after_pos = kw_pos + len(kw)
                    while after_pos < len(stripped) and stripped[after_pos] in " \t":
                        after_pos += 1
                    if after_pos < len(stripped):
                        name_end = after_pos
                        while name_end < len(stripped) and _is_ident_char(stripped[name_end]):
                            name_end += 1
                        def_name = stripped[after_pos:name_end]
                        if def_name:
                            kind = _DEFINITION_KEYWORDS.get(kw, "function")

                            # 计算原始行中的位置
                            orig_kw_pos = ln.find(kw)
                            orig_after = orig_kw_pos + len(kw)
                            while orig_after < len(ln) and ln[orig_after] in " \t":
                                orig_after += 1
                            orig_name_end = orig_after
                            while orig_name_end < len(ln) and _is_ident_char(ln[orig_name_end]):
                                orig_name_end += 1

                            entry = {
                                "kind": _SYMBOL_KIND_MAP.get(kind, 12),
                                "uri": doc_uri,
                                "range": {
                                    "start": {"line": i, "character": orig_after},
                                    "end": {"line": i, "character": orig_name_end},
                                },
                            }
                            all_defs.setdefault(def_name, []).append(entry)

                # 变量定义：设 <名称> 为
                if "设" in stripped and "为" in stripped:
                    m = re.search(r"设\s+(\S+)\s+为", stripped)
                    if m:
                        var_name = m.group(1).rstrip("。，；：,;:")
                        orig_m = re.search(r"设\s+(\S+)\s+为", ln)
                        if orig_m:
                            name_start = orig_m.start(1)
                            name_end = orig_m.end(1)
                            while name_end > name_start and ln[name_end - 1] in "。，；：,;:":
                                name_end -= 1
                            entry = {
                                "kind": _SYMBOL_KIND_MAP.get("variable", 13),
                                "uri": doc_uri,
                                "range": {
                                    "start": {"line": i, "character": name_start},
                                    "end": {"line": i, "character": name_end},
                                },
                            }
                            all_defs.setdefault(var_name, []).append(entry)

        return all_defs
