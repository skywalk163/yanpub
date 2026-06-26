"""示例和贡献命令"""

from __future__ import annotations

import sys

import click

from yanpub.cli import main
from yanpub.core.registry import get_registry

@main.command()
@click.argument("lang_id", required=False)
@click.option("--run", "-r", "example_name", default=None, help="运行指定示例（传入示例名称）")
@click.option("--show", "-s", "show_code", is_flag=True, help="显示示例代码内容")
@click.option("--search", "-S", "keyword", default=None, help="按关键字搜索示例")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 格式输出")
def examples(
    lang_id: str | None,
    example_name: str | None,
    show_code: bool,
    keyword: str | None,
    as_json: bool,
):
    """查看和运行各语言的示例代码

    不带参数：列出所有语言的可用示例

    \b
    yanpub examples              # 列出所有语言的示例
    yanpub examples duan         # 列出段言的所有示例
    yanpub examples duan -s      # 显示段言所有示例的代码
    yanpub examples duan -r hello  # 运行段言的 hello 示例
    yanpub examples -S 递归       # 搜索包含"递归"的示例
    """
    from yanpub.core.examples import get_example_manager

    manager = get_example_manager()

    # 搜索模式
    if keyword:
        results = manager.search(keyword)
        if not results:
            click.echo(f"未找到包含「{keyword}」的示例。")
            return
        _print_search_results(results, show_code, as_json)
        return

    # 指定语言
    if lang_id:
        ex_list = manager.list_for_language(lang_id)
        if not ex_list:
            registry = get_registry()
            if lang_id not in registry:
                click.echo(f"未知语言: {lang_id}", err=True)
                click.echo(f"可用语言: {', '.join(registry.language_ids)}")
                sys.exit(1)
            adapter = registry.get(lang_id)
            click.echo(f"{adapter.name} ({lang_id}) 暂无示例。")
            return

        # 运行指定示例
        if example_name:
            click.echo(f"正在运行 {lang_id}/{example_name} ...", err=True)
            result = manager.run_example(lang_id, example_name)
            if result is None:
                click.echo(f"示例不存在: {lang_id}/{example_name}", err=True)
                available = ", ".join(ex.name for ex in ex_list)
                click.echo(f"可用示例: {available}")
                sys.exit(1)
            if result["stdout"]:
                click.echo(result["stdout"], nl=False)
            if result["stderr"]:
                click.echo(result["stderr"], nl=False, err=True)
            if not result["success"]:
                sys.exit(1)
            return

        # 显示/列出示例
        adapter = get_registry().get(lang_id)
        lang_name = adapter.name if adapter else lang_id
        if as_json:
            _print_examples_json(ex_list)
        elif show_code:
            _print_examples_with_code(lang_name, lang_id, ex_list)
        else:
            _print_examples_list(lang_name, lang_id, ex_list)
        return

    # 列出所有语言的示例
    all_examples = manager.list_all()
    if not all_examples:
        click.echo("暂无任何示例。")
        return

    if as_json:
        _print_all_examples_json(all_examples)
    else:
        total = sum(len(ex_list) for ex_list in all_examples.values())
        click.echo(f"共 {len(all_examples)} 种语言，{total} 个示例：\n")
        for lid in sorted(all_examples.keys()):
            ex_list = all_examples[lid]
            adapter = get_registry().get(lid)
            lang_name = adapter.name if adapter else lid
            names = ", ".join(ex.name for ex in ex_list)
            click.echo(f"  {lang_name} ({lid}): {names}")

def _print_examples_list(lang_name: str, lang_id: str, examples_list: list):
    """打印某语言的示例列表"""
    click.echo(f"{lang_name} ({lang_id}) 的示例：\n")
    for ex in examples_list:
        line = f"  {ex.name}"
        if ex.title != ex.name:
            line += f" — {ex.title}"
        if ex.difficulty:
            line += f" [{ex.difficulty}]"
        if ex.tags:
            line += f" #{' #'.join(ex.tags)}"
        if ex.source == "adapter":
            line += " (语言维护)"
        click.echo(line)

def _print_examples_with_code(lang_name: str, lang_id: str, examples_list: list):
    """打印某语言的示例及代码内容"""
    for i, ex in enumerate(examples_list):
        if i > 0:
            click.echo("\n" + "─" * 60 + "\n")
        header = f"{lang_name}/{ex.name}"
        if ex.title != ex.name:
            header += f" — {ex.title}"
        click.echo(f"── {header} ──\n")
        click.echo(ex.code)

@main.command()
@click.argument("lang_id")
@click.option("--name", "-n", default=None, help="示例名称（文件名，不含扩展名）")
@click.option("--title", "-t", default=None, help="显示标题")
@click.option("--tags", default=None, help="标签，逗号分隔（如: 递归,算法）")
@click.option("--difficulty", "-d", type=click.Choice(["入门", "简单", "中等", "困难"]), default=None, help="难度")
@click.option("--description", "-D", default=None, help="简短描述")
@click.option("--author", "-a", default=None, help="作者署名")
@click.option("--code", "-c", default=None, help="示例代码（或从 stdin 读取）")
@click.option("--file", "-f", "code_file", default=None, help="从文件读取示例代码")
@click.option("--dry-run", is_flag=True, help="仅预览，不写入文件")
@click.option("--output-dir", "-o", default=None, help="输出目录（默认自动推断）")
def contribute(
    lang_id: str,
    name: str | None,
    title: str | None,
    tags: str | None,
    difficulty: str | None,
    description: str | None,
    author: str | None,
    code: str | None,
    code_file: str | None,
    dry_run: bool,
    output_dir: str | None,
):
    """贡献一个示例到指定语言

    交互式创建示例，也可以通过选项直接指定所有参数。

    \b
    yanpub examples contribute duan                    # 交互式创建段言示例
    yanpub examples contribute duan -n sort -t "排序"   # 指定名称和标题
    yanpub examples contribute duan -c "打印('hi')"     # 直接传入代码
    yanpub examples contribute duan -f code.duan        # 从文件读取代码
    echo "打印('hi')" | yanpub examples contribute duan -n hello  # 从 stdin 读取
    """
    from yanpub.core.examples import get_example_manager, validate_example_meta

    registry = get_registry()
    if lang_id not in registry:
        click.echo(f"未知语言: {lang_id}", err=True)
        click.echo(f"可用语言: {', '.join(sorted(registry.language_ids))}")
        sys.exit(1)

    adapter = registry.get(lang_id)
    lang_name = adapter.name if adapter else lang_id

    # 获取代码内容
    if code_file:
        from pathlib import Path as PathLib

        p = PathLib(code_file)
        if not p.exists():
            click.echo(f"文件不存在: {code_file}", err=True)
            sys.exit(1)
        code_content = p.read_text(encoding="utf-8")
    elif code:
        code_content = code
    elif not sys.stdin.isatty():
        code_content = sys.stdin.read()
    else:
        code_content = None

    # 判断是否为交互模式：缺少必需参数时提示
    interactive = sys.stdin.isatty() and (name is None or code_content is None)

    if name is None:
        if not sys.stdin.isatty():
            click.echo("错误：非交互模式下必须指定 --name", err=True)
            sys.exit(1)
        name = click.prompt("示例名称（文件名，不含扩展名）", type=str)
    if title is None:
        if interactive:
            title = click.prompt("显示标题", default=name)
        else:
            title = name
    if code_content is None:
        if not interactive:
            click.echo("错误：非交互模式下必须指定 --code 或 --file", err=True)
            sys.exit(1)
        click.echo(f"\n请输入 {lang_name} 示例代码（输入空行结束）：")
        lines: list[str] = []
        while True:
            line = input()
            if line == "" and lines:
                break
            lines.append(line)
        code_content = "\n".join(lines)
        if not code_content.strip():
            click.echo("代码不能为空。", err=True)
            sys.exit(1)

    # 可选参数：交互模式下提示，非交互模式下默认为空
    if difficulty is None and interactive:
        difficulty = click.prompt(
            "难度",
            type=click.Choice(["入门", "简单", "中等", "困难", ""]),
            default="",
        )
    elif difficulty is None:
        difficulty = ""
    if tags is None:
        if interactive:
            tags_input = click.prompt("标签（逗号分隔，留空跳过）", default="")
            tags_list = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []
        else:
            tags_list = []
    else:
        tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    if description is None and interactive:
        description = click.prompt("简短描述（留空跳过）", default="")
    elif description is None:
        description = ""
    if author is None and interactive:
        author = click.prompt("作者署名（留空跳过）", default="")
    elif author is None:
        author = ""

    # 验证
    issues = validate_example_meta(
        name=name,
        title=title,
        code=code_content,
        lang_id=lang_id,
        tags=tags_list,
        difficulty=difficulty,
    )
    if issues:
        click.echo("\n验证失败：", err=True)
        for issue in issues:
            click.echo(f"  - {issue}", err=True)
        sys.exit(1)

    # 构建预览
    from yanpub.core.examples import _build_example_file

    file_content = _build_example_file(
        title=title,
        tags=tags_list,
        difficulty=difficulty,
        description=description,
        author=author,
        code=code_content,
    )

    # 确定输出路径
    out_dir = PathLib(output_dir) if output_dir else None
    manager = get_example_manager()
    if out_dir is None:
        ext = manager._get_extension_for_lang(lang_id)
    else:
        ext = manager._get_extension_for_lang(lang_id)

    if dry_run:
        click.echo(f"\n--- 预览: {lang_id}/{name}{ext} ---\n")
        click.echo(file_content)
        click.echo("\n--- 预览结束（dry-run 模式，未写入文件）---")
        return

    # 写入文件
    try:
        file_path = manager.contribute_example(
            lang_id=lang_id,
            name=name,
            code=code_content,
            title=title,
            tags=tags_list,
            difficulty=difficulty,
            description=description,
            author=author,
            output_dir=out_dir,
        )
        click.echo(f"示例已创建: {file_path}")
        click.echo(f"  语言: {lang_name} ({lang_id})")
        click.echo(f"  名称: {name}")
        click.echo(f"  标题: {title}")
        if tags_list:
            click.echo(f"  标签: {', '.join(tags_list)}")
        if difficulty:
            click.echo(f"  难度: {difficulty}")
        if author:
            click.echo(f"  作者: {author}")
        click.echo("\n使用以下命令查看:")
        click.echo(f"  yanpub examples {lang_id} -s")
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"创建失败: {e}", err=True)
        sys.exit(1)

@main.command("validate-examples")
@click.argument("lang_id")
@click.argument("name", required=False)
def validate_examples(lang_id: str, name: str | None):
    """验证示例的元数据和代码

    \b
    yanpub examples validate duan          # 验证段言所有示例
    yanpub examples validate duan hello    # 验证指定示例
    """
    from yanpub.core.examples import get_example_manager, validate_example_meta

    manager = get_example_manager()
    ex_list = manager.list_for_language(lang_id)

    if not ex_list:
        registry = get_registry()
        if lang_id not in registry:
            click.echo(f"未知语言: {lang_id}", err=True)
            sys.exit(1)
        click.echo(f"{lang_id} 暂无示例。")
        return

    if name:
        ex_list = [e for e in ex_list if e.name == name]
        if not ex_list:
            click.echo(f"示例不存在: {lang_id}/{name}", err=True)
            sys.exit(1)

    total = len(ex_list)
    passed = 0
    failed = 0

    for ex in ex_list:
        issues = validate_example_meta(
            name=ex.name,
            title=ex.title,
            code=ex.code,
            lang_id=ex.lang_id,
            tags=ex.tags,
            difficulty=ex.difficulty,
        )
        if issues:
            failed += 1
            click.echo(f"  FAIL {ex.name}")
            for issue in issues:
                click.echo(f"       {issue}")
        else:
            passed += 1

    click.echo(f"\n验证完成: {passed}/{total} 通过", nl=False)
    if failed:
        click.echo(f"，{failed} 个失败")
    else:
        click.echo()

def _print_search_results(results: dict, show_code: bool, as_json: bool):
    """打印搜索结果"""
    if as_json:
        _print_all_examples_json(results)
        return

    total = sum(len(ex_list) for ex_list in results.values())
    click.echo(f"找到 {total} 个示例：\n")
    for lid in sorted(results.keys()):
        ex_list = results[lid]
        adapter = get_registry().get(lid)
        lang_name = adapter.name if adapter else lid
        for ex in ex_list:
            line = f"  {lang_name}/{ex.name}"
            if ex.title != ex.name:
                line += f" — {ex.title}"
            click.echo(line)
            if show_code:
                # 缩进显示代码
                for code_line in ex.code.split("\n"):
                    click.echo(f"    {code_line}")
                click.echo()

def _print_examples_json(examples_list: list):
    """以 JSON 格式打印示例列表"""
    import json as json_mod

    data = []
    for ex in examples_list:
        data.append(
            {
                "name": ex.name,
                "title": ex.title,
                "lang_id": ex.lang_id,
                "path": str(ex.path),
                "source": ex.source,
                "tags": ex.tags,
                "difficulty": ex.difficulty,
                "description": ex.description,
                "author": ex.author,
            }
        )
    click.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))

def _print_all_examples_json(all_examples: dict):
    """以 JSON 格式打印所有语言的示例"""
    import json as json_mod

    data = {}
    for lid, ex_list in all_examples.items():
        data[lid] = [
            {
                "name": ex.name,
                "title": ex.title,
                "lang_id": ex.lang_id,
                "path": str(ex.path),
                "source": ex.source,
                "tags": ex.tags,
                "difficulty": ex.difficulty,
                "description": ex.description,
                "author": ex.author,
            }
            for ex in ex_list
        ]
    click.echo(json_mod.dumps(data, ensure_ascii=False, indent=2))
