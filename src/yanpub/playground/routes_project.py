"""Playground 路由 — 多文件项目"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from yanpub.core.adapter.registry import get_registry


def register_project_routes(app: FastAPI) -> None:
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
