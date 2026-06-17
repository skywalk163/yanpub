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

from yanpub.core.registry import get_registry

logger = logging.getLogger("yanpub.playground")


# 静态文件和模板目录
_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app() -> FastAPI:
    app = FastAPI(title="YanPlay - 中文编程语言 Playground")

    # ---- 页面路由 ----

    @app.get("/")
    async def index():
        """Playground 主页"""
        return FileResponse(_STATIC_DIR / "index.html")

    # ---- REST API ----

    @app.get("/api/languages")
    async def list_languages():
        """列出可用语言及其信息"""
        registry = get_registry()
        result = []
        for a in registry:
            result.append({
                "id": a.id,
                "name": a.name,
                "version": a.version,
                "extensions": a.file_extensions,
                "capabilities": a.capabilities,
                "keywords": a.keywords[:50] if len(a.keywords) > 50 else a.keywords,
                "commentSyntax": a.comment_syntax,
                "primaryColor": a.primary_color,
                "description": a.description,
            })
        return result

    @app.get("/api/templates/{lang_id}")
    async def get_template(lang_id: str):
        """获取语言示例代码"""
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

        return JSONResponse({
            "lang": lang,
            "name": adapter.name,
            "code": decoded_code,
        })

    @app.post("/api/run")
    async def run_code_sync(body: dict):
        """同步执行代码（REST 方式，适合简单请求）"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return JSONResponse({
                "type": "error",
                "message": f"未知语言: {lang_id}",
            }, status_code=400)

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

        try:
            while True:
                data = await websocket.receive_json()
                lang_id = data.get("lang", "")
                code = data.get("code", "")
                request_id = data.get("id", "")

                adapter = registry.get(lang_id)
                if adapter is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"未知语言: {lang_id}",
                        "id": request_id,
                    })
                    continue

                # 在线程池中执行
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, adapter.eval, code)

                await websocket.send_json({
                    "type": "result",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exitCode": result.exit_code,
                    "durationMs": result.duration_ms,
                    "id": request_id,
                })

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
            None, executor.execute_with_adapter, adapter, code,
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
            return JSONResponse({
                "type": "error",
                "message": f"未知语言: {lang_id}",
            }, status_code=400)

        from yanpub.core.sandbox import SandboxManager, SandboxConfig

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
        from yanpub.core.sandbox import SandboxManager

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
            return JSONResponse({
                "error": f"未知语言: {lang_id}",
            }, status_code=400)

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
            return JSONResponse({
                "error": f"未知语言: {lang_id}",
            }, status_code=400)

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
            return JSONResponse({
                "error": f"未知语言: {lang_id}",
            }, status_code=400)

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
            return JSONResponse(
                {"error": f"重命名失败: {old_path} → {new_path}"}, status_code=400
            )

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
        result = await loop.run_in_executor(
            None, pm.execute_project, project_id, adapter
        )

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
    from yanpub.core.monitor import get_monitor

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


def _generate_default_template(adapter) -> str:
    """根据语言生成默认示例代码"""
    templates = {
        "duan": '# 段言 (Duan) 示例\n打印("你好，世界！")。\n\n设甲为四十二。\n设乙为甲乘二。\n打印(乙)。',
        "yan": '# 言 (Yan) 示例\n打印("你好，世界！")',
        "moyan": '# 墨言 (Moyan) 示例\n打印("你好，世界！")',
    }
    return templates.get(adapter.id, f'# {adapter.name} 示例\n打印("你好，世界！")')
