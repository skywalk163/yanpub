"""适配器测试框架测试 — adapter_test.py 的单元测试"""

import json
import tempfile
from pathlib import Path


from yanpub.core.adapter.adapter import ExecutionResult, LanguageAdapter, SubprocessAdapter
from yanpub.core.adapter.registry import LanguageRegistry
from yanpub.core.adapter_test import (
    AdapterTestCase,
    AdapterTestResult,
    AdapterTestSuite,
    AdapterTestReport,
    AdapterCompatibilityValidator,
    RegressionTestGenerator,
    BUILTIN_TESTS,
    get_builtin_suite,
)


# ---- 测试用简单适配器 ----


class MockAdapter(SubprocessAdapter):
    """测试用适配器 — 覆盖 eval/run 避免依赖真实子进程"""

    def __init__(self):
        super().__init__(
            name="测试语言",
            lang_id="mock",
            version="0.0.1",
            extensions=[".mock"],
            run_command=["echo", "mock"],
            eval_command=["echo", "mock"],
            keywords=["定义", "返回", "若", "则"],
            primary_color="#000000",
        )

    def eval(self, code: str) -> ExecutionResult:
        return ExecutionResult(stdout="mock\n", exit_code=0, duration_ms=1.0)

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        return ExecutionResult(stdout="mock\n", exit_code=0, duration_ms=1.0)


class EmptyKeywordsAdapter(SubprocessAdapter):
    """无关键字的适配器 — 覆盖 eval/run 避免依赖真实子进程"""

    def __init__(self):
        super().__init__(
            name="空语言",
            lang_id="empty_kw",
            version="0.0.1",
            extensions=[".ekw"],
            run_command=["echo", "ekw"],
            eval_command=["echo", "ekw"],
            keywords=[],
        )

    def eval(self, code: str) -> ExecutionResult:
        return ExecutionResult(stdout="ekw\n", exit_code=0, duration_ms=1.0)

    def run(self, file_path: str, args: list[str] | None = None) -> ExecutionResult:
        return ExecutionResult(stdout="ekw\n", exit_code=0, duration_ms=1.0)


# ---- AdapterTestCase 测试 ----


class TestAdapterTestCase:
    def test_execution_pass(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_exec",
            category="execution",
            code="",
            expected={"success": True, "exit_code": 0},
        )
        result = tc.run(adapter)
        assert result.passed is True
        assert result.test_name == "test_exec"
        assert result.adapter_id == "mock"
        assert result.duration_ms >= 0

    def test_execution_fail(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_exec_fail",
            category="execution",
            code="",
            expected={"success": False},
        )
        result = tc.run(adapter)
        # MockAdapter echo "mock" returns success=True, so this should fail
        assert result.passed is False

    def test_skip_adapters(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_skip",
            category="execution",
            code="",
            expected={"success": True},
            skip_adapters=["mock"],
        )
        result = tc.run(adapter)
        assert result.passed is True
        assert "跳过" in result.message

    def test_diagnostics_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_diag",
            category="diagnostics",
            code="(((",
            expected={"has_errors": True},
        )
        result = tc.run(adapter)
        assert result.test_name == "test_diag"
        # MockAdapter echo "mock" succeeds, so diagnostics should be clean
        assert "has_errors" in result.actual

    def test_completion_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_comp",
            category="completion",
            code="",
            expected={"min_count": 1},
        )
        result = tc.run(adapter)
        assert result.passed is True
        assert result.actual["count"] == 4  # MockAdapter has 4 keywords

    def test_formatting_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_fmt",
            category="formatting",
            code="# clean\n",
            expected={"changed": False},
        )
        result = tc.run(adapter)
        assert result.passed is True

    def test_syntax_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_syntax",
            category="syntax",
            code="",
            expected={"token_count": 0},
        )
        result = tc.run(adapter)
        assert result.passed is True

    def test_unknown_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_unknown",
            category="nonexistent",
            code="",
            expected={},
        )
        result = tc.run(adapter)
        assert result.passed is False
        assert "未知测试分类" in result.message

    def test_contains_stdout(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_stdout",
            category="execution",
            code="",
            expected={"success": True, "contains_stdout": "mock"},
        )
        result = tc.run(adapter)
        assert result.passed is True

    def test_contains_stderr(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_stderr",
            category="execution",
            code="",
            expected={"contains_stderr": "some_error"},
        )
        result = tc.run(adapter)
        assert result.passed is False  # mock echo doesn't produce that stderr

    def test_min_count_max_count(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_count",
            category="completion",
            code="",
            expected={"min_count": 2, "max_count": 10},
        )
        result = tc.run(adapter)
        assert result.passed is True

    def test_navigation_category(self):
        adapter = MockAdapter()
        tc = AdapterTestCase(
            name="test_nav",
            category="navigation",
            code="",
            expected={"has_definition": False},
        )
        result = tc.run(adapter)
        assert result.passed is True


# ---- AdapterTestResult 测试 ----


class TestAdapterTestResult:
    def test_to_dict(self):
        r = AdapterTestResult(
            test_name="test1",
            adapter_id="mock",
            passed=True,
            message="通过",
            duration_ms=10.5,
        )
        d = r.to_dict()
        assert d["test_name"] == "test1"
        assert d["passed"] is True
        assert d["duration_ms"] == 10.5


# ---- AdapterTestSuite 测试 ----


class TestAdapterTestSuite:
    def test_add_test(self):
        suite = AdapterTestSuite(name="test_suite")
        tc = AdapterTestCase(
            name="t1",
            category="execution",
            code="",
            expected={"success": True},
        )
        suite.add_test(tc)
        assert suite.test_count == 1

    def test_add_category(self):
        suite = AdapterTestSuite(name="test_suite")
        tests = [
            AdapterTestCase(
                name="t1",
                category="execution",
                code="",
                expected={"success": True},
            ),
            AdapterTestCase(
                name="t2",
                category="execution",
                code="",
                expected={"success": True},
            ),
        ]
        suite.add_category("execution", tests)
        assert suite.test_count == 2
        assert "execution" in suite.categories

    def test_categories(self):
        suite = AdapterTestSuite()
        suite.add_test(
            AdapterTestCase(
                name="t1", category="execution", code="", expected={}
            )
        )
        suite.add_test(
            AdapterTestCase(
                name="t2", category="diagnostics", code="", expected={}
            )
        )
        assert suite.categories == ["diagnostics", "execution"]

    def test_run_single_adapter(self):
        suite = AdapterTestSuite()
        suite.add_test(
            AdapterTestCase(
                name="t1",
                category="execution",
                code="",
                expected={"success": True, "exit_code": 0},
            )
        )
        adapter = MockAdapter()
        report = suite.run(adapter)
        assert report.adapter_id == "mock"
        assert report.total == 1
        assert report.passed == 1
        assert report.failed == 0

    def test_run_with_categories_filter(self):
        suite = AdapterTestSuite()
        suite.add_test(
            AdapterTestCase(
                name="t1", category="execution", code="", expected={"success": True}
            )
        )
        suite.add_test(
            AdapterTestCase(
                name="t2", category="diagnostics", code="", expected={"has_errors": False}
            )
        )
        adapter = MockAdapter()
        report = suite.run(adapter, categories=["execution"])
        assert report.total == 1
        assert report.results[0].test_name == "t1"

    def test_run_all(self):
        registry = LanguageRegistry()
        registry.register(MockAdapter())
        suite = AdapterTestSuite()
        suite.add_test(
            AdapterTestCase(
                name="t1",
                category="execution",
                code="",
                expected={"success": True, "exit_code": 0},
            )
        )
        reports = suite.run_all(registry)
        assert "mock" in reports
        assert reports["mock"].passed == 1


# ---- AdapterTestReport 测试 ----


class TestAdapterTestReport:
    def _make_report(self):
        return AdapterTestReport(
            adapter_id="mock",
            adapter_name="测试语言",
            total=3,
            passed=2,
            failed=1,
            skipped=0,
            results=[
                AdapterTestResult(
                    test_name="test1",
                    adapter_id="mock",
                    passed=True,
                    message="通过",
                ),
                AdapterTestResult(
                    test_name="test2",
                    adapter_id="mock",
                    passed=True,
                    message="通过",
                ),
                AdapterTestResult(
                    test_name="test3",
                    adapter_id="mock",
                    passed=False,
                    message="exit_code: 期望=0, 实际=1",
                ),
            ],
            duration_ms=100.0,
        )

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["adapter_id"] == "mock"
        assert d["total"] == 3
        assert d["passed"] == 2
        assert d["failed"] == 1
        assert len(d["results"]) == 3

    def test_to_table(self):
        report = self._make_report()
        table = report.to_table()
        assert "测试语言" in table
        assert "总计: 3" in table
        assert "通过: 2" in table
        assert "失败: 1" in table

    def test_to_html(self):
        report = self._make_report()
        html = report.to_html()
        assert "<!DOCTYPE html>" in html
        assert "测试语言" in html
        assert "mock" in html
        assert "PASS" in html
        assert "FAIL" in html

    def test_empty_report(self):
        report = AdapterTestReport(
            adapter_id="empty",
            adapter_name="空",
        )
        table = report.to_table()
        assert "无测试结果" in table
        html = report.to_html()
        assert "0" in html


# ---- AdapterCompatibilityValidator 测试 ----


class TestAdapterCompatibilityValidator:
    def test_valid_adapter(self):
        registry = LanguageRegistry()
        registry.register(MockAdapter())
        validator = AdapterCompatibilityValidator(registry)
        result = validator.validate_adapter(MockAdapter())
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_empty_keywords_warning(self):
        registry = LanguageRegistry()
        registry.register(EmptyKeywordsAdapter())
        validator = AdapterCompatibilityValidator(registry)
        result = validator.validate_adapter(EmptyKeywordsAdapter())
        # Empty keywords should generate a warning, not an error
        assert any("关键字" in w for w in result["warnings"])

    def test_validate_all(self):
        registry = LanguageRegistry()
        registry.register(MockAdapter())
        registry.register(EmptyKeywordsAdapter())
        validator = AdapterCompatibilityValidator(registry)
        results = validator.validate_all()
        assert "mock" in results
        assert "empty_kw" in results

    def test_capabilities_check(self):
        adapter = MockAdapter()
        registry = LanguageRegistry()
        registry.register(adapter)
        validator = AdapterCompatibilityValidator(registry)
        result = validator.validate_adapter(adapter)
        # MockAdapter has keywords and capabilities
        assert result["valid"] is True


# ---- RegressionTestGenerator 测试 ----


class TestRegressionTestGenerator:
    def test_generate_from_execution(self):
        adapter = MockAdapter()
        gen = RegressionTestGenerator()
        tests = gen.generate_from_execution(
            adapter,
            code_samples=["# sample 1\n", "# sample 2\n"],
        )
        assert len(tests) == 2
        assert all(t.category == "execution" for t in tests)
        assert all("regression_mock" in t.name for t in tests)

    def test_generate_from_errors(self):
        adapter = MockAdapter()
        gen = RegressionTestGenerator()
        tests = gen.generate_from_errors(
            adapter,
            error_cases=[
                {"code": "(((", "error_type": "syntax", "message": "语法错误"},
                {"code": "1/0", "error_type": "runtime", "message": "除零错误"},
            ],
        )
        assert len(tests) == 2
        # syntax error → diagnostics category
        assert tests[0].category == "diagnostics"
        assert tests[0].expected["has_errors"] is True
        # runtime error → execution category
        assert tests[1].category == "execution"
        assert tests[1].expected["success"] is False

    def test_save_and_load_suite(self):
        suite = AdapterTestSuite(name="regression_test")
        suite.add_test(
            AdapterTestCase(
                name="t1",
                category="execution",
                code="设甲为三。",
                expected={"success": True},
                description="变量声明",
                skip_adapters=["hanyu", "mingdao"],
            )
        )

        gen = RegressionTestGenerator()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suite.json"
            gen.save_suite(suite, path)

            # Verify JSON is valid
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["name"] == "regression_test"
            assert len(data["tests"]) == 1
            assert data["tests"][0]["skip_adapters"] == ["hanyu", "mingdao"]

            # Load back
            loaded = gen.load_suite(path)
            assert loaded.name == "regression_test"
            assert loaded.test_count == 1
            assert loaded._tests[0].code == "设甲为三。"
            assert loaded._tests[0].skip_adapters == ["hanyu", "mingdao"]


# ---- 内置测试套件 ----


class TestBuiltinSuite:
    def test_builtin_tests_exist(self):
        assert len(BUILTIN_TESTS) > 0
        categories = set(t.category for t in BUILTIN_TESTS)
        assert "execution" in categories
        assert "diagnostics" in categories

    def test_get_builtin_suite(self):
        suite = get_builtin_suite()
        assert suite.name == "builtin"
        assert suite.test_count > 0

    def test_builtin_suite_run(self):
        adapter = MockAdapter()
        suite = get_builtin_suite()
        report = suite.run(adapter)
        assert report.total > 0
        assert report.adapter_id == "mock"
