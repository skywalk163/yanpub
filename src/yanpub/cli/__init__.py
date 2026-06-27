"""言埠 YanPub CLI -- 中文编程语言统一基础设施命令行"""

from __future__ import annotations

import os
import sys

import click

# Windows 终端 UTF-8 输出支持
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

@click.group()
@click.version_option(version="1.7.0")
@click.option("--lang", "-L", "cli_lang", default=None, help="语言设置（zh/en）")
def main(cli_lang: str | None):
    """言埠 YanPub -- 中文编程语言统一基础设施"""
    if cli_lang:
        from yanpub.i18n import set_lang

        set_lang(cli_lang)

# 导入所有子模块，触发命令注册  # noqa: E402
from yanpub.cli import run_repl as _run_repl  # noqa: F401, E402
from yanpub.cli import playground_cmds as _playground_cmds  # noqa: F401, E402
from yanpub.cli import lsp as _lsp  # noqa: F401, E402
from yanpub.cli import pkg as _pkg  # noqa: F401, E402
from yanpub.cli import docs_site as _docs_site  # noqa: F401, E402
from yanpub.cli import examples as _examples  # noqa: F401, E402
from yanpub.cli import adapter as _adapter  # noqa: F401, E402
from yanpub.cli import workspace as _workspace  # noqa: F401, E402
from yanpub.cli import sandbox as _sandbox  # noqa: F401, E402
from yanpub.cli import wasm as _wasm  # noqa: F401, E402
from yanpub.cli import bench as _bench  # noqa: F401, E402
from yanpub.cli import plugin as _plugin  # noqa: F401, E402
from yanpub.cli import debug_ai as _debug_ai  # noqa: F401, E402
from yanpub.cli import signing as _signing  # noqa: F401, E402
from yanpub.cli import infra as _infra  # noqa: F401, E402
from yanpub.cli import refactor as _refactor  # noqa: F401, E402
from yanpub.cli import i18n_cmds as _i18n_cmds  # noqa: F401, E402
from yanpub.cli import lint as _lint  # noqa: F401, E402
from yanpub.cli import hot_update as _hot_update  # noqa: F401, E402
from yanpub.cli import private_registry as _private_registry  # noqa: F401, E402
from yanpub.cli import challenge as _challenge  # noqa: F401, E402
from yanpub.cli import quality as _quality  # noqa: F401, E402
