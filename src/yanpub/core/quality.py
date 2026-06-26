"""适配器质量评分 — 自动化检查适配器完整度、文档覆盖、示例丰富度

评分维度（总分 100）：
1. 基础完整度（0-25）：adapter.py + adapter.yaml 存在、类定义正确、可实例化
2. 元数据质量（0-20）：YAML 字段完整、版本号合法+成熟度、扩展名正确、颜色有效
3. 示例丰富度（0-20）：examples/ 目录存在、示例数量、front matter 质量、多样性
4. 文档覆盖（0-15）：README/CONTRIBUTING、关键字文档质量、描述完整性
5. 功能验证（0-20）：eval/run/repl 可用性、关键字丰富度、capabilities 覆盖、健康检查

输出：
- 终端报告（彩色表格）
- HTML 报告（深色主题）
- JSON 报告
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class DimensionScore:
    """单个评分维度"""

    name: str
    max_score: int
    score: int
    details: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def percentage(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0.0


@dataclass
class QualityReport:
    """适配器质量报告"""

    lang_id: str
    lang_name: str
    total_score: int
    max_score: int
    dimensions: list[DimensionScore] = field(default_factory=list)
    grade: str = ""  # S/A/B/C/D/F

    def __post_init__(self):
        if not self.grade:
            self.grade = self._compute_grade()

    def _compute_grade(self) -> str:
        pct = (self.total_score / self.max_score * 100) if self.max_score > 0 else 0
        if pct >= 95:
            return "S"
        elif pct >= 85:
            return "A"
        elif pct >= 70:
            return "B"
        elif pct >= 55:
            return "C"
        elif pct >= 40:
            return "D"
        return "F"

    @property
    def percentage(self) -> float:
        return (self.total_score / self.max_score * 100) if self.max_score > 0 else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class QualityChecker:
    """适配器质量检查器"""

    def __init__(self, adapters_dir: Optional[Path] = None):
        if adapters_dir is None:
            adapters_dir = Path(__file__).parent.parent / "adapters"
        self._adapters_dir = adapters_dir

    def check_all(self) -> list[QualityReport]:
        """检查所有适配器"""
        reports = []
        if not self._adapters_dir.exists():
            return reports

        for adapter_dir in sorted(self._adapters_dir.iterdir()):
            if not adapter_dir.is_dir() or adapter_dir.name.startswith("_"):
                continue
            report = self.check_one(adapter_dir.name)
            if report is not None:
                reports.append(report)
        return reports

    def check_one(self, lang_id: str) -> Optional[QualityReport]:
        """检查单个适配器"""
        adapter_dir = self._adapters_dir / lang_id
        if not adapter_dir.is_dir():
            return None

        dimensions = [
            self._check_basic(adapter_dir, lang_id),
            self._check_metadata(adapter_dir, lang_id),
            self._check_examples(adapter_dir, lang_id),
            self._check_docs(adapter_dir, lang_id),
            self._check_functionality(adapter_dir, lang_id),
        ]

        total = sum(d.score for d in dimensions)
        max_total = sum(d.max_score for d in dimensions)
        lang_name = self._get_lang_name(adapter_dir)

        return QualityReport(
            lang_id=lang_id,
            lang_name=lang_name,
            total_score=total,
            max_score=max_total,
            dimensions=dimensions,
        )

    def _get_lang_name(self, adapter_dir: Path) -> str:
        """从 adapter.yaml 读取语言名称"""
        yaml_path = adapter_dir / "adapter.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return data.get("name", adapter_dir.name)
            except Exception:
                pass
        return adapter_dir.name

    # ---- 维度 1: 基础完整度 (0-25) ----

    def _check_basic(self, adapter_dir: Path, lang_id: str) -> DimensionScore:
        """基础完整度检查（0-25）"""
        dim = DimensionScore(name="基础完整度", max_score=25, score=0)

        # adapter.yaml 存在 (4)
        yaml_path = adapter_dir / "adapter.yaml"
        if yaml_path.exists():
            dim.score += 4
            dim.details.append("adapter.yaml 存在")
        else:
            dim.suggestions.append("缺少 adapter.yaml 文件")

        # adapter.py 存在 (4)
        py_path = adapter_dir / "adapter.py"
        if py_path.exists():
            dim.score += 4
            dim.details.append("adapter.py 存在")
        else:
            dim.suggestions.append("缺少 adapter.py 文件")
            return dim  # 没有 adapter.py 就无法继续

        # 类定义正确 (7)
        try:
            py_content = py_path.read_text(encoding="utf-8")
            if re.search(r"class\s+\w+Adapter\s*\(\s*\w*Adapter\s*\)", py_content):
                dim.score += 7
                dim.details.append("适配器类定义正确")
            elif re.search(r"class\s+\w+\s*\(\s*\w*Adapter\s*\)", py_content):
                dim.score += 5
                dim.details.append("适配器类定义存在（命名不标准）")
            else:
                dim.suggestions.append("adapter.py 中未找到 Adapter 子类")
        except Exception:
            dim.suggestions.append("无法读取 adapter.py")

        # 可实例化 (10)
        try:
            from yanpub.core.adapter.registry import _load_adapter
            adapter = _load_adapter(adapter_dir)
            if adapter is not None:
                dim.score += 10
                dim.details.append(f"适配器可实例化（{adapter.name} v{adapter.version}）")
            else:
                dim.suggestions.append("适配器无法实例化")
        except Exception as e:
            dim.suggestions.append(f"适配器实例化失败: {e}")

        return dim

    # ---- 维度 2: 元数据质量 (0-20) ----

    def _check_metadata(self, adapter_dir: Path, lang_id: str) -> DimensionScore:
        """元数据质量检查（0-20）"""
        dim = DimensionScore(name="元数据质量", max_score=20, score=0)

        yaml_path = adapter_dir / "adapter.yaml"
        if not yaml_path.exists():
            dim.suggestions.append("缺少 adapter.yaml，无法检查元数据")
            return dim

        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            dim.suggestions.append(f"adapter.yaml 解析失败: {e}")
            return dim

        # 必需字段 (5)
        required_fields = ["name", "id", "version"]
        found = sum(1 for f in required_fields if f in data and data[f])
        if found == len(required_fields):
            dim.score += 5
            dim.details.append("必需字段完整")
        else:
            missing = [f for f in required_fields if f not in data or not data[f]]
            dim.suggestions.append(f"缺少必需字段: {', '.join(missing)}")
            dim.score += int(5 * found / len(required_fields))

        # 版本号合法 + 成熟度 (5)
        version = str(data.get("version", ""))
        if re.match(r"^\d+\.\d+\.\d+", version):
            dim.score += 2
            dim.details.append(f"版本号合法: {version}")
            # 成熟度加分：基于语义版本
            try:
                major = int(version.split(".")[0])
                if major >= 2:
                    dim.score += 3
                    dim.details.append(f"语言成熟（主版本 {major}+）")
                elif major >= 1:
                    dim.score += 2
                    dim.details.append("语言稳定（主版本 1+）")
                else:
                    dim.score += 1
                    dim.details.append("语言早期阶段（主版本 0）")
                    dim.suggestions.append("语言尚在 0.x 阶段，建议推进到 1.0")
            except (ValueError, IndexError):
                pass
        else:
            dim.suggestions.append(f"版本号格式不标准: {version}")

        # 扩展名正确 (5)
        syntax = data.get("syntax", {})
        extensions = syntax.get("file_extensions", [])
        if extensions:
            has_dot_ext = all(e.startswith(".") for e in extensions)
            has_chinese = any(ord(c) > 0x4E00 for ext in extensions for c in ext)
            if has_dot_ext and has_chinese:
                dim.score += 5
                dim.details.append(f"扩展名正确含中文: {extensions}")
            elif has_dot_ext:
                dim.score += 3
                dim.details.append(f"扩展名正确: {extensions}")
                dim.suggestions.append("建议添加中文扩展名（如 .段 .言）")
            else:
                dim.suggestions.append("扩展名应以 '.' 开头")
                dim.score += 1
        else:
            dim.suggestions.append("未配置文件扩展名")

        # 颜色有效 (5)
        colors = data.get("colors", {})
        primary = colors.get("primary", "")
        if re.match(r"^#[0-9A-Fa-f]{6}$", primary):
            dim.score += 5
            dim.details.append(f"主色有效: {primary}")
        elif primary:
            dim.suggestions.append(f"主色格式不标准: {primary}")
        else:
            dim.suggestions.append("未配置主色")

        return dim

    # ---- 维度 3: 示例丰富度 (0-20) ----

    def _check_examples(self, adapter_dir: Path, lang_id: str) -> DimensionScore:
        """示例丰富度检查（0-20）"""
        dim = DimensionScore(name="示例丰富度", max_score=20, score=0)

        examples_dir = adapter_dir / "examples"
        if not examples_dir.exists() or not examples_dir.is_dir():
            dim.suggestions.append("缺少 examples/ 目录")
            return dim

        # 计算示例数量
        example_files = list(examples_dir.iterdir())
        example_files = [f for f in example_files if f.is_file() and not f.name.startswith(".")]
        count = len(example_files)

        # 示例数量得分 (8)
        if count >= 8:
            dim.score += 8
            dim.details.append(f"示例丰富: {count} 个")
        elif count >= 6:
            dim.score += 6
            dim.details.append(f"示例充足: {count} 个")
        elif count >= 3:
            dim.score += 4
            dim.details.append(f"示例适中: {count} 个")
            dim.suggestions.append("建议增加到 6 个以上示例")
        elif count >= 1:
            dim.score += 2
            dim.details.append(f"示例较少: {count} 个")
            dim.suggestions.append("建议增加更多示例（至少 3 个）")
        else:
            dim.suggestions.append("examples/ 目录为空")

        # Front matter 质量 (7)
        fm_count = 0
        fm_with_author = 0
        for f in example_files:
            try:
                content = f.read_text(encoding="utf-8")
                if content.strip().startswith("---"):
                    fm_text = content.split("---")[1]
                    fm_data = yaml.safe_load(fm_text) if fm_text.strip() else {}
                    if fm_data and fm_data.get("title"):
                        fm_count += 1
                        if fm_data.get("author"):
                            fm_with_author += 1
            except Exception:
                continue

        if count > 0 and fm_count == count:
            base = 5
            if fm_with_author >= count // 2:
                base += 2
                dim.details.append(f"所有示例 front matter 完整（含作者）: {fm_with_author}/{count}")
            else:
                dim.details.append("所有示例都有 front matter")
                dim.suggestions.append("建议在 front matter 中添加 author 字段")
            dim.score += base
        elif fm_count > 0:
            ratio = fm_count / count
            dim.score += int(5 * ratio)
            dim.details.append(f"front matter 覆盖率: {fm_count}/{count}")
            dim.suggestions.append(f"有 {count - fm_count} 个示例缺少 front matter")
        else:
            dim.suggestions.append("所有示例都缺少 YAML front matter")

        # 示例多样性 (5) — 检查标签/难度分布
        difficulties = set()
        tags = set()
        for f in example_files:
            try:
                content = f.read_text(encoding="utf-8")
                if content.strip().startswith("---"):
                    fm_text = content.split("---")[1]
                    fm_data = yaml.safe_load(fm_text) if fm_text.strip() else {}
                    if fm_data.get("difficulty"):
                        difficulties.add(fm_data["difficulty"])
                    for tag in fm_data.get("tags", []):
                        tags.add(tag)
            except Exception:
                continue

        diversity_score = 0
        if len(difficulties) >= 3:
            diversity_score += 3
        elif len(difficulties) >= 2:
            diversity_score += 2
        elif len(difficulties) >= 1:
            diversity_score += 1
        else:
            dim.suggestions.append("示例缺少难度标注")

        if len(tags) >= 6:
            diversity_score += 2
        elif len(tags) >= 3:
            diversity_score += 1
        else:
            dim.suggestions.append("示例标签过少，建议增加分类标签")

        dim.score += diversity_score
        if diversity_score >= 4:
            dim.details.append(f"难度和标签丰富: {len(difficulties)} 个难度, {len(tags)} 个标签")
        elif diversity_score > 0:
            dim.details.append(f"难度和标签一般: {len(difficulties)} 个难度, {len(tags)} 个标签")

        return dim

    # ---- 维度 4: 文档覆盖 (0-15) ----

    def _check_docs(self, adapter_dir: Path, lang_id: str) -> DimensionScore:
        """文档覆盖检查（0-15）"""
        dim = DimensionScore(name="文档覆盖", max_score=15, score=0)

        # README (4)
        readme_path = adapter_dir / "README.md"
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8")
                if len(content) >= 100:
                    dim.score += 4
                    dim.details.append(f"README.md 完整（{len(content)} 字）")
                else:
                    dim.score += 2
                    dim.details.append("README.md 过短")
                    dim.suggestions.append("README.md 内容过少，建议补充到 100 字以上")
            except Exception:
                dim.score += 1
        else:
            dim.suggestions.append("建议添加 README.md")

        # CONTRIBUTING (3)
        contrib_path = adapter_dir / "CONTRIBUTING.md"
        if contrib_path.exists():
            dim.score += 3
            dim.details.append("CONTRIBUTING.md 存在")
        else:
            dim.suggestions.append("建议添加 CONTRIBUTING.md（可使用 adapter create 自动生成）")

        # 关键字文档质量 (5) — 区分 list[str] vs list[dict] with description
        keywords_json = adapter_dir / "keywords.json"
        if keywords_json.exists():
            try:
                data = json.loads(keywords_json.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict):
                        # 检查是否包含 description 字段
                        with_desc = sum(1 for kw in data if isinstance(kw, dict) and kw.get("description"))
                        if with_desc >= len(data) * 0.5:
                            dim.score += 5
                            dim.details.append(f"关键字文档丰富: {len(data)} 个（{with_desc} 个含描述）")
                        elif with_desc > 0:
                            dim.score += 3
                            dim.details.append(f"关键字文档部分含描述: {with_desc}/{len(data)}")
                            dim.suggestions.append("建议为所有关键字添加 description 字段")
                        else:
                            dim.score += 2
                            dim.details.append(f"关键字文档存在: {len(data)} 个（无描述）")
                            dim.suggestions.append("建议为关键字添加 description 字段")
                    elif isinstance(data[0], str):
                        # list[str] 格式 — 按数量细分
                        kw_count = len(data)
                        if kw_count >= 100:
                            dim.score += 5
                            dim.details.append(f"关键字文档丰富: {kw_count} 个（仅列表）")
                        elif kw_count >= 50:
                            dim.score += 4
                            dim.details.append(f"关键字文档适中: {kw_count} 个（仅列表）")
                        elif kw_count >= 30:
                            dim.score += 3
                            dim.details.append(f"关键字文档存在: {kw_count} 个（仅列表）")
                        else:
                            dim.score += 2
                            dim.details.append(f"关键字文档较少: {kw_count} 个（仅列表）")
                        dim.suggestions.append("建议将 keywords.json 升级为含描述的对象格式")
            except Exception:
                pass
        else:
            dim.suggestions.append("缺少 keywords.json 关键字文档")

        # 描述完整性 (3)
        yaml_path = adapter_dir / "adapter.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    ydata = yaml.safe_load(f)
                desc = ydata.get("description", "")
                if desc and len(desc) >= 20:
                    dim.score += 3
                    dim.details.append(f"语言描述完整（{len(desc)} 字）")
                elif desc and len(desc) >= 10:
                    dim.score += 2
                    dim.details.append("语言描述简短")
                    dim.suggestions.append("建议将语言描述补充到 20 字以上")
                elif desc:
                    dim.score += 1
                    dim.suggestions.append("语言描述过短，建议补充")
                else:
                    dim.suggestions.append("建议在 adapter.yaml 中添加 description 字段")
            except Exception:
                dim.suggestions.append("无法读取 adapter.yaml")
        else:
            dim.suggestions.append("缺少 adapter.yaml")

        return dim

    # ---- 维度 5: 功能验证 (0-20) ----

    def _check_functionality(self, adapter_dir: Path, lang_id: str) -> DimensionScore:
        """功能验证检查（0-20）"""
        dim = DimensionScore(name="功能验证", max_score=20, score=0)

        try:
            from yanpub.core.adapter.registry import _load_adapter
            adapter = _load_adapter(adapter_dir)
        except Exception:
            dim.suggestions.append("适配器无法加载")
            return dim

        if adapter is None:
            dim.suggestions.append("适配器加载返回 None")
            return dim

        # 关键字丰富度 (6) — 按数量梯度加分
        try:
            kw_count = len(adapter.keywords)
            if kw_count >= 100:
                dim.score += 6
                dim.details.append(f"关键字丰富: {kw_count} 个")
            elif kw_count >= 50:
                dim.score += 5
                dim.details.append(f"关键字充足: {kw_count} 个")
            elif kw_count >= 30:
                dim.score += 4
                dim.details.append(f"关键字适中: {kw_count} 个")
            elif kw_count > 0:
                dim.score += 2
                dim.details.append(f"关键字较少: {kw_count} 个")
                dim.suggestions.append("关键字数量较少，建议补充更多语言特性关键字")
            else:
                dim.suggestions.append("关键字为空")
        except Exception as e:
            dim.suggestions.append(f"关键字加载失败: {e}")

        # capabilities 覆盖 (5) — 检查启用的能力数量
        try:
            caps = adapter.capabilities
            if caps:
                enabled = [k for k, v in caps.items() if v]
                dim.score += 2  # 有声明就给基础分
                if len(enabled) >= 3:
                    dim.score += 3
                    dim.details.append(f"能力丰富: {', '.join(enabled)}")
                elif len(enabled) >= 1:
                    dim.score += 1
                    dim.details.append(f"能力适中: {', '.join(enabled)}")
                    dim.suggestions.append("建议启用更多能力（如 debug、package_manager）")
                else:
                    dim.suggestions.append("所有能力均未启用")
            else:
                dim.suggestions.append("建议声明 capabilities")
        except Exception:
            dim.suggestions.append("无法读取 capabilities")

        # eval 可用 (5)
        try:
            eval_cmd = getattr(adapter, "_eval_command", None)
            if eval_cmd:
                dim.score += 5
                dim.details.append("eval 命令已配置")
            else:
                # 检查 adapter.yaml 中的 execution.eval
                yaml_path = adapter_dir / "adapter.yaml"
                if yaml_path.exists():
                    with open(yaml_path, encoding="utf-8") as f:
                        ydata = yaml.safe_load(f)
                    execution = ydata.get("execution", {})
                    if execution.get("eval"):
                        dim.score += 5
                        dim.details.append("eval 命令已在 YAML 中配置")
                    else:
                        dim.suggestions.append("建议配置 eval 命令以支持在线执行")
                else:
                    dim.suggestions.append("建议配置 eval 命令以支持在线执行")
        except Exception:
            dim.suggestions.append("无法检查 eval 命令")

        # run 命令 (2)
        try:
            run_cmd = getattr(adapter, "_run_command", None)
            if run_cmd:
                dim.score += 2
                dim.details.append("run 命令已配置")
            else:
                dim.suggestions.append("建议配置 run 命令")
        except Exception:
            pass

        # repl 可用 (2)
        try:
            repl_cmd = getattr(adapter, "_repl_command", None)
            if repl_cmd:
                dim.score += 2
                dim.details.append("repl 命令已配置")
            else:
                dim.suggestions.append("建议配置 repl 命令以支持交互式环境")
        except Exception:
            pass

        return dim

    def generate_html(self, reports: list[QualityReport], output_path: Path) -> Path:
        """生成 HTML 质量报告"""
        rows = ""
        for r in reports:
            grade_color = {
                "S": "#2ecc71", "A": "#27ae60", "B": "#3498db",
                "C": "#f39c12", "D": "#e67e22", "F": "#e74c3c",
            }.get(r.grade, "#95a5a6")

            dim_html = ""
            for d in r.dimensions:
                pct = d.percentage
                bar_color = "#2ecc71" if pct >= 80 else "#f39c12" if pct >= 50 else "#e74c3c"
                dim_html += f"""
                <tr>
                    <td>{d.name}</td>
                    <td>{d.score}/{d.max_score}</td>
                    <td><div style="background:{bar_color};width:{pct}%;height:8px;border-radius:4px"></div></td>
                </tr>"""

            suggestions = [s for d in r.dimensions for s in d.suggestions[:3]]
            suggestions_html = ""
            if suggestions:
                suggestions_html = (
                    "<div style='margin-top:8px;color:#f39c12;font-size:13px'>"
                    + "建议: " + "; ".join(suggestions)
                    + "</div>"
                )

            rows += f"""
            <div class="card">
                <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px">
                    <span class="grade" style="background:{grade_color}">{r.grade}</span>
                    <div>
                        <h3 style="margin:0">{r.lang_name} <small style="color:#888">{r.lang_id}</small></h3>
                        <span style="color:#aaa">总分 {r.total_score}/{r.max_score} ({r.percentage:.1f}%)</span>
                    </div>
                </div>
                <table style="width:100%;border-collapse:collapse">
                    <tr style="color:#888"><th style="text-align:left">维度</th><th>分数</th><th style="width:40%">进度</th></tr>
                    {dim_html}
                </table>
                {suggestions_html}
            </div>"""

        avg_score = sum(r.total_score for r in reports) / len(reports) if reports else 0
        max_score = reports[0].max_score if reports else 100

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>言埠 适配器质量报告</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 24px; }}
h1 {{ color: #fff; text-align: center; }}
.card {{ background: #16213e; border-radius: 12px; padding: 20px; margin: 16px 0; }}
.grade {{ display: inline-block; width: 48px; height: 48px; line-height: 48px; text-align: center; border-radius: 50%; font-size: 24px; font-weight: bold; color: #fff; }}
table td, table th {{ padding: 6px 8px; }}
</style>
</head>
<body>
<h1>适配器质量报告</h1>
<p style="text-align:center;color:#888">{len(reports)} 个适配器 | 平均分 {avg_score:.1f}/{max_score}</p>
{rows}
</body>
</html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path
