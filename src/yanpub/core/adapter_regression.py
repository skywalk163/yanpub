"""回归测试生成器 — 从执行结果或错误案例自动生成测试

RegressionTestGenerator — 自动化回归测试
"""

from __future__ import annotations

import json
from pathlib import Path

from yanpub.core.adapter.adapter import LanguageAdapter
from yanpub.core.adapter_test import AdapterTestCase, AdapterTestSuite


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
                    description=f"自动生成的错误回归测试: {err_msg[:50]}"
                    if err_msg
                    else "自动生成的错误回归测试",
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
