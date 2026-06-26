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
        default_code = _generate_default_template(adapter)
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

    # ---- AI 辅助 ----

    _register_ai_routes(app)

    # ---- 实时协作 ----
    _register_collab(app)

    # ---- 多文件项目 ----
    _register_project_routes(app)

    # ---- 性能监控 ----
    _register_monitor_routes(app)

    # ---- 代码分享增强 ----
    _register_share_routes(app)

    # ---- 代码挑战赛 ----
    _register_challenge_routes(app)

    # ---- 适配器质量评分 ----
    _register_quality_routes(app)

    return app


def _register_ai_routes(app: FastAPI) -> None:
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


def _register_project_routes(app: FastAPI) -> None:
    """注册多文件项目路由"""
    from yanpub.playground.project import get_project_manager, _validate_path

    @app.post("/api/project/create")
    async def create_project(body: dict):
        """创建多文件项目"""
        name = body.get("name", "未命名项目")
        language = body.get("language", "duan")
        template = body.get("template", "default")

        pm = get_project_manager()
        project = pm.create_project(name, language, template)

        return project.to_dict()

    @app.get("/api/projects")
    async def list_projects():
        """列出所有项目"""
        pm = get_project_manager()
        return {"projects": pm.list_projects()}

    @app.get("/api/project/{project_id}")
    async def get_project(project_id: str):
        """获取项目详情"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)
        return project.to_dict()

    @app.get("/api/project/{project_id}/files")
    async def list_project_files(project_id: str):
        """列出项目文件"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        return {
            "projectId": project.id,
            "mainFile": project.main_file,
            "files": [pf.to_dict() for pf in project.list_files()],
        }

    @app.put("/api/project/{project_id}/files/{file_path:path}")
    async def update_project_file(project_id: str, file_path: str, body: dict):
        """更新文件内容"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        try:
            file_path = _validate_path(file_path)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        pf = project.get_file(file_path)
        if pf is None:
            return JSONResponse({"error": f"文件不存在: {file_path}"}, status_code=404)

        if "content" in body:
            pf.content = body["content"]
        if "language" in body:
            pf.language = body["language"]
        pf.modified = True
        pm.save_project(project)

        return pf.to_dict()

    @app.post("/api/project/{project_id}/files")
    async def add_project_file(project_id: str, body: dict):
        """添加文件"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        path = body.get("path", "")
        content = body.get("content", "")
        language = body.get("language", project.language)

        try:
            pf = project.add_file(path, content, language)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        pm.save_project(project)
        return pf.to_dict()

    @app.delete("/api/project/{project_id}/files/{file_path:path}")
    async def delete_project_file(project_id: str, file_path: str):
        """删除文件"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        try:
            file_path = _validate_path(file_path)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        if project.remove_file(file_path):
            pm.save_project(project)
            return {"ok": True}
        else:
            return JSONResponse({"error": f"文件不存在: {file_path}"}, status_code=404)

    @app.post("/api/project/{project_id}/files/rename")
    async def rename_project_file(project_id: str, body: dict):
        """重命名文件"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        old_path = body.get("oldPath", "")
        new_path = body.get("newPath", "")

        try:
            _validate_path(old_path)
            _validate_path(new_path)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        if project.rename_file(old_path, new_path):
            pm.save_project(project)
            return {"ok": True, "mainFile": project.main_file}
        else:
            return JSONResponse({"error": f"重命名失败: {old_path} → {new_path}"}, status_code=400)

    @app.post("/api/project/{project_id}/run")
    async def run_project(project_id: str):
        """执行项目"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        registry = get_registry()
        adapter = registry.get(project.language)
        if adapter is None:
            return JSONResponse(
                {"type": "error", "message": f"未知语言: {project.language}"},
                status_code=400,
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, pm.execute_project, project_id, adapter)

        return {
            "type": "result",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.exit_code,
            "durationMs": result.duration_ms,
            "projectId": project_id,
        }

    @app.get("/api/project/{project_id}/templates")
    async def get_project_templates(project_id: str):
        """获取项目模板"""
        pm = get_project_manager()
        project = pm.get_project(project_id)
        if project is None:
            return JSONResponse({"error": "项目不存在"}, status_code=404)

        templates = pm.get_templates(project.language)
        return {"templates": templates}

    @app.delete("/api/project/{project_id}")
    async def delete_project(project_id: str):
        """删除项目"""
        pm = get_project_manager()
        if pm.delete_project(project_id):
            return {"ok": True}
        else:
            return JSONResponse({"error": "项目不存在"}, status_code=404)


def _register_collab(app: FastAPI) -> None:
    """注册实时协作路由（延迟导入避免循环依赖）"""
    try:
        from yanpub.playground.collab import register_collab_routes

        register_collab_routes(app)
    except ImportError:
        logger.warning("实时协作模块不可用")


def _register_monitor_routes(app: FastAPI) -> None:
    """注册性能监控路由"""
    from yanpub.core.perf.monitor import get_monitor

    @app.get("/monitor")
    async def monitor_page():
        """性能监控仪表板页面"""
        return FileResponse(_STATIC_DIR / "monitor.html")

    @app.get("/api/monitor/metrics")
    async def get_metrics(adapter_id: str | None = None):
        """获取性能指标数据"""
        monitor = get_monitor()
        return monitor.get_dashboard_data(adapter_id=adapter_id)

    @app.get("/api/monitor/trend/{adapter_id}")
    async def get_trend(adapter_id: str, metric: str = "eval_duration", points: int = 20):
        """获取趋势数据"""
        monitor = get_monitor()
        trend = monitor.get_trend(adapter_id, metric, points)
        regression = monitor.detect_regression(adapter_id, metric)
        return {
            "adapter_id": adapter_id,
            "metric": metric,
            "trend": trend,
            "regression": regression,
        }

    @app.websocket("/ws/monitor")
    async def monitor_ws(websocket: WebSocket):
        """性能监控实时推送"""
        await websocket.accept()
        monitor = get_monitor()
        monitor.subscribe(websocket)

        try:
            # 保持连接，接收客户端消息（如订阅过滤）
            while True:
                data = await websocket.receive_json()
                # 支持客户端动态切换订阅的适配器
                if "adapter_id" in data:
                    monitor.unsubscribe(websocket)
                    monitor.subscribe(websocket, adapter_id=data["adapter_id"])
        except WebSocketDisconnect:
            pass
        finally:
            monitor.unsubscribe(websocket)


def _register_share_routes(app: FastAPI) -> None:
    """注册代码分享增强路由"""
    from yanpub.playground.share import get_share_manager
    from fastapi.responses import HTMLResponse, RedirectResponse

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


def _generate_default_template(adapter) -> str:
    """根据语言生成默认示例代码（优先从文件读取）"""
    template_file = _TEMPLATES_DIR / adapter.id / "default.txt"
    if template_file.exists():
        return template_file.read_text(encoding="utf-8")
    return f'# {adapter.name} 示例\n打印("你好，世界！")'


def _register_challenge_routes(app: FastAPI) -> None:
    """注册代码挑战赛路由"""
    from yanpub.playground.challenge import ChallengeManager, get_builtin_challenges

    _challenge_mgr = ChallengeManager()

    # 加载内置挑战（如果尚未创建）
    for c in get_builtin_challenges():
        if _challenge_mgr.get_challenge(c.id) is None:
            _challenge_mgr.create_challenge(c)

    @app.get("/api/challenges")
    async def list_challenges(difficulty: str | None = None, tag: str | None = None):
        """列出挑战"""
        challenges = _challenge_mgr.list_challenges(difficulty=difficulty, tag=tag)
        return {
            "challenges": [
                {
                    "id": c.id,
                    "title": c.title,
                    "difficulty": c.difficulty,
                    "tags": c.tags,
                    "score": c.score,
                    "supported_langs": c.supported_langs,
                    "submit_count": c.submit_count,
                    "pass_count": c.pass_count,
                    "pass_rate": round(c.pass_rate, 3),
                }
                for c in challenges
            ]
        }

    @app.get("/api/challenges/{challenge_id}")
    async def get_challenge(challenge_id: str):
        """获取挑战详情"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        result = c.to_dict()
        # 只返回非隐藏的测试用例
        result["public_test_cases"] = [as_dict_tc(tc) for tc in c.public_test_cases]
        result["hidden_test_count"] = sum(1 for tc in c.test_cases if tc.is_hidden)
        return result

    @app.post("/api/challenges/{challenge_id}/submit")
    async def submit_challenge(challenge_id: str, body: dict):
        """提交挑战解答"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        user = body.get("user", "anonymous")

        if not lang_id or not code.strip():
            return JSONResponse({"error": "缺少 lang 或 code 参数"}, status_code=400)

        try:
            submission = _challenge_mgr.submit(challenge_id, user=user, lang_id=lang_id, code=code)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        return submission.to_dict()

    @app.get("/api/challenges/{challenge_id}/leaderboard")
    async def challenge_leaderboard(challenge_id: str, limit: int = 20):
        """挑战排行榜"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        entries = _challenge_mgr.get_leaderboard(challenge_id=challenge_id)
        return {
            "challenge_id": challenge_id,
            "leaderboard": [
                {
                    "rank": e.rank,
                    "user": e.user,
                    "total_score": e.total_score,
                    "challenges_passed": e.challenges_passed,
                    "avg_time_ms": e.avg_time_ms,
                    "best_lang": e.best_lang,
                }
                for e in entries[:limit]
            ],
        }

    @app.get("/api/leaderboard")
    async def global_leaderboard(limit: int = 50):
        """总排行榜"""
        entries = _challenge_mgr.get_leaderboard()
        return {
            "leaderboard": [
                {
                    "rank": e.rank,
                    "user": e.user,
                    "total_score": e.total_score,
                    "challenges_passed": e.challenges_passed,
                    "total_submissions": e.total_submissions,
                    "avg_time_ms": e.avg_time_ms,
                    "best_lang": e.best_lang,
                }
                for e in entries[:limit]
            ],
        }

    @app.get("/api/challenges/{challenge_id}/submissions")
    async def list_submissions(challenge_id: str, user: str | None = None, limit: int = 20):
        """查询提交记录"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        submissions = _challenge_mgr.get_submissions(challenge_id=challenge_id, user=user)
        return {
            "submissions": [s.to_dict() for s in submissions[-limit:]],
        }


def as_dict_tc(tc):
    """TestCase 转字典"""
    from dataclasses import asdict
    return asdict(tc)


def _register_quality_routes(app: FastAPI) -> None:
    """注册适配器质量评分路由"""

    @app.get("/api/quality")
    async def quality_reports(lang_id: str | None = None):
        """适配器质量评分报告"""
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        if lang_id:
            report = checker.check_one(lang_id)
            if report is None:
                return JSONResponse({"error": f"适配器 {lang_id} 不存在"}, status_code=404)
            return {"reports": [report.to_dict()]}
        reports = checker.check_all()
        return {"reports": [r.to_dict() for r in reports]}
