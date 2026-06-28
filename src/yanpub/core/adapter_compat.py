"""适配器兼容性验证器 — 验证适配器是否满足最低兼容性要求

AdapterCompatibilityValidator — 四维检查：属性/方法/类型/能力
"""

from __future__ import annotations

from yanpub.core.adapter.adapter import (
    ExecutionResult,
    LanguageAdapter,
)
from yanpub.core.adapter.registry import LanguageRegistry


class AdapterCompatibilityValidator:
    """适配器兼容性验证器 — 验证适配器是否满足最低兼容性要求"""

    # 必需属性/方法
    _REQUIRED_PROPERTIES = ["name", "id", "version", "file_extensions"]
    _REQUIRED_METHODS = ["run", "eval"]

    def __init__(self, registry: LanguageRegistry):
        self.registry = registry

    def validate_adapter(self, adapter: LanguageAdapter) -> dict:
        """验证单个适配器

        检查：
        1. 必需方法是否实现
        2. 返回值类型是否正确
        3. 关键字列表是否非空
        4. 基本执行是否工作
        5. capabilities 声明是否与实际能力匹配

        Returns:
            {"valid": bool, "errors": [...], "warnings": [...]}
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ---- 1. 必需属性/方法是否实现 ----
        for prop in self._REQUIRED_PROPERTIES:
            if not hasattr(adapter, prop):
                errors.append(f"缺少必需属性: {prop}")
            else:
                # 检查属性是否可调用（有值）
                try:
                    val = getattr(adapter, prop)
                    if callable(val) and not isinstance(val, property):
                        # 方法形式的属性，检查是否是抽象方法
                        if getattr(val, "__isabstractmethod__", False):
                            errors.append(f"属性 {prop} 未实现（仍是抽象方法）")
                except Exception as e:
                    errors.append(f"属性 {prop} 访问失败: {e}")

        for method in self._REQUIRED_METHODS:
            if not hasattr(adapter, method):
                errors.append(f"缺少必需方法: {method}")
            else:
                m = getattr(adapter, method)
                if not callable(m):
                    errors.append(f"{method} 不是可调用方法")
                elif getattr(m, "__isabstractmethod__", False):
                    errors.append(f"方法 {method} 未实现（仍是抽象方法）")

        # ---- 2. 返回值类型检查 ----
        # 检查 name/id/version 是否返回正确类型
        try:
            name = adapter.name
            if not isinstance(name, str) or not name:
                errors.append(f"name 属性应返回非空字符串，实际: {type(name).__name__}")
        except Exception as e:
            errors.append(f"name 属性异常: {e}")

        try:
            lang_id = adapter.id
            if not isinstance(lang_id, str) or not lang_id:
                errors.append(f"id 属性应返回非空字符串，实际: {type(lang_id).__name__}")
        except Exception as e:
            errors.append(f"id 属性异常: {e}")

        try:
            version = adapter.version
            if not isinstance(version, str) or not version:
                errors.append(f"version 属性应返回非空字符串，实际: {type(version).__name__}")
        except Exception as e:
            errors.append(f"version 属性异常: {e}")

        try:
            exts = adapter.file_extensions
            if not isinstance(exts, list):
                errors.append(f"file_extensions 应返回列表，实际: {type(exts).__name__}")
            elif not exts:
                warnings.append("file_extensions 为空列表")
        except Exception as e:
            errors.append(f"file_extensions 属性异常: {e}")

        # 检查 run/eval 返回类型
        try:
            result = adapter.eval("")
            if not isinstance(result, ExecutionResult):
                errors.append(f"eval() 应返回 ExecutionResult，实际: {type(result).__name__}")
        except Exception:
            # eval("") 抛异常不一定错，可能不支持空代码
            pass

        # ---- 3. 关键字列表是否非空 ----
        try:
            keywords = adapter.keywords
            if not isinstance(keywords, list):
                warnings.append(f"keywords 应返回列表，实际: {type(keywords).__name__}")
            elif not keywords:
                warnings.append("关键字列表为空，将影响 LSP 补全能力")
        except Exception as e:
            warnings.append(f"关键字加载异常: {e}")

        # ---- 4. 基本执行是否工作 ----
        try:
            comment = adapter.comment_syntax or "#"
            test_code = f"{comment} compat check\n"
            result = adapter.eval(test_code)
            if result.exit_code == -2:
                # 命令未找到 — 后端不可用
                warnings.append(f"基本执行不可用: {result.stderr.strip()}")
            elif result.exit_code < 0:
                warnings.append(f"基本执行异常: exit_code={result.exit_code}")
        except Exception as e:
            warnings.append(f"基本执行异常: {e}")

        # ---- 5. capabilities 声明是否与实际能力匹配 ----
        try:
            caps = adapter.capabilities
            if not isinstance(caps, dict):
                errors.append(f"capabilities 应返回字典，实际: {type(caps).__name__}")
            else:
                # lsp 声明 vs 实际
                if caps.get("lsp") and not adapter.keywords:
                    warnings.append("capabilities.lsp=True 但 keywords 为空，LSP 功能受限")

                # 补全方法存在性
                if caps.get("lsp") and not hasattr(adapter, "complete"):
                    warnings.append("capabilities.lsp=True 但缺少 complete() 方法")

                # 包管理声明 vs 实际
                if caps.get("package_manager"):
                    if not hasattr(adapter, "list_packages") or not hasattr(
                        adapter, "install_package"
                    ):
                        warnings.append("capabilities.package_manager=True 但缺少包管理方法")
        except Exception as e:
            warnings.append(f"capabilities 检查异常: {e}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_all(self) -> dict[str, dict]:
        """验证所有已注册适配器"""
        results: dict[str, dict] = {}
        for adapter in self.registry:
            results[adapter.id] = self.validate_adapter(adapter)
        return results
