"""适配器健康检查 — 检测语言后端是否可用

健康检查维度：
1. 命令可达性：运行命令是否在 PATH 中
2. 基本执行：能否执行简单代码
3. 关键字加载：关键字列表是否可用
4. 响应时间：执行延迟

结果分级：
- healthy  ✅  所有检查通过
- degraded ⚠️  部分检查失败（如关键字不可用但能执行）
- unhealthy ❌  核心检查失败（如后端不可达）
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field

from yanpub.core.adapter.adapter import LanguageAdapter, SubprocessAdapter


@dataclass
class HealthCheckResult:
    """健康检查结果"""

    adapter_id: str
    adapter_name: str
    status: str  # healthy / degraded / unhealthy
    checks: dict[str, dict] = field(default_factory=dict)
    response_ms: float = 0.0
    message: str = ""

    @property
    def is_healthy(self) -> bool:
        return self.status == "healthy"

    @property
    def is_available(self) -> bool:
        return self.status != "unhealthy"

    def to_dict(self) -> dict:
        return {
            "id": self.adapter_id,
            "name": self.adapter_name,
            "status": self.status,
            "checks": self.checks,
            "response_ms": round(self.response_ms, 1),
            "message": self.message,
        }


def check_adapter_health(adapter: LanguageAdapter) -> HealthCheckResult:
    """执行适配器健康检查

    Args:
        adapter: 语言适配器实例

    Returns:
        HealthCheckResult 包含所有检查结果
    """
    result = HealthCheckResult(
        adapter_id=adapter.id,
        adapter_name=adapter.name,
        status="healthy",
    )

    overall_start = time.monotonic()

    # ---- 检查1: 关键字加载 ----
    try:
        keywords = adapter.keywords
        result.checks["keywords"] = {
            "status": "ok",
            "count": len(keywords),
            "message": f"{len(keywords)} 个关键字已加载",
        }
    except Exception as e:
        result.checks["keywords"] = {
            "status": "fail",
            "message": f"关键字加载失败: {e}",
        }
        result.status = "degraded"

    # ---- 检查2: 命令可达性（仅 SubprocessAdapter）----
    if isinstance(adapter, SubprocessAdapter):
        cmd = adapter._run_command
        if cmd:
            cmd_name = cmd[0]
            if shutil.which(cmd_name):
                result.checks["command"] = {
                    "status": "ok",
                    "command": " ".join(cmd),
                    "message": f"命令 '{cmd_name}' 可达",
                }
            else:
                result.checks["command"] = {
                    "status": "fail",
                    "command": " ".join(cmd),
                    "message": f"命令 '{cmd_name}' 未找到（不在 PATH 中）",
                }
                result.status = "unhealthy"
        else:
            result.checks["command"] = {
                "status": "skip",
                "message": "无运行命令",
            }
    else:
        result.checks["command"] = {
            "status": "skip",
            "message": "非子进程适配器",
        }

    # ---- 检查3: 基本执行 ----
    if result.status != "unhealthy":
        try:
            start = time.monotonic()
            test_code = _get_test_code(adapter)
            exec_result = adapter.eval(test_code)
            elapsed = (time.monotonic() - start) * 1000

            if exec_result.exit_code == 0:
                result.checks["execution"] = {
                    "status": "ok",
                    "response_ms": round(elapsed, 1),
                    "message": f"代码执行成功（{elapsed:.0f}ms）",
                }
            else:
                result.checks["execution"] = {
                    "status": "fail",
                    "response_ms": round(elapsed, 1),
                    "exit_code": exec_result.exit_code,
                    "message": f"代码执行失败（退出码 {exec_result.exit_code}）",
                }
                result.status = "degraded"
        except Exception as e:
            result.checks["execution"] = {
                "status": "fail",
                "message": f"执行异常: {e}",
            }
            result.status = "unhealthy"
    else:
        result.checks["execution"] = {
            "status": "skip",
            "message": "后端不可达，跳过执行检查",
        }

    # ---- 检查4: LSP 能力 ----
    caps = adapter.capabilities
    result.checks["lsp"] = {
        "status": "ok" if caps.get("lsp") else "skip",
        "capabilities": caps,
    }

    overall_elapsed = (time.monotonic() - overall_start) * 1000
    result.response_ms = overall_elapsed

    # 生成总结消息
    if result.status == "healthy":
        result.message = f"{adapter.name} 后端正常运行"
    elif result.status == "degraded":
        failed = [k for k, v in result.checks.items() if v.get("status") == "fail"]
        result.message = f"{adapter.name} 部分功能不可用: {', '.join(failed)}"
    else:
        result.message = f"{adapter.name} 后端不可用"

    return result


def _get_test_code(adapter: LanguageAdapter) -> str:
    """获取用于测试执行的代码片段"""
    # 尝试使用注释语法写一个简单的测试
    comment = adapter.comment_syntax or "#"
    return f'{comment} health check\n打印("ok")。\n'


def check_all_adapters(registry) -> list[HealthCheckResult]:
    """检查所有已注册适配器的健康状态

    Args:
        registry: LanguageRegistry 实例

    Returns:
        所有适配器的健康检查结果列表
    """
    results = []
    for adapter in registry:
        results.append(check_adapter_health(adapter))
    return results


def format_health_report(results: list[HealthCheckResult]) -> str:
    """格式化健康检查报告为可读文本"""
    lines = []
    lines.append("适配器健康检查报告")
    lines.append("=" * 50)

    healthy_count = 0
    degraded_count = 0
    unhealthy_count = 0

    for r in results:
        status_icon = {"healthy": "✅", "degraded": "⚠️", "unhealthy": "❌"}.get(r.status, "?")
        lines.append(f"\n{status_icon} {r.adapter_name} ({r.adapter_id}) — {r.status}")
        lines.append(f"   {r.message}")
        lines.append(f"   响应时间: {r.response_ms:.0f}ms")

        for check_name, check_result in r.checks.items():
            s = check_result.get("status", "unknown")
            icon = {"ok": "✓", "fail": "✗", "skip": "-"}.get(s, "?")
            msg = check_result.get("message", "")
            lines.append(f"   {icon} {check_name}: {msg}")

        if r.status == "healthy":
            healthy_count += 1
        elif r.status == "degraded":
            degraded_count += 1
        else:
            unhealthy_count += 1

    lines.append(f"\n{'=' * 50}")
    lines.append(f"总计: {len(results)} 个适配器")
    lines.append(f"  健康: {healthy_count}  降级: {degraded_count}  不可用: {unhealthy_count}")

    return "\n".join(lines)
