"""Playground 代码分享增强功能测试"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestShareRecord:
    """ShareRecord 数据类"""

    def test_to_dict(self):
        from yanpub.playground.share import ShareRecord

        record = ShareRecord(
            id="abc123",
            lang="duan",
            code='打印("hello")',
            title="测试分享",
            author="测试者",
            created_at=1000000.0,
            views=5,
            expires_at=None,
        )
        d = record.to_dict()
        assert d["id"] == "abc123"
        assert d["lang"] == "duan"
        assert d["code"] == '打印("hello")'
        assert d["title"] == "测试分享"
        assert d["author"] == "测试者"
        assert d["views"] == 5
        assert d["expires_at"] is None

    def test_from_dict(self):
        from yanpub.playground.share import ShareRecord

        data = {
            "id": "xyz789",
            "lang": "yan",
            "code": "print(1)",
            "title": "",
            "author": "",
            "created_at": 2000000.0,
            "views": 0,
            "expires_at": 3000000.0,
        }
        record = ShareRecord.from_dict(data)
        assert record.id == "xyz789"
        assert record.lang == "yan"
        assert record.code == "print(1)"
        assert record.expires_at == 3000000.0

    def test_roundtrip(self):
        from yanpub.playground.share import ShareRecord

        original = ShareRecord(
            id="rt001",
            lang="duan",
            code="test",
            title="RT",
            author="A",
            created_at=1234.0,
            views=10,
            expires_at=5678.0,
        )
        restored = ShareRecord.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.lang == original.lang
        assert restored.code == original.code
        assert restored.title == original.title
        assert restored.author == original.author
        assert restored.views == original.views
        assert restored.expires_at == original.expires_at


class TestShareManager:
    """ShareManager 分享管理器"""

    def _make_manager(self, tmp_path: Path):
        from yanpub.playground.share import ShareManager

        return ShareManager(storage_dir=tmp_path / "shares")

    def test_create_share(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        record = mgr.create_share("duan", '打印("hi")', title="Hello")
        assert record.id
        assert len(record.id) == 6
        assert record.lang == "duan"
        assert record.code == '打印("hi")'
        assert record.title == "Hello"
        assert record.created_at > 0
        assert record.views == 0
        assert record.expires_at is None

    def test_create_share_with_ttl(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        record = mgr.create_share("duan", "code", ttl_hours=24)
        assert record.expires_at is not None
        assert record.expires_at > record.created_at

    def test_create_share_no_ttl(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        record = mgr.create_share("duan", "code", ttl_hours=None)
        assert record.expires_at is None

    def test_get_share(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        created = mgr.create_share("duan", "hello")
        got = mgr.get_share(created.id)
        assert got is not None
        assert got.id == created.id
        assert got.code == "hello"

    def test_get_share_not_found(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        assert mgr.get_share("nonexistent") is None

    def test_increment_views(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        created = mgr.create_share("duan", "code")
        assert created.views == 0
        mgr.increment_views(created.id)
        got = mgr.get_share(created.id)
        assert got.views == 1
        mgr.increment_views(created.id)
        got = mgr.get_share(created.id)
        assert got.views == 2

    def test_list_shares(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        mgr.create_share("duan", "code1", title="First")
        mgr.create_share("yan", "code2", title="Second")
        shares = mgr.list_shares()
        assert len(shares) == 2
        # Should be sorted by created_at desc
        assert shares[0].created_at >= shares[1].created_at

    def test_list_shares_limit(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        for i in range(5):
            mgr.create_share("duan", f"code{i}")
        shares = mgr.list_shares(limit=3)
        assert len(shares) == 3

    def test_delete_share(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        created = mgr.create_share("duan", "code")
        assert mgr.delete_share(created.id) is True
        assert mgr.get_share(created.id) is None
        assert mgr.delete_share(created.id) is False

    def test_cleanup_expired(self, tmp_path: Path):
        import time

        mgr = self._make_manager(tmp_path)
        # Create an already-expired share (ttl=0 means expires immediately)
        expired = mgr.create_share("duan", "expired_code", ttl_hours=0)
        # Manually set expires_at to past
        expired.expires_at = time.time() - 1
        mgr._shares[expired.id] = expired

        # Create a non-expired share
        active = mgr.create_share("duan", "active_code")

        count = mgr.cleanup_expired()
        assert count == 1
        assert mgr.get_share(expired.id) is None
        assert mgr.get_share(active.id) is not None

    def test_persistence(self, tmp_path: Path):
        from yanpub.playground.share import ShareManager

        storage_dir = tmp_path / "shares"
        mgr1 = ShareManager(storage_dir=storage_dir)
        created = mgr1.create_share("duan", "persistent_code", title="Persist Test")

        # Create new manager instance — should load from file
        mgr2 = ShareManager(storage_dir=storage_dir)
        got = mgr2.get_share(created.id)
        assert got is not None
        assert got.code == "persistent_code"
        assert got.title == "Persist Test"

    def test_short_id_uniqueness(self, tmp_path: Path):
        mgr = self._make_manager(tmp_path)
        ids = set()
        for _ in range(50):
            record = mgr.create_share("duan", "code")
            ids.add(record.id)
        # All IDs should be unique
        assert len(ids) == 50


class TestQRCode:
    """二维码 SVG 生成"""

    def test_generate_svg_short_url(self):
        from yanpub.playground.share import ShareManager

        mgr = ShareManager()
        svg = mgr.generate_qrcode_svg("https://example.com/s/abc123")
        assert "<svg" in svg
        assert "</svg>" in svg
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg
        assert "rect" in svg

    def test_generate_svg_long_url(self):
        from yanpub.playground.share import ShareManager

        mgr = ShareManager()
        long_url = "https://example.com/s/abc123?lang=duan&code=" + "x" * 100
        svg = mgr.generate_qrcode_svg(long_url)
        assert "<svg" in svg
        # Longer URLs should use a larger matrix
        assert 'width="' in svg

    def test_generate_svg_empty_url(self):
        from yanpub.playground.share import ShareManager

        mgr = ShareManager()
        svg = mgr.generate_qrcode_svg("")
        assert "<svg" in svg

    def test_generate_svg_unicode(self):
        from yanpub.playground.share import ShareManager

        mgr = ShareManager()
        svg = mgr.generate_qrcode_svg("https://example.com/s/abc?title=你好世界")
        assert "<svg" in svg


class TestGenerateShortId:
    """短链接 ID 生成"""

    def test_default_length(self):
        from yanpub.playground.share import ShareManager

        sid = ShareManager.generate_short_id()
        assert len(sid) == 6

    def test_custom_length(self):
        from yanpub.playground.share import ShareManager

        sid = ShareManager.generate_short_id(length=10)
        assert len(sid) == 10

    def test_charset(self):
        from yanpub.playground.share import ShareManager

        for _ in range(20):
            sid = ShareManager.generate_short_id()
            assert sid.isalnum()
            assert sid.islower() or sid.isdigit() or all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in sid)


class TestShareAPIServer:
    """分享 API 路由测试（使用 FastAPI TestClient）"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from yanpub.playground.server import create_app

        app = create_app()
        return TestClient(app)

    def test_create_share_api(self, client):
        resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": '打印("hello")', "title": "API Test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert len(data["id"]) == 6
        assert "url" in data
        assert "qr_url" in data
        assert data["url"] == f"/s/{data['id']}"

    def test_create_share_missing_lang(self, client):
        resp = client.post(
            "/api/share/create",
            json={"code": "test"},
        )
        assert resp.status_code == 400

    def test_create_share_unknown_lang(self, client):
        resp = client.post(
            "/api/share/create",
            json={"lang": "nonexistent_lang", "code": "test"},
        )
        assert resp.status_code == 404

    def test_get_share_api(self, client):
        # Create a share first
        create_resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "test_code"},
        )
        share_id = create_resp.json()["id"]

        # Get the share
        get_resp = client.get(f"/api/share/{share_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["id"] == share_id
        assert data["lang"] == "duan"
        assert data["code"] == "test_code"

    def test_get_share_not_found(self, client):
        resp = client.get("/api/share/nonexistent")
        assert resp.status_code == 404

    def test_share_qrcode_api(self, client):
        # Create a share first
        create_resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "qr_test"},
        )
        share_id = create_resp.json()["id"]

        # Get QR code
        qr_resp = client.get(f"/api/share/{share_id}/qr")
        assert qr_resp.status_code == 200
        assert "svg" in qr_resp.text.lower() or "image/svg+xml" in qr_resp.headers.get("content-type", "")

    def test_list_shares_api(self, client):
        # Create a share first
        client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "list_test"},
        )

        resp = client.get("/api/shares")
        assert resp.status_code == 200
        data = resp.json()
        assert "shares" in data
        assert isinstance(data["shares"], list)

    def test_delete_share_api(self, client):
        # Create a share first
        create_resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "delete_test"},
        )
        share_id = create_resp.json()["id"]

        # Delete it
        del_resp = client.delete(f"/api/share/{share_id}")
        assert del_resp.status_code == 200

        # Verify it's gone
        get_resp = client.get(f"/api/share/{share_id}")
        assert get_resp.status_code == 404

    def test_short_link_redirect(self, client):
        # Create a share first
        create_resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "redirect_test"},
        )
        share_id = create_resp.json()["id"]

        # Access short link
        resp = client.get(f"/s/{share_id}", follow_redirects=False)
        assert resp.status_code in (307, 301, 302)
        assert f"#share={share_id}" in resp.headers.get("location", "")

    def test_share_views_increment(self, client):
        # Create a share
        create_resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "views_test"},
        )
        share_id = create_resp.json()["id"]

        # Get the share twice
        client.get(f"/api/share/{share_id}")
        get_resp = client.get(f"/api/share/{share_id}")
        assert get_resp.json()["views"] == 2

    def test_create_share_with_ttl(self, client):
        resp = client.post(
            "/api/share/create",
            json={"lang": "duan", "code": "ttl_test", "ttl_hours": 24},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expires_at"] is not None
