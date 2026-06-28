"""适配器测试框架 — 统一的适配器功能验证与回归测试

核心组件：
1. AdapterTestCase  — 单个测试用例，按 category 调用不同适配器方法
2. AdapterTestSuite — 测试套件，管理并运行一组测试用例
3. get_builtin_suite — 获取内置测试套件

拆分模块：
- yanpub.core.adapter_test_builtin — BUILTIN_TESTS, ADAPTER_SPECIFIC_TESTS 数据常量
- yanpub.core.adapter_test_report — AdapterTestReport 测试报告
- yanpub.core.adapter_compat — AdapterCompatibilityValidator 兼容性验证器
- yanpub.core.adapter_regression — RegressionTestGenerator 回归测试生成器

用法：
  yanpub adapter-test              # 运行所有适配器的测试套件
  yanpub adapter-test duan         # 运行指定适配器的测试
  yanpub adapter-validate          # 验证所有适配器兼容性
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from yanpub.core.adapter.adapter import (
    ExecutionResult,
    LanguageAdapter,
)
from yanpub.core.adapter.registry import LanguageRegistry

# 延迟 re-export，保持向后兼容
if TYPE_CHECKING:
    from yanpub.core.adapter_test_report import AdapterTestReport as AdapterTestReport
    from yanpub.core.adapter_compat import AdapterCompatibilityValidator as AdapterCompatibilityValidator
    from yanpub.core.adapter_regression import RegressionTestGenerator as RegressionTestGenerator


__all__ = [
    "AdapterTestResult",
    "AdapterTestCase",
    "AdapterTestSuite",
    "get_builtin_suite",
    "AdapterTestReport",
    "AdapterCompatibilityValidator",
    "RegressionTestGenerator",
    "BUILTIN_TESTS",
    "ADAPTER_SPECIFIC_TESTS",
]


# ---- 延迟 re-export 避免循环依赖 ----


def __getattr__(name: str):
    """从子模块延迟 re-export，保持向后兼容"""
    if name == "AdapterTestReport":
        from yanpub.core import adapter_test_report

        return getattr(adapter_test_report, name)
    if name == "AdapterCompatibilityValidator":
        from yanpub.core import adapter_compat

        return getattr(adapter_compat, name)
    if name == "RegressionTestGenerator":
        from yanpub.core import adapter_regression

        return getattr(adapter_regression, name)
    if name in ("BUILTIN_TESTS", "ADAPTER_SPECIFIC_TESTS"):
        from yanpub.core import adapter_test_builtin

        return getattr(adapter_test_builtin, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    category: (
        str  # "syntax" | "execution" | "completion" | "diagnostics" | "formatting" | "navigation"
    )
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
                {"label": i.label, "kind": i.kind, "insert_text": i.insert_text} for i in items
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
                    mismatches.append(f"count={count} < min_count={expected_val}")
            elif key == "max_count":
                # 最大数量检查
                count = actual.get("count", 0)
                if count > expected_val:
                    mismatches.append(f"count={count} > max_count={expected_val}")
            elif key == "contains_stdout":
                stdout = actual.get("stdout", "")
                if expected_val not in stdout:
                    mismatches.append(f"stdout 不包含 '{expected_val}'")
            elif key == "contains_stderr":
                stderr = actual.get("stderr", "")
                if expected_val not in stderr:
                    mismatches.append(f"stderr 不包含 '{expected_val}'")
            elif actual_val != expected_val:
                mismatches.append(f"{key}: 期望={expected_val}, 实际={actual_val}")

        if mismatches:
            return False, "; ".join(mismatches)
        return True, "通过"


# ============================================================
# 测试套件
# ============================================================


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
    ) -> "AdapterTestReport":
        """对单个适配器运行测试套件

        Args:
            adapter: 语言适配器
            categories: 只运行指定分类，None 表示全部

        Returns:
            AdapterTestReport 测试报告
        """
        from yanpub.core.adapter_test_report import AdapterTestReport

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
    ) -> dict[str, "AdapterTestReport"]:
        """对所有注册适配器运行测试套件

        Args:
            registry: 语言注册中心
            categories: 只运行指定分类

        Returns:
            {adapter_id: AdapterTestReport}
        """
        reports: dict[str, "AdapterTestReport"] = {}
        for adapter in registry:
            reports[adapter.id] = self.run(adapter, categories=categories)
        return reports


def get_builtin_suite() -> AdapterTestSuite:
    """获取内置测试套件"""
    from yanpub.core.adapter_test_builtin import BUILTIN_TESTS

    suite = AdapterTestSuite(name="builtin")
    for test in BUILTIN_TESTS:
        suite.add_test(test)
    return suite
