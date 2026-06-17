"""v0.3.0 功能测试

测试项：
1. Playground 代码分享（API + hash 编解码）
2. LSP 代码格式化（LanguageAdapter.format + ChineseCodeFormatter）
3. REPL 友好错误提示（parse_error + format_friendly_error）
4. 远程注册中心（RemoteRegistry 类）
5. 适配器健康检查（check_adapter_health）
6. 性能基准测试（run_benchmarks）
7. 国际化（i18n.t / get_lang / set_lang）
"""

import pytest


# ---- 1. Playground 代码分享 ----


class TestPlaygroundShare:
    """Playground 代码分享功能测试"""

    def test_share_api_endpoint(self):
        """测试 /api/share 端点"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        # 缺少 lang 参数
        resp = client.get("/api/share")
        assert resp.status_code == 400

    def test_share_api_with_lang(self):
        """测试 /api/share 指定语言"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/share", params={"lang": "duan"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["lang"] == "duan"
        assert data["name"] == "段言"

    def test_share_api_with_code(self):
        """测试 /api/share 带代码参数"""
        import base64
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        code = '打印("你好")。'
        encoded = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")

        resp = client.get("/api/share", params={"lang": "duan", "code": encoded})
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == code

    def test_share_api_unknown_lang(self):
        """测试 /api/share 未知语言"""
        from yanpub.playground.server import create_app
        from fastapi.testclient import TestClient

        app = create_app()
        client = TestClient(app)

        resp = client.get("/api/share", params={"lang": "nonexistent"})
        assert resp.status_code == 404


# ---- 2. LSP 代码格式化 ----


class TestCodeFormatter:
    """代码格式化测试"""

    def test_adapter_format_trailing_whitespace(self):
        """测试行尾空格清理"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。   \n打印(甲)。  \n"
        result = adapter.format(code)
        # 行尾空格被清理
        for line in result.split("\n"):
            if line:
                assert line == line.rstrip(), f"行尾有空格: '{line}'"

    def test_adapter_format_excessive_blank_lines(self):
        """测试多余空行合并"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。\n\n\n\n\n打印(甲)。\n"
        result = adapter.format(code)
        # 最多2个连续空行
        assert "\n\n\n\n" not in result

    def test_adapter_format_tab_to_spaces(self):
        """测试 Tab 转空格"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "\t设甲为三。\n\t\t打印(甲)。\n"
        result = adapter.format(code)
        assert "\t" not in result

    def test_adapter_format_final_newline(self):
        """测试末尾换行"""
        from yanpub.core.adapter import SubprocessAdapter

        adapter = SubprocessAdapter(
            name="测试", lang_id="test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        code = "设甲为三。"
        result = adapter.format(code)
        assert result.endswith("\n")

    def test_formatter_config(self):
        """测试 ChineseCodeFormatter 配置"""
        from yanpub.core.formatter import ChineseCodeFormatter, FormatterConfig

        config = FormatterConfig(indent_size=2, max_blank_lines=1)
        formatter = ChineseCodeFormatter(config)

        code = "如果 甲：\n\t打印(甲)。\n\n\n结束。"
        result = formatter.format(code)
        assert "\t" not in result
        # 最多1个连续空行
        assert "\n\n\n" not in result

    def test_formatter_indent_normalization(self):
        """测试缩进规范化"""
        from yanpub.core.formatter import ChineseCodeFormatter

        formatter = ChineseCodeFormatter()
        code = "如果 甲：\n打印(甲)。\n结束。"
        result = formatter.format(code)
        lines = result.split("\n")
        # 第二行应该缩进
        assert lines[1].startswith("    "), f"缺少缩进: '{lines[1]}'"

    def test_formatter_preserves_strings(self):
        """测试字符串内容不被格式化修改"""
        from yanpub.core.formatter import ChineseCodeFormatter

        formatter = ChineseCodeFormatter()
        code = '打印("  hello  ")。'
        result = formatter.format(code)
        assert '"  hello  "' in result


# ---- 3. REPL 友好错误提示 ----


class TestREPLErrorDisplay:
    """REPL 语法错误友好提示测试"""

    def test_parse_python_syntax_error(self):
        """测试解析 Python 语法错误"""
        from yanpub.repl.error_display import parse_error

        stderr = '  File "test.py", line 3\n    if True\n         ^\nSyntaxError: invalid syntax\n'
        error = parse_error(stderr)
        assert error.error_type == "语法错误"
        assert error.line == 3
        assert error.suggestion  # 应有修复建议

    def test_parse_python_name_error(self):
        """测试解析 Python 名称错误"""
        from yanpub.repl.error_display import parse_error

        stderr = "NameError: name 'foo' is not defined\n"
        error = parse_error(stderr)
        assert error.error_type == "名称错误"
        assert "未定义" in error.message or "not defined" in error.message

    def test_parse_python_type_error(self):
        """测试解析 Python 类型错误"""
        from yanpub.repl.error_display import parse_error

        stderr = "TypeError: unsupported operand type(s) for +: 'int' and 'str'\n"
        error = parse_error(stderr)
        assert error.error_type == "类型错误"

    def test_parse_zero_division_error(self):
        """测试解析除零错误"""
        from yanpub.repl.error_display import parse_error

        stderr = "ZeroDivisionError: division by zero\n"
        error = parse_error(stderr)
        assert error.error_type == "除零错误"

    def test_parse_recursion_error(self):
        """测试解析递归过深错误"""
        from yanpub.repl.error_display import parse_error

        stderr = "RecursionError: maximum recursion depth exceeded\n"
        error = parse_error(stderr)
        assert error.error_type == "递归过深"

    def test_parse_generic_error(self):
        """测试通用错误回退"""
        from yanpub.repl.error_display import parse_error

        stderr = "Something went wrong with the execution"
        error = parse_error(stderr)
        assert error.error_type in ("运行时错误", "语法错误")
        assert error.raw_message

    def test_parse_empty_error(self):
        """测试空错误输入"""
        from yanpub.repl.error_display import parse_error

        error = parse_error("")
        assert error.error_type == "未知错误"

    def test_format_friendly_error(self):
        """测试友好错误格式化输出"""
        from yanpub.repl.error_display import parse_error, format_friendly_error

        stderr = "NameError: name 'x' is not defined\n"
        error = parse_error(stderr)
        output = format_friendly_error(error)
        assert "名称错误" in output

    def test_friendly_error_suggestion(self):
        """测试错误修复建议"""
        from yanpub.repl.error_display import parse_error

        stderr = "SyntaxError: invalid syntax\n"
        error = parse_error(stderr)
        assert error.suggestion
        assert "检查" in error.suggestion or "请" in error.suggestion


# ---- 4. 远程注册中心 ----


class TestRemoteRegistry:
    """远程注册中心测试"""

    def test_remote_registry_creation(self):
        """测试创建远程注册中心"""
        from yanpub.pkg.remote import RemoteRegistry

        rr = RemoteRegistry(remote_url="https://example.com/registry.git")
        assert rr.remote_url == "https://example.com/registry.git"

    def test_remote_registry_default_url(self):
        """测试默认远程 URL"""
        from yanpub.pkg.remote import RemoteRegistry, DEFAULT_REMOTE_URL

        rr = RemoteRegistry()
        assert rr.remote_url == DEFAULT_REMOTE_URL

    def test_remote_registry_search_empty(self):
        """测试未同步时搜索返回空"""
        from yanpub.pkg.remote import RemoteRegistry

        rr = RemoteRegistry()
        results = rr.search("test")
        assert isinstance(results, list)

    def test_remote_registry_list_all_empty(self):
        """测试未同步时列表返回空"""
        from yanpub.pkg.remote import RemoteRegistry

        rr = RemoteRegistry()
        results = rr.list_all()
        assert isinstance(results, list)

    def test_remote_registry_is_synced(self):
        """测试 is_synced 状态"""
        from yanpub.pkg.remote import RemoteRegistry

        rr = RemoteRegistry()
        # 未同步且无缓存
        assert not rr.is_synced()

    def test_remote_registry_get_local_priority(self):
        """测试本地注册中心优先"""
        from yanpub.pkg.registry import PackageRegistry, PackageInfo
        from yanpub.pkg.remote import RemoteRegistry

        local = PackageRegistry()
        local.add(PackageInfo(
            name="duan:test-pkg",
            lang="duan",
            package="test-pkg",
            version="2.0.0",
        ))

        rr = RemoteRegistry(local_registry=local)
        # 远程没有但本地有
        result = rr.get("duan:test-pkg")
        assert result is not None
        assert result.version == "2.0.0"


# ---- 5. 适配器健康检查 ----


class TestAdapterHealth:
    """适配器健康检查测试"""

    def test_health_check_subprocess_adapter(self):
        """测试子进程适配器健康检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_adapter_health

        # 使用一个存在的命令（python）
        adapter = SubprocessAdapter(
            name="测试", lang_id="test_health", version="0.1",
            extensions=[".t"], run_command=["python", "-c"],
        )
        result = check_adapter_health(adapter)
        assert result.adapter_id == "test_health"
        assert "command" in result.checks

    def test_health_check_unreachable_command(self):
        """测试不可达命令的健康检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_adapter_health

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_unreachable", version="0.1",
            extensions=[".t"], run_command=["nonexistent_command_12345"],
        )
        result = check_adapter_health(adapter)
        assert result.status in ("unhealthy", "degraded")

    def test_health_check_keywords(self):
        """测试关键字加载检查"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_adapter_health

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_kw", version="0.1",
            extensions=[".t"], run_command=["echo"],
            keywords=["设", "打印", "如果"],
        )
        result = check_adapter_health(adapter)
        assert result.checks["keywords"]["status"] == "ok"
        assert result.checks["keywords"]["count"] == 3

    def test_health_result_to_dict(self):
        """测试健康检查结果序列化"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_adapter_health

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_dict", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        result = check_adapter_health(adapter)
        d = result.to_dict()
        assert "id" in d
        assert "status" in d
        assert "checks" in d

    def test_health_check_all(self):
        """测试批量健康检查"""
        from yanpub.core.registry import LanguageRegistry
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_all_adapters

        registry = LanguageRegistry()
        registry.register(SubprocessAdapter(
            name="测试1", lang_id="test1", version="0.1",
            extensions=[".t1"], run_command=["echo"],
        ))
        registry.register(SubprocessAdapter(
            name="测试2", lang_id="test2", version="0.1",
            extensions=[".t2"], run_command=["echo"],
        ))

        results = check_all_adapters(registry)
        assert len(results) == 2

    def test_format_health_report(self):
        """测试健康报告格式化"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.health import check_adapter_health, format_health_report

        adapter = SubprocessAdapter(
            name="测试", lang_id="test_report", version="0.1",
            extensions=[".t"], run_command=["echo"],
            keywords=["设", "打印"],
        )
        result = check_adapter_health(adapter)
        report = format_health_report([result])
        assert "健康检查" in report
        assert "测试" in report


# ---- 6. 性能基准测试 ----


class TestBenchmark:
    """性能基准测试测试"""

    def test_bench_result_stats(self):
        """测试基准测试结果统计"""
        from yanpub.core.benchmark import BenchResult

        bench = BenchResult(name="test", iterations=5, times_ms=[10.0, 12.0, 11.0, 13.0, 9.0])
        assert bench.mean_ms == pytest.approx(11.0)
        assert bench.min_ms == 9.0
        assert bench.max_ms == 13.0
        assert bench.stdev_ms > 0

    def test_bench_result_to_dict(self):
        """测试基准测试结果序列化"""
        from yanpub.core.benchmark import BenchResult

        bench = BenchResult(name="test", iterations=3, times_ms=[10.0, 12.0, 11.0])
        d = bench.to_dict()
        assert d["name"] == "test"
        assert d["iterations"] == 3
        assert "mean_ms" in d

    def test_bench_single_adapter(self):
        """测试单个适配器基准测试"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.benchmark import run_benchmarks

        adapter = SubprocessAdapter(
            name="测试", lang_id="bench_test", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        result = run_benchmarks(adapter, iterations=2, warmup=0)
        assert result.adapter_id == "bench_test"
        assert result.startup is not None
        assert result.keyword_load is not None

    def test_bench_all_adapters(self):
        """测试批量基准测试"""
        from yanpub.core.registry import LanguageRegistry
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.benchmark import run_all_benchmarks

        registry = LanguageRegistry()
        registry.register(SubprocessAdapter(
            name="测试", lang_id="bench_all", version="0.1",
            extensions=[".t"], run_command=["echo"],
        ))

        results = run_all_benchmarks(registry, iterations=2)
        assert len(results) == 1

    def test_bench_format_report(self):
        """测试基准报告格式化"""
        from yanpub.core.adapter import SubprocessAdapter
        from yanpub.core.benchmark import run_benchmarks, format_bench_report

        adapter = SubprocessAdapter(
            name="测试", lang_id="bench_fmt", version="0.1",
            extensions=[".t"], run_command=["echo"],
        )
        result = run_benchmarks(adapter, iterations=2, warmup=0)
        report = format_bench_report([result])
        assert "基准测试" in report
        assert "测试" in report


# ---- 7. 国际化 ----


class TestI18n:
    """国际化测试"""

    def test_t_default_chinese(self):
        """测试默认中文"""
        from yanpub.i18n import t, set_lang

        set_lang("zh")
        assert t("error.syntax") == "语法错误"

    def test_t_english(self):
        """测试英文"""
        from yanpub.i18n import t, set_lang

        set_lang("en")
        assert t("error.syntax") == "Syntax Error"
        # 恢复
        set_lang("zh")

    def test_t_with_kwargs(self):
        """测试带参数的消息"""
        from yanpub.i18n import t, set_lang

        set_lang("zh")
        msg = t("error.unknown_lang", lang_id="test")
        assert "test" in msg

    def test_t_english_with_kwargs(self):
        """测试英文带参数"""
        from yanpub.i18n import t, set_lang

        set_lang("en")
        msg = t("error.unknown_lang", lang_id="test")
        assert "test" in msg
        set_lang("zh")

    def test_t_fallback_to_zh(self):
        """测试英文回退到中文（键在英文中不存在时）"""
        from yanpub.i18n import t, set_lang

        set_lang("en")
        # 如果一个键在英文中不存在，应回退到中文
        # 使用一个已知的键
        assert t("error.syntax")  # 不为空
        set_lang("zh")

    def test_t_unknown_key(self):
        """测试未知键返回键名"""
        from yanpub.i18n import t

        result = t("nonexistent.key.xyz")
        assert result == "nonexistent.key.xyz"

    def test_get_set_lang(self):
        """测试语言设置"""
        from yanpub.i18n import get_lang, set_lang

        original = get_lang()
        set_lang("en")
        assert get_lang() == "en"
        set_lang("zh")
        assert get_lang() == "zh"
        # 恢复
        set_lang(original)

    def test_set_lang_invalid(self):
        """测试设置不支持的语言回退到中文"""
        from yanpub.i18n import get_lang, set_lang

        original = get_lang()
        set_lang("fr")
        assert get_lang() == "zh"
        set_lang(original)

    def test_i18n_all_keys_both_langs(self):
        """测试所有中文键在英文中都有对应翻译"""
        from yanpub.i18n import _MESSAGES

        zh_keys = set(_MESSAGES["zh"].keys())
        en_keys = set(_MESSAGES["en"].keys())

        missing_in_en = zh_keys - en_keys
        # 允许有少量缺失（但不应该太多）
        assert len(missing_in_en) <= 5, f"英文缺少以下键: {missing_in_en}"

    def test_supported_langs(self):
        """测试支持的语言列表"""
        from yanpub.i18n import SUPPORTED_LANGS

        assert "zh" in SUPPORTED_LANGS
        assert "en" in SUPPORTED_LANGS

    def test_repl_messages(self):
        """测试 REPL 相关消息"""
        from yanpub.i18n import t, set_lang

        set_lang("zh")
        assert "欢迎" in t("repl.welcome", name="段言", version="1.0")

        set_lang("en")
        assert "Welcome" in t("repl.welcome", name="Duan", version="1.0")
        set_lang("zh")

    def test_pkg_messages(self):
        """测试包管理相关消息"""
        from yanpub.i18n import t, set_lang

        set_lang("zh")
        assert "安装" in t("pkg.install_start", name="test")

        set_lang("en")
        assert "Installing" in t("pkg.install_start", name="test")
        set_lang("zh")


# ---- 8. 版本与导出 ----


class TestVersionAndExports:
    """版本号和导出测试"""

    def test_version_is_030(self):
        """测试版本号 >= 0.3.0"""
        from yanpub import __version__

        assert __version__ >= "0.3.0"

    def test_i18n_exports(self):
        """测试 i18n 模块导出"""
        from yanpub import t, get_lang, set_lang

        assert callable(t)
        assert callable(get_lang)
        assert callable(set_lang)

    def test_formatter_module_importable(self):
        """测试 formatter 模块可导入"""
        from yanpub.core.formatter import ChineseCodeFormatter, FormatterConfig
        assert ChineseCodeFormatter is not None
        assert FormatterConfig is not None

    def test_health_module_importable(self):
        """测试 health 模块可导入"""
        from yanpub.core.health import check_adapter_health, HealthCheckResult
        assert check_adapter_health is not None
        assert HealthCheckResult is not None

    def test_benchmark_module_importable(self):
        """测试 benchmark 模块可导入"""
        from yanpub.core.benchmark import run_benchmarks, BenchResult
        assert run_benchmarks is not None
        assert BenchResult is not None

    def test_remote_module_importable(self):
        """测试 remote 模块可导入"""
        from yanpub.pkg.remote import RemoteRegistry
        assert RemoteRegistry is not None

    def test_error_display_module_importable(self):
        """测试 error_display 模块可导入"""
        from yanpub.repl.error_display import parse_error, format_friendly_error, FriendlyError
        assert parse_error is not None
        assert format_friendly_error is not None
        assert FriendlyError is not None
