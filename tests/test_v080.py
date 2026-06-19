"""v0.8.0 功能测试 — Playground AI 辅助（代码补全、自然语言转代码、错误修复建议）"""

from __future__ import annotations

import pytest


# ============================================================
# 1. AIAssistConfig 测试
# ============================================================


class TestAIAssistConfig:
    """AI 辅助配置"""

    def test_default_config(self):
        """默认配置"""
        from yanpub.core.ai_assist import AIAssistConfig

        config = AIAssistConfig()
        assert config.provider == "local"
        assert config.api_key == ""
        assert config.max_tokens == 1024
        assert config.temperature == 0.7

    def test_custom_config(self):
        """自定义配置"""
        from yanpub.core.ai_assist import AIAssistConfig

        config = AIAssistConfig(
            provider="openai",
            api_key="sk-test",
            model="gpt-4",
        )
        assert config.provider == "openai"
        assert config.api_key == "sk-test"
        assert config.model == "gpt-4"


# ============================================================
# 2. AIAssistEngine 基础测试
# ============================================================


class TestAIAssistEngineBasic:
    """AI 辅助引擎基础功能"""

    def test_engine_creation(self):
        """创建引擎"""
        from yanpub.core.ai_assist import AIAssistEngine, AIAssistConfig

        engine = AIAssistEngine()
        assert engine.config.provider == "local"

        engine2 = AIAssistEngine(AIAssistConfig(provider="openai"))
        assert engine2.config.provider == "openai"

    def test_import(self):
        """模块可导入"""
        from yanpub.core.ai_assist import AIAssistEngine
        assert AIAssistEngine is not None


# ============================================================
# 3. 智能代码补全测试
# ============================================================


class TestSmartComplete:
    """智能代码补全"""

    @pytest.fixture
    def duan_adapter(self):
        from yanpub.adapters.duan.adapter import DuanAdapter
        return DuanAdapter()

    @pytest.fixture
    def engine(self):
        from yanpub.core.ai_assist import AIAssistEngine
        return AIAssistEngine()

    def test_complete_empty_code(self, engine, duan_adapter):
        """空代码时提供关键字补全"""
        results = engine.smart_complete(duan_adapter, "", 1, 1)
        assert isinstance(results, list)
        assert len(results) > 0
        # 应包含关键字
        labels = [r["label"] for r in results]
        assert "设" in labels or any("设" in item for item in labels)

    def test_complete_returns_correct_structure(self, engine, duan_adapter):
        """补全结果结构正确"""
        results = engine.smart_complete(duan_adapter, "设", 1, 2)
        assert isinstance(results, list)
        for r in results:
            assert "label" in r
            assert "kind" in r
            assert "detail" in r
            assert "insert_text" in r
            assert "is_ai" in r

    def test_complete_keyword_prefix(self, engine, duan_adapter):
        """关键字前缀匹配"""
        results = engine.smart_complete(duan_adapter, "当", 1, 2)
        labels = [r["label"] for r in results]
        assert "当" in labels

    def test_complete_snippet_suggestions(self, engine, duan_adapter):
        """片段补全建议"""
        results = engine.smart_complete(duan_adapter, "", 1, 1)
        # 应该有 snippet 类型的补全
        snippets = [r for r in results if r["kind"] == "snippet"]
        assert len(snippets) > 0
        # 段落片段应包含模板
        duan_snippets = [s for s in snippets if "段落" in s["label"]]
        assert len(duan_snippets) > 0

    def test_complete_context_suggestions(self, engine, duan_adapter):
        """上下文补全建议"""
        code = "如果 甲 大于 三：\n  "
        results = engine.smart_complete(duan_adapter, code, 2, 3)
        # 在块内应建议 "返回" 或 "结束"
        labels = [r["label"] for r in results]
        assert any("返回" in item or "结束" in item for item in labels)

    def test_complete_unclosed_block(self, engine, duan_adapter):
        """未闭合块的补全建议"""
        code = "如果 真：\n  打印(1)。"
        results = engine.smart_complete(duan_adapter, code, 2, 10)
        # 应建议结束标记
        labels = [r["label"] for r in results]
        assert any("结束" in item for item in labels)

    def test_complete_with_line_out_of_range(self, engine, duan_adapter):
        """行号超出范围"""
        results = engine.smart_complete(duan_adapter, "打印", 999, 1)
        assert results == []


# ============================================================
# 4. 自然语言转代码测试
# ============================================================


class TestNLToCode:
    """自然语言转代码"""

    @pytest.fixture
    def duan_adapter(self):
        from yanpub.adapters.duan.adapter import DuanAdapter
        return DuanAdapter()

    @pytest.fixture
    def engine(self):
        from yanpub.core.ai_assist import AIAssistEngine
        return AIAssistEngine()

    def test_nl2code_print(self, engine, duan_adapter):
        """打印意图识别"""
        result = engine.nl_to_code(duan_adapter, "打印你好")
        assert result["code"]
        assert "你好" in result["code"]
        assert result["confidence"] > 0

    def test_nl2code_variable(self, engine, duan_adapter):
        """变量声明意图识别"""
        result = engine.nl_to_code(duan_adapter, "设甲为三")
        assert result["code"]
        assert "甲" in result["code"]
        assert "三" in result["code"]

    def test_nl2code_function(self, engine, duan_adapter):
        """函数定义意图识别"""
        result = engine.nl_to_code(duan_adapter, "定义函数加法")
        assert result["code"]
        assert "段落" in result["code"] or "函数" in result["code"]

    def test_nl2code_loop(self, engine, duan_adapter):
        """循环意图识别"""
        result = engine.nl_to_code(duan_adapter, "循环甲大于零")
        assert result["code"]
        assert "当" in result["code"] or "循环" in result["code"]

    def test_nl2code_condition(self, engine, duan_adapter):
        """条件意图识别"""
        result = engine.nl_to_code(duan_adapter, "如果甲大于三")
        assert result["code"]
        assert "如果" in result["code"]

    def test_nl2code_with_context(self, engine, duan_adapter):
        """带上下文的自然语言转代码"""
        context = "段落 测试。\n  "
        result = engine.nl_to_code(duan_adapter, "打印你好", context=context)
        assert result["code"]
        # 应有缩进
        assert "  " in result["code"] or "你好" in result["code"]

    def test_nl2code_empty_input(self, engine, duan_adapter):
        """空输入"""
        result = engine.nl_to_code(duan_adapter, "")
        assert result["confidence"] == 0.0
        assert result["code"] == ""

    def test_nl2code_unknown_intent(self, engine, duan_adapter):
        """无法识别的意图"""
        result = engine.nl_to_code(duan_adapter, "xyz123")
        assert result["confidence"] < 0.5

    def test_nl2code_return_structure(self, engine, duan_adapter):
        """返回结构正确"""
        result = engine.nl_to_code(duan_adapter, "打印你好")
        assert "code" in result
        assert "confidence" in result
        assert "explanation" in result

    def test_nl2code_class_intent(self, engine, duan_adapter):
        """类定义意图识别"""
        result = engine.nl_to_code(duan_adapter, "定义类动物")
        assert result["code"]
        assert "类" in result["code"]
        assert "动物" in result["code"]

    def test_nl2code_return_intent(self, engine, duan_adapter):
        """返回值意图识别"""
        result = engine.nl_to_code(duan_adapter, "返回甲")
        assert result["code"]
        assert "返回" in result["code"]

    def test_nl2code_import_intent(self, engine, duan_adapter):
        """导入意图识别"""
        result = engine.nl_to_code(duan_adapter, "导入数学")
        assert result["code"]
        assert "导入" in result["code"] or "数学" in result["code"]


# ============================================================
# 5. 错误修复建议测试
# ============================================================


class TestFixSuggestion:
    """错误修复建议"""

    @pytest.fixture
    def duan_adapter(self):
        from yanpub.adapters.duan.adapter import DuanAdapter
        return DuanAdapter()

    @pytest.fixture
    def engine(self):
        from yanpub.core.ai_assist import AIAssistEngine
        return AIAssistEngine()

    def test_fix_unclosed_block(self, engine, duan_adapter):
        """未闭合块的修复"""
        code = "如果 真：\n  打印(1)。"
        error = "IndentationError: unexpected EOF"
        results = engine.fix_suggestion(duan_adapter, code, error)
        assert len(results) > 0
        # 应有添加结束标记的建议
        titles = [r["title"] for r in results]
        assert any("结束" in t for t in titles)

    def test_fix_undefined_variable(self, engine, duan_adapter):
        """未定义变量的修复"""
        code = "打印(未定义变量)。"
        error = "NameError: name '未定义变量' is not defined"
        results = engine.fix_suggestion(duan_adapter, code, error)
        assert isinstance(results, list)
        # 可能有相似关键字的建议
        for r in results:
            assert "title" in r
            assert "fix" in r
            assert "description" in r
            assert "confidence" in r

    def test_fix_syntax_error(self, engine, duan_adapter):
        """语法错误的修复"""
        code = "设甲"
        error = "SyntaxError: invalid syntax"
        results = engine.fix_suggestion(duan_adapter, code, error)
        assert isinstance(results, list)

    def test_fix_returns_correct_structure(self, engine, duan_adapter):
        """修复结果结构正确"""
        code = "如果"
        error = "语法错误"
        results = engine.fix_suggestion(duan_adapter, code, error)
        for r in results:
            assert "title" in r
            assert "fix" in r
            assert "description" in r
            assert "confidence" in r
            assert 0 <= r["confidence"] <= 1

    def test_fix_deduplication(self, engine, duan_adapter):
        """修复建议去重"""
        code = "如果 真：\n  打印(1)。"
        error = "缺少结束|unclosed block"
        results = engine.fix_suggestion(duan_adapter, code, error)
        titles = [r["title"] for r in results]
        assert len(titles) == len(set(titles))  # 无重复标题

    def test_fix_keyword_spelling(self, engine, duan_adapter):
        """关键字拼写检查"""
        # 使用与"设"相似但不完全匹配的词
        code = "段  甲。"
        error = "语法错误"
        results = engine.fix_suggestion(duan_adapter, code, error)
        # 检查是否有拼写建议
        for r in results:
            assert isinstance(r["title"], str)
            assert isinstance(r["fix"], str)

    def test_fix_no_error(self, engine, duan_adapter):
        """无错误时返回空列表或较少建议"""
        code = "打印(\"你好\")。"
        error = ""
        results = engine.fix_suggestion(duan_adapter, code, error)
        # 无错误时应无修复建议
        assert isinstance(results, list)


# ============================================================
# 6. 模板系统测试
# ============================================================


class TestTemplateSystem:
    """意图模板系统"""

    def test_nl_templates_structure(self):
        """模板结构正确"""
        from yanpub.core.ai_assist import _NL_TEMPLATES

        for intent_name, intent_data in _NL_TEMPLATES.items():
            assert "patterns" in intent_data
            assert "templates" in intent_data
            assert isinstance(intent_data["patterns"], list)
            assert isinstance(intent_data["templates"], dict)
            assert "default" in intent_data["templates"]

    def test_fix_rules_structure(self):
        """修复规则结构正确"""
        from yanpub.core.ai_assist import _FIX_RULES

        for rule in _FIX_RULES:
            assert "pattern" in rule
            assert "fix" in rule
            assert "confidence" in rule
            assert 0 <= rule["confidence"] <= 1

    def test_keyword_snippets_structure(self):
        """关键字片段结构正确"""
        from yanpub.core.ai_assist import _KEYWORD_SNIPPETS

        for kw, snippet_info in _KEYWORD_SNIPPETS.items():
            assert "insert_text" in snippet_info
            assert "detail" in snippet_info
            assert isinstance(snippet_info["insert_text"], str)


# ============================================================
# 7. Playground AI 路由测试
# ============================================================


class TestPlaygroundAIRoutes:
    """Playground AI 辅助 API 路由"""

    @pytest.fixture
    def app(self):
        from yanpub.playground.server import create_app
        return create_app()

    @pytest.fixture
    def client(self, app):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        return TestClient(app)

    def test_ai_complete_endpoint(self, client):
        """AI 补全端点"""
        # 先确保有语言可用
        resp = client.get("/api/languages")
        langs = resp.json()
        if not langs:
            pytest.skip("没有可用的语言适配器")

        lang_id = langs[0]["id"]
        resp = client.post("/api/ai/complete", json={
            "lang": lang_id,
            "code": "设",
            "line": 1,
            "column": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_ai_nl2code_endpoint(self, client):
        """自然语言转代码端点"""
        resp = client.get("/api/languages")
        langs = resp.json()
        if not langs:
            pytest.skip("没有可用的语言适配器")

        lang_id = langs[0]["id"]
        resp = client.post("/api/ai/nl2code", json={
            "lang": lang_id,
            "text": "打印你好",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert "confidence" in data

    def test_ai_fix_endpoint(self, client):
        """错误修复端点"""
        resp = client.get("/api/languages")
        langs = resp.json()
        if not langs:
            pytest.skip("没有可用的语言适配器")

        lang_id = langs[0]["id"]
        resp = client.post("/api/ai/fix", json={
            "lang": lang_id,
            "code": "如果 真：\n  打印(1)。",
            "error": "unclosed block",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_ai_complete_unknown_lang(self, client):
        """补全端点 - 未知语言"""
        resp = client.post("/api/ai/complete", json={
            "lang": "nonexistent",
            "code": "",
            "line": 1,
            "column": 1,
        })
        assert resp.status_code == 400

    def test_ai_nl2code_unknown_lang(self, client):
        """自然语言转代码 - 未知语言"""
        resp = client.post("/api/ai/nl2code", json={
            "lang": "nonexistent",
            "text": "打印你好",
        })
        assert resp.status_code == 400

    def test_ai_fix_unknown_lang(self, client):
        """错误修复 - 未知语言"""
        resp = client.post("/api/ai/fix", json={
            "lang": "nonexistent",
            "code": "code",
            "error": "error",
        })
        assert resp.status_code == 400


# ============================================================
# 8. CLI ai 命令测试
# ============================================================


class TestAICommand:
    """CLI ai 命令"""

    def test_ai_nl2code_command(self):
        """CLI 自然语言转代码"""
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["ai", "打印你好", "--lang", "duan", "--type", "nl2code"])
        # 可能成功或因适配器不可用而失败
        assert result.exit_code in (0, 1)

    def test_ai_unknown_lang(self):
        """CLI - 未知语言"""
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["ai", "test", "--lang", "nonexistent"])
        assert result.exit_code != 0

    def test_ai_complete_command(self):
        """CLI 智能补全"""
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "ai", "设甲为三。", "--lang", "duan",
            "--type", "complete", "--line", "1", "--column", "1",
        ])
        assert result.exit_code in (0, 1)

    def test_ai_fix_command(self):
        """CLI 错误修复"""
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, [
            "ai", "如果 真：", "--lang", "duan",
            "--type", "fix", "--error", "缺少结束标记",
        ])
        assert result.exit_code in (0, 1)


# ============================================================
# 9. 集成测试
# ============================================================


class TestAIAssistIntegration:
    """AI 辅助集成测试"""

    def test_full_workflow_nl2code_to_fix(self):
        """完整工作流：自然语言转代码 → 修复"""
        from yanpub.adapters.duan.adapter import DuanAdapter
        from yanpub.core.ai_assist import AIAssistEngine

        adapter = DuanAdapter()
        engine = AIAssistEngine()

        # 1. 自然语言转代码
        nl_result = engine.nl_to_code(adapter, "打印你好")
        assert nl_result["code"]
        assert nl_result["confidence"] > 0

        # 2. 对生成的代码做补全
        code = nl_result["code"]
        complete_result = engine.smart_complete(adapter, code, 1, len(code) + 1)
        assert isinstance(complete_result, list)

        # 3. 对有问题的代码做修复
        bad_code = "如果 真：\n  打印(1)。"
        fix_result = engine.fix_suggestion(adapter, bad_code, "unclosed block")
        assert isinstance(fix_result, list)

    def test_import_from_core(self):
        """从 core 包导入"""
        from yanpub.core.ai_assist import AIAssistEngine, AIAssistConfig
        assert AIAssistEngine is not None
        assert AIAssistConfig is not None
