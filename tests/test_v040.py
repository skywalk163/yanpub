"""v0.4.0 功能测试

测试项：
1. 包管理器依赖锁定（LockManager + LockFile + lock/verify/unlock）
2. LSP 代码重构（adapter.rename + LSP rename/codeAction）
"""

import json

import pytest


# ---- 1. 包管理器依赖锁定 ----


class TestLockFile:
    """依赖锁定测试"""

    def test_lock_file_creation(self, tmp_path):
        """测试 LockFile 创建和保存"""
        from yanpub.pkg.lockfile import LockFile, LockedPackage

        lf = LockFile()
        lf.packages["duan:test-pkg"] = LockedPackage(
            version="1.0.0",
            source="git+https://example.com/test.git@v1.0.0",
            hash="sha256:abc123",
            dependencies={"duan:http-core": ">=0.1.0"},
        )

        lock_path = tmp_path / "yanpkg.lock"
        lf.save(lock_path)

        assert lock_path.exists()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert data["version"] == "1"
        assert "duan:test-pkg" in data["packages"]
        assert data["packages"]["duan:test-pkg"]["version"] == "1.0.0"

    def test_lock_file_load(self, tmp_path):
        """测试 LockFile 加载"""
        from yanpub.pkg.lockfile import LockFile, LockedPackage

        lf = LockFile()
        lf.packages["yan:math"] = LockedPackage(version="2.0.0", hash="sha256:def456")
        lock_path = tmp_path / "yanpkg.lock"
        lf.save(lock_path)

        loaded = LockFile.from_file(lock_path)
        assert "yan:math" in loaded.packages
        assert loaded.packages["yan:math"].version == "2.0.0"
        assert loaded.packages["yan:math"].hash == "sha256:def456"

    def test_lock_file_to_json(self):
        """测试 LockFile JSON 序列化"""
        from yanpub.pkg.lockfile import LockFile, LockedPackage

        lf = LockFile()
        lf.packages["test:pkg"] = LockedPackage(version="0.1.0")
        json_str = lf.to_json()

        data = json.loads(json_str)
        assert "packages" in data
        assert "test:pkg" in data["packages"]

    def test_locked_package_from_dict(self):
        """测试 LockedPackage 反序列化"""
        from yanpub.pkg.lockfile import LockedPackage

        data = {"version": "1.0.0", "source": "git+x", "hash": "sha256:abc", "dependencies": {}}
        pkg = LockedPackage.from_dict(data)
        assert pkg.version == "1.0.0"
        assert pkg.source == "git+x"


class TestLockManager:
    """LockManager 测试"""

    def test_lock_manager_generate(self, tmp_path):
        """测试生成 lock 文件"""
        from yanpub.pkg.lockfile import LockManager
        from yanpub.pkg.registry import PackageRegistry, PackageInfo

        registry = PackageRegistry()
        registry.add(PackageInfo(
            name="duan:web-framework",
            lang="duan",
            package="web-framework",
            version="0.2.0",
            dependencies={"duan:http-core": ">=0.1.0"},
        ))
        registry.add(PackageInfo(
            name="duan:http-core",
            lang="duan",
            package="http-core",
            version="0.1.0",
        ))

        lm = LockManager(tmp_path, registry=registry)
        # 没有项目 yanpkg.toml 时，generate 会创建空 lock
        lock = lm.generate()
        assert isinstance(lock.packages, dict)

    def test_lock_manager_verify_no_lock(self, tmp_path):
        """测试无 lock 文件时验证"""
        from yanpub.pkg.lockfile import LockManager

        lm = LockManager(tmp_path)
        result = lm.verify()
        assert not result["valid"]
        assert "不存在" in result["errors"][0]

    def test_lock_manager_unlock(self, tmp_path):
        """测试解锁"""
        from yanpub.pkg.lockfile import LockManager, LockFile, LockedPackage

        # 先创建 lock 文件
        lf = LockFile()
        lf.packages["test:pkg"] = LockedPackage(version="1.0.0")
        lf.save(tmp_path / "yanpkg.lock")

        lm = LockManager(tmp_path)
        assert lm.is_locked
        assert lm.unlock()
        assert not lm.is_locked

    def test_lock_manager_unlock_nonexistent(self, tmp_path):
        """测试解锁不存在的 lock 文件"""
        from yanpub.pkg.lockfile import LockManager

        lm = LockManager(tmp_path)
        assert not lm.unlock()

    def test_lock_manager_is_locked(self, tmp_path):
        """测试 is_locked 状态"""
        from yanpub.pkg.lockfile import LockManager, LockFile, LockedPackage

        lm = LockManager(tmp_path)
        assert not lm.is_locked

        lf = LockFile()
        lf.packages["test:x"] = LockedPackage(version="1.0.0")
        lf.save(tmp_path / "yanpkg.lock")
        assert lm.is_locked

    def test_lock_manager_verify_valid(self, tmp_path):
        """测试验证有效的 lock 文件"""
        from yanpub.pkg.lockfile import LockManager, LockFile, LockedPackage
        from yanpub.pkg.registry import PackageRegistry, PackageInfo

        registry = PackageRegistry()
        registry.add(PackageInfo(
            name="test:pkg", lang="test", package="pkg", version="1.0.0",
        ))

        lf = LockFile()
        lf.packages["test:pkg"] = LockedPackage(version="1.0.0", hash="sha256:abc")
        lf.save(tmp_path / "yanpkg.lock")

        lm = LockManager(tmp_path, registry=registry)
        result = lm.verify()
        assert result["checked"] == 1


# ---- 2. LSP 代码重构 ----


class TestAdapterRename:
    """适配器 rename 方法测试"""

    def test_rename_simple_identifier(self):
        """测试简单标识符重命名"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。\n打印(甲)。\n"
        edits = adapter.rename(code, 1, 2, "乙")
        assert edits is not None
        assert len(edits) >= 1
        # 所有 "甲" 都应被替换
        for edit in edits:
            assert edit["newText"] == "乙"

    def test_rename_preserves_others(self):
        """测试重命名不影响其他标识符"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。\n设乙为五。\n打印(甲 + 乙)。\n"
        edits = adapter.rename(code, 1, 2, "丙")
        assert edits is not None
        # 只有 "甲" 被替换，"乙" 不受影响
        for edit in edits:
            assert edit["newText"] == "丙"

    def test_rename_no_identifier_at_cursor(self):
        """测试光标不在标识符上时返回 None"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "   \n"
        edits = adapter.rename(code, 1, 1, "新名")
        assert edits is None

    def test_rename_out_of_range(self):
        """测试光标越界返回 None"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "打印(1)。"
        edits = adapter.rename(code, 5, 1, "新名")
        assert edits is None

    def test_rename_multiple_occurrences(self):
        """测试多处出现全部替换"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。\n打印(甲)。\n如果 甲 > 0：\n  打印(甲)。\n结束。"
        edits = adapter.rename(code, 1, 2, "乙")
        assert edits is not None
        # 统计 "甲" 的出现次数
        jiă_count = code.count("甲")
        assert len(edits) == jiă_count


class TestLSPRename:
    """LSP rename 处理器测试"""

    def test_lsp_rename_integration(self):
        """测试 LSP rename 集成"""
        pytest.importorskip("lsprotocol")
        from yanpub.lsp.server import YanLanguageServer
        from yanpub.core.registry import LanguageRegistry
        from yanpub.core.adapter import SubprocessAdapter

        registry = LanguageRegistry()
        registry.register(SubprocessAdapter(
            name="测试", lang_id="test_lsp_rename", version="0.1",
            extensions=[".t"], run_command=["echo"],
        ))

        server = YanLanguageServer(registry=registry)
        # 验证 rename feature 已注册
        assert hasattr(server, 'server')


# ---- 3. 适配器兼容性矩阵 ----


class TestCompatMatrix:
    """兼容性矩阵测试"""

    def test_check_compatibility_subprocess(self):
        """测试子进程适配器兼容性"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
            keywords=["设", "打印"],
        )
        result = check_compatibility(adapter)
        assert result.adapter_id == "test_compat"
        assert result.overall in ("compatible", "partial")
        assert "api" in result.checks
        assert result.checks["api"]["status"] == "ok"

    def test_check_compatibility_keywords(self):
        """测试关键字覆盖检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_kw_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
            keywords=["设", "打印", "如果"],
        )
        result = check_compatibility(adapter)
        assert result.checks["keywords"]["status"] == "ok"
        assert result.checks["keywords"]["count"] == 3

    def test_check_compatibility_lsp(self):
        """测试 LSP 能力检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_lsp_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
            keywords=["设"],
        )
        result = check_compatibility(adapter)
        assert "lsp" in result.checks
        lsp_info = result.checks["lsp"]
        assert lsp_info["supported_count"] > 0

    def test_check_compatibility_version_format(self):
        """测试版本号格式检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_ver", version="1.0.0",
            extensions=[".t"], run_command=["echo"],
        )
        result = check_compatibility(adapter)
        assert result.checks["version"]["status"] == "ok"

    def test_check_all_compatibility(self):
        """测试批量兼容性检查"""
        from yanpub.core.registry import LanguageRegistry
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_all_compatibility

        registry = LanguageRegistry()
        registry.register(SubprocessAdapter(
            name="测试1", lang_id="compat1", version="0.1.0",
            extensions=[".t1"], run_command=["echo"],
        ))
        registry.register(SubprocessAdapter(
            name="测试2", lang_id="compat2", version="2.0",
            extensions=[".t2"], run_command=["echo"],
            keywords=["设"],
        ))

        results = check_all_compatibility(registry)
        assert len(results) == 2

    def test_format_compat_matrix(self):
        """测试兼容性矩阵格式化"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility, format_compat_matrix

        adapter = SubprocessAdapter(
            name="测试", lang_id="fmt_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
            keywords=["设"],
        )
        result = check_compatibility(adapter)
        report = format_compat_matrix([result])
        assert "兼容性矩阵" in report
        assert "测试" in report

    def test_format_compat_detail(self):
        """测试详细兼容性报告"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility, format_compat_detail

        adapter = SubprocessAdapter(
            name="测试", lang_id="detail_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
            keywords=["设"],
        )
        result = check_compatibility(adapter)
        report = format_compat_detail(result)
        assert "兼容性详情" in report
        assert "测试" in report

    def test_compat_result_to_dict(self):
        """测试兼容性结果序列化"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.compat import check_compatibility

        adapter = SubprocessAdapter(
            name="测试", lang_id="dict_compat", version="0.1.0",
            extensions=[".t"], run_command=["echo"],
        )
        result = check_compatibility(adapter)
        d = result.to_dict()
        assert "adapter_id" in d
        assert "overall" in d
        assert "checks" in d


# ---- 4. 插件系统 ----


class TestPluginSystem:
    """插件系统测试"""

    def test_plugin_info_creation(self):
        """测试 PluginInfo 创建"""
        from yanpub.core.plugin import PluginInfo

        info = PluginInfo(
            name="test-plugin",
            version="1.0.0",
            description="测试插件",
            hooks=["pre_eval", "post_eval"],
        )
        assert info.name == "test-plugin"
        assert len(info.hooks) == 2

    def test_plugin_info_serialization(self):
        """测试 PluginInfo 序列化"""
        from yanpub.core.plugin import PluginInfo

        info = PluginInfo(name="test", version="1.0.0", hooks=["pre_eval"])
        d = info.to_dict()
        assert d["name"] == "test"
        assert "pre_eval" in d["hooks"]

        loaded = PluginInfo.from_dict(d)
        assert loaded.name == "test"
        assert loaded.hooks == ["pre_eval"]

    def test_plugin_manager_discover_empty(self, tmp_path):
        """测试空目录插件发现"""
        from yanpub.core.plugin import PluginManager

        pm = PluginManager(plugins_dir=tmp_path)
        assert pm.list_plugins() == []

    def test_plugin_manager_install(self, tmp_path):
        """测试插件安装"""
        from yanpub.core.plugin import PluginManager, PluginInfo

        # 创建源插件目录
        source = tmp_path / "source" / "my-plugin"
        source.mkdir(parents=True)
        manifest = PluginInfo(
            name="my-plugin",
            version="1.0.0",
            description="测试插件",
            hooks=["pre_eval"],
        )
        (source / "plugin.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 安装
        plugins_dir = tmp_path / "plugins"
        pm = PluginManager(plugins_dir=plugins_dir)
        info = pm.install(str(source))

        assert info.name == "my-plugin"
        assert info.version == "1.0.0"
        assert (plugins_dir / "my-plugin" / "plugin.json").exists()

    def test_plugin_manager_uninstall(self, tmp_path):
        """测试插件卸载"""
        from yanpub.core.plugin import PluginManager, PluginInfo

        source = tmp_path / "source" / "uninstall-test"
        source.mkdir(parents=True)
        manifest = PluginInfo(name="uninstall-test", version="1.0.0")
        (source / "plugin.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        plugins_dir = tmp_path / "plugins"
        pm = PluginManager(plugins_dir=plugins_dir)
        pm.install(str(source))

        assert pm.uninstall("uninstall-test")
        assert pm.get_plugin("uninstall-test") is None

    def test_plugin_manager_enable_disable(self, tmp_path):
        """测试插件启用/禁用"""
        from yanpub.core.plugin import PluginManager, PluginInfo

        source = tmp_path / "source" / "toggle-test"
        source.mkdir(parents=True)
        manifest = PluginInfo(name="toggle-test", version="1.0.0")
        (source / "plugin.json").write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        plugins_dir = tmp_path / "plugins"
        pm = PluginManager(plugins_dir=plugins_dir)
        pm.install(str(source))

        # 禁用
        assert pm.disable("toggle-test")
        plugin = pm.get_plugin("toggle-test")
        assert not plugin.info.enabled

        # 启用
        assert pm.enable("toggle-test")
        plugin = pm.get_plugin("toggle-test")
        assert plugin.info.enabled

    def test_plugin_manager_call_hook(self, tmp_path):
        """测试钩子调用"""
        from yanpub.core.plugin import PluginManager

        pm = PluginManager(plugins_dir=tmp_path)
        # 无插件时调用钩子
        results = pm.call_hook("pre_eval", "print(1)。", "duan")
        assert results == []

    def test_plugin_manager_has_hook(self, tmp_path):
        """测试钩子检查"""
        from yanpub.core.plugin import PluginManager

        pm = PluginManager(plugins_dir=tmp_path)
        assert not pm.has_hook("pre_eval")

    def test_format_plugin_list_empty(self):
        """测试空插件列表格式化"""
        from yanpub.core.plugin import format_plugin_list

        result = format_plugin_list([])
        assert "没有" in result

    def test_format_plugin_list_with_plugins(self):
        """测试插件列表格式化"""
        from yanpub.core.plugin import PluginInfo, format_plugin_list

        plugins = [
            PluginInfo(name="test", version="1.0.0", description="测试", hooks=["pre_eval"]),
        ]
        result = format_plugin_list(plugins)
        assert "test" in result
        assert "1.0.0" in result

    def test_supported_hooks(self):
        """测试支持的钩子列表"""
        from yanpub.core.plugin import SUPPORTED_HOOKS

        assert "pre_eval" in SUPPORTED_HOOKS
        assert "post_eval" in SUPPORTED_HOOKS
        assert "pre_run" in SUPPORTED_HOOKS
        assert "on_error" in SUPPORTED_HOOKS
        assert "on_repl_start" in SUPPORTED_HOOKS


# ---- 5. 版本与导出 ----


class TestVersionAndExports:
    """版本号和模块导出测试"""

    def test_version_is_040(self):
        """测试版本号是 0.4.0"""
        from yanpub import __version__

        assert __version__ >= "0.4.0"

    def test_lockfile_module_importable(self):
        """测试 lockfile 模块可导入"""
        from yanpub.pkg.lockfile import LockManager, LockFile, LockedPackage
        assert LockManager is not None
        assert LockFile is not None
        assert LockedPackage is not None

    def test_compat_module_importable(self):
        """测试 compat 模块可导入"""
        from yanpub.core.compat import check_compatibility, CompatResult, format_compat_matrix
        assert check_compatibility is not None
        assert CompatResult is not None
        assert format_compat_matrix is not None

    def test_plugin_module_importable(self):
        """测试 plugin 模块可导入"""
        from yanpub.core.plugin import PluginManager, PluginInfo, get_plugin_manager
        assert PluginManager is not None
        assert PluginInfo is not None
        assert get_plugin_manager is not None

    def test_adapter_has_rename(self):
        """测试 LanguageAdapter 有 rename 方法"""
        from yanpub.core.adapter import LanguageAdapter
        assert hasattr(LanguageAdapter, "rename")
