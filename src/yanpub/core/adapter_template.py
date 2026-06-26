"""适配器开发模板 — 快速创建新语言适配器

核心能力：
1. 从用户输入生成完整的适配器目录结构
2. 交互式向导引导用户填写必要信息
3. 自动生成 adapter.py、adapter.yaml、examples/、测试骨架
4. 验证生成的适配器是否可以被自动发现和注册
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from string import Template

from yanpub.core.adapter.adapter import SubprocessAdapter


@dataclass
class AdapterSpec:
    """适配器规格 — 用户填写的核心信息"""

    lang_id: str  # 英文ID，如 "mylang"
    name: str  # 中文名，如 "我语"
    version: str = "0.1.0"
    extensions: list[str] = field(default_factory=list)  # 如 [".my", ".mylang"]
    comment_syntax: str = "#"
    primary_color: str = "#2C3E50"
    # 执行命令
    run_command: str = ""  # 如 "python mylang.py run {file}"
    eval_command: str = ""  # 如 "python mylang.py -e {code}"，空则用临时文件
    eval_mode: str = "stdin"  # "stdin" | "arg"
    repl_command: str = ""  # 如 "python mylang.py -i"，空则无REPL
    # 关键字
    keywords: list[str] = field(default_factory=list)
    # 项目路径（可选，用于动态加载关键字）
    project_dir: str = ""
    # 附加信息
    description: str = ""
    author: str = ""
    repo_url: str = ""

    def __post_init__(self):
        if not self.extensions:
            self.extensions = [f".{self.lang_id}"]


# ---- 模板 ----

_ADAPTER_PY_TEMPLATE = Template('''r"""${name} (${lang_id_class}) 语言适配器

${description_line}
"""

from __future__ import annotations

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter.adapter import SubprocessAdapter


class ${class_name}(SubprocessAdapter):
    """${name}适配器 — 通过子进程调用${name}后端"""

    def __init__(self):
        super().__init__(
            name="${name}",
            lang_id="${lang_id}",
            version="${version}",
            extensions=${extensions_repr},
${run_command_line}
${eval_command_line}
${eval_mode_line}
${repl_command_line}
${keywords_line}
            primary_color="${primary_color}",
        )

    @property
    def comment_syntax(self) -> str:
        return "${comment_syntax}"

    @property
    def repl_prompt(self) -> str:
        return "${name}> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"${name} v{self.version} — ${description_short}\\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )


${keywords_loader_section}
${fallback_keywords_section}
''')

_ADAPTER_YAML_TEMPLATE = Template("""# ${name} (${lang_id_class}) 适配器配置
name: ${name}
id: ${lang_id}
version: "${version}"

backend:
  type: subprocess
  command: "python"

syntax:
  file_extensions: ${extensions_yaml}
  comment_syntax: "${comment_syntax}"

execution:
  run: "${run_command}"
${eval_command_yaml}
${repl_command_yaml}

capabilities:
  repl: ${has_repl}
  lsp: false
  package_manager: false
  wasm: false
  debug: false

colors:
  primary: "${primary_color}"
  secondary: "#3498DB"
  accent: "#2C3E50"
""")

_EXAMPLE_HELLO_TEMPLATE = Template("""---
title: '你好世界'
tags: ['入门', '基础']
difficulty: '入门'
description: '最简单的入门示例'
---

# ${name} 示例
# 用 ${name} 书写你的第一个程序

打印("你好，世界！")
""")

_EXAMPLE_FUNC_TEMPLATE = Template("""---
title: '函数定义'
tags: ['函数', '基础']
difficulty: '简单'
description: '定义和调用函数'
---

# ${name} - 函数定义与调用

# TODO: 用 ${name} 的语法写一个函数定义示例
""")

_CONTRIBUTING_TEMPLATE = Template("""# ${name} (${lang_id_class}) 适配器

## 如何贡献示例

1. 在 `examples/` 目录下创建新的示例文件
2. 文件使用语言的原始扩展名（如 `${example_ext}`）
3. 在文件开头添加 YAML front matter：

```yaml
---
title: '示例标题'
tags: ['标签1', '标签2']
difficulty: '入门|简单|中等|困难'
description: '简短描述'
---
```

4. 运行 `yanpub examples ${lang_id}` 验证示例已被发现
5. 运行 `yanpub adapter validate ${lang_id}` 验证适配器兼容性

## 示例规范

- 每个示例文件应专注于一个概念
- 代码应有注释说明
- difficulty 应与代码复杂度匹配
- 避免过长的示例（建议 30 行以内）

## 适配器维护者

${author_line}
""")


class AdapterTemplateEngine:
    """适配器模板引擎 — 根据规格生成完整的适配器目录"""

    def __init__(self, adapters_dir: Path | None = None):
        if adapters_dir is None:
            adapters_dir = Path(__file__).parent.parent / "adapters"
        self._adapters_dir = adapters_dir

    @property
    def adapters_dir(self) -> Path:
        return self._adapters_dir

    def validate_spec(self, spec: AdapterSpec) -> list[str]:
        """验证适配器规格，返回错误列表（空=通过）"""
        errors: list[str] = []

        # lang_id 校验
        if not spec.lang_id:
            errors.append("语言ID不能为空")
        elif not re.match(r"^[a-z][a-z0-9_]*$", spec.lang_id):
            errors.append("语言ID只能包含小写字母、数字和下划线，且以字母开头")

        # 中文名校验
        if not spec.name:
            errors.append("语言名称不能为空")

        # 版本校验
        if not re.match(r"^\d+\.\d+", spec.version):
            errors.append("版本号格式应为 X.Y 或 X.Y.Z")

        # 扩展名校验
        for ext in spec.extensions:
            if not ext.startswith("."):
                errors.append(f"扩展名 '{ext}' 应以点号开头")

        # run_command 校验
        if not spec.run_command:
            errors.append("运行命令不能为空")
        elif "{file}" not in spec.run_command:
            errors.append("运行命令应包含 {file} 占位符")

        # eval_mode 校验
        if spec.eval_mode not in ("stdin", "arg"):
            errors.append("eval_mode 只能是 'stdin' 或 'arg'")

        # 检查是否已存在
        target_dir = self._adapters_dir / spec.lang_id
        if target_dir.exists():
            errors.append(f"适配器目录已存在: {target_dir}")

        return errors

    def generate(self, spec: AdapterSpec, output_dir: Path | None = None) -> Path:
        """生成完整的适配器目录结构

        Args:
            spec: 适配器规格
            output_dir: 输出目录（默认为 adapters/{lang_id}/）

        Returns:
            生成的适配器目录路径
        """
        if output_dir is None:
            output_dir = self._adapters_dir / spec.lang_id

        output_dir.mkdir(parents=True, exist_ok=True)

        # 生成各文件
        self._generate_adapter_py(spec, output_dir)
        self._generate_adapter_yaml(spec, output_dir)
        self._generate_examples(spec, output_dir)
        self._generate_contributing(spec, output_dir)

        return output_dir

    def _generate_adapter_py(self, spec: AdapterSpec, output_dir: Path) -> None:
        """生成 adapter.py"""
        # 类名：MyLang -> MyLangAdapter
        class_name = _to_class_name(spec.lang_id) + "Adapter"
        lang_id_class = spec.lang_id.capitalize()

        # 扩展名列表
        extensions_repr = repr(spec.extensions)

        # run_command -> list[str]
        run_parts = spec.run_command.replace("{file}", "").split()
        run_parts = [p for p in run_parts if p]
        run_command_line = f"            run_command={run_parts!r},"

        # eval_command
        if spec.eval_command:
            eval_parts = spec.eval_command.replace("{code}", "").split()
            eval_parts = [p for p in eval_parts if p]
            eval_command_line = f"            eval_command={eval_parts!r},"
        else:
            eval_command_line = "            eval_command=None,"

        # eval_mode
        eval_mode_line = f'            eval_mode="{spec.eval_mode}",'

        # repl_command
        if spec.repl_command:
            repl_parts = spec.repl_command.split()
            repl_command_line = f"            repl_command={repl_parts!r},"
        else:
            repl_command_line = "            repl_command=None,"

        # 关键字
        if spec.keywords:
            keywords_line = f"            keywords={spec.keywords!r},"
        else:
            keywords_line = "            # keywords=你的关键字列表,"

        # 关键字加载器
        if spec.keywords:
            keywords_loader_section = ""
            fallback_keywords_section = ""
        else:
            loader_name = f"_load_{spec.lang_id}_keywords"
            keywords_loader_section = (
                f"def {loader_name}() -> list[str]:\n"
                f'    """加载{spec.name}关键字（优先从缓存）"""\n'
                f"    return load_cached_keywords("
                f'"{spec.lang_id}", '
                f"_load_{spec.lang_id}_keywords_dynamic, "
                f"_fallback_{spec.lang_id}_keywords()\n"
                f")\n"
            )
            fallback_keywords_section = (
                f"\ndef _load_{spec.lang_id}_keywords_dynamic() -> list[str]:\n"
                f'    """从{spec.name}项目动态加载关键字"""\n'
                f"    # TODO: 实现{spec.name}项目的关键字动态加载\n"
                f"    # 示例: exec 项目的 keywords.py 获取关键字列表\n"
                f"    return _fallback_{spec.lang_id}_keywords()\n"
                f"\n"
                f"\ndef _fallback_{spec.lang_id}_keywords() -> list[str]:\n"
                f'    """内置基础关键字列表"""\n'
                f"    return []  # TODO: 添加{spec.name}的基础关键字\n"
            )

        # 描述
        description_line = spec.description if spec.description else f"{spec.name}编程语言"
        description_short = spec.description if spec.description else "用中文书写的编程语言"

        content = _ADAPTER_PY_TEMPLATE.substitute(
            name=spec.name,
            lang_id=spec.lang_id,
            lang_id_class=lang_id_class,
            class_name=class_name,
            version=spec.version,
            extensions_repr=extensions_repr,
            run_command_line=run_command_line,
            eval_command_line=eval_command_line,
            eval_mode_line=eval_mode_line,
            repl_command_line=repl_command_line,
            keywords_line=keywords_line,
            primary_color=spec.primary_color,
            comment_syntax=spec.comment_syntax,
            description_line=description_line,
            description_short=description_short,
            keywords_loader_section=keywords_loader_section,
            fallback_keywords_section=fallback_keywords_section,
        )

        (output_dir / "adapter.py").write_text(content, encoding="utf-8")

    def _generate_adapter_yaml(self, spec: AdapterSpec, output_dir: Path) -> None:
        """生成 adapter.yaml"""
        lang_id_class = spec.lang_id.capitalize()

        extensions_yaml = "[" + ", ".join(f'"{e}"' for e in spec.extensions) + "]"

        eval_command_yaml = ""
        if spec.eval_command:
            eval_command_yaml = f'  eval: "{spec.eval_command}"'
        else:
            eval_command_yaml = "  # eval: 暂无eval命令，使用临时文件fallback"

        repl_command_yaml = ""
        if spec.repl_command:
            repl_command_yaml = f'  repl: "{spec.repl_command}"'
        else:
            repl_command_yaml = "  # repl: 暂无REPL"

        has_repl = "true" if spec.repl_command else "false"

        content = _ADAPTER_YAML_TEMPLATE.substitute(
            name=spec.name,
            lang_id=spec.lang_id,
            lang_id_class=lang_id_class,
            version=spec.version,
            extensions_yaml=extensions_yaml,
            comment_syntax=spec.comment_syntax,
            run_command=spec.run_command,
            eval_command_yaml=eval_command_yaml,
            repl_command_yaml=repl_command_yaml,
            has_repl=has_repl,
            primary_color=spec.primary_color,
        )

        (output_dir / "adapter.yaml").write_text(content, encoding="utf-8")

    def _generate_examples(self, spec: AdapterSpec, output_dir: Path) -> None:
        """生成示例目录和示例文件"""
        examples_dir = output_dir / "examples"
        examples_dir.mkdir(exist_ok=True)

        example_ext = spec.extensions[0] if spec.extensions else ".txt"

        # hello 示例
        hello_content = _EXAMPLE_HELLO_TEMPLATE.substitute(name=spec.name, lang_id=spec.lang_id)
        (examples_dir / f"hello{example_ext}").write_text(hello_content, encoding="utf-8")

        # 函数示例
        func_content = _EXAMPLE_FUNC_TEMPLATE.substitute(name=spec.name, lang_id=spec.lang_id)
        (examples_dir / f"function{example_ext}").write_text(func_content, encoding="utf-8")

    def _generate_contributing(self, spec: AdapterSpec, output_dir: Path) -> None:
        """生成 CONTRIBUTING.md"""
        example_ext = spec.extensions[0] if spec.extensions else ".txt"
        author_line = spec.author if spec.author else "待认领 — 欢迎成为维护者！"

        content = _CONTRIBUTING_TEMPLATE.substitute(
            name=spec.name,
            lang_id=spec.lang_id,
            lang_id_class=spec.lang_id.capitalize(),
            example_ext=example_ext,
            author_line=author_line,
        )

        (output_dir / "CONTRIBUTING.md").write_text(content, encoding="utf-8")

    def check_adapter(self, lang_id: str) -> dict:
        """检查适配器是否可以被正确发现和注册

        Returns:
            {"valid": bool, "errors": list[str], "warnings": list[str], "files": list[str]}
        """
        adapter_dir = self._adapters_dir / lang_id
        errors: list[str] = []
        warnings: list[str] = []
        files: list[str] = []

        # 检查目录存在
        if not adapter_dir.exists():
            errors.append(f"适配器目录不存在: {adapter_dir}")
            return {"valid": False, "errors": errors, "warnings": warnings, "files": files}

        # 检查必需文件
        required_files = ["adapter.py", "adapter.yaml"]
        for fname in required_files:
            fpath = adapter_dir / fname
            if fpath.exists():
                files.append(fname)
            else:
                errors.append(f"缺少必需文件: {fname}")

        # 检查 adapter.py 内容
        py_path = adapter_dir / "adapter.py"
        if py_path.exists():
            content = py_path.read_text(encoding="utf-8")

            # 检查是否导入了 SubprocessAdapter
            if "SubprocessAdapter" not in content and "LanguageAdapter" not in content:
                errors.append("adapter.py 未导入 LanguageAdapter 或 SubprocessAdapter")

            # 检查是否定义了适配器类
            if (
                "Adapter(SubprocessAdapter)" not in content
                and "Adapter(LanguageAdapter)" not in content
            ):
                warnings.append(
                    "adapter.py 可能未定义适配器类（需继承 SubprocessAdapter 或 LanguageAdapter）"
                )

            # 检查是否有 __init__
            if "def __init__(self)" not in content:
                warnings.append("adapter.py 可能缺少 __init__ 方法")

        # 检查 adapter.yaml 内容
        yaml_path = adapter_dir / "adapter.yaml"
        if yaml_path.exists():
            import yaml

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                if not isinstance(cfg, dict):
                    errors.append("adapter.yaml 格式错误：应为键值对")
                else:
                    for key in ["name", "id", "version"]:
                        if key not in cfg:
                            errors.append(f"adapter.yaml 缺少必需字段: {key}")

                    if "id" in cfg and cfg["id"] != lang_id:
                        errors.append(
                            f"adapter.yaml 的 id '{cfg['id']}' 与目录名 '{lang_id}' 不匹配"
                        )
            except Exception as e:
                errors.append(f"adapter.yaml 解析失败: {e}")

        # 检查 examples 目录
        examples_dir = adapter_dir / "examples"
        if examples_dir.exists():
            example_files = list(examples_dir.iterdir())
            example_count = sum(
                1 for f in example_files if f.is_file() and not f.name.startswith(".")
            )
            files.append(f"examples/ ({example_count} 个示例)")
            if example_count == 0:
                warnings.append("examples 目录为空，建议添加示例")
        else:
            warnings.append("缺少 examples 目录，建议添加示例文件")

        # 尝试动态加载
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                f"yanpub.adapters.{lang_id}.adapter", str(py_path)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                # 查找适配器类
                from yanpub.core.adapter.adapter import LanguageAdapter

                found_class = None
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, LanguageAdapter)
                        and attr is not LanguageAdapter
                        and attr is not SubprocessAdapter
                    ):
                        found_class = attr
                        break

                if found_class is None:
                    errors.append("adapter.py 中未找到 LanguageAdapter 的子类")
                else:
                    # 尝试实例化
                    try:
                        instance = found_class()
                        # 验证基本属性
                        if not instance.id:
                            errors.append("适配器 id 属性为空")
                        if not instance.name:
                            errors.append("适配器 name 属性为空")
                    except Exception as e:
                        errors.append(f"适配器实例化失败: {e}")

        except Exception as e:
            warnings.append(f"动态加载测试失败（非致命）: {e}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "files": files,
        }


def _to_class_name(lang_id: str) -> str:
    """将 lang_id 转换为类名前缀

    my_lang -> MyLang
    zhixing -> Zhixing
    """
    return "".join(part.capitalize() for part in lang_id.split("_"))


# ---- 交互式向导 ----


def interactive_wizard() -> AdapterSpec:
    """交互式适配器创建向导（非交互环境会使用默认值）"""
    # 注意：实际的交互逻辑由 CLI 层处理
    # 这里只提供默认规格
    return AdapterSpec(
        lang_id="mylang",
        name="我语",
        version="0.1.0",
        extensions=[".my"],
        comment_syntax="#",
        primary_color="#2C3E50",
        run_command="python mylang.py {file}",
        eval_command="python mylang.py -e {code}",
        eval_mode="arg",
        repl_command="python mylang.py -i",
    )
