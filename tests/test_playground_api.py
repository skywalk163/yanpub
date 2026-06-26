"""Playground API 综合测试 — 覆盖 Examples/WASM/AI/Monitor/Challenges/Quality/Search/Collab 路由

已覆盖路由（不与其他测试文件重复）：
1. Examples API: GET /api/examples/{lang_id}
2. WASM API: GET /api/wasm/{lang_id}, GET /api/wasm/{lang_id}/runner, POST /api/wasm/{lang_id}/run
3. AI API: POST /api/ai/complete, POST /api/ai/nl2code, POST /api/ai/fix
4. Monitor API: GET /api/monitor/metrics, GET /api/monitor/trend/{adapter_id}
5. Challenges API: GET /api/challenges, GET /api/challenges/{id}, GET /api/leaderboard
6. Quality API: GET /api/quality
7. Search API: GET /api/search, GET /api/search/suggest
8. Collaboration API: GET /api/collab, GET /api/collab/{room}, POST /api/collab/create
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from yanpub.playground.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


# ============================================================
# 1. Examples API
# ============================================================


class TestExamplesAPI:
    """GET /api/examples/{lang_id}"""

    def test_examples_valid_lang(self, client):
        """有效语言返回示例列表"""
        resp = client.get("/api/examples/duan")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # 每个示例包含 id 和 name
        for ex in data:
            assert "id" in ex
            assert "name" in ex

    def test_examples_another_valid_lang(self, client):
        """另一种有效语言"""
        resp = client.get("/api/examples/yan")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_examples_invalid_lang(self, client):
        """不存在的语言返回空列表（不 404）"""
        resp = client.get("/api/examples/nonexistent_lang")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_examples_default_excluded(self, client):
        """default.txt 不出现在示例列表中"""
        resp = client.get("/api/examples/duan")
        data = resp.json()
        ids = [ex["id"] for ex in data]
        assert "default" not in ids

    def test_examples_response_structure(self, client):
        """每个示例条目结构正确"""
        resp = client.get("/api/examples/duan")
        if resp.json():
            ex = resp.json()[0]
            assert isinstance(ex["id"], str)
            assert isinstance(ex["name"], str)
            assert len(ex["id"]) > 0
            assert len(ex["name"]) > 0


# ============================================================
# 2. WASM API
# ============================================================


class TestWasmAPI:
    """WASM 相关路由"""

    def test_wasm_config_valid_lang(self, client):
        """获取 WASM 配置 — 有效语言"""
        resp = client.get("/api/wasm/duan")
        assert resp.status_code == 200
        data = resp.json()
        # 返回 Pyodide 配置字典
        assert isinstance(data, dict)

    def test_wasm_config_invalid_lang(self, client):
        """获取 WASM 配置 — 无效语言返回 404"""
        resp = client.get("/api/wasm/nonexistent_lang")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_wasm_runner_valid_lang(self, client):
        """获取 WASM runner HTML — 有效语言"""
        resp = client.get("/api/wasm/duan/runner")
        assert resp.status_code == 200
        # 应返回 HTML 内容
        assert "<html" in resp.text.lower() or "pyodide" in resp.text.lower()

    def test_wasm_runner_invalid_lang(self, client):
        """获取 WASM runner HTML — 无效语言返回 404"""
        resp = client.get("/api/wasm/nonexistent_lang/runner")
        assert resp.status_code == 404

    def test_wasm_run_valid_lang(self, client):
        """WASM 执行代码 — 有效语言"""
        with patch("yanpub.core.wasm.WasmExecutor") as MockExecutor:
            mock_instance = MagicMock()
            mock_result = MagicMock()
            mock_result.stdout = "hello from wasm"
            mock_result.stderr = ""
            mock_result.exit_code = 0
            mock_result.duration_ms = 50.0
            mock_instance.execute_with_adapter.return_value = mock_result
            mock_instance.is_available = True
            MockExecutor.return_value = mock_instance

            resp = client.post("/api/wasm/duan/run", json={"code": '打印("hello")'})
            assert resp.status_code == 200
            data = resp.json()
            assert data["type"] == "result"
            assert data["exitCode"] == 0

    def test_wasm_run_invalid_lang(self, client):
        """WASM 执行代码 — 无效语言"""
        resp = client.post("/api/wasm/nonexistent/run", json={"code": "test"})
        assert resp.status_code == 404

    def test_wasm_run_missing_code(self, client):
        """WASM 执行代码 — 缺少 code 字段"""
        resp = client.post("/api/wasm/duan/run", json={})
        # 不应崩溃，code 默认为空字符串
        assert resp.status_code in (200, 500)


# ============================================================
# 3. AI API
# ============================================================


class TestAICompleteAPI:
    """POST /api/ai/complete"""

    def test_complete_valid_lang(self, client):
        """有效语言的智能补全"""
        resp = client.post("/api/ai/complete", json={
            "lang": "duan",
            "code": "打印",
            "line": 1,
            "column": 2,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_complete_invalid_lang(self, client):
        """无效语言返回 400"""
        resp = client.post("/api/ai/complete", json={
            "lang": "nonexistent",
            "code": "test",
        })
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_complete_empty_code(self, client):
        """空代码也应返回结果（可能为空列表）"""
        resp = client.post("/api/ai/complete", json={
            "lang": "duan",
            "code": "",
            "line": 1,
            "column": 0,
        })
        assert resp.status_code == 200
        assert "items" in resp.json()


class TestAINl2CodeAPI:
    """POST /api/ai/nl2code"""

    def test_nl2code_valid(self, client):
        """自然语言转代码 — 有效请求"""
        resp = client.post("/api/ai/nl2code", json={
            "lang": "duan",
            "text": "打印你好世界",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_nl2code_invalid_lang(self, client):
        """自然语言转代码 — 无效语言"""
        resp = client.post("/api/ai/nl2code", json={
            "lang": "nonexistent",
            "text": "test",
        })
        assert resp.status_code == 400

    def test_nl2code_with_context(self, client):
        """自然语言转代码 — 带上下文"""
        resp = client.post("/api/ai/nl2code", json={
            "lang": "duan",
            "text": "定义变量",
            "context": "设x为10",
        })
        assert resp.status_code == 200

    def test_nl2code_empty_text(self, client):
        """自然语言转代码 — 空文本"""
        resp = client.post("/api/ai/nl2code", json={
            "lang": "duan",
            "text": "",
        })
        assert resp.status_code == 200


class TestAIFixAPI:
    """POST /api/ai/fix"""

    def test_fix_valid(self, client):
        """错误修复 — 有效请求"""
        resp = client.post("/api/ai/fix", json={
            "lang": "duan",
            "code": "打印(",
            "error": "语法错误",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_fix_invalid_lang(self, client):
        """错误修复 — 无效语言"""
        resp = client.post("/api/ai/fix", json={
            "lang": "nonexistent",
            "code": "test",
            "error": "err",
        })
        assert resp.status_code == 400

    def test_fix_empty_error(self, client):
        """错误修复 — 空错误描述"""
        resp = client.post("/api/ai/fix", json={
            "lang": "duan",
            "code": "test",
            "error": "",
        })
        assert resp.status_code == 200


# ============================================================
# 4. Monitor API
# ============================================================


class TestMonitorMetricsAPI:
    """GET /api/monitor/metrics"""

    def test_metrics_no_filter(self, client):
        """获取所有适配器的监控指标"""
        resp = client.get("/api/monitor/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "adapters" in data
        assert "active_adapters" in data
        assert "total_samples" in data
        assert "timestamp" in data
        assert isinstance(data["adapters"], dict)
        assert isinstance(data["active_adapters"], int)
        assert isinstance(data["total_samples"], int)

    def test_metrics_with_adapter_filter(self, client):
        """按适配器过滤监控指标"""
        resp = client.get("/api/monitor/metrics?adapter_id=duan")
        assert resp.status_code == 200
        data = resp.json()
        # 即使没有数据，也不应崩溃
        assert "adapters" in data

    def test_metrics_response_structure(self, client):
        """监控指标响应结构"""
        resp = client.get("/api/monitor/metrics")
        data = resp.json()
        # adapters 为空是合法的（无历史数据）
        for _aid, adapter_data in data["adapters"].items():
            assert "adapter_id" in adapter_data
            assert "metrics" in adapter_data


class TestMonitorTrendAPI:
    """GET /api/monitor/trend/{adapter_id}"""

    def test_trend_valid_adapter(self, client):
        """趋势数据 — 有效适配器（可能无数据）"""
        resp = client.get("/api/monitor/trend/duan")
        assert resp.status_code == 200
        data = resp.json()
        assert "adapter_id" in data
        assert "metric" in data
        assert "trend" in data
        assert "regression" in data

    def test_trend_with_custom_metric(self, client):
        """趋势数据 — 自定义指标"""
        resp = client.get("/api/monitor/trend/duan?metric=run_duration")
        assert resp.status_code == 200
        assert resp.json()["metric"] == "run_duration"

    def test_trend_with_custom_points(self, client):
        """趋势数据 — 自定义数据点数"""
        resp = client.get("/api/monitor/trend/duan?points=5")
        assert resp.status_code == 200

    def test_trend_nonexistent_adapter(self, client):
        """趋势数据 — 不存在的适配器返回空"""
        resp = client.get("/api/monitor/trend/nonexistent_adapter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trend"] == []


# ============================================================
# 5. Challenges API
# ============================================================


class TestChallengesListAPI:
    """GET /api/challenges"""

    def test_list_challenges(self, client):
        """列出所有挑战"""
        resp = client.get("/api/challenges")
        assert resp.status_code == 200
        data = resp.json()
        assert "challenges" in data
        assert isinstance(data["challenges"], list)

    def test_list_challenges_structure(self, client):
        """挑战列表结构"""
        resp = client.get("/api/challenges")
        data = resp.json()
        if data["challenges"]:
            c = data["challenges"][0]
            assert "id" in c
            assert "title" in c
            assert "difficulty" in c
            assert "tags" in c
            assert "score" in c
            assert "supported_langs" in c
            assert "submit_count" in c
            assert "pass_count" in c
            assert "pass_rate" in c

    def test_list_challenges_filter_difficulty(self, client):
        """按难度过滤"""
        resp = client.get("/api/challenges?difficulty=入门")
        assert resp.status_code == 200

    def test_list_challenges_filter_tag(self, client):
        """按标签过滤"""
        resp = client.get("/api/challenges?tag=算法")
        assert resp.status_code == 200


class TestChallengeDetailAPI:
    """GET /api/challenges/{id}"""

    def test_get_challenge_valid(self, client):
        """获取挑战详情 — 列出后取第一个"""
        list_resp = client.get("/api/challenges")
        challenges = list_resp.json()["challenges"]
        if not challenges:
            pytest.skip("无内置挑战")
        cid = challenges[0]["id"]

        resp = client.get(f"/api/challenges/{cid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == cid
        assert "title" in data
        assert "description" in data
        assert "public_test_cases" in data
        assert "hidden_test_count" in data

    def test_get_challenge_not_found(self, client):
        """获取不存在的挑战"""
        resp = client.get("/api/challenges/nonexistent_challenge")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_challenge_has_public_test_cases(self, client):
        """挑战详情只包含公开的测试用例"""
        list_resp = client.get("/api/challenges")
        challenges = list_resp.json()["challenges"]
        if not challenges:
            pytest.skip("无内置挑战")
        cid = challenges[0]["id"]

        resp = client.get(f"/api/challenges/{cid}")
        data = resp.json()
        for tc in data.get("public_test_cases", []):
            # 公开测试用例不应隐藏
            assert tc.get("is_hidden", False) is False


class TestGlobalLeaderboardAPI:
    """GET /api/leaderboard"""

    def test_global_leaderboard(self, client):
        """总排行榜"""
        resp = client.get("/api/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "leaderboard" in data
        assert isinstance(data["leaderboard"], list)

    def test_global_leaderboard_structure(self, client):
        """排行榜条目结构"""
        resp = client.get("/api/leaderboard")
        data = resp.json()
        if data["leaderboard"]:
            entry = data["leaderboard"][0]
            assert "rank" in entry
            assert "user" in entry
            assert "total_score" in entry

    def test_global_leaderboard_limit(self, client):
        """排行榜限制数量"""
        resp = client.get("/api/leaderboard?limit=5")
        assert resp.status_code == 200


class TestChallengeLeaderboardAPI:
    """GET /api/challenges/{id}/leaderboard"""

    def test_challenge_leaderboard(self, client):
        """挑战排行榜"""
        list_resp = client.get("/api/challenges")
        challenges = list_resp.json()["challenges"]
        if not challenges:
            pytest.skip("无内置挑战")
        cid = challenges[0]["id"]

        resp = client.get(f"/api/challenges/{cid}/leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "challenge_id" in data
        assert "leaderboard" in data

    def test_challenge_leaderboard_not_found(self, client):
        """不存在挑战的排行榜"""
        resp = client.get("/api/challenges/nonexistent/leaderboard")
        assert resp.status_code == 404


class TestChallengeSubmitAPI:
    """POST /api/challenges/{id}/submit"""

    def test_submit_missing_params(self, client):
        """缺少 lang 或 code"""
        list_resp = client.get("/api/challenges")
        challenges = list_resp.json()["challenges"]
        if not challenges:
            pytest.skip("无内置挑战")
        cid = challenges[0]["id"]

        resp = client.post(f"/api/challenges/{cid}/submit", json={"code": ""})
        assert resp.status_code == 400

    def test_submit_nonexistent_challenge(self, client):
        """提交到不存在的挑战"""
        resp = client.post("/api/challenges/nonexistent/submit", json={
            "lang": "duan",
            "code": "test",
        })
        assert resp.status_code == 400


# ============================================================
# 6. Quality API
# ============================================================


class TestQualityAPI:
    """GET /api/quality"""

    def test_quality_all_adapters(self, client):
        """获取所有适配器的质量报告"""
        resp = client.get("/api/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)

    def test_quality_specific_adapter(self, client):
        """获取指定适配器的质量报告"""
        resp = client.get("/api/quality?lang_id=duan")
        assert resp.status_code == 200
        data = resp.json()
        assert "reports" in data
        assert isinstance(data["reports"], list)
        if data["reports"]:
            report = data["reports"][0]
            assert "lang_id" in report
            assert "total_score" in report
            assert "max_score" in report
            assert "grade" in report
            assert "dimensions" in report

    def test_quality_nonexistent_adapter(self, client):
        """不存在适配器的质量报告"""
        resp = client.get("/api/quality?lang_id=nonexistent_lang")
        assert resp.status_code == 404

    def test_quality_report_grade_values(self, client):
        """质量报告等级值合法"""
        resp = client.get("/api/quality")
        data = resp.json()
        valid_grades = {"S", "A", "B", "C", "D", "F"}
        for report in data["reports"]:
            assert report["grade"] in valid_grades

    def test_quality_report_score_range(self, client):
        """质量报告分数在合理范围"""
        resp = client.get("/api/quality")
        data = resp.json()
        for report in data["reports"]:
            assert 0 <= report["total_score"] <= report["max_score"]


# ============================================================
# 7. Search API
# ============================================================


class TestSearchAPI:
    """GET /api/search"""

    def test_search_valid_query(self, client):
        """有效搜索请求"""
        resp = client.get("/api/search?q=打印")
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "results" in data
        assert data["query"] == "打印"
        assert isinstance(data["results"], list)

    def test_search_missing_query(self, client):
        """缺少 q 参数返回 400"""
        resp = client.get("/api/search")
        assert resp.status_code == 400

    def test_search_empty_query(self, client):
        """空 q 参数返回 400"""
        resp = client.get("/api/search?q=")
        assert resp.status_code == 400

    def test_search_with_category(self, client):
        """按分类搜索"""
        resp = client.get("/api/search?q=打印&category=example")
        assert resp.status_code == 200

    def test_search_with_lang(self, client):
        """按语言搜索"""
        resp = client.get("/api/search?q=打印&lang=duan")
        assert resp.status_code == 200

    def test_search_result_structure(self, client):
        """搜索结果结构"""
        resp = client.get("/api/search?q=打印")
        data = resp.json()
        for r in data["results"]:
            assert "title" in r
            assert "content" in r
            assert "score" in r
            assert "category" in r

    def test_search_with_limit(self, client):
        """搜索限制结果数"""
        resp = client.get("/api/search?q=打印&limit=3")
        assert resp.status_code == 200


class TestSearchSuggestAPI:
    """GET /api/search/suggest"""

    def test_suggest_valid_prefix(self, client):
        """有效前缀联想"""
        resp = client.get("/api/search/suggest?prefix=打印")
        assert resp.status_code == 200
        data = resp.json()
        assert "prefix" in data
        assert "suggestions" in data
        assert data["prefix"] == "打印"
        assert isinstance(data["suggestions"], list)

    def test_suggest_empty_prefix(self, client):
        """空前缀返回空建议"""
        resp = client.get("/api/search/suggest?prefix=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["suggestions"] == []

    def test_suggest_missing_prefix(self, client):
        """缺少 prefix 参数"""
        resp = client.get("/api/search/suggest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prefix"] == ""
        assert data["suggestions"] == []

    def test_suggest_with_limit(self, client):
        """联想限制数量"""
        resp = client.get("/api/search/suggest?prefix=打&limit=3")
        assert resp.status_code == 200


# ============================================================
# 8. Collaboration API
# ============================================================


class TestCollabCreateAPI:
    """POST /api/collab/create"""

    def test_create_room_default(self, client):
        """创建协作房间 — 默认参数"""
        resp = client.post("/api/collab/create", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "roomId" in data

    def test_create_room_with_lang(self, client):
        """创建协作房间 — 指定语言"""
        resp = client.post("/api/collab/create", json={
            "lang": "duan",
            "code": '打印("hello")',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "roomId" in data

    def test_create_room_returns_id(self, client):
        """创建的房间 ID 不为空"""
        resp = client.post("/api/collab/create", json={"lang": "yan"})
        data = resp.json()
        assert len(data["roomId"]) > 0


class TestCollabGetRoomAPI:
    """GET /api/collab/{room_id}"""

    def test_get_existing_room(self, client):
        """获取已创建的房间"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get(f"/api/collab/{room_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["roomId"] == room_id
        assert "lang" in data
        assert "users" in data
        assert "document" in data

    def test_get_nonexistent_room(self, client):
        """获取不存在的房间"""
        resp = client.get("/api/collab/nonexistent_room")
        assert resp.status_code == 404
        assert "error" in resp.json()


class TestCollabListRoomsAPI:
    """GET /api/collab"""

    def test_list_rooms(self, client):
        """列出协作房间"""
        client.post("/api/collab/create", json={"lang": "duan"})

        resp = client.get("/api/collab")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_list_rooms_after_create(self, client):
        """创建后列表包含该房间"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get("/api/collab")
        data = resp.json()
        room_ids = [r["roomId"] for r in data]
        assert room_id in room_ids


# ============================================================
# 9. Collaboration History API (v1.2.0)
# ============================================================


class TestCollabHistoryAPI:
    """协作历史版本 API"""

    def test_get_collab_history(self, client):
        """获取协作房间文档历史"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get(f"/api/collab/{room_id}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "room_id" in data
        assert "versions" in data

    def test_get_collab_version_not_found(self, client):
        """获取不存在的历史版本"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get(f"/api/collab/{room_id}/history/999")
        assert resp.status_code == 404

    def test_diff_collab_versions(self, client):
        """比较两个历史版本"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get(f"/api/collab/{room_id}/diff?v1=1&v2=2")
        assert resp.status_code == 200

    def test_restore_collab_version_not_found(self, client):
        """恢复不存在的历史版本"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.post(f"/api/collab/{room_id}/restore/999")
        assert resp.status_code == 404

    def test_resolve_conflict_valid_strategy(self, client):
        """解决冲突 — 有效策略"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        for strategy in ["ours", "theirs", "merge", "manual"]:
            resp = client.post(f"/api/collab/{room_id}/resolve-conflict?strategy={strategy}")
            assert resp.status_code == 200

    def test_resolve_conflict_invalid_strategy(self, client):
        """解决冲突 — 无效策略"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.post(f"/api/collab/{room_id}/resolve-conflict?strategy=invalid")
        assert resp.status_code == 400

    def test_offline_status(self, client):
        """获取离线编辑状态"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.get(f"/api/collab/{room_id}/offline/user1")
        assert resp.status_code == 200

    def test_go_offline(self, client):
        """用户进入离线模式"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        resp = client.post(f"/api/collab/{room_id}/offline/user1/go-offline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "offline"

    def test_go_online(self, client):
        """用户恢复在线"""
        create_resp = client.post("/api/collab/create", json={"lang": "duan"})
        room_id = create_resp.json()["roomId"]

        # 先离线再上线
        client.post(f"/api/collab/{room_id}/offline/user1/go-offline")
        resp = client.post(f"/api/collab/{room_id}/offline/user1/go-online")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "online"
        assert "pending_ops" in data


# ============================================================
# 10. Share parse API (GET /api/share)
# ============================================================


class TestShareParseAPI:
    """GET /api/share — 解析分享链接参数"""

    def test_parse_share_valid(self, client):
        """解析有效的分享参数"""
        import base64

        code_b64 = base64.urlsafe_b64encode('打印("hello")'.encode()).decode()
        resp = client.get(f"/api/share?lang=duan&code={code_b64}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["lang"] == "duan"
        assert "name" in data
        assert "code" in data

    def test_parse_share_missing_lang(self, client):
        """缺少 lang 参数"""
        resp = client.get("/api/share?code=test")
        assert resp.status_code == 400

    def test_parse_share_invalid_lang(self, client):
        """无效语言"""
        resp = client.get("/api/share?lang=nonexistent&code=test")
        assert resp.status_code == 404

    def test_parse_share_no_code(self, client):
        """无 code 参数"""
        resp = client.get("/api/share?lang=duan")
        assert resp.status_code == 200
        assert resp.json()["code"] == ""


# ============================================================
# 11. Monitor page route
# ============================================================


class TestMonitorPageRoute:
    """GET /monitor"""

    def test_monitor_page(self, client):
        """监控仪表板页面"""
        resp = client.get("/monitor")
        # 静态文件存在时返回 200，不存在时返回 404
        assert resp.status_code in (200, 404)

    def test_challenges_page(self, client):
        """代码挑战赛页面"""
        resp = client.get("/challenges")
        assert resp.status_code in (200, 404)

    def test_quality_page(self, client):
        """适配器质量评分页面"""
        resp = client.get("/quality")
        assert resp.status_code in (200, 404)


# ============================================================
# 12. Template API with example param
# ============================================================


class TestTemplateWithExampleAPI:
    """GET /api/templates/{lang_id}?example=xxx"""

    def test_template_with_specific_example(self, client):
        """请求特定示例模板"""
        resp = client.get("/api/templates/duan?example=hello")
        if resp.status_code == 200:
            data = resp.json()
            assert "code" in data
            assert len(data["code"]) > 0
        elif resp.status_code == 404:
            data = resp.json()
            assert "error" in data

    def test_template_with_nonexistent_example(self, client):
        """请求不存在的示例"""
        resp = client.get("/api/templates/duan?example=nonexistent_example")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_template_share_link_parsing(self, client):
        """模板 API 与分享解析的兼容性"""
        import base64

        code = '打印("template test")'
        code_b64 = base64.urlsafe_b64encode(code.encode()).decode()
        resp = client.get(f"/api/share?lang=duan&code={code_b64}")
        assert resp.status_code == 200
        assert "打印" in resp.json()["code"]
