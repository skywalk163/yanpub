"""示例代码管理功能测试"""

from __future__ import annotations

import pytest

from yanpub.core.examples import (
    ExampleInfo,
    ExampleManager,
    _build_example_file,
    _parse_front_matter,
    _scan_examples_from_dir,
    get_example_manager,
    validate_example_meta,
)


class TestFrontMatter:
    """测试 YAML front matter 解析"""

    def test_no_front_matter(self):
        content = "# 纯代码\n打印('hello')\n"
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert body == content

    def test_with_front_matter(self):
        content = "---\ntitle: 你好\ntags: [入门]\ndifficulty: 入门\n---\n打印('hello')\n"
        meta, body = _parse_front_matter(content)
        assert meta["title"] == "你好"
        assert meta["tags"] == ["入门"]
        assert meta["difficulty"] == "入门"
        assert "打印('hello')" in body
        assert "---" not in body

    def test_with_description(self):
        content = "---\ntitle: 测试\ndescription: 这是一个测试\n---\n代码\n"
        meta, body = _parse_front_matter(content)
        assert meta["title"] == "测试"
        assert meta["description"] == "这是一个测试"
        assert "代码" in body

    def test_malformed_front_matter(self):
        # 没有关闭的 ---
        content = "---\ntitle: 测试\n代码\n"
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert body == content

    def test_front_matter_not_dict(self):
        # front matter 内容不是 dict
        content = "---\n- item1\n- item2\n---\n代码\n"
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert body == content


class TestScanExamples:
    """测试目录扫描"""

    def test_scan_nonexistent_dir(self, tmp_path):
        result = _scan_examples_from_dir(tmp_path / "nonexistent", "test", "adapter")
        assert result == []

    def test_scan_empty_dir(self, tmp_path):
        result = _scan_examples_from_dir(tmp_path, "test", "adapter")
        assert result == []

    def test_scan_with_example_files(self, tmp_path):
        # 创建示例文件
        (tmp_path / "hello.txt").write_text(
            "---\ntitle: 你好世界\ntags: [入门]\n---\n打印('hello')\n",
            encoding="utf-8",
        )
        (tmp_path / "fib.txt").write_text(
            "---\ntitle: 斐波那契\ntags: [递归, 算法]\ndifficulty: 中等\n---\n递归代码\n",
            encoding="utf-8",
        )

        result = _scan_examples_from_dir(tmp_path, "testlang", "adapter")
        assert len(result) == 2
        assert result[0].name == "fib"
        assert result[0].title == "斐波那契"
        assert "递归" in result[0].tags
        assert result[0].source == "adapter"
        assert result[1].name == "hello"
        assert result[1].title == "你好世界"

    def test_scan_skip_json_yaml(self, tmp_path):
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        (tmp_path / "config.yaml").write_text("k: v", encoding="utf-8")
        (tmp_path / "hello.txt").write_text("代码\n", encoding="utf-8")

        result = _scan_examples_from_dir(tmp_path, "testlang", "adapter")
        assert len(result) == 1
        assert result[0].name == "hello"

    def test_scan_skip_hidden_files(self, tmp_path):
        (tmp_path / ".hidden").write_text("隐藏", encoding="utf-8")
        (tmp_path / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "hello.txt").write_text("代码\n", encoding="utf-8")

        result = _scan_examples_from_dir(tmp_path, "testlang", "adapter")
        assert len(result) == 1

    def test_scan_no_front_matter(self, tmp_path):
        (tmp_path / "hello.txt").write_text("打印('hello')\n", encoding="utf-8")

        result = _scan_examples_from_dir(tmp_path, "testlang", "builtin")
        assert len(result) == 1
        assert result[0].title == "hello"  # title 默认等于 name
        assert result[0].tags == []
        assert result[0].source == "builtin"


class TestExampleInfo:
    """测试 ExampleInfo 数据类"""

    def test_code_property_strips_front_matter(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text(
            "---\ntitle: 测试\n---\n打印('hello')\n",
            encoding="utf-8",
        )
        info = ExampleInfo(
            name="test",
            title="测试",
            lang_id="test",
            path=f,
            source="adapter",
        )
        code = info.code
        assert "打印('hello')" in code
        assert "---" not in code

    def test_code_property_no_front_matter(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("打印('hello')\n", encoding="utf-8")
        info = ExampleInfo(
            name="test",
            title="测试",
            lang_id="test",
            path=f,
            source="adapter",
        )
        assert info.code == "打印('hello')\n"


class TestExampleManager:
    """测试 ExampleManager"""

    @pytest.fixture
    def manager(self):
        return ExampleManager()

    def test_list_all(self, manager):
        all_examples = manager.list_all()
        # 应该发现至少几种语言的示例
        assert len(all_examples) >= 1
        # 每种语言至少有 hello 示例
        for lang_id, examples in all_examples.items():
            names = [e.name for e in examples]
            assert "hello" in names, f"{lang_id} 缺少 hello 示例"

    def test_list_for_language(self, manager):
        duan_examples = manager.list_for_language("duan")
        assert len(duan_examples) >= 1
        names = [e.name for e in duan_examples]
        assert "hello" in names

    def test_list_for_nonexistent_language(self, manager):
        examples = manager.list_for_language("nonexistent_lang")
        assert examples == []

    def test_get_example(self, manager):
        ex = manager.get_example("duan", "hello")
        assert ex is not None
        assert ex.title == "你好世界"
        assert ex.lang_id == "duan"
        assert ex.source == "adapter"

    def test_get_nonexistent_example(self, manager):
        ex = manager.get_example("duan", "nonexistent")
        assert ex is None

    def test_search(self, manager):
        results = manager.search("递归")
        assert len(results) >= 1
        # 至少段言有递归相关的示例
        duan_results = results.get("duan", [])
        assert len(duan_results) >= 1
        names = [e.name for e in duan_results]
        assert "fibonacci" in names or "hanoi" in names

    def test_search_no_results(self, manager):
        results = manager.search("zzzzzzz_nonexistent")
        assert len(results) == 0

    def test_refresh(self, manager):
        # 先获取一次缓存
        manager.list_all()
        assert manager._cache is not None
        # 刷新后缓存应被清除
        manager.refresh()
        assert manager._cache is None

    def test_all_languages_have_examples(self, manager):
        """所有已注册语言都应有示例"""
        from yanpub.core.adapter.registry import get_registry

        registry = get_registry()
        all_examples = manager.list_all()

        for adapter in registry:
            assert adapter.id in all_examples, f"{adapter.name} ({adapter.id}) 没有示例"

    def test_example_source_is_adapter(self, manager):
        """适配器目录下的示例来源应为 adapter"""
        duan_examples = manager.list_for_language("duan")
        for ex in duan_examples:
            assert ex.source == "adapter"

    def test_example_difficulty_and_tags(self, manager):
        """示例应有难度和标签"""
        duan_examples = manager.list_for_language("duan")
        hello = next(e for e in duan_examples if e.name == "hello")
        assert hello.difficulty == "入门"
        assert "入门" in hello.tags


class TestExampleManagerSingleton:
    """测试全局单例"""

    def test_get_example_manager_returns_instance(self):
        mgr = get_example_manager()
        assert isinstance(mgr, ExampleManager)

    def test_singleton(self):
        mgr1 = get_example_manager()
        mgr2 = get_example_manager()
        assert mgr1 is mgr2


class TestValidateExampleMeta:
    """测试示例元数据验证"""

    def test_valid_meta(self):
        issues = validate_example_meta(
            name="hello",
            title="你好世界",
            code="打印('hello')",
            lang_id="duan",
            tags=["入门"],
            difficulty="入门",
        )
        assert issues == []

    def test_empty_name(self):
        issues = validate_example_meta(
            name="",
            title="标题",
            code="代码",
            lang_id="duan",
        )
        assert any("名称不能为空" in i for i in issues)

    def test_unsafe_name_characters(self):
        issues = validate_example_meta(
            name="hello/world",
            title="标题",
            code="代码",
            lang_id="duan",
        )
        assert any("不安全字符" in i for i in issues)

    def test_chinese_name_allowed(self):
        issues = validate_example_meta(
            name="排序算法",
            title="排序",
            code="代码",
            lang_id="duan",
        )
        assert issues == []

    def test_empty_title(self):
        issues = validate_example_meta(
            name="hello",
            title="",
            code="代码",
            lang_id="duan",
        )
        assert any("标题不能为空" in i for i in issues)

    def test_empty_code(self):
        issues = validate_example_meta(
            name="hello",
            title="标题",
            code="",
            lang_id="duan",
        )
        assert any("代码不能为空" in i for i in issues)

    def test_unknown_language(self):
        issues = validate_example_meta(
            name="hello",
            title="标题",
            code="代码",
            lang_id="nonexistent_lang_xyz",
        )
        assert any("未知语言" in i for i in issues)

    def test_invalid_difficulty(self):
        issues = validate_example_meta(
            name="hello",
            title="标题",
            code="代码",
            lang_id="duan",
            difficulty="地狱级",
        )
        assert any("难度取值不合法" in i for i in issues)

    def test_valid_difficulties(self):
        for diff in ("", "入门", "简单", "中等", "困难"):
            issues = validate_example_meta(
                name="hello",
                title="标题",
                code="代码",
                lang_id="duan",
                difficulty=diff,
            )
            assert issues == [], f"difficulty={diff!r} 应通过验证"

    def test_empty_tag(self):
        issues = validate_example_meta(
            name="hello",
            title="标题",
            code="代码",
            lang_id="duan",
            tags=["算法", ""],
        )
        assert any("标签为空" in i for i in issues)


class TestBuildExampleFile:
    """测试示例文件构建"""

    def test_minimal(self):
        content = _build_example_file(
            title="测试",
            tags=[],
            difficulty="",
            description="",
            author="",
            code="打印('hello')",
        )
        assert content.startswith("---\n")
        assert "title: 测试" in content
        assert "---\n" in content[4:]  # 关闭的 ---
        assert "打印('hello')" in content

    def test_full_meta(self):
        content = _build_example_file(
            title="排序",
            tags=["算法", "递归"],
            difficulty="中等",
            description="排序算法示例",
            author="张三",
            code="排序([3,1,2])",
        )
        assert "title: 排序" in content
        assert "算法" in content
        assert "递归" in content
        assert "difficulty: 中等" in content
        assert "description: 排序算法示例" in content
        assert "author: 张三" in content
        assert "排序([3,1,2])" in content

    def test_roundtrip(self):
        """构建的文件应能被 _parse_front_matter 正确解析"""
        content = _build_example_file(
            title="回环测试",
            tags=["测试"],
            difficulty="简单",
            description="回环测试描述",
            author="李四",
            code="打印('roundtrip')",
        )
        meta, body = _parse_front_matter(content)
        assert meta["title"] == "回环测试"
        assert "测试" in meta["tags"]
        assert meta["difficulty"] == "简单"
        assert meta["description"] == "回环测试描述"
        assert meta["author"] == "李四"
        assert "打印('roundtrip')" in body


class TestContributeExample:
    """测试贡献示例功能"""

    @pytest.fixture
    def manager(self, tmp_path):
        """创建一个使用临时目录的 ExampleManager"""
        mgr = ExampleManager()
        # 不使用全局缓存
        return mgr

    def test_contribute_creates_file(self, manager, tmp_path):
        file_path = manager.contribute_example(
            lang_id="duan",
            name="test_contribute",
            code="设甲为三",
            title="贡献测试",
            tags=["测试"],
            difficulty="入门",
            description="测试贡献",
            author="测试者",
            output_dir=tmp_path,
        )
        assert file_path.exists()
        content = file_path.read_text(encoding="utf-8")
        assert "title: 贡献测试" in content
        assert "author: 测试者" in content
        assert "设甲为三" in content

    def test_contribute_file_has_correct_extension(self, manager, tmp_path):
        file_path = manager.contribute_example(
            lang_id="duan",
            name="ext_test",
            code="代码",
            title="扩展名测试",
            output_dir=tmp_path,
        )
        # duan 适配器的扩展名包含 .段 和 .duan
        assert file_path.suffix in (".段", ".duan")

    def test_contribute_validates_name(self, manager, tmp_path):
        with pytest.raises(ValueError, match="验证失败"):
            manager.contribute_example(
                lang_id="duan",
                name="bad/name",
                code="代码",
                output_dir=tmp_path,
            )

    def test_contribute_validates_empty_code(self, manager, tmp_path):
        with pytest.raises(ValueError, match="验证失败"):
            manager.contribute_example(
                lang_id="duan",
                name="empty_code",
                code="",
                output_dir=tmp_path,
            )

    def test_contribute_validates_unknown_language(self, manager, tmp_path):
        # validate_example_meta 在 output_dir 提供时仍会检测语言，
        # 但 contribute_example 会先抛出 ValueError（包含"未知语言"信息）
        with pytest.raises((ValueError, FileNotFoundError)):
            manager.contribute_example(
                lang_id="nonexistent_lang_xyz",
                name="test",
                code="代码",
                output_dir=tmp_path,
            )

    def test_contribute_creates_output_dir(self, manager, tmp_path):
        new_dir = tmp_path / "new_examples"
        file_path = manager.contribute_example(
            lang_id="duan",
            name="mkdir_test",
            code="代码",
            output_dir=new_dir,
        )
        assert new_dir.exists()
        assert file_path.exists()

    def test_contribute_clears_cache(self, manager, tmp_path):
        # 先填充缓存
        manager.list_all()
        assert manager._cache is not None
        # 贡献后缓存应被清除
        manager.contribute_example(
            lang_id="duan",
            name="cache_test",
            code="代码",
            output_dir=tmp_path,
        )
        assert manager._cache is None


class TestExampleInfoAuthor:
    """测试 ExampleInfo 的 author 字段"""

    def test_author_default_empty(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("代码\n", encoding="utf-8")
        info = ExampleInfo(
            name="test",
            title="测试",
            lang_id="test",
            path=f,
            source="adapter",
        )
        assert info.author == ""

    def test_author_from_front_matter(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text(
            "---\ntitle: 测试\nauthor: 张三\n---\n代码\n",
            encoding="utf-8",
        )
        results = _scan_examples_from_dir(tmp_path, "test", "adapter")
        assert len(results) == 1
        assert results[0].author == "张三"
