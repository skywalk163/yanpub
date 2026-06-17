"""插件系统 — 第三方工具链插件的发现、加载和管理

插件目录结构:
  ~/.yanpub/plugins/
  ├── my-plugin/
  │   ├── plugin.json    # 插件元信息
  │   └── plugin.py      # 插件实现（可选）

plugin.json 格式:
  {
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "我的自定义插件",
    "author": "开发者",
    "hooks": ["pre_eval", "post_eval", "pre_run"],
    "entry_point": "plugin.py:MyPlugin"
  }

插件钩子（Hooks）:
  - pre_eval(code, lang_id)     → 执行代码前
  - post_eval(code, result, lang_id) → 执行代码后
  - pre_run(file_path, lang_id) → 运行文件前
  - post_run(file_path, result, lang_id) → 运行文件后
  - on_error(error, lang_id)    → 错误发生时
  - on_repl_start(lang_id)      → REPL 启动时
  - on_repl_command(cmd, lang_id) → REPL 命令执行时

使用方式:
  yanpub plugin list              # 列出已安装插件
  yanpub plugin install <path>    # 安装插件
  yanpub plugin uninstall <name>  # 卸载插件
  yanpub plugin enable <name>     # 启用插件
  yanpub plugin disable <name>    # 禁用插件
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


# 默认插件目录
_PLUGINS_DIR = Path.home() / ".yanpub" / "plugins"


@dataclass
class PluginInfo:
    """插件元信息"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    hooks: list[str] = field(default_factory=list)
    entry_point: str = ""  # "plugin.py:MyPlugin"
    enabled: bool = True
    installed_at: str = ""
    path: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PluginInfo":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# 支持的钩子列表
SUPPORTED_HOOKS = {
    "pre_eval", "post_eval",
    "pre_run", "post_run",
    "on_error",
    "on_repl_start", "on_repl_command",
}


class Plugin:
    """已加载的插件实例"""

    def __init__(self, info: PluginInfo, instance: Any = None):
        self.info = info
        self.instance = instance
        self._handlers: dict[str, Callable] = {}

    def get_handler(self, hook_name: str) -> Optional[Callable]:
        """获取钩子处理函数"""
        if hook_name in self._handlers:
            return self._handlers[hook_name]
        if self.instance and hasattr(self.instance, hook_name):
            handler = getattr(self.instance, hook_name)
            if callable(handler):
                self._handlers[hook_name] = handler
                return handler
        return None


class PluginManager:
    """插件管理器

    负责插件的发现、加载、启用/禁用和生命周期管理。
    """

    def __init__(self, plugins_dir: Path | None = None):
        self._dir = plugins_dir or _PLUGINS_DIR
        self._plugins: dict[str, Plugin] = {}
        self._discover()

    @property
    def plugins_dir(self) -> Path:
        return self._dir

    def _discover(self) -> None:
        """发现并加载所有已安装插件"""
        if not self._dir.exists():
            return

        for plugin_dir in self._dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest = plugin_dir / "plugin.json"
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                info = PluginInfo.from_dict(data)
                info.path = str(plugin_dir)
                # 检查是否禁用
                disabled_file = plugin_dir / ".disabled"
                info.enabled = not disabled_file.exists()
                # 加载插件实例
                plugin = Plugin(info)
                if info.enabled and info.entry_point:
                    self._load_plugin_instance(plugin)
                self._plugins[info.name] = plugin
            except (json.JSONDecodeError, KeyError):
                continue

    def _load_plugin_instance(self, plugin: Plugin) -> None:
        """加载插件的 Python 实现"""
        info = plugin.info
        if not info.entry_point or ":" not in info.entry_point:
            return

        module_path, class_name = info.entry_point.rsplit(":", 1)
        plugin_dir = Path(info.path)
        py_file = plugin_dir / module_path

        if not py_file.exists():
            return

        try:
            spec = importlib.util.spec_from_file_location(
                f"yanpub_plugin_{info.name}",
                str(py_file),
            )
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            cls = getattr(module, class_name, None)
            if cls is not None:
                plugin.instance = cls()
        except Exception:
            pass  # 插件加载失败，跳过

    def list_plugins(self) -> list[PluginInfo]:
        """列出所有已安装插件"""
        return [p.info for p in self._plugins.values()]

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """获取插件"""
        return self._plugins.get(name)

    def install(self, source_path: str, name: str | None = None) -> PluginInfo:
        """安装插件

        Args:
            source_path: 插件源目录路径
            name: 插件名称（覆盖 plugin.json 中的名称）
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"插件源目录不存在: {source_path}")

        # 读取 plugin.json
        manifest = source / "plugin.json"
        if not manifest.exists():
            raise FileNotFoundError(f"插件缺少 plugin.json: {manifest}")

        data = json.loads(manifest.read_text(encoding="utf-8"))
        info = PluginInfo.from_dict(data)
        if name:
            info.name = name

        # 复制到插件目录
        target = self._dir / info.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)

        info.path = str(target)
        info.installed_at = datetime.now().isoformat()

        # 保存更新后的 manifest
        manifest_data = info.to_dict()
        (target / "plugin.json").write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 加载插件
        plugin = Plugin(info)
        if info.entry_point:
            self._load_plugin_instance(plugin)
        self._plugins[info.name] = plugin

        return info

    def uninstall(self, name: str) -> bool:
        """卸载插件"""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False

        plugin_dir = Path(plugin.info.path)
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir, ignore_errors=True)
        return True

    def enable(self, name: str) -> bool:
        """启用插件"""
        plugin = self._plugins.get(name)
        if plugin is None:
            return False

        disabled_file = Path(plugin.info.path) / ".disabled"
        if disabled_file.exists():
            disabled_file.unlink()

        plugin.info.enabled = True
        if plugin.info.entry_point and plugin.instance is None:
            self._load_plugin_instance(plugin)
        return True

    def disable(self, name: str) -> bool:
        """禁用插件"""
        plugin = self._plugins.get(name)
        if plugin is None:
            return False

        disabled_file = Path(plugin.info.path) / ".disabled"
        disabled_file.touch()

        plugin.info.enabled = False
        plugin.instance = None  # 释放实例
        return True

    def call_hook(self, hook_name: str, *args, **kwargs) -> list[Any]:
        """调用所有插件的指定钩子

        Args:
            hook_name: 钩子名称
            *args, **kwargs: 传递给钩子的参数

        Returns:
            所有钩子的返回值列表
        """
        results = []
        for plugin in self._plugins.values():
            if not plugin.info.enabled:
                continue
            handler = plugin.get_handler(hook_name)
            if handler:
                try:
                    result = handler(*args, **kwargs)
                    results.append(result)
                except Exception:
                    pass  # 插件错误不应影响主流程
        return results

    def has_hook(self, hook_name: str) -> bool:
        """检查是否有任何插件注册了指定钩子"""
        return any(
            p.info.enabled and p.get_handler(hook_name) is not None
            for p in self._plugins.values()
        )


# ---- 全局插件管理器 ----

_global_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器"""
    global _global_manager
    if _global_manager is None:
        _global_manager = PluginManager()
    return _global_manager


def format_plugin_list(plugins: list[PluginInfo]) -> str:
    """格式化插件列表"""
    if not plugins:
        return "没有已安装的插件。"

    lines = []
    lines.append(f"已安装 {len(plugins)} 个插件：\n")
    for p in plugins:
        status = "✓" if p.enabled else "✗"
        hooks = ", ".join(p.hooks) if p.hooks else "无"
        lines.append(f"  {status} {p.name} v{p.version} — {p.description}")
        lines.append(f"     钩子: {hooks}")

    return "\n".join(lines)
