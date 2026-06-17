"""Playground 测试"""

import pytest
from fastapi.testclient import TestClient

from yanpub.playground.server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestPlaygroundAPI:
    def test_homepage(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "CodeMirror" in resp.text or "codemirror" in resp.text.lower()

    def test_list_languages(self, client):
        resp = client.get("/api/languages")
        assert resp.status_code == 200
        langs = resp.json()
        assert len(langs) >= 3
        ids = [lang["id"] for lang in langs]
        assert "duan" in ids
        assert "yan" in ids
        assert "moyan" in ids

    def test_language_has_keywords(self, client):
        resp = client.get("/api/languages")
        langs = resp.json()
        duan = next(lang for lang in langs if lang["id"] == "duan")
        assert len(duan["keywords"]) > 0
        assert duan["primaryColor"] == "#E85D3A"

    def test_get_template_duan(self, client):
        resp = client.get("/api/templates/duan")
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert len(data["code"]) > 0

    def test_get_template_unknown(self, client):
        resp = client.get("/api/templates/nonexistent")
        assert resp.status_code == 404

    def test_run_code_duan(self, client):
        resp = client.post("/api/run", json={
            "lang": "duan",
            "code": '打印("Playground test")。',
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "result"
        assert data["exitCode"] == 0
        assert "Playground test" in data["stdout"]

    def test_run_code_unknown_lang(self, client):
        resp = client.post("/api/run", json={
            "lang": "nonexistent",
            "code": "hello",
        })
        assert resp.status_code == 400

    def test_run_code_with_error(self, client):
        resp = client.post("/api/run", json={
            "lang": "duan",
            "code": "这段代码有语法错误",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exitCode"] != 0

    def test_websocket_run(self, client):
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"lang": "duan", "code": '打印("WS test")。'})
            data = ws.receive_json()
            assert data["type"] == "result"
            assert data["exitCode"] == 0
            assert "WS test" in data["stdout"]

    def test_websocket_unknown_lang(self, client):
        with client.websocket_connect("/ws/run") as ws:
            ws.send_json({"lang": "nonexistent", "code": "hello"})
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_static_files_accessible(self, client):
        # 验证静态文件路由已挂载
        resp = client.get("/")
        assert resp.status_code == 200
