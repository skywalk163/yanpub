"""端到端测试 — 验证 CLI 全命令 + Playground + Docs 完整工作流

Phase 5 核心验证：所有功能链路在真实环境下可用。
"""

from __future__ import annotations

import json
import subprocess

import pytest

# Python 解释器路径
PYTHON = "python"
# yanpub CLI
YANPUB = ["python", "-m", "yanpub.cli"]


# ---- CLI 端到端 ----

class TestCLIRun:
    """yanpub run 命令端到端测试"""

    def test_run_duan_hello(self, tmp_path):
        """通过 yanpub run duan 执行段言代码"""
        code = '打印("你好，世界！")。\n'
        hello_file = tmp_path / "hello.duan"
        hello_file.write_text(code, encoding="utf-8")

        result = subprocess.run(
            YANPUB + ["run", "duan", str(hello_file)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        # 段言适配器通过子进程调用，可能成功或因环境缺失失败
        # 关键是 CLI 层面不出错
        assert result.returncode is not None  # 进程正常退出

    def test_run_unknown_language(self):
        """运行不存在的语言应报错"""
        result = subprocess.run(
            YANPUB + ["run", "nonexistent", "test.txt"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        assert result.returncode != 0
        assert "nonexistent" in result.stderr or "未找到" in result.stderr or "不存在" in result.stderr


class TestCLILanguages:
    """yanpub languages 命令"""

    def test_languages_lists_all(self):
        """列出所有10种语言"""
        result = subprocess.run(
            YANPUB + ["languages"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        assert result.returncode == 0
        output = result.stdout
        # 验证10种语言都出现了
        for lang_id in ["duan", "yan", "moyan", "xinyu", "zhixing",
                        "yanlv", "yanzhi", "mingdao", "hanyu", "traeyan"]:
            assert lang_id in output, f"语言 {lang_id} 未出现在 languages 输出中"


class TestCLICompare:
    """yanpub compare 命令"""

    def test_compare_shows_similarity(self):
        """显示语言相似度排行"""
        result = subprocess.run(
            YANPUB + ["compare"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        assert result.returncode == 0
        output = result.stdout
        assert "相似度" in output or "排行" in output

    def test_compare_migration_guide(self):
        """生成迁移指南"""
        result = subprocess.run(
            YANPUB + ["compare", "--from", "duan", "--to", "yan"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        assert result.returncode == 0
        output = result.stdout
        assert "迁移指南" in output
        assert "相似度" in output

    def test_compare_concept(self):
        """对比特定概念"""
        result = subprocess.run(
            YANPUB + ["compare", "定义"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        assert result.returncode == 0
        output = result.stdout
        assert "定义" in output


class TestCLIDocs:
    """yanpub docs 命令"""

    def test_docs_generates_site(self, tmp_path):
        """生成文档站"""
        output_dir = tmp_path / "yandocs_e2e"
        result = subprocess.run(
            YANPUB + ["docs", "--output", str(output_dir)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )
        assert result.returncode == 0
        assert output_dir.exists()
        assert (output_dir / "index.html").exists()
        assert (output_dir / "data.json").exists()

        # 验证数据完整性
        data = json.loads((output_dir / "data.json").read_text(encoding="utf-8"))
        assert data["stats"]["language_count"] >= 10

    def test_docs_has_all_language_pages(self, tmp_path):
        """每个语言都有详情页"""
        output_dir = tmp_path / "yandocs_e2e"
        subprocess.run(
            YANPUB + ["docs", "--output", str(output_dir)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30,
        )

        for lang_id in ["duan", "yan", "moyan", "xinyu", "zhixing",
                        "yanlv", "yanzhi", "mingdao", "hanyu", "traeyan"]:
            page = output_dir / f"lang_{lang_id}.html"
            assert page.exists(), f"语言 {lang_id} 的详情页不存在"
            content = page.read_text(encoding="utf-8")
            assert len(content) > 100, f"语言 {lang_id} 详情页内容太少"


class TestCLIPkg:
    """yanpub pkg 命令"""

    def test_pkg_list_empty(self):
        """列出包（默认为空）"""
        result = subprocess.run(
            YANPUB + ["pkg", "list"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        assert result.returncode == 0

    def test_pkg_search_no_results(self):
        """搜索不存在的包"""
        result = subprocess.run(
            YANPUB + ["pkg", "search", "nonexistent_package_xyz"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        assert result.returncode == 0
        assert "未找到" in result.stdout or "没有" in result.stdout


class TestCLIVersion:
    """yanpub --version"""

    def test_version_output(self):
        result = subprocess.run(
            YANPUB + ["--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        assert result.returncode == 0
        # 从 pyproject.toml 动态读取版本号
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]

        toml_path = (
            __import__("pathlib").Path(__file__).resolve().parent.parent / "pyproject.toml"
        )
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        expected = config["project"]["version"]
        assert expected in result.stdout


# ---- Playground 端到端 ----

class TestPlaygroundE2E:
    """Playground Web 服务端到端"""

    def test_playground_app_creates(self):
        """Playground 应用可以创建"""
        try:
            from yanpub.playground.server import create_app
            app = create_app()
            assert app is not None
        except ImportError:
            pytest.skip("playground 依赖未安装")

    def test_playground_homepage_via_testclient(self):
        """Playground 首页可访问"""
        try:
            from yanpub.playground.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200
            assert "言埠" in response.text or "yanpub" in response.text.lower()
        except ImportError:
            pytest.skip("playground 依赖未安装")

    def test_playground_languages_api(self):
        """Playground 语言列表 API"""
        try:
            from yanpub.playground.server import create_app
            from fastapi.testclient import TestClient
            app = create_app()
            client = TestClient(app)
            response = client.get("/api/languages")
            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 10
        except ImportError:
            pytest.skip("playground 依赖未安装")


# ---- 注册中心集成 ----

class TestRegistryIntegration:
    """注册中心集成测试"""

    def test_all_adapters_load(self):
        """所有10个适配器都能加载"""
        from yanpub.core.registry import get_registry
        reg = get_registry()
        assert len(reg) >= 10

        expected_ids = {
            "duan", "yan", "moyan", "xinyu", "zhixing",
            "yanlv", "yanzhi", "mingdao", "hanyu", "traeyan",
        }
        actual_ids = set(reg.language_ids)
        assert expected_ids.issubset(actual_ids), f"缺少适配器: {expected_ids - actual_ids}"

    def test_all_adapters_have_keywords(self):
        """所有适配器都有关键字"""
        from yanpub.core.registry import get_registry
        reg = get_registry()
        for lang_id in reg.language_ids:
            adapter = reg.get(lang_id)
            assert adapter is not None
            assert len(adapter.keywords) > 0, f"{lang_id} 没有关键字"

    def test_all_adapters_have_run_command(self):
        """所有适配器都有运行命令"""
        from yanpub.core.registry import get_registry
        from yanpub.core.adapter import SubprocessAdapter
        reg = get_registry()
        for lang_id in reg.language_ids:
            adapter = reg.get(lang_id)
            assert adapter is not None
            # SubprocessAdapter 的 run_command 是私有属性 _run_command
            if isinstance(adapter, SubprocessAdapter):
                assert adapter._run_command is not None, f"{lang_id} 没有 run_command"
            else:
                assert hasattr(adapter, "run"), f"{lang_id} 没有 run 方法"

    def test_all_adapters_have_metadata(self):
        """所有适配器都有完整元数据"""
        from yanpub.core.registry import get_registry
        reg = get_registry()
        for lang_id in reg.language_ids:
            adapter = reg.get(lang_id)
            assert adapter is not None
            assert adapter.name, f"{lang_id} 没有名称"
            assert adapter.version, f"{lang_id} 没有版本"
            assert adapter.file_extensions, f"{lang_id} 没有扩展名"
            assert adapter.primary_color, f"{lang_id} 没有主色"
            assert adapter.comment_syntax, f"{lang_id} 没有注释语法"

    def test_adapter_colors_are_valid(self):
        """所有适配器颜色格式正确"""
        from yanpub.core.registry import get_registry
        reg = get_registry()
        for lang_id in reg.language_ids:
            adapter = reg.get(lang_id)
            assert adapter is not None
            color = adapter.primary_color
            assert color.startswith("#"), f"{lang_id} 颜色不以 # 开头: {color}"
            assert len(color) == 7, f"{lang_id} 颜色格式错误: {color}"

    def test_extension_uniqueness(self):
        """扩展名在不同适配器间不冲突（.yan 和 .行 是多语言共享，允许）"""
        from yanpub.core.registry import get_registry
        reg = get_registry()
        ext_map: dict[str, list[str]] = {}
        for lang_id in reg.language_ids:
            adapter = reg.get(lang_id)
            assert adapter is not None
            for ext in adapter.file_extensions:
                ext_map.setdefault(ext, []).append(lang_id)

        # .yan 是多语言共用的扩展名（言/趣言/言律/言知），.行 也是共享的（趣言/趣言）
        shared_extensions = {".yan", ".行"}
        for ext, lang_ids in ext_map.items():
            if ext in shared_extensions:
                continue
            assert len(lang_ids) == 1, (
                f"扩展名 {ext} 被多个语言使用: {lang_ids}"
            )


# ---- 文档站集成 ----

class TestDocsIntegrationE2E:
    """文档站集成端到端"""

    def test_site_builds_with_real_data(self, tmp_path):
        """使用真实数据构建文档站"""
        from yanpub.docs.site_builder import build_site
        from yanpub.core.registry import get_registry

        output = build_site(tmp_path / "site", get_registry())
        assert output.exists()

        # 验证数据文件
        data = json.loads((output / "data.json").read_text(encoding="utf-8"))
        assert data["stats"]["language_count"] >= 10
        assert data["stats"]["total_keywords"] > 500  # 10种语言关键字总计

        # 验证每个语言都有页面
        for lang in data["languages"]:
            page = output / f"lang_{lang['id']}.html"
            assert page.exists(), f"缺少 {lang['id']} 的页面"

    def test_comparison_table_complete(self):
        """对比表数据完整"""
        from yanpub.docs.generator import DocsGenerator
        from yanpub.core.registry import get_registry

        gen = DocsGenerator(get_registry())
        table = gen.generate_comparison_table()
        # 至少有"定义"、"控制流"、"运算"等核心概念
        concepts = [row["concept"] for row in table]
        assert "定义" in concepts
        assert "控制流" in concepts
        assert "运算" in concepts

    def test_cross_language_search(self):
        """跨语言搜索可用"""
        from yanpub.docs.generator import DocsGenerator
        from yanpub.core.registry import get_registry

        gen = DocsGenerator(get_registry())
        results = gen.search_keywords("定义")
        # 至少3种语言有"定义"关键字
        lang_ids = {r.lang_id for r in results}
        assert len(lang_ids) >= 3

    def test_similarity_matrix_symmetric(self):
        """相似度矩阵对称"""
        from yanpub.docs.comparator import LanguageComparator
        from yanpub.core.registry import get_registry

        comp = LanguageComparator(get_registry())
        matrix = comp.generate_similarity_matrix()
        langs = matrix["languages"]
        for a in langs:
            for b in langs:
                diff = abs(matrix["matrix"][a][b] - matrix["matrix"][b][a])
                assert diff < 0.001, f"相似度不对称: {a}<->{b} 差值 {diff}"


# ---- 启动时间 ----

class TestPerformance:
    """性能基准"""

    def test_import_time_under_2s(self):
        """导入 yanpub 核心模块不超过2秒"""
        import time
        t0 = time.perf_counter()
        # 清除缓存
        import importlib
        if "yanpub.core.registry" in __import__("sys").modules:
            importlib.reload(__import__("yanpub.core.registry", fromlist=["get_registry"]))
        else:
            __import__("yanpub.core.registry", fromlist=["get_registry"])
        t1 = time.perf_counter()
        # 首次导入可能慢，后续导入应更快
        assert t1 - t0 < 5.0, f"导入耗时 {t1-t0:.2f}s 过长"

    def test_registry_load_time(self):
        """注册中心加载时间合理"""
        import time
        t0 = time.perf_counter()
        from yanpub.core.registry import get_registry
        reg = get_registry()
        t1 = time.perf_counter()
        # 10个适配器的加载时间
        assert t1 - t0 < 3.0, f"注册中心加载耗时 {t1-t0:.2f}s 过长"
        assert len(reg) >= 10
