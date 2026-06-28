"""Playground 路由 — 代码分享增强、协作历史、文档搜索"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from yanpub.core.adapter.registry import get_registry

# 模板目录（与 server.py 共享）
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def register_share_routes(app: FastAPI) -> None:
    """注册代码分享增强路由"""
    from yanpub.playground.share import get_share_manager

    @app.post("/api/share/create")
    async def create_share(body: dict):
        """创建分享链接

        body: {"lang": str, "code": str, "title": str, "author": str, "ttl_hours": int}
        返回: {"id": str, "url": str, "qr_url": str}
        """
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        title = body.get("title", "")
        author = body.get("author", "")
        ttl_hours = body.get("ttl_hours")

        if not lang_id or not code.strip():
            return JSONResponse({"error": "缺少 lang 或 code 参数"}, status_code=400)

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({"error": f"未知语言: {lang_id}"}, status_code=404)

        mgr = get_share_manager()
        record = mgr.create_share(
            lang=lang_id,
            code=code,
            title=title,
            author=author,
            ttl_hours=ttl_hours,
        )

        # 构建完整 URL（使用请求的 host）
        base_url = f"/s/{record.id}"
        qr_url = f"/api/share/{record.id}/qr"

        return {
            "id": record.id,
            "url": base_url,
            "qr_url": qr_url,
            "title": record.title,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
        }

    @app.get("/api/share/{share_id}")
    async def get_share(share_id: str):
        """获取分享内容"""
        mgr = get_share_manager()
        record = mgr.get_share(share_id)
        if record is None:
            return JSONResponse({"error": "分享不存在或已过期"}, status_code=404)

        # 增加访问计数
        mgr.increment_views(share_id)

        # 查询语言名称
        registry = get_registry()
        adapter = registry.get(record.lang)
        lang_name = adapter.name if adapter else record.lang

        return {
            "id": record.id,
            "lang": record.lang,
            "lang_name": lang_name,
            "code": record.code,
            "title": record.title,
            "author": record.author,
            "created_at": record.created_at,
            "views": record.views,
            "expires_at": record.expires_at,
        }

    @app.get("/api/share/{share_id}/qr")
    async def get_share_qrcode(share_id: str):
        """获取分享二维码（SVG）"""
        mgr = get_share_manager()
        record = mgr.get_share(share_id)
        if record is None:
            return JSONResponse({"error": "分享不存在或已过期"}, status_code=404)

        # 构建 URL
        share_url = f"/s/{share_id}"
        svg = mgr.generate_qrcode_svg(share_url)
        return HTMLResponse(content=svg, media_type="image/svg+xml")

    @app.get("/api/shares")
    async def list_shares(limit: int = 50):
        """列出最近的分享"""
        mgr = get_share_manager()
        records = mgr.list_shares(limit=limit)

        # 附加语言名称
        registry = get_registry()
        result = []
        for record in records:
            adapter = registry.get(record.lang)
            d = record.to_dict()
            d["lang_name"] = adapter.name if adapter else record.lang
            result.append(d)

        return {"shares": result}

    @app.delete("/api/share/{share_id}")
    async def delete_share(share_id: str):
        """删除分享"""
        mgr = get_share_manager()
        if mgr.delete_share(share_id):
            return {"ok": True}
        else:
            return JSONResponse({"error": "分享不存在"}, status_code=404)

    @app.get("/s/{share_id}")
    async def short_link_redirect(share_id: str):
        """短链接重定向到主页并加载分享内容"""
        mgr = get_share_manager()
        record = mgr.get_share(share_id)
        if record is None:
            return JSONResponse({"error": "分享不存在或已过期"}, status_code=404)

        # 重定向到主页，用 #share= 参数
        return RedirectResponse(url=f"/#share={share_id}")

    # ---- v1.2.0: 协作增强 API ----

    @app.get("/api/collab/{room_id}/history")
    async def get_collab_history(room_id: str, limit: int = 20):
        """获取协作房间的文档历史"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        versions = enhancer.list_versions(room_id, limit)
        return {"room_id": room_id, "versions": versions}

    @app.get("/api/collab/{room_id}/history/{version}")
    async def get_collab_version(room_id: str, version: int):
        """获取协作房间的指定版本"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        snap = enhancer.get_version(room_id, version)
        if snap is None:
            return JSONResponse({"error": "版本不存在"}, status_code=404)
        return snap.to_dict()

    @app.get("/api/collab/{room_id}/diff")
    async def diff_collab_versions(room_id: str, v1: int, v2: int):
        """比较协作房间的两个版本"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        return enhancer.diff_versions(room_id, v1, v2)

    @app.post("/api/collab/{room_id}/restore/{version}")
    async def restore_collab_version(room_id: str, version: int):
        """恢复协作房间到指定版本"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        content = enhancer.restore_version(room_id, version)
        if content is None:
            return JSONResponse({"error": "版本不存在"}, status_code=404)
        return {"ok": True, "version": version, "content": content}

    @app.post("/api/collab/{room_id}/resolve-conflict")
    async def resolve_collab_conflict(room_id: str, strategy: str = "merge"):
        """解决协作冲突"""
        from yanpub.playground.collab_history import ResolutionStrategy

        try:
            strat = ResolutionStrategy(strategy)
        except ValueError:
            return JSONResponse({"error": f"无效策略: {strategy}"}, status_code=400)
        return {"ok": True, "strategy": strat.value}

    @app.get("/api/collab/{room_id}/offline/{user_id}")
    async def get_offline_status(room_id: str, user_id: str):
        """获取用户离线编辑状态"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        buf = enhancer.get_offline_buffer(room_id, user_id)
        return buf.to_dict()

    @app.post("/api/collab/{room_id}/offline/{user_id}/go-offline")
    async def go_offline(room_id: str, user_id: str):
        """用户进入离线模式"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        enhancer.go_offline(room_id, user_id)
        return {"ok": True, "status": "offline"}

    @app.post("/api/collab/{room_id}/offline/{user_id}/go-online")
    async def go_online(room_id: str, user_id: str):
        """用户恢复在线，返回待同步操作"""
        from yanpub.playground.collab_history import get_collab_enhancer

        enhancer = get_collab_enhancer()
        ops = enhancer.go_online(room_id, user_id)
        return {
            "ok": True,
            "status": "online",
            "pending_ops": len(ops),
            "ops": [o.to_dict() for o in ops],
        }

    # ---- v1.2.0: 文档搜索 API ----

    @app.get("/api/search")
    async def search_docs(q: str = "", category: str = "", lang: str = "", limit: int = 20):
        """全文搜索"""
        from yanpub.docs.search import get_search_engine

        if not q:
            return JSONResponse({"error": "缺少 q 参数"}, status_code=400)

        engine = get_search_engine()
        engine.build_index()

        if category == "example":
            results = engine.search_examples(q, lang_id=lang, limit=limit)
        else:
            results = engine.search(q, limit=limit, category=category)

        return {"query": q, "results": [r.to_dict() for r in results]}

    @app.get("/api/search/suggest")
    async def search_suggest(prefix: str = "", limit: int = 8):
        """关键字联想"""
        from yanpub.docs.search import get_search_engine

        if not prefix:
            return {"prefix": "", "suggestions": []}

        engine = get_search_engine()
        engine.build_index()

        suggestions = engine.suggest(prefix, limit)
        return {"prefix": prefix, "suggestions": suggestions}


def generate_default_template(adapter) -> str:
    """根据语言生成默认示例代码（优先从文件读取）"""
    template_file = _TEMPLATES_DIR / adapter.id / "default.txt"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    return f'# {adapter.name} 示例\n打印("你好，世界！")'
