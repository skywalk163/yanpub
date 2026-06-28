"""语言语法对比矩阵 — 同一概念在不同语言中的代码写法对比

核心设计：定义一组"语法概念"，每种语言提供该概念的实际代码片段，
生成"概念 × 语言"的矩阵，让用户直观看到各语言的语法差异。

本文件为模块入口，数据定义在 syntax_matrix_data.py，HTML 渲染在 syntax_matrix_html.py。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from yanpub.core.adapter.registry import get_registry


# ---- 语法概念定义 ----


@dataclass
class SyntaxConcept:
    """一个语法概念"""

    id: str  # 概念标识，如 "var_declare"
    title: str  # 显示标题，如 "变量声明"
    category: str  # 分类：基础/函数/控制流/数据结构/面向对象/异常/模块
    description: str  # 简短描述
    difficulty: str = "入门"  # 难度


@dataclass
class SnippetEntry:
    """某个语言在某个概念下的代码片段"""

    lang_id: str
    code: str
    note: str = ""  # 额外说明（如"中文运算符"、"前缀调用"等）


# ---- 从数据模块加载 ----

from yanpub.core.syntax_matrix_data import CONCEPTS_ARGS, SNIPPETS  # noqa: E402

CONCEPTS: list[SyntaxConcept] = [SyntaxConcept(*args) for args in CONCEPTS_ARGS]

# 向后兼容：确保外部可直接 from yanpub.core.syntax_matrix import SNIPPETS, CONCEPTS
__all__ = ["SyntaxConcept", "SnippetEntry", "CONCEPTS", "SNIPPETS", "SyntaxMatrix"]


class SyntaxMatrix:
    """语法对比矩阵引擎"""

    def __init__(self):
        self._concepts = CONCEPTS
        self._snippets = SNIPPETS

    @property
    def concepts(self) -> list[SyntaxConcept]:
        return list(self._concepts)

    @property
    def lang_ids(self) -> list[str]:
        """所有参与对比的语言 ID"""
        ids: set[str] = set()
        for concept_snippets in self._snippets.values():
            ids.update(concept_snippets.keys())
        return sorted(ids)

    def get_concept(self, concept_id: str) -> Optional[SyntaxConcept]:
        """获取概念定义"""
        for c in self._concepts:
            if c.id == concept_id:
                return c
        return None

    def get_snippet(self, concept_id: str, lang_id: str) -> Optional[SnippetEntry]:
        """获取某个语言在某个概念下的代码片段"""
        return self._snippets.get(concept_id, {}).get(lang_id)

    def get_concept_snippets(self, concept_id: str) -> dict[str, SnippetEntry]:
        """获取某个概念下所有语言的代码片段"""
        return dict(self._snippets.get(concept_id, {}))

    def get_language_snippets(self, lang_id: str) -> dict[str, SnippetEntry]:
        """获取某个语言在所有概念下的代码片段"""
        result: dict[str, SnippetEntry] = {}
        for concept_id, snippets in self._snippets.items():
            if lang_id in snippets:
                result[concept_id] = snippets[lang_id]
        return result

    def analyze_styles(self, lang_id: str) -> dict[str, str]:
        """分析某个语言的语法风格特征"""
        styles: dict[str, str] = {}

        # 变量风格
        var_snippet = self._snippets.get("var_declare", {}).get(lang_id)
        if var_snippet:
            code = var_snippet.code
            if "设" in code and "为" in code:
                styles["变量风格"] = "设…为…"
            elif "定义" in code and "=" in code:
                styles["变量风格"] = "定义…=…"
            elif code.startswith("定") and "等于" in code:
                styles["变量风格"] = "定…等于…"
            elif "定 " in code:
                styles["变量风格"] = "定…=…"
            elif "变量" in code and "为" in code:
                styles["变量风格"] = "变量…为…"
            else:
                styles["变量风格"] = "其他"

        # 函数风格
        func_snippet = self._snippets.get("func_def", {}).get(lang_id)
        if func_snippet:
            code = func_snippet.code
            if "段落" in code:
                styles["函数风格"] = "段落…参数…结束"
            elif "就是函" in code:
                styles["函数风格"] = "Lisp 风格"
            elif "{" in code:
                styles["函数风格"] = "花括号块"
            elif "参数" in code and "为" in code:
                styles["函数风格"] = "函数…参数…为类型…返回"
            else:
                styles["函数风格"] = "前缀调用"

        # 语句结束
        if func_snippet:
            code = func_snippet.code
            has_end = "结束" in code
            has_period = "。" in code
            if has_period and has_end:
                styles["语句结束"] = "中文句号 。"
            elif has_period:
                styles["语句结束"] = "中文句号 。"
            elif "{" in code:
                styles["语句结束"] = "花括号 {}"
            elif has_end:
                styles["语句结束"] = "「结束」关键字"
            else:
                styles["语句结束"] = "缩进"

        # 代码块
        if_snippet = self._snippets.get("if_else", {}).get(lang_id)
        if if_snippet:
            code = if_snippet.code
            if "{" in code:
                styles["代码块"] = "花括号"
            elif "：" in code:
                styles["代码块"] = "冒号缩进"
            elif "结束" in code:
                styles["代码块"] = "「结束」关键字"
            else:
                styles["代码块"] = "纯缩进"

        # 运算风格
        assign_snippet = self._snippets.get("var_assign", {}).get(lang_id)
        if assign_snippet:
            code = assign_snippet.code
            if "相加" in code or "加" in code:
                styles["运算风格"] = "中文运算符"
            elif "+" in code or "+=" in code:
                styles["运算风格"] = "ASCII 运算符"
            else:
                styles["运算风格"] = "前缀运算"

        # 注释
        styles["注释"] = "# 单行"
        for _cid, _snippets in self._snippets.items():
            s = _snippets.get(lang_id)
            if s and s.code.startswith("--"):
                styles["注释"] = "-- 单行"
                break
            if s and s.code.startswith("//"):
                styles["注释"] = "// 单行"
                break

        return styles

    def compare(self, lang_ids: list[str] | None = None) -> list[dict]:
        """生成对比矩阵数据"""
        if lang_ids is None:
            lang_ids = self.lang_ids

        result: list[dict] = []
        for concept in self._concepts:
            snippets: dict[str, SnippetEntry] = {}
            for lid in lang_ids:
                snippet = self._snippets.get(concept.id, {}).get(lid)
                if snippet:
                    snippets[lid] = snippet
            result.append({"concept": concept, "snippets": snippets})
        return result

    # 别名：get_matrix = compare
    def get_matrix(self) -> list[dict]:
        """生成对比矩阵数据（compare 的别名）"""
        return self.compare()

    def get_categories(self) -> list[str]:
        """获取所有概念分类"""
        seen: list[str] = []
        for c in self._concepts:
            if c.category not in seen:
                seen.append(c.category)
        return seen

    def get_concepts_by_category(self, category: str) -> list[SyntaxConcept]:
        """按分类获取概念"""
        return [c for c in self._concepts if c.category == category]

    def compute_syntax_style(self) -> dict[str, dict[str, str]]:
        """计算所有语言的语法风格特征"""
        result: dict[str, dict[str, str]] = {}
        for lid in self.lang_ids:
            result[lid] = self.analyze_styles(lid)
        return result

    def to_html(self, lang_ids: list[str] | None = None, output_path: str | None = None) -> str:
        """生成 HTML 对比页面"""
        from yanpub.core.syntax_matrix_html import build_html

        if lang_ids is None:
            lang_ids = self.lang_ids

        registry = get_registry()
        matrix = self.compare(lang_ids)

        # 语法风格
        styles = {}
        for lid in lang_ids:
            styles[lid] = self.analyze_styles(lid)

        # 颜色映射
        color_map: dict[str, str] = {}
        for lid in lang_ids:
            adapter = registry.get(lid)
            if adapter:
                color = getattr(adapter, "_primary_color", None) or "#2C3E50"
                color_map[lid] = color

        html = build_html(lang_ids, matrix, styles, color_map, registry)

        if output_path is not None:
            Path(output_path).write_text(html, encoding="utf-8")

        return html

    def generate_html(self, output_path: str | None = None) -> str:
        """生成 HTML 对比页面（to_html 的别名）"""
        return self.to_html(output_path=output_path)
