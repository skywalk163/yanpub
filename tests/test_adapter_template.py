"""适配器开发模板功能测试"""

from __future__ import annotations

import pytest

from yanpub.core.adapter_template import AdapterSpec, AdapterTemplateEngine


class TestAdapterSpec:
    """测试 AdapterSpec 数据类"""

    def test_default_extensions(self):
        spec = AdapterSpec(lang_id="mylang", name="我语")
        assert spec.extensions == [".mylang"]

    def test_custom_extensions(self):
        spec = AdapterSpec(lang_id="mylang", name="我语", extensions=[".my", ".ml"])
        assert spec.extensions == [".my", ".ml"]

    def test_post_init_extensions(self):
        spec = AdapterSpec(lang_id="mylang", name="我语", extensions=[])
        # 空列表会被 __post_init__ 填充
        assert spec.extensions == [".mylang"]


class TestAdapterTemplateEngine:
    """测试 AdapterTemplateEngine"""

    @pytest.fixture
    def engine(self, tmp_path):
        return AdapterTemplateEngine(adapters_dir=tmp_path / "adapters")

    @pytest.fixture
    def sample_spec(self):
        return AdapterSpec(
            lang_id="mylang",
            name="我语",
            version="0.1.0",
            extensions=[".my"],
            comment_syntax="#",
            primary_color="#FF5733",
            run_command="python mylang.py {file}",
            eval_command="python mylang.py -e {code}",
            eval_mode="arg",
            repl_command="python mylang.py -i",
            keywords=["定义", "函数", "如果", "返回", "打印"],
            description="测试用中文编程语言",
            author="测试作者",
        )

    def test_validate_spec_valid(self, engine, sample_spec):
        errors = engine.validate_spec(sample_spec)
        assert errors == []

    def test_validate_spec_empty_lang_id(self, engine):
        spec = AdapterSpec(lang_id="", name="我语", run_command="python x.py {file}")
        errors = engine.validate_spec(spec)
        assert any("语言ID" in e for e in errors)

    def test_validate_spec_invalid_lang_id(self, engine):
        spec = AdapterSpec(lang_id="My-Lang!", name="我语", run_command="python x.py {file}")
        errors = engine.validate_spec(spec)
        assert any("语言ID" in e for e in errors)

    def test_validate_spec_empty_name(self, engine):
        spec = AdapterSpec(lang_id="mylang", name="", run_command="python x.py {file}")
        errors = engine.validate_spec(spec)
        assert any("名称" in e for e in errors)

    def test_validate_spec_bad_version(self, engine):
        spec = AdapterSpec(
            lang_id="mylang", name="我语", version="abc", run_command="python x.py {file}"
        )
        errors = engine.validate_spec(spec)
        assert any("版本" in e for e in errors)

    def test_validate_spec_bad_extension(self, engine):
        spec = AdapterSpec(
            lang_id="mylang", name="我语", extensions=["my"], run_command="python x.py {file}"
        )
        errors = engine.validate_spec(spec)
        assert any("点号" in e for e in errors)

    def test_validate_spec_no_file_placeholder(self, engine):
        spec = AdapterSpec(lang_id="mylang", name="我语", run_command="python x.py")
        errors = engine.validate_spec(spec)
        assert any("{file}" in e for e in errors)

    def test_validate_spec_already_exists(self, engine, sample_spec, tmp_path):
        # 先创建一次
        adapters_dir = tmp_path / "adapters"
        adapters_dir.mkdir()
        (adapters_dir / "mylang").mkdir()
        errors = engine.validate_spec(sample_spec)
        assert any("已存在" in e for e in errors)

    def test_validate_spec_bad_eval_mode(self, engine):
        spec = AdapterSpec(
            lang_id="mylang", name="我语", run_command="python x.py {file}", eval_mode="bad"
        )
        errors = engine.validate_spec(spec)
        assert any("eval_mode" in e for e in errors)

    def test_generate_full(self, engine, sample_spec):
        output = engine.generate(sample_spec)

        # 检查目录结构
        assert output.exists()
        assert (output / "adapter.py").exists()
        assert (output / "adapter.yaml").exists()
        assert (output / "CONTRIBUTING.md").exists()
        assert (output / "examples").exists()
        assert (output / "examples" / "hello.my").exists()
        assert (output / "examples" / "function.my").exists()

    def test_generate_adapter_py_content(self, engine, sample_spec):
        output = engine.generate(sample_spec)
        content = (output / "adapter.py").read_text(encoding="utf-8")

        # 检查关键内容
        assert "class MylangAdapter(SubprocessAdapter)" in content
        assert 'name="我语"' in content
        assert 'lang_id="mylang"' in content
        assert 'version="0.1.0"' in content
        assert "['定义', '函数', '如果', '返回', '打印']" in content
        assert 'primary_color="#FF5733"' in content
        assert "comment_syntax" in content

    def test_generate_adapter_yaml_content(self, engine, sample_spec):
        output = engine.generate(sample_spec)
        content = (output / "adapter.yaml").read_text(encoding="utf-8")

        assert "name: 我语" in content
        assert "id: mylang" in content
        assert 'version: "0.1.0"' in content
        assert "repl: true" in content
        assert '"#FF5733"' in content

    def test_generate_no_eval(self, engine, tmp_path):
        spec = AdapterSpec(
            lang_id="noeval",
            name="无求值",
            run_command="python noeval.py {file}",
            eval_command="",
            repl_command="",
        )
        output = engine.generate(spec)
        content = (output / "adapter.py").read_text(encoding="utf-8")

        assert "eval_command=None" in content
        assert "repl_command=None" in content

    def test_generate_no_keywords(self, engine, tmp_path):
        spec = AdapterSpec(
            lang_id="nokw",
            name="无关键字",
            run_command="python nokw.py {file}",
            keywords=[],
        )
        output = engine.generate(spec)
        content = (output / "adapter.py").read_text(encoding="utf-8")

        # 应包含关键字加载器骨架
        assert "load_cached_keywords" in content
        assert "fallback" in content.lower()

    def test_generate_custom_output_dir(self, engine, sample_spec, tmp_path):
        custom_dir = tmp_path / "custom_output"
        output = engine.generate(sample_spec, output_dir=custom_dir)

        assert output == custom_dir
        assert (output / "adapter.py").exists()

    def test_check_adapter_valid(self, engine, sample_spec):
        engine.generate(sample_spec)
        result = engine.check_adapter("mylang")

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert "adapter.py" in result["files"]
        assert "adapter.yaml" in result["files"]

    def test_check_adapter_nonexistent(self, engine):
        result = engine.check_adapter("nonexistent")

        assert result["valid"] is False
        assert any("不存在" in e for e in result["errors"])

    def test_check_adapter_missing_files(self, engine, tmp_path):
        adapters_dir = tmp_path / "adapters" / "incomplete"
        adapters_dir.mkdir(parents=True)

        result = engine.check_adapter("incomplete")
        assert result["valid"] is False
        assert any("adapter.py" in e for e in result["errors"])
        assert any("adapter.yaml" in e for e in result["errors"])

    def test_check_adapter_no_examples_warning(self, engine, tmp_path):
        adapters_dir = tmp_path / "adapters" / "noexamples"
        adapters_dir.mkdir(parents=True)

        # 只创建必需文件
        (adapters_dir / "adapter.py").write_text(
            "from yanpub.core.adapter.adapter import SubprocessAdapter\n"
            "class NoexamplesAdapter(SubprocessAdapter):\n"
            "    def __init__(self):\n"
            '        super().__init__(name="无示例", lang_id="noexamples", version="0.1.0", extensions=[".ne"], run_command=["echo"])\n'
            "    def run(self, file_path, args=None): return self._exec(self._run_command + [file_path])\n"
            "    def eval(self, code): return self._exec(self._eval_command, stdin=code)\n",
            encoding="utf-8",
        )
        (adapters_dir / "adapter.yaml").write_text(
            'name: 无示例\nid: noexamples\nversion: "0.1.0"\n',
            encoding="utf-8",
        )

        result = engine.check_adapter("noexamples")
        # 应有缺少 examples 的警告
        assert any("examples" in w.lower() or "示例" in w for w in result["warnings"])

    def test_check_adapter_yaml_id_mismatch(self, engine, tmp_path):
        adapters_dir = tmp_path / "adapters" / "mismatch"
        adapters_dir.mkdir(parents=True)

        (adapters_dir / "adapter.py").write_text(
            "from yanpub.core.adapter.adapter import SubprocessAdapter\n"
            "class MismatchAdapter(SubprocessAdapter):\n"
            "    def __init__(self):\n"
            '        super().__init__(name="不匹配", lang_id="mismatch", version="0.1.0", extensions=[".mm"], run_command=["echo"])\n'
            "    def run(self, file_path, args=None): return self._exec(self._run_command + [file_path])\n"
            "    def eval(self, code): return self._exec(self._eval_command, stdin=code)\n",
            encoding="utf-8",
        )
        (adapters_dir / "adapter.yaml").write_text(
            'name: 不匹配\nid: wrong_id\nversion: "0.1.0"\n',
            encoding="utf-8",
        )

        result = engine.check_adapter("mismatch")
        assert any("不匹配" in e for e in result["errors"])

    def test_examples_have_front_matter(self, engine, sample_spec):
        output = engine.generate(sample_spec)
        hello = output / "examples" / "hello.my"
        content = hello.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "title:" in content
        assert "你好世界" in content

    def test_contributing_md(self, engine, sample_spec):
        output = engine.generate(sample_spec)
        contributing = output / "CONTRIBUTING.md"
        content = contributing.read_text(encoding="utf-8")
        assert "我语" in content
        assert "mylang" in content
        assert "测试作者" in content


class TestToClassName:
    """测试 lang_id 到类名转换"""

    def test_simple(self):
        from yanpub.core.adapter_template import _to_class_name

        assert _to_class_name("mylang") == "Mylang"
        assert _to_class_name("zhixing") == "Zhixing"

    def test_with_underscore(self):
        from yanpub.core.adapter_template import _to_class_name

        assert _to_class_name("my_lang") == "MyLang"
        assert _to_class_name("test_lang_v2") == "TestLangV2"


class TestAdapterCheckIntegration:
    """集成测试 — 验证生成的适配器可被注册中心发现"""

    def test_generated_adapter_is_discoverable(self, tmp_path):
        engine = AdapterTemplateEngine(adapters_dir=tmp_path)
        spec = AdapterSpec(
            lang_id="discoverable",
            name="可发现",
            version="0.1.0",
            extensions=[".disc"],
            run_command="python disc.py {file}",
            eval_command="python disc.py -e {code}",
            eval_mode="arg",
            keywords=["定义", "函数", "打印"],
        )
        engine.generate(spec)

        result = engine.check_adapter("discoverable")
        assert result["valid"] is True
        assert len(result["errors"]) == 0
