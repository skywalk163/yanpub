"""Tests for Playground 多文件项目功能"""

from __future__ import annotations

import pytest
from pathlib import Path


class TestProjectPathValidation:
    """路径安全验证"""

    def test_valid_simple_path(self):
        from yanpub.playground.project import _validate_path
        assert _validate_path("main.duan") == "main.duan"

    def test_valid_subdirectory_path(self):
        from yanpub.playground.project import _validate_path
        assert _validate_path("lib/helper.duan") == "lib/helper.duan"

    def test_valid_deep_path(self):
        from yanpub.playground.project import _validate_path
        assert _validate_path("a/b/c.duan") == "a/b/c.duan"

    def test_reject_empty_path(self):
        from yanpub.playground.project import _validate_path
        with pytest.raises(ValueError, match="不能为空"):
            _validate_path("")

    def test_reject_parent_traversal(self):
        from yanpub.playground.project import _validate_path
        with pytest.raises(ValueError, match="路径穿越"):
            _validate_path("../etc/passwd")

    def test_reject_absolute_path(self):
        from yanpub.playground.project import _validate_path
        with pytest.raises(ValueError, match="绝对路径"):
            _validate_path("/etc/passwd")

    def test_reject_mid_traversal(self):
        from yanpub.playground.project import _validate_path
        with pytest.raises(ValueError, match="路径穿越"):
            _validate_path("foo/../../etc/passwd")

    def test_normalize_backslash(self):
        from yanpub.playground.project import _validate_path
        assert _validate_path("lib\\helper.duan") == "lib/helper.duan"


class TestProjectFile:
    """ProjectFile 数据类"""

    def test_create(self):
        from yanpub.playground.project import ProjectFile
        pf = ProjectFile(path="main.duan", content="hello")
        assert pf.path == "main.duan"
        assert pf.content == "hello"
        assert pf.language == ""
        assert pf.modified is False

    def test_to_dict(self):
        from yanpub.playground.project import ProjectFile
        pf = ProjectFile(path="main.duan", content="hello", language="duan", modified=True)
        d = pf.to_dict()
        assert d["path"] == "main.duan"
        assert d["content"] == "hello"
        assert d["language"] == "duan"
        assert d["modified"] is True

    def test_from_dict(self):
        from yanpub.playground.project import ProjectFile
        d = {"path": "lib/a.duan", "content": "code", "language": "duan", "modified": False}
        pf = ProjectFile.from_dict(d)
        assert pf.path == "lib/a.duan"
        assert pf.content == "code"

    def test_roundtrip(self):
        from yanpub.playground.project import ProjectFile
        pf = ProjectFile(path="x.duan", content="y", language="z", modified=True)
        pf2 = ProjectFile.from_dict(pf.to_dict())
        assert pf2.path == pf.path
        assert pf2.content == pf.content
        assert pf2.language == pf.language
        assert pf2.modified == pf.modified


class TestProject:
    """Project 数据类"""

    def test_create_project(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        assert p.id == "abc"
        assert p.name == "test"
        assert p.language == "duan"
        assert p.main_file == "main.duan"
        assert len(p.files) == 0
        assert p.created_at > 0

    def test_add_file(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        pf = p.add_file("lib/utils.duan", "# utils", "duan")
        assert pf.path == "lib/utils.duan"
        assert pf.content == "# utils"
        assert "lib/utils.duan" in p.files

    def test_add_file_rejects_bad_path(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        with pytest.raises(ValueError):
            p.add_file("../evil.duan")

    def test_remove_file(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("a.duan", "code")
        assert p.remove_file("a.duan") is True
        assert len(p.files) == 0

    def test_remove_nonexistent_file(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        assert p.remove_file("nope.duan") is False

    def test_get_file(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("a.duan", "code")
        pf = p.get_file("a.duan")
        assert pf is not None
        assert pf.content == "code"
        assert p.get_file("nope.duan") is None

    def test_list_files_sorted(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("z.duan", "z")
        p.add_file("a.duan", "a")
        p.add_file("m.duan", "m")
        paths = [f.path for f in p.list_files()]
        assert paths == ["a.duan", "m.duan", "z.duan"]

    def test_rename_file(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("old.duan", "code")
        assert p.rename_file("old.duan", "new.duan") is True
        assert "new.duan" in p.files
        assert "old.duan" not in p.files
        assert p.get_file("new.duan").content == "code"

    def test_rename_file_updates_main(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan", main_file="main.duan")
        p.add_file("main.duan", "code")
        p.rename_file("main.duan", "entry.duan")
        assert p.main_file == "entry.duan"

    def test_rename_nonexistent(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        assert p.rename_file("nope.duan", "new.duan") is False

    def test_rename_to_existing(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("a.duan", "a")
        p.add_file("b.duan", "b")
        assert p.rename_file("a.duan", "b.duan") is False

    def test_to_dict(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("main.duan", "hello")
        d = p.to_dict()
        assert d["id"] == "abc"
        assert d["name"] == "test"
        assert d["language"] == "duan"
        assert d["mainFile"] == "main.duan"
        assert "main.duan" in d["files"]

    def test_from_dict(self):
        from yanpub.playground.project import Project
        p = Project(id="abc", name="test", language="duan")
        p.add_file("main.duan", "hello")
        d = p.to_dict()
        p2 = Project.from_dict(d)
        assert p2.id == p.id
        assert p2.name == p.name
        assert len(p2.files) == 1
        assert p2.get_file("main.duan").content == "hello"


class TestProjectManager:
    """ProjectManager 核心功能"""

    def test_create_default_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_project("test", "duan")
        assert p.name == "test"
        assert p.language == "duan"
        assert len(p.files) >= 1
        assert p.main_file == "main.duan"

    def test_create_multi_file_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_project("test", "duan", template="multi-file")
        assert len(p.files) == 2
        assert "main.duan" in p.files
        assert "lib/utils.duan" in p.files

    def test_get_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_project("test", "duan")
        assert pm.get_project(p.id) is p
        assert pm.get_project("nonexistent") is None

    def test_list_projects(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p1 = pm.create_project("a", "duan")
        p2 = pm.create_project("b", "duan")
        projects = pm.list_projects()
        assert len(projects) == 2
        ids = [p["id"] for p in projects]
        assert p1.id in ids
        assert p2.id in ids

    def test_delete_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_project("test", "duan")
        assert pm.delete_project(p.id) is True
        assert pm.get_project(p.id) is None
        assert pm.delete_project("nonexistent") is False

    def test_save_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_project("test", "duan")
        p.name = "renamed"
        pm.save_project(p)
        assert pm.get_project(p.id).name == "renamed"

    def test_execute_project(self):
        from yanpub.playground.project import ProjectManager
        from yanpub.core.adapter.adapter import LanguageAdapter, ExecutionResult

        class MockAdapter(LanguageAdapter):
            @property
            def name(self): return "Mock"
            @property
            def id(self): return "mock"
            @property
            def version(self): return "1.0"
            @property
            def file_extensions(self): return [".mock"]
            def run(self, file_path, args=None):
                code = Path(file_path).read_text(encoding="utf-8")
                return ExecutionResult(stdout=f"RAN:{code}", exit_code=0, duration_ms=10)
            def eval(self, code):
                return ExecutionResult(stdout=f"EVAL:{code}", exit_code=0, duration_ms=5)

        pm = ProjectManager()
        p = pm.create_project("test", "mock")
        p.add_file("main.mock", "hello world", "mock")

        mock = MockAdapter()
        result = pm.execute_project(p.id, mock)
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_execute_project_multi_file(self):
        from yanpub.playground.project import ProjectManager
        from yanpub.core.adapter.adapter import LanguageAdapter, ExecutionResult

        class MockAdapter(LanguageAdapter):
            @property
            def name(self): return "Mock"
            @property
            def id(self): return "mock"
            @property
            def version(self): return "1.0"
            @property
            def file_extensions(self): return [".mock"]
            def run(self, file_path, args=None):
                code = Path(file_path).read_text(encoding="utf-8")
                lib_path = Path(file_path).parent / "lib" / "utils.mock"
                lib_content = ""
                if lib_path.exists():
                    lib_content = lib_path.read_text(encoding="utf-8")
                return ExecutionResult(
                    stdout=f"MAIN:{code}|LIB:{lib_content}",
                    exit_code=0,
                    duration_ms=10,
                )
            def eval(self, code):
                return ExecutionResult(stdout="", exit_code=0, duration_ms=5)

        pm = ProjectManager()
        p = pm.create_project("test", "mock")
        p.add_file("main.mock", "main code", "mock")
        p.add_file("lib/utils.mock", "lib code", "mock")

        mock = MockAdapter()
        result = pm.execute_project(p.id, mock)
        assert result.exit_code == 0
        assert "main code" in result.stdout
        assert "lib code" in result.stdout

    def test_execute_nonexistent_project(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        result = pm.execute_project("nonexistent", None)
        assert result.exit_code == -1
        assert "不存在" in result.stderr

    def test_execute_empty_project(self):
        from yanpub.playground.project import ProjectManager, Project
        pm = ProjectManager()
        p = Project(id="empty", name="empty", language="duan")
        pm.save_project(p)
        result = pm.execute_project("empty", None)
        assert result.exit_code == -1
        assert "没有文件" in result.stderr

    def test_get_templates(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        templates = pm.get_templates("duan")
        assert len(templates) >= 2
        names = [t["name"] for t in templates]
        assert "默认项目" in names
        assert "多文件项目" in names

    def test_get_templates_unknown_lang(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        templates = pm.get_templates("unknown_lang")
        assert len(templates) >= 1

    def test_create_from_template(self):
        from yanpub.playground.project import ProjectManager
        pm = ProjectManager()
        p = pm.create_from_template("test", "duan", "multi-file")
        assert len(p.files) == 2

    def test_global_project_manager(self):
        from yanpub.playground.project import get_project_manager
        pm1 = get_project_manager()
        pm2 = get_project_manager()
        assert pm1 is pm2


class TestProjectAPI:
    """Playground API 路由测试"""

    @pytest.fixture
    def client(self):
        from yanpub.playground.server import create_app
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        app = create_app()
        return TestClient(app)

    def test_create_project(self, client):
        resp = client.post("/api/project/create", json={
            "name": "测试项目",
            "language": "duan",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "测试项目"
        assert data["language"] == "duan"
        assert len(data["files"]) >= 1

    def test_get_project(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.get(f"/api/project/{project_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == project_id

    def test_get_nonexistent_project(self, client):
        resp = client.get("/api/project/nonexistent")
        assert resp.status_code == 404

    def test_list_project_files(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.get(f"/api/project/{project_id}/files")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert len(data["files"]) >= 1

    def test_add_project_file(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.post(f"/api/project/{project_id}/files", json={
            "path": "lib/helper.duan",
            "content": "# helper",
            "language": "duan",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "lib/helper.duan"

    def test_add_file_rejects_bad_path(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.post(f"/api/project/{project_id}/files", json={
            "path": "../evil.duan",
            "content": "",
        })
        assert resp.status_code == 400

    def test_update_project_file(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.put(f"/api/project/{project_id}/files/main.duan", json={
            "content": "new content",
        })
        assert resp.status_code == 200
        assert resp.json()["content"] == "new content"
        assert resp.json()["modified"] is True

    def test_delete_project_file(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        client.post(f"/api/project/{project_id}/files", json={
            "path": "extra.duan",
            "content": "extra",
        })

        resp = client.delete(f"/api/project/{project_id}/files/extra.duan")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_rename_project_file(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.post(f"/api/project/{project_id}/files/rename", json={
            "oldPath": "main.duan",
            "newPath": "entry.duan",
        })
        assert resp.status_code == 200
        assert resp.json()["mainFile"] == "entry.duan"

    def test_run_project(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.post(f"/api/project/{project_id}/run")
        # May fail if duan adapter not available, but should not crash
        assert resp.status_code in (200, 400)

    def test_get_project_templates(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.get(f"/api/project/{project_id}/templates")
        assert resp.status_code == 200
        assert len(resp.json()["templates"]) >= 1

    def test_list_projects(self, client):
        client.post("/api/project/create", json={"name": "a", "language": "duan"})
        client.post("/api/project/create", json={"name": "b", "language": "duan"})

        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert len(resp.json()["projects"]) >= 2

    def test_delete_project(self, client):
        resp = client.post("/api/project/create", json={
            "name": "test",
            "language": "duan",
        })
        project_id = resp.json()["id"]

        resp = client.delete(f"/api/project/{project_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/project/{project_id}")
        assert resp.status_code == 404


class TestProjectCLI:
    """CLI project 命令测试"""

    def test_project_create(self):
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["project", "create", "-n", "CLI测试", "-L", "duan"])
        assert result.exit_code == 0
        assert "项目已创建" in result.output
        assert "CLI测试" in result.output

    def test_project_list_empty(self):
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        # The global ProjectManager may have projects from other tests,
        # so we just verify the command runs without error
        result = runner.invoke(main, ["project", "list"])
        assert result.exit_code == 0
        # Output should contain either "没有项目" or a project listing
        assert "项目列表" in result.output or "没有项目" in result.output

    def test_project_delete_nonexistent(self):
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["project", "delete", "-p", "nonexistent"])
        assert result.exit_code == 1
        assert "项目不存在" in result.output

    def test_project_help(self):
        from click.testing import CliRunner
        from yanpub.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["project", "--help"])
        assert result.exit_code == 0
        assert "项目管理" in result.output
