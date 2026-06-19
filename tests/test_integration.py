"""端到端集成测试 — 验证 Phase 1 核心功能"""

import os
import sys

import pytest

# Windows 终端 UTF-8 支持
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from yanpub.core.registry import get_registry
from yanpub.adapters.duan.adapter import DuanAdapter

from conftest import skip_if_no_backend


# ---- 段言适配器集成测试 ----

class TestDuanAdapterIntegration:
    """段言适配器与真实后端的集成测试"""

    @pytest.fixture
    def duan(self):
        return DuanAdapter()

    def test_metadata(self, duan):
        assert duan.name == "段言"
        assert duan.id == "duan"
        assert duan.version == "1.3.8"
        assert ".duan" in duan.file_extensions
        assert ".段" in duan.file_extensions

    def test_keywords_loaded(self, duan):
        """验证从段言项目动态加载了关键字"""
        assert len(duan.keywords) > 50  # keywords.py 中有 100+ 个
        assert "设" in duan.keywords
        assert "段落" in duan.keywords
        assert "返回" in duan.keywords
        assert "打印" in duan.keywords

    def test_run_hello(self, duan):
        """运行 hello.duan 示例文件"""
        hello_file = r"G:\dumategithub\duan\examples\hello.duan"
        if not os.path.exists(hello_file):
            pytest.skip("段言示例文件不存在")

        result = duan.run(hello_file)
        assert result.exit_code == 0
        assert "你好，世界" in result.stdout

    def test_eval_simple(self, duan):
        """执行简单代码片段"""
        skip_if_no_backend("duan")
        result = duan.eval('打印("yanpub test")。')
        assert result.exit_code == 0
        assert "yanpub test" in result.stdout

    def test_eval_arithmetic(self, duan):
        """执行算术运算"""
        skip_if_no_backend("duan")
        result = duan.eval("设甲为三。打印(甲)。")
        assert result.exit_code == 0
        assert "3" in result.stdout

    def test_eval_error(self, duan):
        """执行有语法错误的代码"""
        skip_if_no_backend("duan")
        result = duan.eval("这段代码有错误")
        assert result.exit_code != 0

    def test_repl_properties(self, duan):
        assert duan.repl_prompt == "段言> "
        assert "段言" in duan.repl_welcome
        assert "1.3.8" in duan.repl_welcome

    def test_capabilities(self, duan):
        caps = duan.capabilities
        assert caps["repl"] is True
        assert caps["lsp"] is True  # 有关键字就能提供基本 LSP

    def test_comment_syntax(self, duan):
        assert duan.comment_syntax == "#"


# ---- 注册中心集成测试 ----

class TestRegistryIntegration:
    """注册中心自动发现与加载集成测试"""

    def test_auto_discover(self):
        registry = get_registry()
        assert len(registry) >= 3  # duan, moyan, yan

    def test_duan_registered(self):
        registry = get_registry()
        assert "duan" in registry

    def test_yan_registered(self):
        registry = get_registry()
        assert "yan" in registry

    def test_moyan_registered(self):
        registry = get_registry()
        assert "moyan" in registry

    def test_get_duan_adapter(self):
        registry = get_registry()
        adapter = registry.get("duan")
        assert adapter is not None
        assert adapter.name == "段言"

    def test_list_languages(self):
        registry = get_registry()
        langs = registry.list_languages()
        ids = [lang["id"] for lang in langs]
        assert "duan" in ids
        assert "yan" in ids
        assert "moyan" in ids


# ---- CLI 端到端测试 ----

class TestCLIIntegration:
    """CLI 命令端到端测试"""

    def test_run_duan_hello(self):
        """验证 yanpub run duan <file> 工作正常"""
        hello_file = r"G:\dumategithub\duan\examples\hello.duan"
        if not os.path.exists(hello_file):
            pytest.skip("段言示例文件不存在")

        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "yanpub.cli", "run", "duan", hello_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0
        assert "你好，世界" in result.stdout
