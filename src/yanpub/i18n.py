"""国际化（i18n）框架 — 支持中英双语消息

使用方式:
  from yanpub.i18n import t

  msg = t("error.syntax")       # 按当前语言返回消息
  msg = t("error.syntax", lang="en")  # 指定语言

  yanpub --lang en ...    # CLI 切换语言
  环境变量 YANPUB_LANG=en  # 也可以通过环境变量设置

设计原则:
  - 默认中文（zh），可切换为英文（en）
  - 消息键使用点分格式: category.subkey
  - 纯 Python dict，无第三方依赖
  - 支持格式化参数: t("welcome", name="段言")
"""

from __future__ import annotations

import os
from typing import Optional

# 当前语言
_current_lang: str = "zh"

# 支持的语言列表
SUPPORTED_LANGS = ["zh", "en"]


# ---- 消息字典 ----

_MESSAGES: dict[str, dict[str, str]] = {
    # ---- 通用 ----
    "zh": {
        # 通用
        "app.name": "言埠 YanPub",
        "app.tagline": "中文编程语言统一基础设施",
        "app.version": "版本 {version}",

        # 错误
        "error.syntax": "语法错误",
        "error.runtime": "运行时错误",
        "error.name": "名称错误",
        "error.type": "类型错误",
        "error.import": "导入错误",
        "error.not_found": "未找到: {name}",
        "error.unknown_lang": "未知语言: {lang_id}",
        "error.no_adapter": "没有可用的语言适配器",
        "error.command_failed": "命令执行失败: {command}",

        # REPL
        "repl.welcome": "欢迎使用 {name} v{version}！输入 :help 查看帮助。",
        "repl.prompt": "{name}> ",
        "repl.continuation": "... ",
        "repl.goodbye": "再见！",
        "repl.cancel": "  (取消)",
        "repl.switched": "切换到 {name}",
        "repl.command_help": "内置命令：",
        "repl.command_langs": "列出可用语言",
        "repl.command_keywords": "显示当前语言关键字",
        "repl.command_quit": "退出",
        "repl.unknown_command": "未知命令: {cmd}，输入 :help 查看帮助",
        "repl.keywords_count": "{name} 关键字（{count}个）：",
        "repl.no_keywords": "未提供关键字列表",

        # 包管理
        "pkg.install_start": "安装 {name}...",
        "pkg.install_ok": "[OK] {name} 安装成功",
        "pkg.install_fail": "[FAIL] {name} 安装失败",
        "pkg.publish_ok": "[OK] {name} v{version} 已发布到本地注册中心",
        "pkg.not_found": "未找到 yanpkg.toml: {path}",
        "pkg.version_downgrade": "版本未升级: 当前 {current} -> 发布 {new}",
        "pkg.search_empty": "未找到匹配 '{query}' 的包。",
        "pkg.no_packages": "注册中心没有包。",
        "pkg.no_installed": "没有已安装的包。",
        "pkg.sync_start": "正在同步远程注册中心...",
        "pkg.sync_done": "同步完成：{count} 个包",

        # LSP
        "lsp.starting": "YanLSP 启动: {host}:{port}",
        "lsp.starting_stdio": "YanLSP 启动 (stdio)",

        # Playground
        "playground.starting": "启动 Playground: http://{host}:{port}",

        # 健康检查
        "health.title": "适配器健康检查报告",
        "health.healthy": "健康",
        "health.degraded": "降级",
        "health.unhealthy": "不可用",

        # 基准测试
        "bench.title": "性能基准测试报告",
        "bench.running": "正在运行基准测试...",
        "bench.startup": "启动时间",
        "bench.keyword_load": "关键字加载",
        "bench.execution": "代码执行",
        "bench.throughput": "吞吐量",

        # 适配器
        "adapter.loaded": "适配器 '{name}' 加载成功",
        "adapter.load_failed": "加载适配器 '{name}' 失败: {error}",
    },

    "en": {
        # General
        "app.name": "YanPub",
        "app.tagline": "Unified Infrastructure for Chinese Programming Languages",
        "app.version": "Version {version}",

        # Errors
        "error.syntax": "Syntax Error",
        "error.runtime": "Runtime Error",
        "error.name": "Name Error",
        "error.type": "Type Error",
        "error.import": "Import Error",
        "error.not_found": "Not found: {name}",
        "error.unknown_lang": "Unknown language: {lang_id}",
        "error.no_adapter": "No language adapters available",
        "error.command_failed": "Command failed: {command}",

        # REPL
        "repl.welcome": "Welcome to {name} v{version}! Type :help for help.",
        "repl.prompt": "{name}> ",
        "repl.continuation": "... ",
        "repl.goodbye": "Goodbye!",
        "repl.cancel": "  (cancelled)",
        "repl.switched": "Switched to {name}",
        "repl.command_help": "Built-in commands:",
        "repl.command_langs": "List available languages",
        "repl.command_keywords": "Show current language keywords",
        "repl.command_quit": "Quit",
        "repl.unknown_command": "Unknown command: {cmd}, type :help for help",
        "repl.keywords_count": "{name} keywords ({count}):",
        "repl.no_keywords": "No keywords provided",

        # Package manager
        "pkg.install_start": "Installing {name}...",
        "pkg.install_ok": "[OK] {name} installed successfully",
        "pkg.install_fail": "[FAIL] {name} installation failed",
        "pkg.publish_ok": "[OK] {name} v{version} published to local registry",
        "pkg.not_found": "yanpkg.toml not found: {path}",
        "pkg.version_downgrade": "Version not upgraded: current {current} -> publishing {new}",
        "pkg.search_empty": "No packages matching '{query}'.",
        "pkg.no_packages": "No packages in the registry.",
        "pkg.no_installed": "No packages installed.",
        "pkg.sync_start": "Syncing remote registry...",
        "pkg.sync_done": "Sync complete: {count} packages",

        # LSP
        "lsp.starting": "YanLSP starting: {host}:{port}",
        "lsp.starting_stdio": "YanLSP starting (stdio)",

        # Playground
        "playground.starting": "Starting Playground: http://{host}:{port}",

        # Health check
        "health.title": "Adapter Health Check Report",
        "health.healthy": "Healthy",
        "health.degraded": "Degraded",
        "health.unhealthy": "Unhealthy",

        # Benchmark
        "bench.title": "Performance Benchmark Report",
        "bench.running": "Running benchmarks...",
        "bench.startup": "Startup",
        "bench.keyword_load": "Keyword Load",
        "bench.execution": "Execution",
        "bench.throughput": "Throughput",

        # Adapter
        "adapter.loaded": "Adapter '{name}' loaded successfully",
        "adapter.load_failed": "Failed to load adapter '{name}': {error}",
    },
}


def get_lang() -> str:
    """获取当前语言设置"""
    return _current_lang


def set_lang(lang: str) -> None:
    """设置当前语言"""
    global _current_lang
    if lang in SUPPORTED_LANGS:
        _current_lang = lang
    else:
        _current_lang = "zh"  # 回退到中文


def init_lang() -> None:
    """从环境变量初始化语言设置"""
    env_lang = os.environ.get("YANPUB_LANG", "").lower()
    if env_lang:
        set_lang(env_lang)
    else:
        # 检测系统语言
        import locale
        try:
            sys_lang = locale.getlocale()[0] or ""
            if sys_lang.startswith("en"):
                set_lang("en")
        except Exception:
            pass


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """翻译消息

    Args:
        key: 消息键（点分格式，如 "error.syntax"）
        lang: 指定语言（默认使用当前语言）
        **kwargs: 格式化参数

    Returns:
        翻译后的消息字符串
    """
    target_lang = lang or _current_lang

    # 查找消息
    messages = _MESSAGES.get(target_lang, {})
    msg = messages.get(key)

    # 回退到中文
    if msg is None and target_lang != "zh":
        msg = _MESSAGES.get("zh", {}).get(key)

    # 回退到键名本身
    if msg is None:
        msg = key

    # 格式化参数
    if kwargs:
        try:
            msg = msg.format(**kwargs)
        except (KeyError, IndexError):
            pass

    return msg


# 启动时初始化语言
init_lang()
