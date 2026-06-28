"""Playground 后端 — FastAPI 应用

API:
  GET  /                  主页
  GET  /api/languages     列出可用语言
  GET  /api/templates/{lang}  获取语言示例代码
  GET  /api/share         解析分享链接（query: lang, code）
  POST /api/run           同步执行代码
  WS   /ws/run            WebSocket 执行代码（支持多轮交互）
  POST /api/ai/complete   AI 智能补全
  POST /api/ai/nl2code    自然语言转代码
  POST /api/ai/fix        错误修复建议
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from yanpub.core.adapter.registry import get_registry

# 路由分组模块
from yanpub.playground.routes_ai import register_ai_routes
from yanpub.playground.routes_challenge import register_challenge_routes, register_quality_routes
from yanpub.playground.routes_monitor import register_collab, register_monitor_routes
from yanpub.playground.routes_project import register_project_routes
from yanpub.playground.routes_share import generate_default_template, register_share_routes

logger = logging.getLogger("yanpub.playground")


# 静态文件和模板目录
_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app() -> FastAPI:
    app = FastAPI(title="YanPlay - 中文编程语言 Playground")

    # ---- 安全中间件 ----
    from yanpub.playground.security import install_security_middleware

    install_security_middleware(app)

    # ---- 页面路由 ----

    @app.get("/")
    async def index():
        """Playground 主页"""
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/challenges")
    async def challenges_page():
        """代码挑战赛页面"""
        return FileResponse(_STATIC_DIR / "challenges.html")

    @app.get("/quality")
    async def quality_page():
        """适配器质量评分页面"""
        return FileResponse(_STATIC_DIR / "quality.html")

    # ---- REST API ----

    @app.get("/api/languages")
    async def list_languages():
        """列出可用语言及其信息"""
        registry = get_registry()
        result = []
        for a in registry:
            result.append(
                {
                    "id": a.id,
                    "name": a.name,
                    "version": a.version,
                    "extensions": a.file_extensions,
                    "capabilities": a.capabilities,
                    "keywords": a.keywords[:50] if len(a.keywords) > 50 else a.keywords,
                    "commentSyntax": a.comment_syntax,
                    "primaryColor": a.primary_color,
                    "description": a.description,
                }
            )
        return result

    # 示例元数据：文件名 -> 显示名
    _EXAMPLE_META = {
        "hello": "Hello World",
        "fibonacci": "斐波那契数列",
        "hanoi": "汉诺塔",
        "turing": "图灵机原型机",
        "bubble": "冒泡排序",
    }

    @app.get("/api/examples/{lang_id}")
    async def list_examples(lang_id: str):
        """获取语言的示例列表"""
        lang_dir = _TEMPLATES_DIR / lang_id
        if not lang_dir.exists():
            return JSONResponse([])
        examples = []
        for txt in sorted(lang_dir.glob("*.txt")):
            name = txt.stem
            if name == "default":
                continue
            display = _EXAMPLE_META.get(name, name)
            examples.append({"id": name, "name": display})
        return JSONResponse(examples)

    @app.get("/api/templates/{lang_id}")
    async def get_template(lang_id: str, example: str = ""):
        """获取语言示例代码"""
        # 指定示例名
        if example:
            template_file = _TEMPLATES_DIR / lang_id / f"{example}.txt"
            if template_file.exists():
                return JSONResponse({"code": template_file.read_text(encoding="utf-8")})
            return JSONResponse({"code": "", "error": f"示例不存在: {example}"}, status_code=404)

        # 先查自定义模板文件
        template_file = _TEMPLATES_DIR / lang_id / "default.txt"
        if template_file.exists():
            return JSONResponse({"code": template_file.read_text(encoding="utf-8")})

        # 再查内置模板
        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({"code": "", "error": f"未知语言: {lang_id}"}, status_code=404)

        # 生成默认示例
        default_code = generate_default_template(adapter)
        return JSONResponse({"code": default_code})

    @app.get("/api/share")
    async def parse_share_link(lang: str = "", code: str = ""):
        """解析分享链接参数，返回语言和代码"""
        if not lang:
            return JSONResponse({"error": "缺少 lang 参数"}, status_code=400)

        registry = get_registry()
        adapter = registry.get(lang)
        if adapter is None:
            return JSONResponse({"error": f"未知语言: {lang}"}, status_code=404)

        decoded_code = ""
        if code:
            try:
                decoded_code = base64.urlsafe_b64decode(code).decode("utf-8")
            except Exception:
                decoded_code = code

        return JSONResponse(
            {
                "lang": lang,
                "name": adapter.name,
                "code": decoded_code,
            }
        )

    @app.post("/api/run")
    async def run_code_sync(body: dict):
        """同步执行代码（REST 方式，适合简单请求）"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")

        # 代码长度校验
        from yanpub.playground.security import MAX_CODE_LENGTH

        if len(code) > MAX_CODE_LENGTH:
            return JSONResponse(
                {"type": "error", "message": f"代码过长，最大允许 {MAX_CODE_LENGTH} 字符"},
                status_code=413,
            )

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse(
                {
                    "type": "error",
                    "message": f"未知语言: {lang_id}",
                },
                status_code=400,
            )

        # 在线程池中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, adapter.eval, code)

        return {
            "type": "result",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
        }

    # ---- WebSocket ----

    @app.websocket("/ws/run")
    async def run_code_ws(websocket: WebSocket):
        """WebSocket 执行代码（支持连续执行和多轮交互）"""
        await websocket.accept()
        registry = get_registry()

        from yanpub.playground.security import MAX_CODE_LENGTH

        try:
            while True:
                data = await websocket.receive_json()
                lang_id = data.get("lang", "")
                code = data.get("code", "")
                request_id = data.get("id", "")

                # 代码长度校验
                if len(code) > MAX_CODE_LENGTH:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"代码过长，最大允许 {MAX_CODE_LENGTH} 字符",
                            "id": request_id,
                        }
                    )
                    continue

                adapter = registry.get(lang_id)
                if adapter is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"未知语言: {lang_id}",
                            "id": request_id,
                        }
                    )
                    continue

                # 在线程池中执行
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, adapter.eval, code)

                await websocket.send_json(
                    {
                        "type": "result",
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exitCode": result.exit_code,
                        "durationMs": result.duration_ms,
                        "id": request_id,
                    }
                )

        except WebSocketDisconnect:
            pass

    # ---- 静态文件 ----

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # ---- WASM 执行 ----

    @app.get("/api/wasm/{lang_id}")
    async def get_wasm_config(lang_id: str):
        """获取语言的 WASM/Pyodide 执行配置"""
        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({"error": f"未知语言: {lang_id}"}, status_code=404)

        from yanpub.core.wasm import generate_pyodide_config

        config = generate_pyodide_config(adapter)
        return JSONResponse(config)

    @app.get("/api/wasm/{lang_id}/runner")
    async def get_wasm_runner(lang_id: str):
        """获取语言的 Pyodide runner HTML"""
        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({"error": f"未知语言: {lang_id}"}, status_code=404)

        from yanpub.core.wasm import generate_pyodide_runner_html
        from fastapi.responses import HTMLResponse

        html = generate_pyodide_runner_html(adapter)
        return HTMLResponse(content=html)

    @app.post("/api/wasm/{lang_id}/run")
    async def run_wasm_code(lang_id: str, body: dict):
        """通过 WASM/Pyodide 执行代码（服务器端）"""
        code = body.get("code", "")

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({"error": f"未知语言: {lang_id}"}, status_code=404)

        from yanpub.core.wasm import WasmExecutor

        executor = WasmExecutor()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            executor.execute_with_adapter,
            adapter,
            code,
        )

        return {
            "type": "result",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
            "executor": "wasm" if executor.is_available else "fallback",
        }

    # ---- 沙箱执行 ----

    @app.post("/api/sandbox/run")
    async def run_sandbox_code(body: dict):
        """沙箱执行代码（安全隔离环境）"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        backend = body.get("backend", "auto")
        memory = body.get("memory", "512m")
        timeout = body.get("timeout", 30.0)
        network = body.get("network", False)

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse(
                {
                    "type": "error",
                    "message": f"未知语言: {lang_id}",
                },
                status_code=400,
            )

        # 安全校验 sandbox 参数
        from yanpub.playground.security import validate_sandbox_params

        param_error = validate_sandbox_params(body)
        if param_error:
            return JSONResponse({"type": "error", "message": param_error}, status_code=400)

        from yanpub.core.security.sandbox import SandboxManager, SandboxConfig

        config = SandboxConfig(
            backend=backend,
            memory_limit=memory,
            timeout=timeout,
            network=network,
        )
        manager = SandboxManager(config)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, manager.execute_code, adapter, code)

        # 清理
        try:
            manager.cleanup()
        except Exception:
            pass

        return {
            "type": "sandbox_result",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
            "memoryUsedMb": result.memory_used_mb,
            "sandboxId": result.sandbox_id,
            "backend": result.backend,
        }

    @app.get("/api/sandbox/status")
    async def sandbox_status():
        """查询沙箱后端状态"""
        from yanpub.core.security.sandbox import SandboxManager

        status = SandboxManager.get_backend_status()
        available = [name for name, info in status.items() if info["available"]]

        return {
            "backends": status,
            "available": available,
            "recommended": available[0] if available else "process",
        }

    # ---- 路由分组 ----

    register_ai_routes(app)
    register_collab(app)
    register_project_routes(app)
    register_monitor_routes(app)
    register_share_routes(app)
    register_challenge_routes(app)
    register_quality_routes(app)

    return app
