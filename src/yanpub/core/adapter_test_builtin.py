"""内置测试用例数据常量

BUILTIN_TESTS — 通用适配器测试用例列表
ADAPTER_SPECIFIC_TESTS — 适配器特定测试用例字典
"""

from __future__ import annotations

from yanpub.core.adapter_test import AdapterTestCase

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
        code='# clean\n打印("hi")。\n',
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
