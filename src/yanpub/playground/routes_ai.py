"""Playground 路由 — AI 辅助"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from yanpub.core.adapter.registry import get_registry


def register_ai_routes(app: FastAPI) -> None:
    """注册 AI 辅助路由"""
    from yanpub.core.ai_assist import AIAssistEngine, AIAssistConfig

    _ai_engine = AIAssistEngine(AIAssistConfig())

    @app.post("/api/ai/complete")
    async def ai_complete(body: dict):
        """AI 智能补全"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        line = body.get("line", 1)
        column = body.get("column", 1)

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse(
                {
                    "error": f"未知语言: {lang_id}",
                },
                status_code=400,
            )

        result = _ai_engine.smart_complete(adapter, code, line, column)
        return {"items": result}

    @app.post("/api/ai/nl2code")
    async def ai_nl2code(body: dict):
        """自然语言转代码"""
        lang_id = body.get("lang", "")
        text = body.get("text", "")
        context = body.get("context", "")

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse(
                {
                    "error": f"未知语言: {lang_id}",
                },
                status_code=400,
            )

        result = _ai_engine.nl_to_code(adapter, text, context)
        return result

    @app.post("/api/ai/fix")
    async def ai_fix(body: dict):
        """错误修复建议"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        error = body.get("error", "")

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse(
                {
                    "error": f"未知语言: {lang_id}",
                },
                status_code=400,
            )

        result = _ai_engine.fix_suggestion(adapter, code, error)
        return {"suggestions": result}
