"""Playground 多文件项目管理

支持创建、编辑和执行多文件项目，每个项目包含多个源文件，
以 main_file 为入口执行。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from yanpub.core.adapter import ExecutionResult, LanguageAdapter


def _validate_path(path: str) -> str:
    """验证文件路径安全性，禁止 .. 和绝对路径"""
    if not path:
        raise ValueError("文件路径不能为空")
    # 统一使用正斜杠
    path = path.replace("\\", "/")
    if os.path.isabs(path):
        raise ValueError(f"禁止使用绝对路径: {path}")
    # normpath 在 Windows 上会将 / 转为 \，所以用原始路径检查
    parts = path.split("/")
    if ".." in parts:
        raise ValueError(f"禁止路径穿越: {path}")
    # 不允许以 / 开头
    if path.startswith("/"):
        raise ValueError(f"禁止使用绝对路径: {path}")
    return path


@dataclass
class ProjectFile:
    """项目文件"""

    path: str  # 相对路径，如 "main.duan", "lib/helper.duan"
    content: str = ""
    language: str = ""  # 语言 ID
    modified: bool = False

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "content": self.content,
            "language": self.language,
            "modified": self.modified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProjectFile:
        return cls(
            path=data["path"],
            content=data.get("content", ""),
            language=data.get("language", ""),
            modified=data.get("modified", False),
        )


@dataclass
class Project:
    """多文件项目"""

    id: str
    name: str
    language: str  # 主语言
    files: dict[str, ProjectFile] = field(default_factory=dict)  # path → ProjectFile
    main_file: str = "main.duan"  # 入口文件
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()
        if not self.updated_at:
            self.updated_at = self.created_at

    def add_file(self, path: str, content: str = "", language: str = "") -> ProjectFile:
        """添加文件到项目"""
        path = _validate_path(path)
        pf = ProjectFile(path=path, content=content, language=language)
        self.files[path] = pf
        self.updated_at = time.time()
        return pf

    def remove_file(self, path: str) -> bool:
        """删除项目文件"""
        if path not in self.files:
            return False
        del self.files[path]
        self.updated_at = time.time()
        return True

    def get_file(self, path: str) -> Optional[ProjectFile]:
        """获取项目文件"""
        return self.files.get(path)

    def list_files(self) -> list[ProjectFile]:
        """列出所有文件（按路径排序）"""
        return [self.files[k] for k in sorted(self.files.keys())]

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """重命名文件"""
        if old_path not in self.files:
            return False
        new_path = _validate_path(new_path)
        if new_path in self.files:
            return False
        pf = self.files.pop(old_path)
        pf.path = new_path
        self.files[new_path] = pf
        if self.main_file == old_path:
            self.main_file = new_path
        self.updated_at = time.time()
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "mainFile": self.main_file,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        files = {}
        raw_files = data.get("files", {})
        for k, v in raw_files.items():
            if isinstance(v, dict):
                files[k] = ProjectFile.from_dict(v)
            else:
                # 兼容：v 可能是 ProjectFile 实例
                files[k] = v
        return cls(
            id=data["id"],
            name=data["name"],
            language=data["language"],
            files=files,
            main_file=data.get("mainFile", data.get("main_file", "main.duan")),
            created_at=data.get("createdAt", data.get("created_at", 0.0)),
            updated_at=data.get("updatedAt", data.get("updated_at", 0.0)),
        )


# ---- 模板 ----

_TEMPLATES: dict[str, list[dict]] = {
    "duan": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "段言基础项目模板",
            "files": {
                "main.duan": (
                    "# 段言 (Duan) 示例\n"
                    "打印(\"你好，世界！\")。\n\n"
                    "设甲为四十二。\n设乙为甲乘二。\n打印(乙)。\n\n"
                    "段落 求和 参数 甲 乙\n  返回 甲 加 乙。\n结束\n\n"
                    "设结果为 求和 三 五。\n打印(结果)。\n\n"
                    "# 斐波那契数列\n"
                    "段落 斐波那契 参数 甲\n"
                    "  如果 甲 小于 二 那么\n    返回 甲。\n  结束\n"
                    "  返回 斐波那契(甲减一) 加 斐波那契(甲减二)。\n结束\n\n"
                    "设斐为 斐波那契(十)。\n打印(\"斐波那契(10) = \")。\n打印(斐)。"
                ),
            },
            "mainFile": "main.duan",
        },
        {
            "id": "multi-file",
            "name": "多文件项目",
            "description": "包含库文件和主文件",
            "files": {
                "lib/utils.duan": "# 工具库\n段落 加一(甲)。\n  返回 甲加一。\n结束。",
                "main.duan": "# 主文件\n导入《utils》。\n设结果为加一(四十一)。\n打印(结果)。",
            },
            "mainFile": "main.duan",
        },
    ],
    "yan": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "言基础项目模板",
            "files": {
                "main.yan": (
                    "-- 言 (Yan) 示例\n"
                    "打印(\"你好，世界！\")\n\n"
                    "定义 甲 = 42\n定义 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定义 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "-- 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.yan",
        },
    ],
    "moyan": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "墨言基础项目模板",
            "files": {
                "main.moyan": (
                    "-- 墨言 (Moyan) 示例\n"
                    "打印(\"你好，世界！\")\n\n"
                    "定义 甲 = 42\n定义 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定义 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "-- 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.moyan",
        },
    ],
    "mingdao": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "明道基础项目模板",
            "files": {
                "main.rkt": (
                    "#lang mingdao\n"
                    "# 明道 (Mingdao) 示例\n\n"
                    "打印 42\n\n"
                    "定义 甲 = 42\n定义 乙 = 甲 * 2\n打印 乙\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定义 结果 = 求和(3, 5)\n打印 结果\n\n"
                    "# 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印 斐波那契(10)"
                ),
            },
            "mainFile": "main.rkt",
        },
    ],
    "zhixing": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "知行基础项目模板",
            "files": {
                "main.yan": (
                    "# 知行 (Zhixing) 示例\n"
                    "打印(\"你好，世界！\")\n\n"
                    "定 甲 = 42\n定 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "# 斐波那契数列\n"
                    "函 斐波那契(甲) {\n"
                    "  若 甲 < 2 则 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.yan",
        },
    ],
    "yanzhi": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "言知基础项目模板",
            "files": {
                "main.yan": (
                    "# 言知 (Yanzhi) 示例\n"
                    "打印(\"你好，世界！\")\n\n"
                    "定义 甲 = 42\n定义 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定义 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "# 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.yan",
        },
    ],
    "xinyu": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "心语基础项目模板",
            "files": {
                "main.xinyu": (
                    "# 心语 (XinYu) 示例\n"
                    "打印(\"你好，世界！\")\n\n"
                    "定 甲 = 42\n定 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "# 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.xinyu",
        },
    ],
    "yanlv": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "言律基础项目模板",
            "files": {
                "main.yan": (
                    "# 言律 (YanLv) 示例\n"
                    "输出(\"你好，世界！\")\n\n"
                    "定 甲 = 42\n定 乙 = 甲 * 2\n输出(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定 结果 = 求和(3, 5)\n输出(结果)\n\n"
                    "# 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "输出(\"斐波那契(10) = \" + 斐波那契(10))"
                ),
            },
            "mainFile": "main.yan",
        },
    ],
    "traeyan": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "趣言基础项目模板",
            "files": {
                "main.yan": (
                    "# 趣言 (traeyan) 示例\n"
                    "印\"你好，世界！\"。\n\n"
                    "定甲等于42。\n定乙等于加甲 2。\n印乙。\n\n"
                    "定mysum等于函a b：\n"
                    "  返加a b。\n"
                    "。\n\n"
                    "定result等于mysum 3 5。\n印result。\n\n"
                    "# 斐波那契数列\n"
                    "定fib等于函n：\n"
                    "  若小n 2：\n    返n。\n  结束\n"
                    "  返加fib减n 1 fib减n 2。\n"
                    "。\n\n"
                    "印\"斐波那契(10)等于\"。\n印fib 10。"
                ),
            },
            "mainFile": "main.yan",
        },
    ],
    "hanyu": [
        {
            "id": "default",
            "name": "默认项目",
            "description": "翰语基础项目模板",
            "files": {
                "main.hanyu": (
                    "# 翰语 (Hanyu) 示例\n"
                    "打印(42)\n\n"
                    "定义 甲 = 42\n定义 乙 = 甲 * 2\n打印(乙)\n\n"
                    "函数 求和(甲, 乙) {\n  返回 甲 + 乙\n}\n\n"
                    "定义 结果 = 求和(3, 5)\n打印(结果)\n\n"
                    "# 斐波那契数列\n"
                    "函数 斐波那契(甲) {\n"
                    "  如果 甲 < 2 那么 {\n    返回 甲\n  }\n"
                    "  返回 斐波那契(甲 - 1) + 斐波那契(甲 - 2)\n}\n\n"
                    "打印(斐波那契(10))"
                ),
            },
            "mainFile": "main.hanyu",
        },
    ],
}


def _get_default_template(lang_id: str) -> dict:
    """获取语言默认模板"""
    if lang_id in _TEMPLATES and _TEMPLATES[lang_id]:
        return _TEMPLATES[lang_id][0]
    # 通用模板
    return {
        "id": "default",
        "name": "默认项目",
        "description": f"{lang_id} 基础项目模板",
        "files": {
            f"main.{lang_id}": f'# {lang_id} 示例\n打印("你好，世界！")',
        },
        "mainFile": f"main.{lang_id}",
    }


class ProjectManager:
    """项目管理器"""

    def __init__(self, storage_dir: Path | None = None):
        self._projects: dict[str, Project] = {}
        self._storage_dir = storage_dir

    def create_project(
        self, name: str, language: str, template: str = "default"
    ) -> Project:
        """创建多文件项目"""
        project_id = uuid.uuid4().hex[:12]
        tmpl = None

        # 查找模板
        lang_templates = _TEMPLATES.get(language, [])
        for t in lang_templates:
            if t["id"] == template:
                tmpl = t
                break

        if tmpl is None:
            tmpl = _get_default_template(language)

        main_file = tmpl.get("mainFile", f"main.{language}")
        project = Project(
            id=project_id,
            name=name,
            language=language,
            main_file=main_file,
        )

        # 从模板创建文件
        for path, content in tmpl.get("files", {}).items():
            project.add_file(path, content, language)

        self._projects[project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        return self._projects.get(project_id)

    def list_projects(self) -> list[dict]:
        """列出所有项目"""
        result = []
        for p in self._projects.values():
            result.append({
                "id": p.id,
                "name": p.name,
                "language": p.language,
                "fileCount": len(p.files),
                "mainFile": p.main_file,
                "createdAt": p.created_at,
                "updatedAt": p.updated_at,
            })
        return sorted(result, key=lambda x: x["updatedAt"], reverse=True)

    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        if project_id not in self._projects:
            return False
        del self._projects[project_id]
        return True

    def save_project(self, project: Project) -> None:
        """保存项目（更新内存）"""
        project.updated_at = time.time()
        self._projects[project.id] = project

    def execute_project(
        self, project_id: str, adapter: LanguageAdapter
    ) -> ExecutionResult:
        """执行项目 — 将所有文件写入临时目录，运行 main_file"""
        project = self._projects.get(project_id)
        if project is None:
            return ExecutionResult(
                stderr=f"项目不存在: {project_id}",
                exit_code=-1,
            )

        if not project.files:
            return ExecutionResult(
                stderr="项目没有文件",
                exit_code=-1,
            )

        main_file = project.get_file(project.main_file)
        if main_file is None:
            return ExecutionResult(
                stderr=f"入口文件不存在: {project.main_file}",
                exit_code=-1,
            )

        # 创建临时目录并写入所有文件
        tmp_dir = tempfile.mkdtemp(prefix="yanpub_project_")
        try:
            for pf in project.list_files():
                # 统一路径分隔符
                rel_path = pf.path.replace("\\", "/")
                file_path = os.path.join(tmp_dir, *rel_path.split("/"))
                # 确保目录存在
                file_dir = os.path.dirname(file_path)
                if file_dir:
                    os.makedirs(file_dir, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(pf.content)

            # 执行 main_file
            main_rel = project.main_file.replace("\\", "/")
            main_path = os.path.join(tmp_dir, *main_rel.split("/"))
            return adapter.run(main_path)
        except Exception as e:
            return ExecutionResult(
                stderr=f"执行失败: {e}",
                exit_code=-1,
            )
        finally:
            # 清理临时目录
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def get_templates(self, language: str) -> list[dict]:
        """获取语言可用模板"""
        lang_templates = _TEMPLATES.get(language, [])
        if not lang_templates:
            # 返回通用模板
            return [_get_default_template(language)]
        return lang_templates

    def create_from_template(
        self, name: str, language: str, template_id: str
    ) -> Project:
        """从指定模板创建项目"""
        return self.create_project(name, language, template=template_id)


# 全局 ProjectManager 实例
_global_manager: ProjectManager | None = None


def get_project_manager() -> ProjectManager:
    """获取全局 ProjectManager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ProjectManager()
    return _global_manager
