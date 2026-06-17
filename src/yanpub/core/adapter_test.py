"""适配器测试框架 — 统一的适配器功能验证与回归测试

核心组件：
1. AdapterTestCase  — 单个测试用例，按 category 调用不同适配器方法
2. AdapterTestSuite — 测试套件，管理并运行一组测试用例
3. AdapterTestReport — 测试报告，支持 table/json/html 输出
4. AdapterCompatibilityValidator — 适配器兼容性验证器
5. RegressionTestGenerator — 回归测试生成器

用法：
  yanpub adapter-test              # 运行所有适配器的测试套件
  yanpub adapter-test duan         # 运行指定适配器的测试
  yanpub adapter-validate          # 验证所有适配器兼容性
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

from yanpub.core.adapter import (
    ExecutionResult,
    LanguageAdapter,
)
from yanpub.core.registry import LanguageRegistry


# ============================================================
# 测试用例与结果
# ============================================================


@dataclass
class AdapterTestResult:
    """适配器测试结果"""

    test_name: str
    adapter_id: str
    passed: bool
    message: str = ""
    duration_ms: float = 0.0
    actual: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "adapter_id": self.adapter_id,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "actual": self.actual,
            "expected": self.expected,
        }


@dataclass
class AdapterTestCase:
    """适配器测试用例"""

    name: str
    category: str  # "syntax" | "execution" | "completion" | "diagnostics" | "formatting" | "navigation"
    code: str
    expected: dict
    description: str = ""
    skip_adapters: list[str] = field(default_factory=list)

    def run(self, adapter: LanguageAdapter) -> AdapterTestResult:
        """运行测试用例，根据 category 调用不同适配器方法"""
        start = time.monotonic()

        if adapter.id in self.skip_adapters:
            elapsed = (time.monotonic() - start) * 1000
            return AdapterTestResult(
                test_name=self.name,
                adapter_id=adapter.id,
                passed=True,
                message="跳过（适配器不适用）",
                duration_ms=elapsed,
            )

        try:
            if self.category == "execution":
                actual = self._run_execution(adapter)
            elif self.category == "completion":
                actual = self._run_completion(adapter)
            elif self.category == "diagnostics":
                actual = self._run_diagnostics(adapter)
            elif self.category == "formatting":
                actual = self._run_formatting(adapter)
            elif self.category == "syntax":
                actual = self._run_syntax(adapter)
            elif self.category == "navigation":
                actual = self._run_navigation(adapter)
            else:
                elapsed = (time.monotonic() - start) * 1000
                return AdapterTestResult(
                    test_name=self.name,
                    adapter_id=adapter.id,
                    passed=False,
                    message=f"未知测试分类: {self.category}",
                    duration_ms=elapsed,
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return AdapterTestResult(
                test_name=self.name,
                adapter_id=adapter.id,
                passed=False,
                message=f"测试执行异常: {e}",
                duration_ms=elapsed,
                actual={"error": str(e)},
                expected=self.expected,
            )

        elapsed = (time.monotonic() - start) * 1000
        passed, message = self._check(actual, self.expected)

        return AdapterTestResult(
            test_name=self.name,
            adapter_id=adapter.id,
            passed=passed,
            message=message,
            duration_ms=elapsed,
            actual=actual,
            expected=self.expected,
        )

    # ---- category 分发方法 ----

    def _run_execution(self, adapter: LanguageAdapter) -> dict:
        """执行类测试：调用 adapter.eval()"""
        result = adapter.eval(self.code)
        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

    def _run_completion(self, adapter: LanguageAdapter) -> dict:
        """补全类测试：调用 adapter.complete()"""
        items = adapter.complete(self.code, line=1, column=1)
        return {
            "items": [
                {"label": i.label, "kind": i.kind, "insert_text": i.insert_text}
                for i in items
            ],
            "count": len(items),
        }

    def _run_diagnostics(self, adapter: LanguageAdapter) -> dict:
        """诊断类测试：调用 adapter.diagnose()"""
        diags = adapter.diagnose(self.code)
        return {
            "diagnostics": [
                {
                    "line": d.line,
                    "column": d.column,
                    "severity": d.severity,
                    "message": d.message,
                }
                for d in diags
            ],
            "count": len(diags),
            "has_errors": any(d.severity == "error" for d in diags),
            "has_warnings": any(d.severity == "warning" for d in diags),
        }

    def _run_formatting(self, adapter: LanguageAdapter) -> dict:
        """格式化类测试：调用 adapter.format()"""
        formatted = adapter.format(self.code)
        return {
            "formatted": formatted,
            "changed": formatted != self.code,
            "length": len(formatted),
        }

    def _run_syntax(self, adapter: LanguageAdapter) -> dict:
        """语法类测试：调用 adapter.tokenize() 和 adapter.parse()"""
        tokens = adapter.tokenize(self.code)
        ast = adapter.parse(self.code)
        return {
            "token_count": len(tokens),
            "tokens": [
                {"type": t.type, "value": t.value, "line": t.line, "column": t.column}
                for t in tokens
            ],
            "has_ast": ast is not None,
            "parseable": ast is not None or len(tokens) > 0,
        }

    def _run_navigation(self, adapter: LanguageAdapter) -> dict:
        """导航类测试：调用 adapter.definition() / references()"""
        definition = adapter.definition(self.code, line=1, column=1)
        references = adapter.references(self.code, line=1, column=1)
        return {
            "has_definition": definition is not None,
            "definition_count": len(definition) if definition else 0,
            "has_references": references is not None,
            "references_count": len(references) if references else 0,
        }

    # ---- 结果检查 ----

    def _check(self, actual: dict, expected: dict) -> tuple[bool, str]:
        """对比实际结果与期望结果

        支持的期望键：
        - "success": bool — 检查执行成功
        - "exit_code": int — 检查退出码
        - "has_errors": bool — 检查是否有错误诊断
        - "has_warnings": bool — 检查是否有警告
        - "count" / "min_count" / "max_count": int — 检查数量
        - "changed": bool — 检查格式化是否改变
        - "parseable": bool — 检查是否可解析
        - "has_ast": bool — 检查是否有 AST
        - "contains_stdout": str — 检查 stdout 包含某子串
        - "contains_stderr": str — 检查 stderr 包含某子串
        """
        mismatches = []

        for key, expected_val in expected.items():
            actual_val = actual.get(key)

            if key == "min_count":
                # 最小数量检查
                count = actual.get("count", 0)
                if count < expected_val:
                    mismatches.append(
                        f"count={count} < min_count={expected_val}"
                    )
            elif key == "max_count":
                # 最大数量检查
                count = actual.get("count", 0)
                if count > expected_val:
                    mismatches.append(
                        f"count={count} > max_count={expected_val}"
                    )
            elif key == "contains_stdout":
                stdout = actual.get("stdout", "")
                if expected_val not in stdout:
                    mismatches.append(
                        f"stdout 不包含 '{expected_val}'"
                    )
            elif key == "contains_stderr":
                stderr = actual.get("stderr", "")
                if expected_val not in stderr:
                    mismatches.append(
                        f"stderr 不包含 '{expected_val}'"
                    )
            elif actual_val != expected_val:
                mismatches.append(
                    f"{key}: 期望={expected_val}, 实际={actual_val}"
                )

        if mismatches:
            return False, "; ".join(mismatches)
        return True, "通过"


# ============================================================
# 测试套件
# ============================================================


@dataclass
class AdapterTestReport:
    """适配器测试报告"""

    adapter_id: str
    adapter_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[AdapterTestResult] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "duration_ms": round(self.duration_ms, 2),
        }

    def to_table(self) -> str:
        """格式化为文本表格"""
        lines = []
        lines.append(f"适配器测试报告: {self.adapter_name} ({self.adapter_id})")
        lines.append("=" * 70)
        lines.append(
            f"总计: {self.total}  通过: {self.passed}  "
            f"失败: {self.failed}  跳过: {self.skipped}  "
            f"耗时: {self.duration_ms:.0f}ms"
        )
        lines.append("-" * 70)

        if not self.results:
            lines.append("（无测试结果）")
        else:
            for r in self.results:
                if r.message == "跳过（适配器不适用）":
                    icon = "⊘"
                    status = "SKIP"
                elif r.passed:
                    icon = "✓"
                    status = "PASS"
                else:
                    icon = "✗"
                    status = "FAIL"
                lines.append(
                    f"  {icon} [{status:4s}] {r.test_name:30s} "
                    f"{r.duration_ms:6.1f}ms  {r.message}"
                )

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_html(self) -> str:
        """生成 HTML 报告（使用 string.Template 避免花括号冲突）"""
        tmpl = Template(
            """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>适配器测试报告 - ${adapter_name}</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #f8f9fa; }
  h1 { color: #2C3E50; border-bottom: 2px solid #3498DB; padding-bottom: 0.5rem; }
  .summary { display: flex; gap: 1.5rem; margin: 1.5rem 0; }
  .summary .card { background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 120px; text-align: center; }
  .summary .card .number { font-size: 2rem; font-weight: bold; }
  .summary .card .label { color: #7f8c8d; font-size: 0.9rem; }
  .card.pass .number { color: #27ae60; }
  .card.fail .number { color: #e74c3c; }
  .card.skip .number { color: #f39c12; }
  .card.total .number { color: #2C3E50; }
  .card.time .number { color: #3498DB; font-size: 1.5rem; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th { background: #2C3E50; color: white; padding: 0.75rem 1rem; text-align: left; }
  td { padding: 0.6rem 1rem; border-bottom: 1px solid #ecf0f1; }
  tr:hover { background: #f1f2f6; }
  .pass { color: #27ae60; font-weight: bold; }
  .fail { color: #e74c3c; font-weight: bold; }
  .skip { color: #f39c12; }
  .bar { height: 8px; border-radius: 4px; background: #ecf0f1; margin-top: 0.5rem; }
  .bar-fill { height: 100%; border-radius: 4px; background: #27ae60; }
</style>
</head>
<body>
<h1>适配器测试报告</h1>
<p>${adapter_name} (${adapter_id})</p>

<div class="summary">
  <div class="card total"><div class="number">${total}</div><div class="label">总计</div></div>
  <div class="card pass"><div class="number">${passed}</div><div class="label">通过</div></div>
  <div class="card fail"><div class="number">${failed}</div><div class="label">失败</div></div>
  <div class="card skip"><div class="number">${skipped}</div><div class="label">跳过</div></div>
  <div class="card time"><div class="number">${duration_ms}</div><div class="label">耗时(ms)</div></div>
</div>

<div class="bar"><div class="bar-fill" style="width: ${pass_pct}%"></div></div>

<table>
<tr><th>状态</th><th>测试名</th><th>耗时</th><th>信息</th></tr>
${rows}
</table>
</body>
</html>"""
        )

        pass_pct = f"{self.passed / self.total * 100:.0f}" if self.total > 0 else "0"

        row_parts = []
        for r in self.results:
            if r.message == "跳过（适配器不适用）":
                status = '<span class="skip">⊘ SKIP</span>'
            elif r.passed:
                status = '<span class="pass">✓ PASS</span>'
            else:
                status = '<span class="fail">✗ FAIL</span>'
            row_parts.append(
                f"<tr><td>{status}</td><td>{r.test_name}</td>"
                f"<td>{r.duration_ms:.1f}ms</td><td>{r.message}</td></tr>"
            )

        return tmpl.substitute(
            adapter_name=self.adapter_name,
            adapter_id=self.adapter_id,
            total=self.total,
            passed=self.passed,
            failed=self.failed,
            skipped=self.skipped,
            duration_ms=f"{self.duration_ms:.0f}",
            pass_pct=pass_pct,
            rows="\n".join(row_parts),
        )


class AdapterTestSuite:
    """适配器测试套件"""

    def __init__(self, name: str = "default"):
        self.name = name
        self._tests: list[AdapterTestCase] = []

    def add_test(self, test: AdapterTestCase) -> None:
        """添加单个测试用例"""
        self._tests.append(test)

    def add_category(self, category: str, tests: list[AdapterTestCase]) -> None:
        """添加一组同分类的测试用例"""
        for t in tests:
            if t.category != category:
                t = AdapterTestCase(
                    name=t.name,
                    category=category,
                    code=t.code,
                    expected=t.expected,
                    description=t.description,
                    skip_adapters=t.skip_adapters,
                )
            self._tests.append(t)

    @property
    def categories(self) -> list[str]:
        """所有测试分类"""
        return sorted(set(t.category for t in self._tests))

    @property
    def test_count(self) -> int:
        return len(self._tests)

    def run(
        self,
        adapter: LanguageAdapter,
        categories: list[str] | None = None,
    ) -> AdapterTestReport:
        """对单个适配器运行测试套件

        Args:
            adapter: 语言适配器
            categories: 只运行指定分类，None 表示全部

        Returns:
            AdapterTestReport 测试报告
        """
        start = time.monotonic()
        report = AdapterTestReport(
            adapter_id=adapter.id,
            adapter_name=adapter.name,
        )

        for test in self._tests:
            if categories and test.category not in categories:
                continue
            result = test.run(adapter)
            report.results.append(result)
            report.total += 1

            if result.message == "跳过（适配器不适用）":
                report.skipped += 1
            elif result.passed:
                report.passed += 1
            else:
                report.failed += 1

        report.duration_ms = (time.monotonic() - start) * 1000
        return report

    def run_all(
        self,
        registry: LanguageRegistry,
        categories: list[str] | None = None,
    ) -> dict[str, AdapterTestReport]:
        """对所有注册适配器运行测试套件

        Args:
            registry: 语言注册中心
            categories: 只运行指定分类

        Returns:
            {adapter_id: AdapterTestReport}
        """
        reports: dict[str, AdapterTestReport] = {}
        for adapter in registry:
            reports[adapter.id] = self.run(adapter, categories=categories)
        return reports


# ============================================================
# 内置测试用例
# ============================================================

BUILTIN_TESTS: list[AdapterTestCase] = [
    # ---- execution 类 ----
    AdapterTestCase(
        name="empty_eval",
        category="execution",
        code="",
        expected={"success": True, "exit_code": 0},
        description="空代码执行应成功",
    ),
    AdapterTestCase(
        name="comment_eval",
        category="execution",
        code="# comment only",
        expected={"success": True, "exit_code": 0},
        description="仅注释代码执行应成功",
    ),
    AdapterTestCase(
        name="syntax_error_exec",
        category="execution",
        code="(((",
        expected={"success": False},
        description="语法错误代码执行应失败",
    ),
    # ---- diagnostics 类 ----
    AdapterTestCase(
        name="syntax_error_diag",
        category="diagnostics",
        code="(((",
        expected={"has_errors": True},
        description="语法错误应被诊断检测",
    ),
    AdapterTestCase(
        name="clean_code_diag",
        category="diagnostics",
        code="# clean code\n",
        expected={"has_errors": False},
        description="干净代码不应有错误诊断",
    ),
    # ---- completion 类 ----
    AdapterTestCase(
        name="keyword_completion",
        category="completion",
        code="",
        expected={"min_count": 1},
        description="空代码应返回关键字补全（至少1项）",
        skip_adapters=[],
    ),
    # ---- formatting 类 ----
    AdapterTestCase(
        name="format_clean",
        category="formatting",
        code="# clean\n打印(\"hi\")。\n",
        expected={"changed": False},
        description="已格式化代码不应被改变",
    ),
    AdapterTestCase(
        name="format_trailing_ws",
        category="formatting",
        code="# line   \n",
        expected={"changed": True},
        description="带尾随空格的代码应被格式化",
    ),
    # ---- syntax 类 ----
    AdapterTestCase(
        name="tokenize_empty",
        category="syntax",
        code="",
        expected={"token_count": 0},
        description="空代码词法分析应返回0个token",
    ),
]

# 适配器特定的 execution 测试（不同语言语法不同）
ADAPTER_SPECIFIC_TESTS: dict[str, list[AdapterTestCase]] = {
    "duan": [
        AdapterTestCase(
            name="duan_variable_decl",
            category="execution",
            code="设甲为三。",
            expected={"success": True},
            description="段言变量声明",
        ),
        AdapterTestCase(
            name="duan_function_def",
            category="execution",
            code="段落 加一(甲)。设甲为甲加一。返回甲。结束。",
            expected={"success": True},
            description="段言函数定义",
        ),
    ],
    "yan": [
        AdapterTestCase(
            name="yan_variable_decl",
            category="execution",
            code="定 甲 为 三",
            expected={"success": True},
            description="言变量声明",
        ),
    ],
}


def get_builtin_suite() -> AdapterTestSuite:
    """获取内置测试套件"""
    suite = AdapterTestSuite(name="builtin")
    for test in BUILTIN_TESTS:
        suite.add_test(test)
    return suite


# ============================================================
# 适配器兼容性验证器
# ============================================================


class AdapterCompatibilityValidator:
    """适配器兼容性验证器 — 验证适配器是否满足最低兼容性要求"""

    # 必需属性/方法
    _REQUIRED_PROPERTIES = ["name", "id", "version", "file_extensions"]
    _REQUIRED_METHODS = ["run", "eval"]

    def __init__(self, registry: LanguageRegistry):
        self.registry = registry

    def validate_adapter(self, adapter: LanguageAdapter) -> dict:
        """验证单个适配器

        检查：
        1. 必需方法是否实现
        2. 返回值类型是否正确
        3. 关键字列表是否非空
        4. 基本执行是否工作
        5. capabilities 声明是否与实际能力匹配

        Returns:
            {"valid": bool, "errors": [...], "warnings": [...]}
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ---- 1. 必需属性/方法是否实现 ----
        for prop in self._REQUIRED_PROPERTIES:
            if not hasattr(adapter, prop):
                errors.append(f"缺少必需属性: {prop}")
            else:
                # 检查属性是否可调用（有值）
                try:
                    val = getattr(adapter, prop)
                    if callable(val) and not isinstance(val, property):
                        # 方法形式的属性，检查是否是抽象方法
                        if getattr(val, "__isabstractmethod__", False):
                            errors.append(f"属性 {prop} 未实现（仍是抽象方法）")
                except Exception as e:
                    errors.append(f"属性 {prop} 访问失败: {e}")

        for method in self._REQUIRED_METHODS:
            if not hasattr(adapter, method):
                errors.append(f"缺少必需方法: {method}")
            else:
                m = getattr(adapter, method)
                if not callable(m):
                    errors.append(f"{method} 不是可调用方法")
                elif getattr(m, "__isabstractmethod__", False):
                    errors.append(f"方法 {method} 未实现（仍是抽象方法）")

        # ---- 2. 返回值类型检查 ----
        # 检查 name/id/version 是否返回正确类型
        try:
            name = adapter.name
            if not isinstance(name, str) or not name:
                errors.append(f"name 属性应返回非空字符串，实际: {type(name).__name__}")
        except Exception as e:
            errors.append(f"name 属性异常: {e}")

        try:
            lang_id = adapter.id
            if not isinstance(lang_id, str) or not lang_id:
                errors.append(f"id 属性应返回非空字符串，实际: {type(lang_id).__name__}")
        except Exception as e:
            errors.append(f"id 属性异常: {e}")

        try:
            version = adapter.version
            if not isinstance(version, str) or not version:
                errors.append(f"version 属性应返回非空字符串，实际: {type(version).__name__}")
        except Exception as e:
            errors.append(f"version 属性异常: {e}")

        try:
            exts = adapter.file_extensions
            if not isinstance(exts, list):
                errors.append(f"file_extensions 应返回列表，实际: {type(exts).__name__}")
            elif not exts:
                warnings.append("file_extensions 为空列表")
        except Exception as e:
            errors.append(f"file_extensions 属性异常: {e}")

        # 检查 run/eval 返回类型
        try:
            result = adapter.eval("")
            if not isinstance(result, ExecutionResult):
                errors.append(
                    f"eval() 应返回 ExecutionResult，实际: {type(result).__name__}"
                )
        except Exception:
            # eval("") 抛异常不一定错，可能不支持空代码
            pass

        # ---- 3. 关键字列表是否非空 ----
        try:
            keywords = adapter.keywords
            if not isinstance(keywords, list):
                warnings.append(f"keywords 应返回列表，实际: {type(keywords).__name__}")
            elif not keywords:
                warnings.append("关键字列表为空，将影响 LSP 补全能力")
        except Exception as e:
            warnings.append(f"关键字加载异常: {e}")

        # ---- 4. 基本执行是否工作 ----
        try:
            comment = adapter.comment_syntax or "#"
            test_code = f"{comment} compat check\n"
            result = adapter.eval(test_code)
            if result.exit_code == -2:
                # 命令未找到 — 后端不可用
                warnings.append(
                    f"基本执行不可用: {result.stderr.strip()}"
                )
            elif result.exit_code < 0:
                warnings.append(f"基本执行异常: exit_code={result.exit_code}")
        except Exception as e:
            warnings.append(f"基本执行异常: {e}")

        # ---- 5. capabilities 声明是否与实际能力匹配 ----
        try:
            caps = adapter.capabilities
            if not isinstance(caps, dict):
                errors.append(f"capabilities 应返回字典，实际: {type(caps).__name__}")
            else:
                # lsp 声明 vs 实际
                if caps.get("lsp") and not adapter.keywords:
                    warnings.append(
                        "capabilities.lsp=True 但 keywords 为空，LSP 功能受限"
                    )

                # 补全方法存在性
                if caps.get("lsp") and not hasattr(adapter, "complete"):
                    warnings.append(
                        "capabilities.lsp=True 但缺少 complete() 方法"
                    )

                # 包管理声明 vs 实际
                if caps.get("package_manager"):
                    if not hasattr(adapter, "list_packages") or not hasattr(
                        adapter, "install_package"
                    ):
                        warnings.append(
                            "capabilities.package_manager=True 但缺少包管理方法"
                        )
        except Exception as e:
            warnings.append(f"capabilities 检查异常: {e}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_all(self) -> dict[str, dict]:
        """验证所有已注册适配器"""
        results: dict[str, dict] = {}
        for adapter in self.registry:
            results[adapter.id] = self.validate_adapter(adapter)
        return results


# ============================================================
# 回归测试生成器
# ============================================================


class RegressionTestGenerator:
    """回归测试生成器 — 从执行结果或错误案例自动生成测试"""

    def __init__(self):
        self._counter = 0

    def generate_from_execution(
        self,
        adapter: LanguageAdapter,
        code_samples: list[str],
    ) -> list[AdapterTestCase]:
        """从执行结果生成回归测试

        执行每个代码样本，记录输出作为期望结果。
        """
        tests: list[AdapterTestCase] = []

        for code in code_samples:
            self._counter += 1
            result = adapter.eval(code)

            # 构建期望结果
            expected: dict = {
                "success": result.success,
                "exit_code": result.exit_code,
            }
            if result.stdout:
                expected["contains_stdout"] = result.stdout.strip()
            if result.stderr and not result.success:
                # 只记录失败的 stderr 关键片段
                expected["contains_stderr"] = result.stderr.strip()[:100]

            # 生成测试名
            # 从代码中提取第一行作为名称提示
            first_line = code.strip().split("\n")[0][:20] if code.strip() else "empty"
            name = f"regression_{adapter.id}_{self._counter}_{first_line}"

            tests.append(
                AdapterTestCase(
                    name=name,
                    category="execution",
                    code=code,
                    expected=expected,
                    description="自动生成的回归测试（来自执行结果）",
                )
            )

        return tests

    def generate_from_errors(
        self,
        adapter: LanguageAdapter,
        error_cases: list[dict],
    ) -> list[AdapterTestCase]:
        """从错误案例生成回归测试

        error_cases 格式:
        [
            {"code": "...", "error_type": "syntax"|"runtime", "message": "..."},
            ...
        ]
        """
        tests: list[AdapterTestCase] = []

        for case in error_cases:
            self._counter += 1
            code = case.get("code", "")
            error_type = case.get("error_type", "runtime")
            err_msg = case.get("message", "")

            if error_type == "syntax":
                # 语法错误：应被诊断检测到
                expected = {"has_errors": True}
                category = "diagnostics"
            else:
                # 运行时错误：执行应失败
                expected = {"success": False}
                if err_msg:
                    expected["contains_stderr"] = err_msg[:100]
                category = "execution"

            name = f"regression_error_{adapter.id}_{self._counter}"
            tests.append(
                AdapterTestCase(
                    name=name,
                    category=category,
                    code=code,
                    expected=expected,
                    description=f"自动生成的错误回归测试: {err_msg[:50]}" if err_msg else "自动生成的错误回归测试",
                )
            )

        return tests

    def save_suite(self, suite: AdapterTestSuite, path: Path) -> None:
        """将测试套件序列化为 JSON"""
        data = {
            "name": suite.name,
            "tests": [
                {
                    "name": t.name,
                    "category": t.category,
                    "code": t.code,
                    "expected": t.expected,
                    "description": t.description,
                    "skip_adapters": t.skip_adapters,
                }
                for t in suite._tests
            ],
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_suite(self, path: Path) -> AdapterTestSuite:
        """从 JSON 反序列化测试套件"""
        data = json.loads(path.read_text(encoding="utf-8"))
        suite = AdapterTestSuite(name=data.get("name", "loaded"))
        for t_data in data.get("tests", []):
            suite.add_test(
                AdapterTestCase(
                    name=t_data["name"],
                    category=t_data["category"],
                    code=t_data["code"],
                    expected=t_data["expected"],
                    description=t_data.get("description", ""),
                    skip_adapters=t_data.get("skip_adapters", []),
                )
            )
        return suite
