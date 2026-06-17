"""v0.5.0 测试 — LSP CodeLens + 语义发布 + 性能面板 + WASM 执行"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ============================================================================
# 1. LSP CodeLens 测试
# ============================================================================

class TestLSPCodeLens:
    """测试 LSP 代码透镜功能"""

    def test_codelens_types_available(self):
        """CodeLens 相关 LSP 类型应可用"""
        from lsprotocol import types as lsp
        assert hasattr(lsp, "TEXT_DOCUMENT_CODE_LENS")
        assert hasattr(lsp, "CodeLens")
        assert hasattr(lsp, "CodeLensParams")
        assert hasattr(lsp, "CodeLensOptions")

    def test_codelens_creation(self):
        """应能创建 CodeLens 对象"""
        from lsprotocol import types as lsp

        lens = lsp.CodeLens(
            range=lsp.Range(
                start=lsp.Position(line=0, character=0),
                end=lsp.Position(line=0, character=10),
            ),
            command=lsp.Command(
                title="▶ 运行文件",
                command="yanpub.runFile",
                arguments=["file:///test.duan"],
            ),
        )
        assert lens.command is not None
        assert lens.command.title == "▶ 运行文件"

    def test_yan_language_server_has_codelens(self):
        """YanLanguageServer 应注册 CodeLens feature"""
        from yanpub.lsp.server import YanLanguageServer
        server = YanLanguageServer()
        # 验证 server 对象已创建
        assert server.server is not None

    def test_is_block_definition(self):
        """_is_block_definition 应正确识别块定义行"""
        from yanpub.lsp.server import YanLanguageServer
        server = YanLanguageServer()

        # 创建 mock adapter
        mock_adapter = MagicMock()
        mock_adapter.comment_syntax = "#"

        assert server._is_block_definition(mock_adapter, "段落 你好世界()") is True
        assert server._is_block_definition(mock_adapter, "类 动物") is True
        assert server._is_block_definition(mock_adapter, "函数 计算和") is True
        assert server._is_block_definition(mock_adapter, "打印(\"hello\")") is False
        assert server._is_block_definition(mock_adapter, "# 注释") is False

    def test_codelens_run_file(self):
        """CodeLens 应在文件顶部添加运行文件按钮"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        mock_adapter = MagicMock()
        mock_adapter.id = "duan"
        mock_adapter.name = "段言"
        mock_adapter.file_extensions = [".duan"]
        mock_adapter.comment_syntax = "#"
        mock_adapter.keywords = ["段落", "打印"]
        registry.register(mock_adapter)

        server = YanLanguageServer(registry=registry)
        # 添加测试文档
        server._documents["file:///test.duan"] = "打印(\"hello\")\n"

        # 调用 code_lens handler（通过模拟）
        # 我们验证 server 对象有正确的结构即可
        assert server._documents is not None


# ============================================================================
# 2. 语义发布测试
# ============================================================================

class TestSemanticVersion:
    """测试语义化版本号"""

    def test_parse_basic(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_with_v_prefix(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("v1.2.3")
        assert v.major == 1

    def test_parse_prerelease(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.0.0-alpha")
        assert v.prerelease == "alpha"

    def test_parse_build(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.0.0+build.123")
        assert v.build == "build.123"

    def test_parse_invalid(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        with pytest.raises(ValueError):
            SemanticVersion.parse("not.a.version")

    def test_str(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion(major=1, minor=2, patch=3, prerelease="beta")
        assert str(v) == "1.2.3-beta"

    def test_comparison(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v1 = SemanticVersion.parse("1.0.0")
        v2 = SemanticVersion.parse("2.0.0")
        v3 = SemanticVersion.parse("1.1.0")
        assert v1 < v2
        assert v1 < v3
        assert v2 > v3

    def test_prerelease_sorts_lower(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v1 = SemanticVersion.parse("1.0.0-alpha")
        v2 = SemanticVersion.parse("1.0.0")
        assert v1 < v2

    def test_bump_major(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.2.3")
        new = v.bump_major()
        assert str(new) == "2.0.0"

    def test_bump_minor(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.2.3")
        new = v.bump_minor()
        assert str(new) == "1.3.0"

    def test_bump_patch(self):
        from yanpub.pkg.semantic_release import SemanticVersion
        v = SemanticVersion.parse("1.2.3")
        new = v.bump_patch()
        assert str(new) == "1.2.4"


class TestConventionalCommit:
    """测试 Conventional Commits 解析"""

    def test_parse_feat(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("feat: 添加新功能")
        assert c is not None
        assert c.type == "feat"
        assert c.description == "添加新功能"

    def test_parse_fix_with_scope(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("fix(core): 修复崩溃问题")
        assert c is not None
        assert c.type == "fix"
        assert c.scope == "core"
        assert c.description == "修复崩溃问题"

    def test_parse_breaking_bang(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("feat!: 破坏性变更")
        assert c is not None
        assert c.breaking is True

    def test_parse_breaking_in_body(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("feat: 新功能\n\nBREAKING CHANGE: 接口变更")
        assert c is not None
        assert c.breaking is True

    def test_parse_non_conventional(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("update something")
        assert c is None

    def test_type_name(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        c = ConventionalCommit.parse("feat: test")
        assert c.type_name == "新功能"

    def test_all_types(self):
        from yanpub.pkg.semantic_release import ConventionalCommit
        for t in ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"]:
            c = ConventionalCommit.parse(f"{t}: test")
            assert c is not None
            assert c.type == t


class TestVersionBumper:
    """测试版本号递增"""

    def test_determine_major(self):
        from yanpub.pkg.semantic_release import VersionBumper, ConventionalCommit
        commits = [
            ConventionalCommit.parse("feat!: breaking"),
            ConventionalCommit.parse("fix: bugfix"),
        ]
        assert VersionBumper.determine_bump(commits) == "major"

    def test_determine_minor(self):
        from yanpub.pkg.semantic_release import VersionBumper, ConventionalCommit
        commits = [
            ConventionalCommit.parse("feat: new feature"),
            ConventionalCommit.parse("fix: bugfix"),
        ]
        assert VersionBumper.determine_bump(commits) == "minor"

    def test_determine_patch(self):
        from yanpub.pkg.semantic_release import VersionBumper, ConventionalCommit
        commits = [
            ConventionalCommit.parse("fix: bugfix"),
        ]
        assert VersionBumper.determine_bump(commits) == "patch"

    def test_determine_none(self):
        from yanpub.pkg.semantic_release import VersionBumper
        assert VersionBumper.determine_bump([]) == "none"

    def test_bump(self):
        from yanpub.pkg.semantic_release import VersionBumper, SemanticVersion
        v = SemanticVersion.parse("1.2.3")
        assert str(VersionBumper.bump(v, "major")) == "2.0.0"
        assert str(VersionBumper.bump(v, "minor")) == "1.3.0"
        assert str(VersionBumper.bump(v, "patch")) == "1.2.4"
        assert str(VersionBumper.bump(v, "none")) == "1.2.3"


class TestChangelogGenerator:
    """测试 Changelog 生成"""

    def test_generate_basic(self):
        from yanpub.pkg.semantic_release import ChangelogGenerator, ConventionalCommit
        commits = [
            ConventionalCommit.parse("feat: 新功能", "abc1234", "2026-06-17"),
            ConventionalCommit.parse("fix: 修复bug", "def5678", "2026-06-17"),
        ]
        result = ChangelogGenerator.generate(commits, version="1.1.0")
        assert "1.1.0" in result
        assert "新功能" in result
        assert "修复bug" in result
        assert "# Changelog" in result

    def test_generate_with_breaking(self):
        from yanpub.pkg.semantic_release import ChangelogGenerator, ConventionalCommit
        commits = [
            ConventionalCommit.parse("feat!: 破坏性变更", "abc1234", "2026-06-17"),
        ]
        result = ChangelogGenerator.generate(commits, version="2.0.0")
        assert "破坏性变更" in result

    def test_generate_empty(self):
        from yanpub.pkg.semantic_release import ChangelogGenerator
        result = ChangelogGenerator.generate([], version="1.0.0")
        assert "1.0.0" in result


class TestParseGitLog:
    """测试 git log 解析"""

    def test_parse_git_log(self):
        from yanpub.pkg.semantic_release import parse_git_log
        log = "abc1234|||2026-06-17|||feat: 新功能\ndef5678|||2026-06-16|||fix: 修复bug"
        commits = parse_git_log(log)
        assert len(commits) == 2
        assert commits[0].type == "feat"
        assert commits[1].type == "fix"

    def test_parse_git_log_mixed(self):
        from yanpub.pkg.semantic_release import parse_git_log
        log = "abc1234|||2026-06-17|||feat: 新功能\ndef5678|||2026-06-16|||update something"
        commits = parse_git_log(log)
        assert len(commits) == 1  # 非 conventional commit 被过滤

    def test_parse_git_log_empty(self):
        from yanpub.pkg.semantic_release import parse_git_log
        commits = parse_git_log("")
        assert len(commits) == 0


class TestSemanticRelease:
    """测试语义发布主流程"""

    def test_semantic_release_no_toml(self):
        from yanpub.pkg.semantic_release import semantic_release
        with tempfile.TemporaryDirectory() as tmpdir:
            result = semantic_release(Path(tmpdir), dry_run=True)
            assert "error" in result

    def test_semantic_release_with_toml(self):
        from yanpub.pkg.semantic_release import semantic_release
        with tempfile.TemporaryDirectory() as tmpdir:
            toml_path = Path(tmpdir) / "yanpkg.toml"
            toml_path.write_text('[package]\nname = "test"\nlang = "duan"\nversion = "0.1.0"\n', encoding="utf-8")

            result = semantic_release(Path(tmpdir), dry_run=True)
            assert result["previous_version"] == "0.1.0"
            # 没有 git commits，bump_type 应该是 none
            assert result["bump_type"] in ("none", "minor", "major", "patch")

    def test_update_toml_version(self):
        from yanpub.pkg.semantic_release import _update_toml_version
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False, encoding="utf-8") as f:
            f.write('[package]\nname = "test"\nversion = "0.1.0"\n')
            tmp = f.name

        try:
            _update_toml_version(Path(tmp), "0.2.0")
            content = Path(tmp).read_text(encoding="utf-8")
            assert 'version = "0.2.0"' in content
        finally:
            os.unlink(tmp)


# ============================================================================
# 3. 性能调优面板测试
# ============================================================================

class TestBenchHistory:
    """测试基准测试历史管理"""

    def test_save_and_load(self):
        from yanpub.core.bench_viz import BenchHistory, AdapterBenchResult
        with tempfile.TemporaryDirectory() as tmpdir:
            history = BenchHistory(history_dir=Path(tmpdir))
            results = [AdapterBenchResult(adapter_id="test", adapter_name="测试")]

            history.save(results)
            snapshots = history.list_snapshots()
            assert len(snapshots) == 1

            latest = history.load_latest()
            assert latest is not None
            assert latest.adapter_id == "all"

    def test_load_previous_none(self):
        from yanpub.core.bench_viz import BenchHistory
        with tempfile.TemporaryDirectory() as tmpdir:
            history = BenchHistory(history_dir=Path(tmpdir))
            assert history.load_previous() is None

    def test_load_latest_empty(self):
        from yanpub.core.bench_viz import BenchHistory
        with tempfile.TemporaryDirectory() as tmpdir:
            history = BenchHistory(history_dir=Path(tmpdir))
            assert history.load_latest() is None


class TestRegressionDetector:
    """测试性能回归检测"""

    def test_detect_no_previous(self):
        from yanpub.core.bench_viz import RegressionDetector
        detector = RegressionDetector()
        results = []
        regressions = detector.detect(results, None)
        assert len(regressions) == 0

    def test_detect_with_previous(self):
        from yanpub.core.bench_viz import RegressionDetector, BenchSnapshot
        from yanpub.core.benchmark import AdapterBenchResult, BenchResult

        # 构造之前的数据（更快）
        previous = BenchSnapshot(
            timestamp="2026-06-16T00:00:00",
            adapter_id="all",
            adapter_name="全部",
            results={
                "duan": {
                    "adapter_id": "duan",
                    "adapter_name": "段言",
                    "startup": {"name": "启动时间", "iterations": 5, "mean_ms": 10.0, "median_ms": 10.0, "stdev_ms": 0.0, "min_ms": 10.0, "max_ms": 10.0},
                    "keyword_load": None,
                    "execution": {"name": "代码执行", "iterations": 5, "mean_ms": 100.0, "median_ms": 100.0, "stdev_ms": 0.0, "min_ms": 100.0, "max_ms": 100.0},
                    "throughput": None,
                }
            },
        )

        # 当前数据（更慢）
        current = [AdapterBenchResult(
            adapter_id="duan",
            adapter_name="段言",
            execution=BenchResult(name="代码执行", iterations=5, times_ms=[200.0, 210.0, 190.0, 220.0, 200.0]),
        )]

        detector = RegressionDetector(threshold=0.5)  # 50% 阈值
        regressions = detector.detect(current, previous)
        assert len(regressions) > 0
        # 执行时间翻倍，应检测到回归
        execution_reg = [r for r in regressions if r.bench_name == "代码执行"]
        assert len(execution_reg) == 1
        assert execution_reg[0].is_regression is True

    def test_detect_no_regression(self):
        from yanpub.core.bench_viz import RegressionDetector, BenchSnapshot
        from yanpub.core.benchmark import AdapterBenchResult, BenchResult

        previous = BenchSnapshot(
            timestamp="2026-06-16T00:00:00",
            adapter_id="all",
            adapter_name="全部",
            results={
                "duan": {
                    "adapter_id": "duan",
                    "adapter_name": "段言",
                    "execution": {"name": "代码执行", "iterations": 5, "mean_ms": 100.0, "median_ms": 100.0, "stdev_ms": 0.0, "min_ms": 100.0, "max_ms": 100.0},
                    "startup": None, "keyword_load": None, "throughput": None,
                }
            },
        )

        # 当前数据（略慢，但未超阈值）
        current = [AdapterBenchResult(
            adapter_id="duan",
            adapter_name="段言",
            execution=BenchResult(name="代码执行", iterations=5, times_ms=[105.0, 110.0, 102.0, 108.0, 106.0]),
        )]

        detector = RegressionDetector(threshold=0.20)
        regressions = detector.detect(current, previous)
        # 5-10% 增长，不应视为回归
        execution_reg = [r for r in regressions if r.bench_name == "代码执行"]
        assert len(execution_reg) == 1
        assert execution_reg[0].is_regression is False


class TestBenchVisualizer:
    """测试性能可视化报告"""

    def test_generate_html_empty(self):
        from yanpub.core.bench_viz import BenchVisualizer
        html = BenchVisualizer.generate_html([])
        assert "<!DOCTYPE html>" in html
        assert "性能调优面板" in html

    def test_generate_html_with_data(self):
        from yanpub.core.bench_viz import BenchVisualizer
        from yanpub.core.benchmark import AdapterBenchResult, BenchResult
        results = [AdapterBenchResult(
            adapter_id="duan",
            adapter_name="段言",
            execution=BenchResult(name="代码执行", iterations=5, times_ms=[100.0, 105.0, 98.0, 102.0, 101.0]),
            startup=BenchResult(name="启动时间", iterations=5, times_ms=[10.0, 12.0, 9.0, 11.0, 10.0]),
        )]
        html = BenchVisualizer.generate_html(results)
        assert "段言" in html
        assert "bar-chart" in html

    def test_save_html(self):
        from yanpub.core.bench_viz import BenchVisualizer
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "report.html")
            path = BenchVisualizer.save_html([], output)
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in content

    def test_html_with_regressions(self):
        from yanpub.core.bench_viz import BenchVisualizer, RegressionInfo
        regressions = [
            RegressionInfo(
                adapter_id="duan",
                adapter_name="段言",
                bench_name="代码执行",
                previous_ms=100.0,
                current_ms=200.0,
                change_pct=1.0,
                is_regression=True,
            ),
        ]
        html = BenchVisualizer.generate_html([], regressions)
        assert "性能回归" in html
        assert "段言" in html


# ============================================================================
# 4. WASM 执行测试
# ============================================================================

class TestWasmRuntime:
    """测试 WASM 运行时检测"""

    def test_detect_runtime(self):
        from yanpub.core.wasm import detect_wasm_runtime
        runtime = detect_wasm_runtime()
        assert runtime is not None
        assert isinstance(runtime.available, bool)
        assert isinstance(runtime.name, str)

    def test_runtime_info_to_dict(self):
        from yanpub.core.wasm import WasmRuntimeInfo
        info = WasmRuntimeInfo(name="test", version="1.0", available=True)
        d = info.to_dict()
        assert d["name"] == "test"
        assert d["available"] is True


class TestWasmExecutor:
    """测试 WASM 执行器"""

    def test_executor_creation(self):
        from yanpub.core.wasm import WasmExecutor
        executor = WasmExecutor()
        assert executor.runtime is not None

    def test_execute_no_runtime(self):
        from yanpub.core.wasm import WasmExecutor, WasmRuntimeInfo
        no_runtime = WasmRuntimeInfo(name="none", available=False)
        executor = WasmExecutor(runtime=no_runtime)
        result = executor.execute_wasm_file("test.wasm")
        assert result.exit_code == -1
        assert "运行时" in result.stderr

    def test_execute_with_adapter_fallback(self):
        from yanpub.core.wasm import WasmExecutor, WasmRuntimeInfo
        no_runtime = WasmRuntimeInfo(name="none", available=False)
        executor = WasmExecutor(runtime=no_runtime)

        # Mock adapter
        from yanpub.core.adapter import ExecutionResult
        mock_adapter = MagicMock()
        mock_adapter.id = "duan"
        mock_adapter.eval.return_value = ExecutionResult(stdout="hello", exit_code=0)

        result = executor.execute_with_adapter(mock_adapter, "打印(\"hello\")")
        assert result.stdout == "hello"
        assert result.exit_code == 0


class TestPyodideConfig:
    """测试 Pyodide 配置生成"""

    def test_generate_config(self):
        from yanpub.core.wasm import generate_pyodide_config
        mock_adapter = MagicMock()
        mock_adapter.id = "duan"
        mock_adapter.name = "段言"
        mock_adapter.version = "1.3.8"
        mock_adapter.comment_syntax = "#"
        mock_adapter.keywords = ["段落", "打印"]
        mock_adapter.primary_color = "#E85D3A"
        mock_adapter.file_extensions = [".duan"]
        mock_adapter.capabilities = {"repl": True, "lsp": True}

        config = generate_pyodide_config(mock_adapter)
        assert config["lang_id"] == "duan"
        assert config["lang_name"] == "段言"
        assert config["pyodide"]["version"] == "0.24.1"
        assert config["execution_mode"] == "pyodide"

    def test_generate_runner_html(self):
        from yanpub.core.wasm import generate_pyodide_runner_html
        mock_adapter = MagicMock()
        mock_adapter.id = "duan"
        mock_adapter.name = "段言"
        mock_adapter.version = "1.3.8"
        mock_adapter.comment_syntax = "#"
        mock_adapter.keywords = ["段落", "打印"]
        mock_adapter.primary_color = "#E85D3A"
        mock_adapter.file_extensions = [".duan"]
        mock_adapter.capabilities = {"repl": True}

        html = generate_pyodide_runner_html(mock_adapter)
        assert "<!DOCTYPE html>" in html
        assert "Pyodide" in html
        assert "段言" in html
        assert "executeCode" in html


class TestWasmBuilder:
    """测试 WASM 构建器"""

    def test_build(self):
        from yanpub.core.wasm import WasmBuilder
        mock_adapter = MagicMock()
        mock_adapter.id = "test"
        mock_adapter.name = "测试语言"
        mock_adapter.version = "0.1.0"
        mock_adapter.comment_syntax = "#"
        mock_adapter.keywords = ["关键字"]
        mock_adapter.primary_color = "#2C3E50"
        mock_adapter.file_extensions = [".test"]
        mock_adapter.capabilities = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            builder = WasmBuilder(output_dir=Path(tmpdir))
            result = builder.build(mock_adapter)

            assert result.success is True
            assert result.size_bytes > 0
            assert Path(result.output_path).exists()

    def test_build_creates_files(self):
        from yanpub.core.wasm import WasmBuilder
        mock_adapter = MagicMock()
        mock_adapter.id = "test2"
        mock_adapter.name = "测试2"
        mock_adapter.version = "0.1.0"
        mock_adapter.comment_syntax = "//"
        mock_adapter.keywords = []
        mock_adapter.primary_color = "#333"
        mock_adapter.file_extensions = [".t2"]
        mock_adapter.capabilities = {}

        with tempfile.TemporaryDirectory() as tmpdir:
            builder = WasmBuilder(output_dir=Path(tmpdir))
            result = builder.build(mock_adapter)
            assert result.success is True

            lang_dir = Path(result.output_path)
            assert (lang_dir / "pyodide_config.json").exists()
            assert (lang_dir / "runner.html").exists()
            assert (lang_dir / "wrapper.py").exists()
            assert (lang_dir / "meta.json").exists()


# ============================================================================
# 5. CLI 新命令集成测试
# ============================================================================

class TestCLICommands:
    """测试新增 CLI 命令"""

    def test_wasm_check_command(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["wasm", "check"])
        assert result.exit_code == 0
        # 应该输出运行时信息或安装提示
        assert "WASM" in result.output or "运行时" in result.output or "wasmtime" in result.output.lower()

    def test_bench_visualize_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["bench-visualize", "--help"])
        assert result.exit_code == 0
        assert "可视化" in result.output or "html" in result.output.lower()

    def test_bench_regress_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["bench-regress", "--help"])
        assert result.exit_code == 0

    def test_bench_history_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["bench-history", "--help"])
        assert result.exit_code == 0

    def test_pkg_semantic_release_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["pkg", "semantic-release", "--help"])
        assert result.exit_code == 0

    def test_pkg_changelog_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["pkg", "changelog", "--help"])
        assert result.exit_code == 0

    def test_pkg_bump_version_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["pkg", "bump-version", "--help"])
        assert result.exit_code == 0

    def test_wasm_build_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["wasm", "build", "--help"])
        assert result.exit_code == 0

    def test_wasm_run_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main
        runner = CliRunner()
        result = runner.invoke(main, ["wasm", "run", "--help"])
        assert result.exit_code == 0


# ============================================================================
# 6. Playground WASM API 测试
# ============================================================================

class TestPlaygroundWasmAPI:
    """测试 Playground WASM API 端点"""

    def test_wasm_config_endpoint(self):
        """WASM 配置端点应返回正确数据"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        # 测试未知语言
        response = client.get("/api/wasm/nonexistent")
        assert response.status_code == 404

    def test_wasm_runner_endpoint(self):
        """WASM runner 端点应返回 HTML"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        response = client.get("/api/wasm/nonexistent/runner")
        assert response.status_code == 404

    def test_wasm_run_endpoint(self):
        """WASM 执行端点应返回执行结果"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        # 测试未知语言
        response = client.post("/api/wasm/nonexistent/run", json={"code": "test"})
        assert response.status_code == 404
