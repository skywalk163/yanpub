"""YanPkg 包管理器测试"""


import pytest

from yanpub.pkg.registry import PackageRegistry, PackageInfo
from yanpub.pkg.resolver import DependencyResolver
from yanpub.pkg.cache import PackageCache
from yanpub.pkg.installer import Installer


# ---- PackageInfo 测试 ----

class TestPackageInfo:
    def test_create_with_full_name(self):
        pkg = PackageInfo(name="duan:web-framework", lang="duan", package="web-framework")
        assert pkg.name == "duan:web-framework"
        assert pkg.lang == "duan"
        assert pkg.package == "web-framework"

    def test_auto_parse_name(self):
        pkg = PackageInfo(name="yan:math-utils", lang="", package="")
        assert pkg.lang == "yan"
        assert pkg.package == "math-utils"

    def test_to_dict_roundtrip(self):
        pkg = PackageInfo(
            name="duan:http-core",
            lang="duan",
            package="http-core",
            version="0.2.0",
            description="HTTP core library",
        )
        d = pkg.to_dict()
        pkg2 = PackageInfo.from_dict(d)
        assert pkg2.name == pkg.name
        assert pkg2.version == pkg.version
        assert pkg2.description == pkg.description


# ---- PackageRegistry 测试 ----

class TestPackageRegistry:
    @pytest.fixture
    def tmp_dir(self, tmp_path):
        return tmp_path / "registry"

    @pytest.fixture
    def registry(self, tmp_dir):
        return PackageRegistry(registry_dir=tmp_dir)

    def test_empty(self, registry):
        assert len(registry) == 0

    def test_add_and_get(self, registry):
        pkg = PackageInfo(name="duan:test-pkg", lang="duan", package="test-pkg", version="1.0.0")
        registry.add(pkg)
        assert "duan:test-pkg" in registry
        result = registry.get("duan:test-pkg")
        assert result is not None
        assert result.version == "1.0.0"

    def test_remove(self, registry):
        pkg = PackageInfo(name="duan:test-pkg", lang="duan", package="test-pkg")
        registry.add(pkg)
        assert registry.remove("duan:test-pkg") is True
        assert "duan:test-pkg" not in registry

    def test_remove_nonexistent(self, registry):
        assert registry.remove("duan:nonexistent") is False

    def test_search_by_name(self, registry):
        registry.add(PackageInfo(name="duan:web-framework", lang="duan", package="web-framework", description="Web framework"))
        registry.add(PackageInfo(name="yan:math-utils", lang="yan", package="math-utils", description="Math utilities"))
        results = registry.search("web")
        assert len(results) == 1
        assert results[0].name == "duan:web-framework"

    def test_search_by_lang(self, registry):
        registry.add(PackageInfo(name="duan:web-framework", lang="duan", package="web-framework"))
        registry.add(PackageInfo(name="yan:math-utils", lang="yan", package="math-utils"))
        results = registry.search("utils", lang="yan")
        assert len(results) == 1
        assert results[0].lang == "yan"

    def test_list_by_lang(self, registry):
        registry.add(PackageInfo(name="duan:pkg-a", lang="duan", package="pkg-a"))
        registry.add(PackageInfo(name="duan:pkg-b", lang="duan", package="pkg-b"))
        registry.add(PackageInfo(name="yan:pkg-c", lang="yan", package="pkg-c"))
        duan_pkgs = registry.list_by_lang("duan")
        assert len(duan_pkgs) == 2

    def test_persistence(self, tmp_dir, registry):
        registry.add(PackageInfo(name="duan:test", lang="duan", package="test", version="2.0.0"))
        # 创建新的 registry 实例，从磁盘加载
        registry2 = PackageRegistry(registry_dir=tmp_dir)
        assert "duan:test" in registry2
        assert registry2.get("duan:test").version == "2.0.0"


# ---- DependencyResolver 测试 ----

class TestDependencyResolver:
    @pytest.fixture
    def registry_with_deps(self, tmp_path):
        reg = PackageRegistry(registry_dir=tmp_path / "reg")
        reg.add(PackageInfo(
            name="duan:app",
            lang="duan",
            package="app",
            version="1.0.0",
            dependencies={"duan:http-core": ">=0.1.0", "duan:json-utils": "^1.0.0"},
        ))
        reg.add(PackageInfo(
            name="duan:http-core",
            lang="duan",
            package="http-core",
            version="0.2.0",
            dependencies={"duan:logger": ">=0.1.0"},
        ))
        reg.add(PackageInfo(
            name="duan:json-utils",
            lang="duan",
            package="json-utils",
            version="1.1.0",
        ))
        reg.add(PackageInfo(
            name="duan:logger",
            lang="duan",
            package="logger",
            version="0.1.0",
        ))
        return reg

    def test_resolve_simple(self, registry_with_deps):
        resolver = DependencyResolver(registry_with_deps)
        deps = resolver.resolve("duan:json-utils")
        assert len(deps) == 1
        assert deps[0].name == "duan:json-utils"

    def test_resolve_with_deps(self, registry_with_deps):
        resolver = DependencyResolver(registry_with_deps)
        deps = resolver.resolve("duan:http-core")
        names = [d.name for d in deps]
        # logger 应在 http-core 之前
        assert "duan:logger" in names
        assert "duan:http-core" in names
        logger_idx = names.index("duan:logger")
        http_idx = names.index("duan:http-core")
        assert logger_idx < http_idx

    def test_resolve_deep(self, registry_with_deps):
        resolver = DependencyResolver(registry_with_deps)
        deps = resolver.resolve("duan:app")
        names = [d.name for d in deps]
        # 依赖顺序：logger, http-core, json-utils, app
        assert "duan:logger" in names
        assert "duan:http-core" in names
        assert "duan:json-utils" in names
        assert "duan:app" in names
        app_idx = names.index("duan:app")
        assert app_idx == len(names) - 1  # app 应该在最后

    def test_version_matching(self):
        assert DependencyResolver._version_matches("1.2.3", "1.2.3")
        assert DependencyResolver._version_matches("1.2.3", "*")
        assert DependencyResolver._version_matches("1.2.3", "^1.0.0")
        assert DependencyResolver._version_matches("1.2.3", "~1.2.0")
        assert DependencyResolver._version_matches("1.2.3", ">=1.0.0")
        assert not DependencyResolver._version_matches("1.2.3", "^2.0.0")
        assert not DependencyResolver._version_matches("1.2.3", "~1.3.0")


# ---- PackageCache 测试 ----

class TestPackageCache:
    @pytest.fixture
    def cache(self, tmp_path):
        return PackageCache(cache_dir=tmp_path / "cache")

    def test_empty(self, cache):
        assert len(cache.list_all()) == 0

    def test_add_and_get(self, cache):
        path = cache.add("duan:test-pkg", "duan", "test-pkg", "1.0.0")
        assert path.exists()
        cp = cache.get("duan:test-pkg")
        assert cp is not None
        assert cp.version == "1.0.0"

    def test_is_cached(self, cache):
        cache.add("duan:test-pkg", "duan", "test-pkg", "1.0.0")
        assert cache.is_cached("duan:test-pkg")
        assert cache.is_cached("duan:test-pkg", "1.0.0")
        assert not cache.is_cached("duan:test-pkg", "2.0.0")
        assert not cache.is_cached("duan:nonexistent")

    def test_remove(self, cache):
        cache.add("duan:test-pkg", "duan", "test-pkg", "1.0.0")
        assert cache.remove("duan:test-pkg")
        assert not cache.is_cached("duan:test-pkg")

    def test_list_by_lang(self, cache):
        cache.add("duan:pkg-a", "duan", "pkg-a", "1.0.0")
        cache.add("duan:pkg-b", "duan", "pkg-b", "0.5.0")
        cache.add("yan:pkg-c", "yan", "pkg-c", "1.0.0")
        duan_pkgs = cache.list_by_lang("duan")
        assert len(duan_pkgs) == 2

    def test_add_with_source(self, cache, tmp_path):
        # 创建临时源文件
        src_dir = tmp_path / "source"
        src_dir.mkdir()
        (src_dir / "main.duan").write_text("打印('hello')。", encoding="utf-8")

        path = cache.add("duan:hello-pkg", "duan", "hello-pkg", "0.1.0", source_path=src_dir)
        assert (path / "main.duan").exists()

    def test_persistence(self, tmp_path, cache):
        cache.add("duan:test", "duan", "test", "1.0.0")
        # 新实例从磁盘加载
        cache2 = PackageCache(cache_dir=tmp_path / "cache")
        assert cache2.is_cached("duan:test")


# ---- Installer 测试 ----

class TestInstaller:
    @pytest.fixture
    def installer(self, tmp_path):
        reg = PackageRegistry(registry_dir=tmp_path / "reg")
        cache = PackageCache(cache_dir=tmp_path / "cache")
        return Installer(registry=reg, cache=cache)

    def test_install_nonexistent_package(self, installer):
        result = installer.install("duan:nonexistent")
        assert result is False

    def test_install_local_package(self, installer):
        # 先注册包
        installer.registry.add(PackageInfo(
            name="duan:hello",
            lang="duan",
            package="hello",
            version="1.0.0",
            source_type="local",
            source_url="",  # 空路径 → 只记录元数据
        ))
        result = installer.install("duan:hello")
        assert result is True
        assert installer.cache.is_cached("duan:hello")

    def test_install_without_lang_prefix(self, installer):
        installer.registry.add(PackageInfo(
            name="duan:web",
            lang="duan",
            package="web",
            version="0.1.0",
            description="Web framework",
        ))
        # 不带语言前缀，应该能搜索到
        result = installer.install("web")
        assert result is True
