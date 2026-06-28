"""AI 辅助引擎 — 智能代码补全、自然语言转代码、错误修复建议

所有功能基于规则和模板实现（provider="local"），不依赖外部 AI API。
预留了 provider/api_key/model 字段，支持未来扩展。
"""

from __future__ import annotations

import difflib
import re

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.ai_data import AIAssistConfig, _BLOCK_KEYWORDS, _FIX_RULES, _KEYWORD_SNIPPETS, _NL_TEMPLATES
from yanpub.core.keyword_docs import categorize_keyword


# ============================================================
# 向后兼容 — 重新导出从 ai_data 迁移的名称
# ============================================================


def __getattr__(name: str):
    """模块级 __getattr__，保持从 ai_assist 导入旧名称的兼容性。

    - AIAssistConfig: 数据类已迁至 ai_data
    - _NL_TEMPLATES / _FIX_RULES / _BLOCK_KEYWORDS / _KEYWORD_SNIPPETS:
      常量已迁至 ai_data，但测试可能仍从本模块导入
    """
    _MIGRATED = {
        "AIAssistConfig",
        "_NL_TEMPLATES",
        "_FIX_RULES",
        "_BLOCK_KEYWORDS",
        "_KEYWORD_SNIPPETS",
    }
    if name in _MIGRATED:
        from yanpub.core import ai_data

        return getattr(ai_data, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================
# AI 辅助引擎
# ============================================================


class AIAssistEngine:
    """AI 辅助引擎 — 提供代码补全、自然语言转代码、错误修复"""

    def __init__(self, config: AIAssistConfig | None = None):
        self.config = config or AIAssistConfig()

    # ---- 1. 智能代码补全 ----

    def smart_complete(
        self,
        adapter: LanguageAdapter,
        code: str,
        line: int,
        column: int,
    ) -> list[dict]:
        """智能代码补全

        基于上下文的智能补全，超越简单的关键字补全：
        - 基于模式匹配：检测 if/当 后面的条件结构、段落后的代码块等
        - 基于关键字上下文：根据前后文推断可能的补全项
        - 基于错误修复：如果当前位置有语法错误，提供修复建议

        Args:
            adapter: 语言适配器
            code: 完整代码
            line: 光标行号（1-based）
            column: 光标列号（1-based）

        Returns:
            [{"label": str, "kind": str, "detail": str,
              "insert_text": str, "is_ai": bool}]
        """
        results: list[dict] = []

        # 获取当前行文本
        lines = code.split("\n")
        if line < 1 or line > len(lines):
            return results

        current_line = lines[line - 1]
        # 光标前的文本
        prefix = current_line[: column - 1] if column > 0 else ""

        # --- 1a. 基于关键字的片段补全 ---
        for kw, snippet_info in _KEYWORD_SNIPPETS.items():
            # 如果前缀以某个关键字结尾或为空且关键字以该前缀开头
            if self._matches_prefix(kw, prefix):
                results.append(
                    {
                        "label": kw,
                        "kind": "snippet",
                        "detail": snippet_info.get("detail", ""),
                        "insert_text": snippet_info["insert_text"],
                        "is_ai": True,
                    }
                )

        # --- 1b. 基于适配器关键字的补全 ---
        all_keywords = adapter.keywords
        if prefix.strip():
            # 过滤以当前输入开头的关键字
            matching = [kw for kw in all_keywords if kw.startswith(prefix.strip())]
        else:
            matching = all_keywords

        for kw in matching:
            # 避免重复（已作为 snippet 添加的跳过）
            if any(r["label"] == kw for r in results):
                continue

            category = categorize_keyword(kw)
            results.append(
                {
                    "label": kw,
                    "kind": "keyword",
                    "detail": f"关键字 ({category})" if category != "其他" else "关键字",
                    "insert_text": kw,
                    "is_ai": True,
                }
            )

        # --- 1c. 基于模式匹配的上下文补全 ---
        context_suggestions = self._context_suggestions(adapter, code, line, column)
        for s in context_suggestions:
            if not any(r["label"] == s["label"] for r in results):
                results.append(s)

        # --- 1d. 基于诊断的修复建议 ---
        fix_suggestions = self._diagnosis_suggestions(adapter, code, line)
        for s in fix_suggestions:
            if not any(r["label"] == s["label"] for r in results):
                results.append(s)

        return results

    # ---- 2. 自然语言转代码 ----

    def nl_to_code(
        self,
        adapter: LanguageAdapter,
        natural_text: str,
        context: str = "",
    ) -> dict:
        """自然语言转代码

        将中文自然语言描述转换为对应语言的代码片段。

        基于模板和规则实现（不依赖外部 API）：
        - 预定义常见意图模板：打印、循环、条件、变量声明、函数定义
        - 基于适配器关键字映射：将自然语言动词映射到语言关键字
        - 上下文感知：根据已有代码推断新代码的缩进和上下文

        Args:
            adapter: 语言适配器
            natural_text: 自然语言描述
            context: 已有代码上下文

        Returns:
            {"code": str, "confidence": float, "explanation": str}
        """
        text = natural_text.strip()
        if not text:
            return {
                "code": "",
                "confidence": 0.0,
                "explanation": "输入为空",
            }

        lang_id = adapter.id

        # 尝试匹配意图模板
        for intent_name, intent_data in _NL_TEMPLATES.items():
            for pattern in intent_data["patterns"]:
                if pattern in text:
                    code = self._apply_template(
                        intent_data,
                        lang_id,
                        text,
                        pattern,
                    )
                    # 推断缩进
                    if context:
                        indent = self._infer_indent(context)
                        code = self._apply_indent(code, indent)
                    return {
                        "code": code,
                        "confidence": 0.8,
                        "explanation": f"识别意图: {intent_name}（匹配关键词「{pattern}」）",
                    }

        # 尝试基于适配器关键字的简单映射
        for kw in adapter.keywords:
            if kw in text:
                snippet_info = _KEYWORD_SNIPPETS.get(kw)
                if snippet_info:
                    code = self._fill_snippet_from_nl(snippet_info["insert_text"], text)
                    return {
                        "code": code,
                        "confidence": 0.5,
                        "explanation": f"基于关键字「{kw}」生成",
                    }

        # 无法识别
        return {
            "code": f"# 无法识别: {text}",
            "confidence": 0.1,
            "explanation": f"未能识别自然语言描述「{text}」中的意图",
        }

    # ---- 3. 错误修复建议 ----

    def fix_suggestion(
        self,
        adapter: LanguageAdapter,
        code: str,
        error: str,
    ) -> list[dict]:
        """错误修复建议

        分析执行错误，提供修复建议。

        基于规则实现：
        - 常见错误模式匹配（未定义变量、缺少关键字、语法错误）
        - 基于适配器关键字检查拼写错误（编辑距离）
        - 基于代码结构推断缺失的结束标记

        Args:
            adapter: 语言适配器
            code: 原始代码
            error: 错误信息

        Returns:
            [{"title": str, "fix": str, "description": str, "confidence": float}]
        """
        results: list[dict] = []

        # --- 3a. 规则匹配 ---
        for rule in _FIX_RULES:
            if re.search(rule["pattern"], error, re.IGNORECASE):
                fix_type = rule["fix"]
                confidence = rule["confidence"]

                if fix_type == "add_end_marker":
                    fix_code = self._fix_add_end_marker(adapter, code)
                    if fix_code != code:
                        results.append(
                            {
                                "title": "添加缺失的结束标记",
                                "fix": fix_code,
                                "description": "检测到未闭合的代码块，已添加「结束」标记",
                                "confidence": confidence,
                            }
                        )

                elif fix_type == "suggest_similar":
                    similar_fixes = self._fix_suggest_similar(adapter, code, error)
                    results.extend(similar_fixes)

                elif fix_type == "suggest_syntax_fix":
                    syntax_fixes = self._fix_suggest_syntax(adapter, code, error)
                    results.extend(syntax_fixes)

        # --- 3b. 拼写检查（基于编辑距离） ---
        spell_fixes = self._check_keyword_spelling(adapter, code)
        results.extend(spell_fixes)

        # --- 3c. 结构检查（缺失结束标记） ---
        if not any(r["title"] == "添加缺失的结束标记" for r in results):
            structure_fix = self._fix_add_end_marker(adapter, code)
            if structure_fix != code:
                results.append(
                    {
                        "title": "添加缺失的结束标记",
                        "fix": structure_fix,
                        "description": "检测到未闭合的代码块，已添加「结束」标记",
                        "confidence": 0.8,
                    }
                )

        # 去重
        seen: set[str] = set()
        unique_results: list[dict] = []
        for r in results:
            key = r["title"]
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        return unique_results

    # ============================================================
    # 私有方法 — 智能补全
    # ============================================================

    def _matches_prefix(self, keyword: str, prefix: str) -> bool:
        """判断关键字是否匹配当前前缀"""
        stripped = prefix.strip()
        if not stripped:
            # 空前缀：所有关键字都匹配
            return True
        # 关键字以当前输入的最后一个词开头
        last_word = stripped.split()[-1] if stripped else ""
        return keyword.startswith(last_word)

    def _context_suggestions(
        self,
        adapter: LanguageAdapter,
        code: str,
        line: int,
        column: int,
    ) -> list[dict]:
        """基于上下文的补全建议"""
        results: list[dict] = []
        lines = code.split("\n")

        if line < 1 or line > len(lines):
            return results

        # 检查前一行是否开启了代码块
        if line >= 2:
            prev_line = lines[line - 2].strip()
            for block_kw, end_marker in _BLOCK_KEYWORDS.items():
                if prev_line.startswith(block_kw) and end_marker:
                    # 在块内，建议结束标记
                    if not any(r["label"] == end_marker for r in results):
                        results.append(
                            {
                                "label": end_marker,
                                "kind": "keyword",
                                "detail": f"闭合「{block_kw}」块",
                                "insert_text": end_marker + "。",
                                "is_ai": True,
                            }
                        )
                    break

        # 检查当前行是否在段落定义内
        current_indent = len(lines[line - 1]) - len(lines[line - 1].lstrip())
        if current_indent > 0:
            # 在缩进块内，可能需要 "返回" 或 "结束"
            for kw in ["返回", "结束"]:
                if kw in adapter.keywords:
                    if not any(r["label"] == kw for r in results):
                        results.append(
                            {
                                "label": kw,
                                "kind": "keyword",
                                "detail": "块内关键字",
                                "insert_text": kw + "。",
                                "is_ai": True,
                            }
                        )

        return results

    def _diagnosis_suggestions(
        self,
        adapter: LanguageAdapter,
        code: str,
        line: int,
    ) -> list[dict]:
        """基于诊断的补全建议"""
        results: list[dict] = []

        # 快速检查：如果代码有未闭合的块
        block_stack: list[str] = []
        for ln in code.split("\n"):
            stripped = ln.strip()
            for block_kw in _BLOCK_KEYWORDS:
                if stripped.startswith(block_kw):
                    block_stack.append(block_kw)
            if stripped.startswith("结束"):
                if block_stack:
                    block_stack.pop()

        if block_stack:
            # 有未闭合的块，建议添加结束标记
            last_unclosed = block_stack[-1]
            end_marker = _BLOCK_KEYWORDS.get(last_unclosed, "结束")
            if end_marker:
                results.append(
                    {
                        "label": f"{end_marker}。（闭合 {last_unclosed}）",
                        "kind": "snippet",
                        "detail": f"闭合未结束的「{last_unclosed}」块",
                        "insert_text": end_marker + "。",
                        "is_ai": True,
                    }
                )

        return results

    # ============================================================
    # 私有方法 — 自然语言转代码
    # ============================================================

    def _apply_template(
        self,
        intent_data: dict,
        lang_id: str,
        text: str,
        matched_pattern: str,
    ) -> str:
        """应用意图模板，从自然语言中提取参数"""
        templates = intent_data["templates"]
        template = templates.get(lang_id, templates.get("default", ""))

        # 提取参数
        params = self._extract_nl_params(text, matched_pattern, intent_data)

        # 填充模板
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template

    def _extract_nl_params(
        self,
        text: str,
        matched_pattern: str,
        intent_data: dict,
    ) -> dict[str, str]:
        """从自然语言中提取模板参数"""
        params: dict[str, str] = {}

        # 移除已匹配的模式词
        remainder = text.replace(matched_pattern, "", 1).strip()

        if intent_data.get("patterns") and matched_pattern in intent_data["patterns"]:
            intent_name = ""
            for name, data in _NL_TEMPLATES.items():
                if data is intent_data:
                    intent_name = name
                    break

            if intent_name == "print":
                # "打印你好" → text="你好"
                params["text"] = remainder if remainder else "内容"
            elif intent_name == "variable":
                # "设甲为三" → name="甲", value="三"
                # "定义变量 甲 为 42" → name="甲", value="42"
                var_match = re.match(
                    r'["\']?(.+?)["\']?\s*(?:为|是|=)\s*["\']?(.+?)["\']?$',
                    remainder,
                )
                if var_match:
                    params["name"] = var_match.group(1).strip()
                    params["value"] = var_match.group(2).strip()
                else:
                    params["name"] = remainder if remainder else "名"
                    params["value"] = "值"
            elif intent_name == "function":
                # "定义函数 加法" → name="加法"
                name = remainder.strip()
                params["name"] = name if name else "函数名"
            elif intent_name == "loop":
                # "循环 甲 大于 零" → condition="甲 大于 零"
                params["condition"] = remainder if remainder else "条件"
                params["body"] = '打印("循环体")。'
            elif intent_name == "condition":
                # "如果 甲 大于 三" → condition="甲 大于 三"
                params["condition"] = remainder if remainder else "条件"
                params["body"] = '打印("条件成立")。'
            elif intent_name == "class":
                # "定义类 动物" → name="动物"
                name = remainder.strip()
                params["name"] = name if name else "类名"
                params["attr"] = "属性名"
                params["param"] = "参数名"
            elif intent_name == "return":
                # "返回 甲" → value="甲"
                params["value"] = remainder if remainder else "值"
            elif intent_name == "import":
                # "导入 数学" → module="数学"
                params["module"] = remainder if remainder else "模块名"

        return params

    def _infer_indent(self, context: str) -> str:
        """从上下文推断缩进"""
        if not context:
            return ""
        lines = context.split("\n")
        # 取最后一行的缩进
        if lines:
            last_line = lines[-1]
            indent = ""
            for ch in last_line:
                if ch in (" ", "\t"):
                    indent += ch
                else:
                    break
            # 如果最后一行以冒号或段落开头结尾，增加一级缩进
            stripped = last_line.strip()
            if stripped.endswith(("：", ":")):
                indent += "  "
            return indent
        return ""

    def _apply_indent(self, code: str, indent: str) -> str:
        """为代码添加缩进"""
        if not indent:
            return code
        lines = code.split("\n")
        return "\n".join(indent + line for line in lines)

    def _fill_snippet_from_nl(self, snippet: str, text: str) -> str:
        """从自然语言文本填充片段模板"""
        # 简单实现：用文本替换第一个占位符
        result = snippet
        # 提取花括号内的占位符名
        placeholders = re.findall(r"\{(\w+)\}", snippet)
        for ph in placeholders:
            # 用文本内容填充（去掉已有的关键字词）
            clean = text.strip()
            if not clean:
                clean = ph
            result = result.replace("{" + ph + "}", clean, 1)
        return result

    # ============================================================
    # 私有方法 — 错误修复
    # ============================================================

    def _fix_add_end_marker(self, adapter: LanguageAdapter, code: str) -> str:
        """为未闭合的代码块添加结束标记"""
        lines = code.split("\n")
        block_stack: list[tuple[str, int]] = []  # (关键字, 行号)

        for i, ln in enumerate(lines):
            stripped = ln.strip()
            for block_kw in _BLOCK_KEYWORDS:
                if stripped.startswith(block_kw) and not stripped.startswith(block_kw + "标记"):
                    block_stack.append((block_kw, i))
            if stripped.startswith("结束"):
                if block_stack:
                    block_stack.pop()

        if not block_stack:
            return code

        # 添加缺失的结束标记
        result_lines = list(lines)
        for block_kw, line_no in reversed(block_stack):
            # 获取对应缩进（使用原始代码中块开头的缩进）
            indent = ""
            if line_no < len(lines):
                original_line = lines[line_no]
                for ch in original_line:
                    if ch in (" ", "\t"):
                        indent += ch
                    else:
                        break
            end_marker = _BLOCK_KEYWORDS.get(block_kw, "结束")
            if end_marker:
                result_lines.append(indent + end_marker + "。")

        result = "\n".join(result_lines)
        return result if result != code else code

    def _fix_suggest_similar(
        self,
        adapter: LanguageAdapter,
        code: str,
        error: str,
    ) -> list[dict]:
        """建议相似的关键字（针对未定义变量错误）"""
        results: list[dict] = []

        # 从错误信息中提取未定义的名称
        name_match = re.search(
            r"未定义.*?['\"]?(\S+?)['\"]?|name\s+['\"]?(\S+?)['\"]?\s+is\s+not\s+defined",
            error,
            re.IGNORECASE,
        )
        undefined_name = ""
        if name_match:
            undefined_name = name_match.group(1) or name_match.group(2) or ""

        if not undefined_name:
            return results

        # 在适配器关键字中找相似的
        similar = difflib.get_close_matches(
            undefined_name,
            adapter.keywords,
            n=3,
            cutoff=0.4,
        )

        for match in similar:
            # 生成修复后的代码
            fixed_code = code.replace(undefined_name, match, 1)
            results.append(
                {
                    "title": f"将「{undefined_name}」改为「{match}」",
                    "fix": fixed_code,
                    "description": f"「{undefined_name}」未定义，您是否想用关键字「{match}」？",
                    "confidence": 0.7,
                }
            )

        return results

    def _fix_suggest_syntax(
        self,
        adapter: LanguageAdapter,
        code: str,
        error: str,
    ) -> list[dict]:
        """建议语法修复"""
        results: list[dict] = []

        # 检查中文标点混用
        # 中文冒号 vs 英文冒号
        if "：" in code:
            # 可能需要在中文语境中使用中文冒号
            pass

        # 检查缺少句号
        lines = code.split("\n")
        fixed_lines = list(lines)
        changed = False
        for i, ln in enumerate(fixed_lines):
            stripped = ln.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # 如果行以关键字开头且不以句号或冒号结尾，可能缺少句号
            for kw in adapter.keywords:
                if stripped.startswith(kw) and not stripped.endswith(("。", "：", ":", "）", ")")):
                    # 简单检查：是否看起来像完整语句
                    if len(stripped) > len(kw) and not any(
                        stripped.endswith(c) for c in ("：", ":", "）", ")")
                    ):
                        fixed_lines[i] = ln + "。"
                        changed = True
                        break

        if changed:
            fixed_code = "\n".join(fixed_lines)
            results.append(
                {
                    "title": "补全缺失的句号",
                    "fix": fixed_code,
                    "description": "部分语句可能缺少句号（。）作为结束符",
                    "confidence": 0.5,
                }
            )

        return results

    def _check_keyword_spelling(
        self,
        adapter: LanguageAdapter,
        code: str,
    ) -> list[dict]:
        """基于编辑距离检查关键字拼写"""
        results: list[dict] = []
        all_keywords = adapter.keywords

        if not all_keywords:
            return results

        # 提取代码中的中文词
        chinese_words = re.findall(r"[\u4e00-\u9fff]+", code)

        for word in chinese_words:
            # 跳过已知的正确关键字
            if word in all_keywords:
                continue

            # 在关键字中找近似的
            similar = difflib.get_close_matches(word, all_keywords, n=1, cutoff=0.6)
            if similar:
                fixed_code = code.replace(word, similar[0], 1)
                results.append(
                    {
                        "title": f"将「{word}」改为「{similar[0]}」",
                        "fix": fixed_code,
                        "description": f"「{word}」可能是「{similar[0]}」的拼写错误",
                        "confidence": 0.6,
                    }
                )

        return results
