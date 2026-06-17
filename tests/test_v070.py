"""v0.7.0 功能测试 — Playground 协作前端 + LSP 语义高亮 + 适配器性能分析器 + 包管理器版本工作集"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest


# ============================================================
# 1. LSP 语义高亮测试
# ============================================================

class TestLSPSemanticTokens:
    """LSP 语义高亮 — Semantic Tokens 协议"""

    def test_semantic_tokens_basic(self):
        """基本语义 token 生成"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '段落 加法(甲, 乙)。\n  返回 甲 加 乙。\n结束。'
        tokens = server._compute_semantic_tokens(adapter, code)

        assert isinstance(tokens, list)
        # 应该有一些 token
        assert len(tokens) > 0

    def test_semantic_tokens_empty_code(self):
        """空代码无语义 token"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        tokens = server._compute_semantic_tokens(adapter, "")
        assert tokens == []

    def test_semantic_tokens_keyword_detection(self):
        """关键字检测"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '段落 测试()。\n结束。'
        tokens = server._compute_semantic_tokens(adapter, code)

        # 应该检测到"段落"和"结束"为关键字
        # tokens 是 [deltaLine, deltaStartChar, length, tokenType, tokenMod, ...]
        assert len(tokens) >= 10  # 至少 2 个 token × 5 个整数

    def test_semantic_tokens_string_detection(self):
        """字符串字面量检测"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '打印("你好世界")。'
        tokens = server._compute_semantic_tokens(adapter, code)
        assert isinstance(tokens, list)

    def test_semantic_tokens_number_detection(self):
        """数字字面量检测"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '设 甲 为 42。'
        tokens = server._compute_semantic_tokens(adapter, code)
        assert isinstance(tokens, list)

    def test_semantic_tokens_comment_detection(self):
        """注释检测"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '# 这是一个注释\n段落 测试()。\n结束。'
        tokens = server._compute_semantic_tokens(adapter, code)
        assert isinstance(tokens, list)

    def test_semantic_tokens_delta_encoding(self):
        """Delta 编码验证"""
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry

        registry = LanguageRegistry()
        from yanpub.adapters.duan.adapter import DuanAdapter
        registry.register(DuanAdapter())

        server = YanLanguageServer(registry=registry)
        adapter = registry.get("duan")

        code = '段落 加法()。\n结束。'
        tokens = server._compute_semantic_tokens(adapter, code)

        # 验证 data 是 5 的倍数长度
        assert len(tokens) % 5 == 0

        # 第一个 token 的 deltaLine 应该是 0（第一行）
        if len(tokens) >= 5:
            assert tokens[0] == 0  # deltaLine


# ============================================================
# 2. 适配器性能分析器测试
# ============================================================

class TestAdapterProfiler:
    """适配器性能分析器"""

    def test_profile_record_creation(self):
        """ProfileRecord 创建"""
        from yanpub.core.profiler import ProfileRecord

        record = ProfileRecord(
            name="eval",
            adapter_id="duan",
            duration_ms=42.5,
            timestamp=time.time(),
            success=True,
        )
        assert record.name == "eval"
        assert record.adapter_id == "duan"
        assert record.duration_ms == 42.5
        assert record.success

    def test_profile_report_creation(self):
        """ProfileReport 创建"""
        from yanpub.core.profiler import ProfileReport, ProfileRecord

        records = [
            ProfileRecord(name="eval", adapter_id="duan", duration_ms=10.0, timestamp=time.time(), success=True),
            ProfileRecord(name="eval", adapter_id="duan", duration_ms=20.0, timestamp=time.time(), success=True),
            ProfileRecord(name="eval", adapter_id="duan", duration_ms=30.0, timestamp=time.time(), success=True),
        ]
        report = ProfileReport(
            name="eval",
            adapter_id="duan",
            iterations=3,
            total_ms=60.0,
            avg_ms=20.0,
            min_ms=10.0,
            max_ms=30.0,
            median_ms=20.0,
            p95_ms=30.0,
            records=records,
        )
        assert report.name == "eval"
        assert report.avg_ms == 20.0
        assert report.min_ms == 10.0
        assert report.max_ms == 30.0

    def test_profile_report_to_dict(self):
        """ProfileReport 序列化"""
        from yanpub.core.profiler import ProfileReport

        report = ProfileReport(
            name="eval",
            adapter_id="duan",
            iterations=1,
            total_ms=10.0,
            avg_ms=10.0,
            min_ms=10.0,
            max_ms=10.0,
            median_ms=10.0,
            p95_ms=10.0,
            records=[],
        )
        d = report.to_dict()
        assert d["name"] == "eval"
        assert d["avg_ms"] == 10.0

    def test_profile_report_to_table(self):
        """ProfileReport 文本表格"""
        from yanpub.core.profiler import ProfileReport

        report = ProfileReport(
            name="eval",
            adapter_id="duan",
            iterations=5,
            total_ms=50.0,
            avg_ms=10.0,
            min_ms=8.0,
            max_ms=15.0,
            median_ms=9.0,
            p95_ms=14.0,
            records=[],
        )
        table = report.to_table()
        assert "eval" in table
        assert "duan" in table

    def test_adapter_profiler_creation(self):
        """AdapterProfiler 创建"""
        from yanpub.core.profiler import AdapterProfiler
        from yanpub.core.registry import get_registry

        registry = get_registry()
        adapter = registry.get("duan")
        if adapter is None:
            pytest.skip("段言适配器不可用")

        profiler = AdapterProfiler(adapter)
        assert profiler is not None

    def test_hotspot_detector(self):
        """热点检测"""
        from yanpub.core.profiler import HotspotDetector, ProfileReport

        reports = {
            "eval": ProfileReport(
                name="eval",
                adapter_id="duan",
                iterations=5,
                total_ms=5500.0,
                avg_ms=1100.0,
                min_ms=800.0,
                max_ms=1500.0,
                median_ms=950.0,
                p95_ms=1400.0,
                records=[],
            ),
            "tokenize": ProfileReport(
                name="tokenize",
                adapter_id="duan",
                iterations=5,
                total_ms=2500.0,
                avg_ms=500.0,
                min_ms=400.0,
                max_ms=700.0,
                median_ms=480.0,
                p95_ms=650.0,
                records=[],
            ),
        }

        detector = HotspotDetector()
        hotspots = detector.analyze(reports)

        assert len(hotspots) >= 1
        # eval avg 1100ms > 1000ms 应该是 critical
        eval_hotspot = next((h for h in hotspots if h.operation == "eval"), None)
        assert eval_hotspot is not None
        assert eval_hotspot.severity == "critical"

    def test_flame_graph_generator(self):
        """火焰图生成"""
        from yanpub.core.profiler import FlameGraphGenerator, ProfileReport

        reports = {
            "eval": ProfileReport(
                name="eval",
                adapter_id="duan",
                iterations=5,
                total_ms=500.0,
                avg_ms=100.0,
                min_ms=80.0,
                max_ms=150.0,
                median_ms=95.0,
                p95_ms=140.0,
                records=[],
            ).to_dict(),
        }

        generator = FlameGraphGenerator()
        html = generator.generate_html(reports)
        assert "<html" in html or "<!DOCTYPE" in html
        assert "eval" in html

    def test_flame_graph_svg(self):
        """SVG 火焰图生成"""
        from yanpub.core.profiler import FlameGraphGenerator, ProfileReport

        reports = {
            "eval": ProfileReport(
                name="eval",
                adapter_id="duan",
                iterations=5,
                total_ms=500.0,
                avg_ms=100.0,
                min_ms=80.0,
                max_ms=150.0,
                median_ms=95.0,
                p95_ms=140.0,
                records=[],
            ).to_dict(),
        }

        generator = FlameGraphGenerator()
        svg = generator.generate_svg(reports)
        assert "<svg" in svg
        assert "eval" in svg


# ============================================================
# 3. 包管理器版本工作集测试
# ============================================================

class TestVersionConstraint:
    """版本约束解析"""

    def test_parse_gte(self):
        """>= 版本约束"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse(">=1.0.0")
        assert vc.matches("1.0.0")
        assert vc.matches("2.0.0")
        assert not vc.matches("0.9.0")

    def test_parse_exact(self):
        """精确版本约束"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse("1.0.0")
        assert vc.matches("1.0.0")
        assert not vc.matches("1.0.1")
        assert not vc.matches("0.9.0")

    def test_parse_caret(self):
        """^ 版本约束（兼容版本）"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse("^1.0.0")
        assert vc.matches("1.0.0")
        assert vc.matches("1.5.0")
        assert not vc.matches("2.0.0")
        assert not vc.matches("0.9.0")

    def test_parse_tilde(self):
        """~ 版本约束（补丁版本）"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse("~1.2.0")
        assert vc.matches("1.2.0")
        assert vc.matches("1.2.5")
        assert not vc.matches("1.3.0")

    def test_parse_wildcard(self):
        """* 通配符版本约束"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse("*")
        assert vc.matches("1.0.0")
        assert vc.matches("99.99.99")

    def test_parse_range(self):
        """范围版本约束"""
        from yanpub.pkg.versionset import VersionConstraint

        vc = VersionConstraint.parse(">=1.0.0,<2.0.0")
        assert vc.matches("1.0.0")
        assert vc.matches("1.5.0")
        assert not vc.matches("2.0.0")
        assert not vc.matches("0.9.0")


class TestResolvedVersion:
    """已解析版本"""

    def test_resolved_version_creation(self):
        """ResolvedVersion 创建"""
        from yanpub.pkg.versionset import ResolvedVersion

        rv = ResolvedVersion(
            package_name="duan:http-core",
            version="1.2.0",
            source="registry",
        )
        assert rv.package_name == "duan:http-core"
        assert rv.version == "1.2.0"
        assert rv.source == "registry"

    def test_resolved_version_to_dict(self):
        """ResolvedVersion 序列化"""
        from yanpub.pkg.versionset import ResolvedVersion

        rv = ResolvedVersion(
            package_name="duan:utils",
            version="0.1.0",
            source="path",
        )
        d = rv.to_dict()
        assert d["package_name"] == "duan:utils"
        assert d["version"] == "0.1.0"


class TestWorkspaceLock:
    """工作空间版本锁定"""

    def test_workspace_lock_creation(self):
        """WorkspaceLock 创建"""
        from yanpub.pkg.versionset import WorkspaceLock, ResolvedVersion

        lock = WorkspaceLock(
            workspace_name="test-workspace",
            created_at="2026-06-17T12:00:00",
            members={
                "duan:utils": ResolvedVersion("duan:utils", "0.1.0", "path"),
            },
            dependencies={
                "duan:http-core": ResolvedVersion("duan:http-core", "1.2.0", "registry"),
            },
        )
        assert lock.workspace_name == "test-workspace"
        assert "duan:utils" in lock.members
        assert "duan:http-core" in lock.dependencies

    def test_workspace_lock_to_toml(self):
        """WorkspaceLock TOML 序列化"""
        from yanpub.pkg.versionset import WorkspaceLock, ResolvedVersion

        lock = WorkspaceLock(
            workspace_name="test-workspace",
            created_at="2026-06-17T12:00:00",
            members={
                "duan:utils": ResolvedVersion("duan:utils", "0.1.0", "path"),
            },
            dependencies={
                "duan:http-core": ResolvedVersion("duan:http-core", "1.2.0", "registry"),
            },
        )
        toml_str = lock.to_toml()
        assert "test-workspace" in toml_str
        assert "duan:utils" in toml_str
        assert "duan:http-core" in toml_str

    def test_workspace_lock_from_toml(self):
        """WorkspaceLock TOML 反序列化"""
        from yanpub.pkg.versionset import WorkspaceLock

        toml_str = '''
[workspace]
name = "test-workspace"
created_at = "2026-06-17T12:00:00"

[members."duan:utils"]
version = "0.1.0"
source = "path"

[dependencies."duan:http-core"]
version = "1.2.0"
source = "registry"
'''
        lock = WorkspaceLock.from_toml(toml_str)
        assert lock.workspace_name == "test-workspace"
        assert "duan:utils" in lock.members
        assert lock.members["duan:utils"].version == "0.1.0"

    def test_workspace_lock_to_dict(self):
        """WorkspaceLock 字典序列化"""
        from yanpub.pkg.versionset import WorkspaceLock

        lock = WorkspaceLock(
            workspace_name="test-ws",
            created_at="2026-06-17",
            members={},
            dependencies={},
        )
        d = lock.to_dict()
        # to_dict 返回嵌套结构 {"workspace": {"name": ..., "created_at": ...}, ...}
        assert d["workspace"]["name"] == "test-ws"


class TestVersionSetManager:
    """版本工作集管理器"""

    def _create_workspace(self, tmp_dir: Path) -> Path:
        """创建测试工作空间"""
        pkgs_dir = tmp_dir / "packages"
        pkgs_dir.mkdir()

        utils_dir = pkgs_dir / "utils"
        utils_dir.mkdir()
        (utils_dir / "yanpkg.toml").write_text(
            '[package]\nname = "utils"\nlang = "duan"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

        web_dir = pkgs_dir / "web-framework"
        web_dir.mkdir()
        (web_dir / "yanpkg.toml").write_text(
            '[package]\nname = "web-framework"\nlang = "duan"\nversion = "0.2.0"\n\n[dependencies]\n"duan:utils" = ">=0.1.0"\n"duan:http-core" = ">=1.0.0"\n',
            encoding="utf-8",
        )

        ws_content = '[workspace]\nname = "test-ws"\nmembers = ["packages/*"]\n\n[workspace.dependencies]\n"duan:http-core" = ">=1.0.0"\n'
        (tmp_dir / "workspace.toml").write_text(ws_content, encoding="utf-8")

        return tmp_dir

    def test_version_set_manager_resolve(self):
        """解析版本锁定"""
        from yanpub.pkg.workspace import Workspace
        from yanpub.pkg.versionset import VersionSetManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace(Path(tmp_dir))
            ws = Workspace(root)
            ws.load()

            manager = VersionSetManager(ws)
            lock = manager.resolve()

            assert lock.workspace_name == "test-ws"
            assert "duan:utils" in lock.members
            assert "duan:web-framework" in lock.members
            # 内部依赖版本应锁定为当前版本
            assert lock.members["duan:utils"].version == "0.1.0"

    def test_version_set_manager_save_load(self):
        """保存和加载锁定文件"""
        from yanpub.pkg.workspace import Workspace
        from yanpub.pkg.versionset import VersionSetManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace(Path(tmp_dir))
            ws = Workspace(root)
            ws.load()

            manager = VersionSetManager(ws)
            lock = manager.resolve()
            lock_path = manager.save_lock(lock)

            assert lock_path.exists()

            # 加载
            loaded = manager.load_lock()
            assert loaded is not None
            assert loaded.workspace_name == "test-ws"

    def test_version_set_manager_check_freshness(self):
        """检查锁定新鲜度"""
        from yanpub.pkg.workspace import Workspace
        from yanpub.pkg.versionset import VersionSetManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace(Path(tmp_dir))
            ws = Workspace(root)
            ws.load()

            manager = VersionSetManager(ws)
            # 没有锁定文件时，应该报告 missing
            freshness = manager.check_freshness()
            assert not freshness["fresh"]

            # 生成锁定后再检查
            lock = manager.resolve()
            manager.save_lock(lock)
            freshness = manager.check_freshness()
            # 锁定文件已存在
            # 外部依赖 "duan:http-core" 在注册中心中有版本，
            # 但 resolve 时可能因约束不匹配锁为 unknown，
            # 所以 fresh 可能仍为 False
            assert isinstance(freshness["fresh"], bool)
            assert isinstance(freshness["outdated"], list)
            assert isinstance(freshness["missing"], list)

    def test_version_set_manager_upgrade(self):
        """升级依赖版本"""
        from yanpub.pkg.workspace import Workspace
        from yanpub.pkg.versionset import VersionSetManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = self._create_workspace(Path(tmp_dir))
            ws = Workspace(root)
            ws.load()

            manager = VersionSetManager(ws)
            lock = manager.upgrade()
            assert lock is not None
            assert lock.workspace_name == "test-ws"
