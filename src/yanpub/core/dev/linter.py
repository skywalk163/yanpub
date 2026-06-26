"""LSP 代码风格检查 — Lint 规则引擎 + 自定义规则 + 自动修复

核心类:
- LintRule: 单条规则定义
- LintResult: 检查结果
- LintRuleEngine: 规则引擎，管理规则的注册、执行、修复
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from yanpub.core.adapter.adapter import Diagnostic


class LintSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class LintCategory(str, Enum):
    STYLE = "style"
    COMPLEXITY = "complexity"
    NAMING = "naming"
    SYNTAX = "syntax"
    BEST_PRACTICE = "best_practice"
    SECURITY = "security"


@dataclass
class LintRule:
    """单条 Lint 规则"""

    rule_id: str
    name: str
    description: str
    severity: LintSeverity = LintSeverity.WARNING
    category: LintCategory = LintCategory.STYLE
    enabled: bool = True
    auto_fix: bool = False
    check_fn: Callable[[str, str], list[LintResult]] | None = None
    fix_fn: Callable[[str, str, list[LintResult]], str] | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "category": self.category.value,
            "enabled": self.enabled,
            "auto_fix": self.auto_fix,
        }


@dataclass
class LintResult:
    """Lint 检查结果"""

    rule_id: str
    line: int  # 1-based
    column: int  # 1-based
    message: str
    severity: LintSeverity = LintSeverity.WARNING
    end_line: int = 0
    end_column: int = 0
    fix_text: str = ""

    def to_diagnostic(self) -> Diagnostic:
        return Diagnostic(
            line=self.line,
            column=self.column,
            severity=self.severity.value,
            message=f"[{self.rule_id}] {self.message}",
            source="yanlinter",
        )

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "severity": self.severity.value,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "fix_text": self.fix_text,
        }


# ============================================================
# 内置规则实现
# ============================================================


def _check_trailing_whitespace(code: str, lang_id: str) -> list[LintResult]:
    """W001: 行尾空白"""
    results = []
    for i, line in enumerate(code.split("\n"), 1):
        stripped = line.rstrip()
        if len(line) > len(stripped) and stripped:
            results.append(
                LintResult(
                    rule_id="W001",
                    line=i,
                    column=len(stripped) + 1,
                    message="行尾有多余空白字符",
                    severity=LintSeverity.INFO,
                    end_line=i,
                    end_column=len(line) + 1,
                    fix_text=stripped,
                )
            )
    return results


def _fix_trailing_whitespace(code: str, lang_id: str, results: list[LintResult]) -> str:
    lines = code.split("\n")
    for r in results:
        if r.rule_id == "W001" and 0 < r.line <= len(lines):
            lines[r.line - 1] = lines[r.line - 1].rstrip()
    return "\n".join(lines)


def _check_long_line(code: str, lang_id: str) -> list[LintResult]:
    """W002: 行过长"""
    MAX_LEN = 100
    results = []
    for i, line in enumerate(code.split("\n"), 1):
        if len(line) > MAX_LEN:
            results.append(
                LintResult(
                    rule_id="W002",
                    line=i,
                    column=MAX_LEN + 1,
                    message=f"行长度 {len(line)} 超过限制 {MAX_LEN}",
                    severity=LintSeverity.WARNING,
                    end_line=i,
                    end_column=len(line) + 1,
                )
            )
    return results


def _check_missing_newline_eof(code: str, lang_id: str) -> list[LintResult]:
    """W003: 文件末尾缺少换行"""
    if code and not code.endswith("\n"):
        lines = code.split("\n")
        return [
            LintResult(
                rule_id="W003",
                line=len(lines),
                column=len(lines[-1]) + 1 if lines else 1,
                message="文件末尾缺少换行符",
                severity=LintSeverity.INFO,
                fix_text=code + "\n",
            )
        ]
    return []


def _fix_missing_newline_eof(code: str, lang_id: str, results: list[LintResult]) -> str:
    if code and not code.endswith("\n"):
        return code + "\n"
    return code


def _check_consecutive_blank_lines(code: str, lang_id: str) -> list[LintResult]:
    """W004: 连续空行过多"""
    MAX_BLANK = 2
    results = []
    lines = code.split("\n")
    blank_count = 0
    for i, line in enumerate(lines, 1):
        if line.strip() == "":
            blank_count += 1
            if blank_count > MAX_BLANK:
                results.append(
                    LintResult(
                        rule_id="W004",
                        line=i,
                        column=1,
                        message=f"连续空行超过 {MAX_BLANK} 行",
                        severity=LintSeverity.INFO,
                        end_line=i,
                        end_column=1,
                    )
                )
        else:
            blank_count = 0
    return results


def _check_todo_fixme(code: str, lang_id: str) -> list[LintResult]:
    """W005: TODO/FIXME 注释"""
    results = []
    for i, line in enumerate(code.split("\n"), 1):
        if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line, re.IGNORECASE):
            results.append(
                LintResult(
                    rule_id="W005",
                    line=i,
                    column=1,
                    message="发现 TODO/FIXME/HACK/XXX 注释",
                    severity=LintSeverity.INFO,
                    end_line=i,
                    end_column=len(line) + 1,
                )
            )
    return results


def _check_mixed_indent(code: str, lang_id: str) -> list[LintResult]:
    """E001: 缩进混用空格和制表符"""
    results = []
    for i, line in enumerate(code.split("\n"), 1):
        leading = ""
        for ch in line:
            if ch in (" ", "\t"):
                leading += ch
            else:
                break
        if " " in leading and "\t" in leading:
            results.append(
                LintResult(
                    rule_id="E001",
                    line=i,
                    column=1,
                    message="缩进混用空格和制表符",
                    severity=LintSeverity.WARNING,
                    end_line=i,
                    end_column=len(leading) + 1,
                )
            )
    return results


def _check_empty_function(code: str, lang_id: str) -> list[LintResult]:
    """W006: 空函数/段落体"""
    results = []
    lines = code.split("\n")

    # 检测模式: 函数/段落/函 定义后紧接结束
    func_start_re = re.compile(
        r"^\s*(段落|函数|函)\s+\S+.*[）)]\s*$"
        r"|^\s*(段落|函数|函)\s+\S+\s*(参数|param)?.*$",
    )
    end_re = re.compile(r"^\s*(结束|}\s*$)")

    i = 0
    while i < len(lines):
        line = lines[i]
        if func_start_re.match(line) or ("{" in line and "}" not in line):
            # 找到函数开始，检查下一行是否直接结束
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and (end_re.match(lines[j]) or lines[j].strip() == "}"):
                results.append(
                    LintResult(
                        rule_id="W006",
                        line=i + 1,
                        column=1,
                        message="空函数体",
                        severity=LintSeverity.INFO,
                        end_line=j + 1,
                        end_column=len(lines[j]) + 1,
                    )
                )
        i += 1
    return results


def _check_deep_nesting(code: str, lang_id: str) -> list[LintResult]:
    """C001: 嵌套层级过深"""
    MAX_DEPTH = 4
    results = []
    lines = code.split("\n")
    depth = 0
    max_depth_val = 0
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        # 中文关键字增加嵌套
        for kw in (
            "如果",
            "若",
            "当",
            "当满足",
            "当满",
            "遍历",
            "对于",
            "循环当",
            "尝试",
            "函数",
            "函",
            "段落",
            "类",
        ):
            if stripped.startswith(kw) or f" {kw}" in stripped or f"\t{kw}" in stripped:
                depth += 1
                break
        # 右花括号减少嵌套
        close_count = stripped.count("}")
        if close_count > 0:
            depth = max(0, depth - close_count)
        if depth > max_depth_val:
            max_depth_val = depth
        if depth > MAX_DEPTH:
            results.append(
                LintResult(
                    rule_id="C001",
                    line=i,
                    column=1,
                    message=f"嵌套层级 {depth} 超过限制 {MAX_DEPTH}",
                    severity=LintSeverity.WARNING,
                    end_line=i,
                    end_column=len(line) + 1,
                )
            )
    return results


def _check_naming_convention(code: str, lang_id: str) -> list[LintResult]:
    """N001: 变量命名过短（单字符非循环变量）"""
    results = []
    loop_vars = {"i", "j", "k", "甲", "乙", "丙", "丁"}
    # 匹配 定义/定/设 X = 模式
    pattern = re.compile(r"(?:定义|定|设)\s+(\S+)\s*(?:=|为)")
    for i, line in enumerate(code.split("\n"), 1):
        m = pattern.search(line)
        if m:
            name = m.group(1)
            if len(name) == 1 and name not in loop_vars:
                results.append(
                    LintResult(
                        rule_id="N001",
                        line=i,
                        column=m.start() + 1,
                        message=f"变量名 '{name}' 过短，建议使用更具描述性的名称",
                        severity=LintSeverity.HINT,
                        end_line=i,
                        end_column=m.end() + 1,
                    )
                )
    return results


def _check_duplicate_keywords(code: str, lang_id: str) -> list[LintResult]:
    """E002: 重复关键字（如 如果如果）"""
    results = []
    dup_pattern = re.compile(r"(如果|否则|当|返回|定义|定)\1+")
    for i, line in enumerate(code.split("\n"), 1):
        for m in dup_pattern.finditer(line):
            results.append(
                LintResult(
                    rule_id="E002",
                    line=i,
                    column=m.start() + 1,
                    message=f"重复关键字 '{m.group()}'",
                    severity=LintSeverity.ERROR,
                    end_line=i,
                    end_column=m.end() + 1,
                )
            )
    return results


# ============================================================
# 内置规则表
# ============================================================

_BUILTIN_RULES: list[LintRule] = [
    LintRule(
        rule_id="W001",
        name="trailing-whitespace",
        description="行尾有多余空白字符",
        severity=LintSeverity.INFO,
        category=LintCategory.STYLE,
        auto_fix=True,
        check_fn=_check_trailing_whitespace,
        fix_fn=_fix_trailing_whitespace,
    ),
    LintRule(
        rule_id="W002",
        name="line-too-long",
        description="行长度超过 100 字符限制",
        severity=LintSeverity.WARNING,
        category=LintCategory.STYLE,
        check_fn=_check_long_line,
    ),
    LintRule(
        rule_id="W003",
        name="missing-final-newline",
        description="文件末尾缺少换行符",
        severity=LintSeverity.INFO,
        category=LintCategory.STYLE,
        auto_fix=True,
        check_fn=_check_missing_newline_eof,
        fix_fn=_fix_missing_newline_eof,
    ),
    LintRule(
        rule_id="W004",
        name="too-many-blank-lines",
        description="连续空行超过 2 行",
        severity=LintSeverity.INFO,
        category=LintCategory.STYLE,
        check_fn=_check_consecutive_blank_lines,
    ),
    LintRule(
        rule_id="W005",
        name="todo-fixme",
        description="发现 TODO/FIXME/HACK/XXX 注释",
        severity=LintSeverity.INFO,
        category=LintCategory.BEST_PRACTICE,
        check_fn=_check_todo_fixme,
    ),
    LintRule(
        rule_id="W006",
        name="empty-function",
        description="空函数体",
        severity=LintSeverity.INFO,
        category=LintCategory.BEST_PRACTICE,
        check_fn=_check_empty_function,
    ),
    LintRule(
        rule_id="E001",
        name="mixed-indent",
        description="缩进混用空格和制表符",
        severity=LintSeverity.WARNING,
        category=LintCategory.STYLE,
        check_fn=_check_mixed_indent,
    ),
    LintRule(
        rule_id="E002",
        name="duplicate-keyword",
        description="重复关键字",
        severity=LintSeverity.ERROR,
        category=LintCategory.SYNTAX,
        check_fn=_check_duplicate_keywords,
    ),
    LintRule(
        rule_id="C001",
        name="deep-nesting",
        description="嵌套层级超过 4 层",
        severity=LintSeverity.WARNING,
        category=LintCategory.COMPLEXITY,
        check_fn=_check_deep_nesting,
    ),
    LintRule(
        rule_id="N001",
        name="short-variable-name",
        description="变量名过短",
        severity=LintSeverity.HINT,
        category=LintCategory.NAMING,
        check_fn=_check_naming_convention,
    ),
]


# ============================================================
# Lint 规则引擎
# ============================================================


class LintRuleEngine:
    """Lint 规则引擎 — 管理规则的注册、执行、修复"""

    def __init__(self):
        self._rules: dict[str, LintRule] = {}
        # 注册内置规则
        for rule in _BUILTIN_RULES:
            self._rules[rule.rule_id] = rule

    # ---- 规则管理 ----

    def register_rule(self, rule: LintRule) -> None:
        """注册自定义规则"""
        self._rules[rule.rule_id] = rule

    def unregister_rule(self, rule_id: str) -> bool:
        """移除规则"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            self._rules[rule_id].enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            self._rules[rule_id].enabled = False
            return True
        return False

    def get_rule(self, rule_id: str) -> LintRule | None:
        return self._rules.get(rule_id)

    def list_rules(self, category: LintCategory | None = None) -> list[LintRule]:
        rules = list(self._rules.values())
        if category:
            rules = [r for r in rules if r.category == category]
        return sorted(rules, key=lambda r: r.rule_id)

    # ---- 检查 ----

    def lint(self, code: str, lang_id: str = "") -> list[LintResult]:
        """对所有启用的规则执行检查"""
        results = []
        for rule in self._rules.values():
            if not rule.enabled or not rule.check_fn:
                continue
            try:
                rule_results = rule.check_fn(code, lang_id)
                results.extend(rule_results)
            except Exception:
                pass  # 规则执行失败不影响其他规则
        # 按行号排序
        results.sort(key=lambda r: (r.line, r.column))
        return results

    def lint_with_rule(self, code: str, lang_id: str, rule_ids: list[str]) -> list[LintResult]:
        """仅对指定规则执行检查"""
        results = []
        for rid in rule_ids:
            rule = self._rules.get(rid)
            if rule and rule.enabled and rule.check_fn:
                try:
                    results.extend(rule.check_fn(code, lang_id))
                except Exception:
                    pass
        results.sort(key=lambda r: (r.line, r.column))
        return results

    # ---- 自动修复 ----

    def fix(self, code: str, lang_id: str = "") -> tuple[str, list[LintResult]]:
        """对所有可自动修复的规则执行修复，返回 (修复后代码, 已修复结果)"""
        fixed_code = code
        fixed_results = []
        for rule in self._rules.values():
            if not rule.enabled or not rule.auto_fix or not rule.fix_fn:
                continue
            try:
                results = rule.check_fn(code, lang_id)
                if results:
                    fixed_code = rule.fix_fn(fixed_code, lang_id, results)
                    fixed_results.extend(results)
            except Exception:
                pass
        return fixed_code, fixed_results

    # ---- 统计 ----

    def summary(self, results: list[LintResult]) -> dict:
        """统计检查结果"""
        by_severity = {}
        by_rule = {}
        for r in results:
            by_severity[r.severity.value] = by_severity.get(r.severity.value, 0) + 1
            by_rule[r.rule_id] = by_rule.get(r.rule_id, 0) + 1
        return {
            "total": len(results),
            "by_severity": by_severity,
            "by_rule": by_rule,
        }
