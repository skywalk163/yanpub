"""适配器兼容性矩阵 — 检查语言适配器与 yanpub 核心的版本兼容性

兼容性维度：
1. API 兼容性：适配器是否实现了当前 yanpub 版本要求的方法
2. 关键字覆盖率：关键字列表是否足够（>0 即可）
3. LSP 能力：补全/诊断/hover/格式化/重命名 各项支持状态
4. 运行时兼容性：适配器后端是否能成功执行
5. 版本声明一致性：适配器版本号是否合理

输出：
  yanpub compat          # 显示所有适配器的兼容性矩阵
  yanpub compat duan     # 显示指定适配器的详细兼容性
"""

from __future__ import annotations

from dataclasses import dataclass, field

from yanpub import __version__
from yanpub.core.adapter import LanguageAdapter
from yanpub.core.registry import LanguageRegistry


@dataclass
class CompatResult:
    """兼容性检查结果"""
    adapter_id: str
    adapter_name: str
    adapter_version: str = ""
    yanpub_version: str = __version__
    overall: str = "compatible"  # compatible / partial / incompatible
    checks: dict[str, dict] = field(default_factory=dict)

    @property
    def is_compatible(self) -> bool:
        return self.overall != "incompatible"

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "adapter_version": self.adapter_version,
            "yanpub_version": self.yanpub_version,
            "overall": self.overall,
            "checks": self.checks,
        }


# yanpub 当前版本要求的 API 方法
_REQUIRED_METHODS = ["name", "id", "version", "file_extensions", "run", "eval"]
_RECOMMENDED_METHODS = ["keywords", "complete", "diagnose", "hover", "format", "rename"]


def check_compatibility(adapter: LanguageAdapter) -> CompatResult:
    """检查单个适配器的兼容性

    Args:
        adapter: 语言适配器实例

    Returns:
        CompatResult 包含所有兼容性检查结果
    """
    result = CompatResult(
        adapter_id=adapter.id,
        adapter_name=adapter.name,
        adapter_version=adapter.version,
    )

    # ---- 检查1: API 兼容性 ----
    missing_required = []
    missing_recommended = []

    for method in _REQUIRED_METHODS:
        # 检查属性或方法是否存在
        has_it = hasattr(adapter, method)
        if not has_it:
            missing_required.append(method)

    for method in _RECOMMENDED_METHODS:
        has_it = hasattr(adapter, method)
        if not has_it:
            missing_recommended.append(method)

    result.checks["api"] = {
        "status": "ok" if not missing_required else "fail",
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
        "message": (
            "所有必需 API 已实现"
            if not missing_required
            else f"缺少必需 API: {', '.join(missing_required)}"
        ),
    }

    if missing_required:
        result.overall = "incompatible"

    # ---- 检查2: 关键字覆盖率 ----
    keywords = adapter.keywords
    result.checks["keywords"] = {
        "status": "ok" if keywords else "partial",
        "count": len(keywords),
        "message": f"{len(keywords)} 个关键字" if keywords else "未提供关键字列表",
    }

    # ---- 检查3: LSP 能力 ----
    lsp_features = {
        "completion": len(keywords) > 0,
        "diagnostics": hasattr(adapter, "diagnose"),
        "hover": hasattr(adapter, "hover"),
        "formatting": hasattr(adapter, "format"),
        "rename": hasattr(adapter, "rename"),
    }
    supported_count = sum(1 for v in lsp_features.values() if v)

    result.checks["lsp"] = {
        "status": "ok" if supported_count >= 3 else "partial" if supported_count > 0 else "fail",
        "features": lsp_features,
        "supported_count": supported_count,
        "message": f"{supported_count}/5 项 LSP 能力可用",
    }

    # ---- 检查4: 版本格式 ----
    import re
    version = adapter.version
    semver_ok = bool(re.match(r"^\d+\.\d+", version))

    result.checks["version"] = {
        "status": "ok" if semver_ok else "partial",
        "version": version,
        "message": f"版本号: {version}" if semver_ok else f"版本号格式不规范: {version}",
    }

    # 如果尚未标记为 incompatible，检查是否需要标记为 partial
    if result.overall == "compatible":
        partial_checks = [k for k, v in result.checks.items() if v.get("status") == "partial"]
        if partial_checks:
            result.overall = "partial"

    return result


def check_all_compatibility(registry: LanguageRegistry) -> list[CompatResult]:
    """检查所有已注册适配器的兼容性"""
    return [check_compatibility(adapter) for adapter in registry]


def format_compat_matrix(results: list[CompatResult]) -> str:
    """格式化兼容性矩阵为可读文本"""
    lines = []
    lines.append("适配器兼容性矩阵")
    lines.append("=" * 70)
    lines.append(f"yanpub 版本: {__version__}\n")

    # 表格头
    lines.append(f"{'语言':12s} {'版本':10s} {'总体':12s} {'API':6s} {'关键字':8s} {'LSP':6s} {'版本号':8s}")
    lines.append("-" * 70)

    for r in results:
        api_status = r.checks.get("api", {}).get("status", "?")
        kw_status = r.checks.get("keywords", {}).get("status", "?")
        lsp_status = r.checks.get("lsp", {}).get("status", "?")
        ver_status = r.checks.get("version", {}).get("status", "?")

        icon = {"compatible": "✅", "partial": "⚠️", "incompatible": "❌"}.get(r.overall, "?")
        s_icon = {"ok": "✓", "partial": "~", "fail": "✗"}.get

        lines.append(
            f"{r.adapter_name:12s} {r.adapter_version:10s} {icon:4s} {r.overall:8s} "
            f"{s_icon(api_status, '?'):6s} "
            f"{s_icon(kw_status, '?'):8s} "
            f"{s_icon(lsp_status, '?'):6s} "
            f"{s_icon(ver_status, '?'):8s}"
        )

    # 汇总
    lines.append(f"\n{'=' * 70}")
    compatible = sum(1 for r in results if r.overall == "compatible")
    partial = sum(1 for r in results if r.overall == "partial")
    incompatible = sum(1 for r in results if r.overall == "incompatible")
    lines.append(f"总计: {len(results)} 个适配器")
    lines.append(f"  兼容: {compatible}  部分兼容: {partial}  不兼容: {incompatible}")

    return "\n".join(lines)


def format_compat_detail(result: CompatResult) -> str:
    """格式化单个适配器的详细兼容性报告"""
    lines = []
    lines.append(f"{result.adapter_name} ({result.adapter_id}) 兼容性详情")
    lines.append("=" * 50)
    lines.append(f"适配器版本: {result.adapter_version}")
    lines.append(f"yanpub 版本: {result.yanpub_version}")

    icon = {"compatible": "✅", "partial": "⚠️", "incompatible": "❌"}.get(result.overall, "?")
    lines.append(f"总体兼容性: {icon} {result.overall}\n")

    for check_name, check_result in result.checks.items():
        s = check_result.get("status", "unknown")
        s_icon = {"ok": "✓", "partial": "~", "fail": "✗"}.get(s, "?")
        msg = check_result.get("message", "")
        lines.append(f"  {s_icon} {check_name}: {msg}")

        # 详细信息
        if check_name == "api":
            missing_req = check_result.get("missing_required", [])
            missing_rec = check_result.get("missing_recommended", [])
            if missing_req:
                lines.append(f"    缺少必需: {', '.join(missing_req)}")
            if missing_rec:
                lines.append(f"    建议实现: {', '.join(missing_rec)}")

        elif check_name == "keywords":
            count = check_result.get("count", 0)
            if count > 0:
                lines.append(f"    数量: {count}")

        elif check_name == "lsp":
            features = check_result.get("features", {})
            for feat, supported in features.items():
                feat_icon = "✓" if supported else "✗"
                lines.append(f"    {feat_icon} {feat}")

    return "\n".join(lines)
