"""YanREPL — 统一交互式环境

基于 prompt_toolkit，支持：
- 多语言热切换（:lang duan）
- 中文关键字语法高亮
- Tab 补全（关键字 + 内置命令）
- 命令历史
- 多行输入检测
"""


def __getattr__(name):
    if name == "YanREPL":
        from yanpub.repl.core import YanREPL

        globals()["YanREPL"] = YanREPL
        return YanREPL
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["YanREPL"]
