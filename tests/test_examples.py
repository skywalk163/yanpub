"""示例代码管理功能测试"""

from __future__ import annotations

import pytest

from yanpub.core.examples import (
    ExampleInfo,
    ExampleManager,
    _parse_front_matter,
    _scan_examples_from_dir,
    get_example_manager,
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
        from yanpub.core.registry import get_registry

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
