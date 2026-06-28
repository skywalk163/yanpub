"""适配器测试报告 — 支持 table/json/html 输出

AdapterTestReport — 测试报告数据类
"""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Template

from yanpub.core.adapter_test import AdapterTestResult


@dataclass
class AdapterTestReport:
    """适配器测试报告"""

    adapter_id: str
    adapter_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[AdapterTestResult] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "adapter_id": self.adapter_id,
            "adapter_name": self.adapter_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "duration_ms": round(self.duration_ms, 2),
        }

    def to_table(self) -> str:
        """格式化为文本表格"""
        lines = []
        lines.append(f"适配器测试报告: {self.adapter_name} ({self.adapter_id})")
        lines.append("=" * 70)
        lines.append(
            f"总计: {self.total}  通过: {self.passed}  "
            f"失败: {self.failed}  跳过: {self.skipped}  "
            f"耗时: {self.duration_ms:.0f}ms"
        )
        lines.append("-" * 70)

        if not self.results:
            lines.append("（无测试结果）")
        else:
            for r in self.results:
                if r.message == "跳过（适配器不适用）":
                    icon = "⊘"
                    status = "SKIP"
                elif r.passed:
                    icon = "✓"
                    status = "PASS"
                else:
                    icon = "✗"
                    status = "FAIL"
                lines.append(
                    f"  {icon} [{status:4s}] {r.test_name:30s} {r.duration_ms:6.1f}ms  {r.message}"
                )

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_html(self) -> str:
        """生成 HTML 报告（使用 string.Template 避免花括号冲突）"""
        tmpl = Template(
            """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>适配器测试报告 - ${adapter_name}</title>
<style>
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #f8f9fa; }
  h1 { color: #2C3E50; border-bottom: 2px solid #3498DB; padding-bottom: 0.5rem; }
  .summary { display: flex; gap: 1.5rem; margin: 1.5rem 0; }
  .summary .card { background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 120px; text-align: center; }
  .summary .card .number { font-size: 2rem; font-weight: bold; }
  .summary .card .label { color: #7f8c8d; font-size: 0.9rem; }
  .card.pass .number { color: #27ae60; }
  .card.fail .number { color: #e74c3c; }
  .card.skip .number { color: #f39c12; }
  .card.total .number { color: #2C3E50; }
  .card.time .number { color: #3498DB; font-size: 1.5rem; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th { background: #2C3E50; color: white; padding: 0.75rem 1rem; text-align: left; }
  td { padding: 0.6rem 1rem; border-bottom: 1px solid #ecf0f1; }
  tr:hover { background: #f1f2f6; }
  .pass { color: #27ae60; font-weight: bold; }
  .fail { color: #e74c3c; font-weight: bold; }
  .skip { color: #f39c12; }
  .bar { height: 8px; border-radius: 4px; background: #ecf0f1; margin-top: 0.5rem; }
  .bar-fill { height: 100%; border-radius: 4px; background: #27ae60; }
</style>
</head>
<body>
<h1>适配器测试报告</h1>
<p>${adapter_name} (${adapter_id})</p>

<div class="summary">
  <div class="card total"><div class="number">${total}</div><div class="label">总计</div></div>
  <div class="card pass"><div class="number">${passed}</div><div class="label">通过</div></div>
  <div class="card fail"><div class="number">${failed}</div><div class="label">失败</div></div>
  <div class="card skip"><div class="number">${skipped}</div><div class="label">跳过</div></div>
  <div class="card time"><div class="number">${duration_ms}</div><div class="label">耗时(ms)</div></div>
</div>

<div class="bar"><div class="bar-fill" style="width: ${pass_pct}%"></div></div>

<table>
<tr><th>状态</th><th>测试名</th><th>耗时</th><th>信息</th></tr>
${rows}
</table>
</body>
</html>"""
        )

        pass_pct = f"{self.passed / self.total * 100:.0f}" if self.total > 0 else "0"

        row_parts = []
        for r in self.results:
            if r.message == "跳过（适配器不适用）":
                status = '<span class="skip">⊘ SKIP</span>'
            elif r.passed:
                status = '<span class="pass">✓ PASS</span>'
            else:
                status = '<span class="fail">✗ FAIL</span>'
            row_parts.append(
                f"<tr><td>{status}</td><td>{r.test_name}</td>"
                f"<td>{r.duration_ms:.1f}ms</td><td>{r.message}</td></tr>"
            )

        return tmpl.substitute(
            adapter_name=self.adapter_name,
            adapter_id=self.adapter_id,
            total=self.total,
            passed=self.passed,
            failed=self.failed,
            skipped=self.skipped,
            duration_ms=f"{self.duration_ms:.0f}",
            pass_pct=pass_pct,
            rows="\n".join(row_parts),
        )
