"""国际化（i18n）框架 — 支持中英日韩多语言消息

使用方式:
  from yanpub.i18n import t

  msg = t("error.syntax")       # 按当前语言返回消息
  msg = t("error.syntax", lang="en")  # 指定语言

  yanpub --lang en ...    # CLI 切换语言
  环境变量 YANPUB_LANG=en  # 也可以通过环境变量设置

  # I18nManager 高级用法
  from yanpub.i18n import I18nManager
  mgr = I18nManager()
  mgr.load_translations(Path("lang/"))   # 从 YAML 加载自定义翻译
  mgr.export_translations("en", Path("en.yaml"))  # 导出翻译
  missing = mgr.get_missing_keys("zh", "ja")  # 检查缺失键

设计原则:
  - 默认中文（zh），可切换为英文（en）、日语（ja）、韩语（ko）
  - 消息键使用点分格式: category.subkey
  - 纯 Python dict + 可选 YAML 扩展
  - 支持格式化参数: t("welcome", name="段言")
  - I18nManager 是可选增强层，原有 t() 函数保持向后兼容
"""

from yanpub.i18n_pkg._core import get_lang, set_lang, init_lang, t  # noqa: F401
from yanpub.i18n_pkg.translations import MESSAGES, SUPPORTED_LANGS, _MESSAGES  # noqa: F401
from yanpub.i18n_pkg.translator import I18nManager  # noqa: F401

__all__ = [
    "t",
    "get_lang",
    "set_lang",
    "init_lang",
    "I18nManager",
    "MESSAGES",
    "SUPPORTED_LANGS",
    "_MESSAGES",
]
