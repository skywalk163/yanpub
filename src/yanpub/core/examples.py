"""示例代码管理 — 发现、展示和运行各语言的示例程序

示例来源（优先级从高到低）：
1. 适配器目录下的 examples/ 子目录（由各语言自己维护）
2. playground/templates/{lang_id}/ 内置模板（yanpub 自带）

每个示例文件可以包含前置元数据（YAML front matter）：
    ---
    title: 斐波那契数列
    tags: [递归, 算法]
    difficulty: 中等
    ---
    实际代码...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from yanpub.core.adapter import LanguageAdapter
from yanpub.core.registry import get_registry


@dataclass
class ExampleInfo:
    """单个示例的信息"""

    name: str  # 文件名（不含扩展名），如 "fibonacci"
    title: str  # 显示标题，如 "斐波那契数列"
    lang_id: str  # 所属语言 ID
    path: Path  # 文件绝对路径
    source: str  # 来源: "adapter" | "builtin"
    tags: list[str] = field(default_factory=list)  # 标签
    difficulty: str = ""  # 难度: 入门/简单/中等/困难
    description: str = ""  # 简短描述

    @property
    def code(self) -> str:
        """读取示例代码内容（自动剥离 YAML front matter）"""
        content = self.path.read_text(encoding="utf-8")
        _, body = _parse_front_matter(content)
        return body


def _parse_front_matter(content: str) -> tuple[dict, str]:
    """解析 YAML front matter，返回 (metadata, 剩余内容)

    格式：
        ---
        key: value
        ---
        实际代码
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    yaml_str = content[3:end].strip()
    body = content[end + 3 :].lstrip("\n")

    try:
        import yaml

        meta = yaml.safe_load(yaml_str)
        if not isinstance(meta, dict):
            return {}, content
        return meta, body
    except Exception:
        return {}, content


def _scan_examples_from_dir(examples_dir: Path, lang_id: str, source: str) -> list[ExampleInfo]:
    """扫描目录中的示例文件，返回 ExampleInfo 列表"""
    if not examples_dir.exists() or not examples_dir.is_dir():
        return []

    results: list[ExampleInfo] = []

    for fp in sorted(examples_dir.iterdir()):
        if fp.is_dir():
            continue
        if fp.name.startswith(".") or fp.name.startswith("_"):
            continue
        # 支持任何文本文件扩展名（.txt, .duan, .段, .py, .rkt 等）
        if fp.suffix in (".json", ".yaml", ".yml", ".toml", ".pyc"):
            continue

        try:
            content = fp.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        meta, _ = _parse_front_matter(content)
        name = fp.stem
        # 把中文文件名中的点号等替换
        title = meta.get("title", name)
        tags = meta.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        difficulty = str(meta.get("difficulty", ""))
        description = str(meta.get("description", ""))

        results.append(
            ExampleInfo(
                name=name,
                title=title,
                lang_id=lang_id,
                path=fp,
                source=source,
                tags=tags,
                difficulty=difficulty,
                description=description,
            )
        )

    return results


class ExampleManager:
    """示例代码管理器 — 统一发现和管理所有语言的示例"""

    def __init__(self):
        self._cache: dict[str, list[ExampleInfo]] | None = None

    def _discover_all(self) -> dict[str, list[ExampleInfo]]:
        """发现所有语言的示例（按语言分组）"""
        registry = get_registry()
        result: dict[str, list[ExampleInfo]] = {}

        for adapter in registry:
            lang_id = adapter.id
            examples: list[ExampleInfo] = []

            # 来源 1: 适配器目录下的 examples/ 子目录
            adapter_examples_dir = self._get_adapter_examples_dir(adapter)
            adapter_examples = _scan_examples_from_dir(adapter_examples_dir, lang_id, "adapter")
            examples.extend(adapter_examples)

            # 来源 2: playground/templates/{lang_id}/ 内置模板
            builtin_dir = self._get_builtin_templates_dir(lang_id)
            builtin_examples = _scan_examples_from_dir(builtin_dir, lang_id, "builtin")
            # 去重：如果适配器已有同名示例，跳过内置版
            adapter_names = {e.name for e in adapter_examples}
            for ex in builtin_examples:
                if ex.name not in adapter_names:
                    examples.append(ex)

            if examples:
                result[lang_id] = examples

        return result

    def _get_adapter_examples_dir(self, adapter: LanguageAdapter) -> Path:
        """获取适配器的 examples 目录

        优先使用 adapter.examples_dir 属性，
        回退到适配器模块所在目录下的 examples/ 子目录。
        """
        # 如果适配器自定义了 examples_dir
        custom_dir = getattr(adapter, "examples_dir", None)
        if custom_dir is not None:
            p = Path(custom_dir)
            if p.is_absolute():
                return p
            # 相对路径：相对于适配器模块所在目录
            return self._get_adapter_module_dir(adapter) / custom_dir

        # 默认：适配器模块所在目录下的 examples/
        return self._get_adapter_module_dir(adapter) / "examples"

    def _get_adapter_module_dir(self, adapter: LanguageAdapter) -> Path:
        """获取适配器模块文件所在的目录"""
        import inspect

        module = inspect.getmodule(type(adapter))
        if module is not None and hasattr(module, "__file__") and module.__file__:
            return Path(module.__file__).parent
        # 回退：adapters/{lang_id}/
        adapters_dir = Path(__file__).parent.parent / "adapters"
        return adapters_dir / adapter.id

    def _get_builtin_templates_dir(self, lang_id: str) -> Path:
        """获取 playground 内置模板目录"""
        return Path(__file__).parent.parent / "playground" / "templates" / lang_id

    def refresh(self) -> None:
        """清除缓存，强制重新扫描"""
        self._cache = None

    def list_all(self) -> dict[str, list[ExampleInfo]]:
        """列出所有语言的示例（按语言 ID 分组）"""
        if self._cache is None:
            self._cache = self._discover_all()
        return self._cache

    def list_for_language(self, lang_id: str) -> list[ExampleInfo]:
        """列出指定语言的示例"""
        all_examples = self.list_all()
        return all_examples.get(lang_id, [])

    def get_example(self, lang_id: str, name: str) -> Optional[ExampleInfo]:
        """获取指定语言的指定示例"""
        for ex in self.list_for_language(lang_id):
            if ex.name == name:
                return ex
        return None

    def search(self, keyword: str) -> dict[str, list[ExampleInfo]]:
        """按关键字搜索示例（匹配标题、标签、名称）"""
        keyword_lower = keyword.lower()
        result: dict[str, list[ExampleInfo]] = {}

        for lang_id, examples in self.list_all().items():
            matched = [
                ex
                for ex in examples
                if keyword_lower in ex.title.lower()
                or keyword_lower in ex.name.lower()
                or any(keyword_lower in tag.lower() for tag in ex.tags)
            ]
            if matched:
                result[lang_id] = matched

        return result

    def run_example(self, lang_id: str, name: str) -> Optional[dict]:
        """运行指定示例，返回执行结果

        Returns:
            {"success": bool, "stdout": str, "stderr": str, "duration_ms": float}
            或 None（示例不存在）
        """
        example = self.get_example(lang_id, name)
        if example is None:
            return None

        registry = get_registry()
        adapter = registry.get(lang_id)
        if adapter is None:
            return None

        result = adapter.eval(example.code)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }


# ---- 全局单例 ----

_example_manager: Optional[ExampleManager] = None


def get_example_manager() -> ExampleManager:
    """获取全局示例管理器"""
    global _example_manager
    if _example_manager is None:
        _example_manager = ExampleManager()
    return _example_manager
