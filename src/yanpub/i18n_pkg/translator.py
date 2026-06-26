"""I18nManager — 国际化管理器扩展

提供翻译文件导入导出、缺失键检查、自动翻译建议、文档翻译等功能。
I18nManager 是可选的增强层，原有的 t() 函数仍然可用。
"""

from __future__ import annotations

import re
from pathlib import Path

from yanpub.i18n_pkg.translations import MESSAGES, SUPPORTED_LANGS
from yanpub.i18n_pkg._core import t


class I18nManager:
    """国际化管理器 — 扩展 i18n 支持"""

    def __init__(self):
        self._custom_messages: dict[str, dict[str, str]] = {}

    # ---- 翻译文件管理 ----

    def load_translations(self, lang_dir: Path) -> None:
        """从目录加载自定义翻译文件（YAML 格式）

        扫描 lang_dir 下的 {lang}.yaml 文件，合并到 MESSAGES 中。
        自定义翻译会覆盖同名键，但不会删除已有键。

        Args:
            lang_dir: 包含 {lang}.yaml 文件的目录
        """
        import yaml

        if not lang_dir.is_dir():
            return

        for yaml_file in lang_dir.glob("*.yaml"):
            lang_id = yaml_file.stem
            if lang_id not in SUPPORTED_LANGS:
                continue
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    # 记录自定义消息
                    self._custom_messages.setdefault(lang_id, {}).update(data)
                    # 合并到全局消息字典
                    MESSAGES.setdefault(lang_id, {}).update(data)
            except Exception:
                pass

    def export_translations(self, lang: str, output_path: Path) -> None:
        """导出指定语言的翻译为 YAML 文件

        Args:
            lang: 语言代码（如 "en", "ja"）
            output_path: 输出文件路径
        """
        import yaml

        messages = MESSAGES.get(lang, {})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                dict(messages), f, allow_unicode=True, default_flow_style=False, sort_keys=True
            )

    # ---- 缺失键检查 ----

    def get_missing_keys(self, source_lang: str = "zh", target_lang: str = "en") -> list[str]:
        """获取目标语言中缺失的翻译键

        Args:
            source_lang: 源语言（默认 "zh"）
            target_lang: 目标语言

        Returns:
            缺失的键列表
        """
        source_keys = set(MESSAGES.get(source_lang, {}).keys())
        target_keys = set(MESSAGES.get(target_lang, {}).keys())
        return sorted(source_keys - target_keys)

    # ---- 自动翻译 ----

    def auto_translate(self, source_lang: str = "zh", target_lang: str = "en") -> dict[str, str]:
        """基于规则自动翻译缺失的键

        翻译规则：
        - 已有完整翻译的键直接复制
        - 格式化参数保留
        - 消息键推断：category.subkey → 英文首字母大写+空格
        - 返回未翻译的键和自动翻译建议

        Args:
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            自动翻译建议 {key: suggested_translation}
        """
        missing = self.get_missing_keys(source_lang, target_lang)
        if not missing:
            return {}

        suggestions: dict[str, str] = {}
        for key in missing:
            source_msg = MESSAGES.get(source_lang, {}).get(key, "")
            if not source_msg:
                continue

            if target_lang == "en":
                suggestions[key] = self._infer_english(key, source_msg)
            elif target_lang == "ja":
                suggestions[key] = self._infer_japanese(key, source_msg)
            elif target_lang == "ko":
                suggestions[key] = self._infer_korean(key, source_msg)
            else:
                suggestions[key] = source_msg  # 回退到原文

        return suggestions

    def _infer_english(self, key: str, source_msg: str) -> str:
        """从消息键推断英文翻译

        规则：点分键名 → 首字母大写 + 空格分隔
        保留格式化参数（如 {name}）
        """
        parts = key.split(".")
        # 将每个部分首字母大写
        title_parts = [p.replace("_", " ").title() for p in parts]
        inferred = " ".join(title_parts)

        # 如果源消息中有格式化参数，也加到推断结果中
        fmt_params = re.findall(r"\{(\w+)\}", source_msg)
        if fmt_params:
            param_str = ", ".join(f"{{{p}}}" for p in fmt_params)
            inferred = f"{inferred} ({param_str})"

        return inferred

    def _infer_japanese(self, key: str, source_msg: str) -> str:
        """从消息键推断日语翻译（简化规则）"""
        parts = key.split(".")
        title_parts = [p.replace("_", " ").title() for p in parts]
        return " / ".join(title_parts)

    def _infer_korean(self, key: str, source_msg: str) -> str:
        """从消息键推断韩语翻译（简化规则）"""
        parts = key.split(".")
        title_parts = [p.replace("_", " ").title() for p in parts]
        return " / ".join(title_parts)

    # ---- 文档翻译 ----

    def translate_doc(self, doc_data: dict, target_lang: str) -> dict:
        """翻译文档数据结构

        递归翻译文档 dict 中的中文文本字段。
        仅翻译已知的文本字段键，其他字段保持原样。

        Args:
            doc_data: 文档数据字典
            target_lang: 目标语言

        Returns:
            翻译后的文档数据字典
        """
        # 需要翻译的文本字段名
        translatable_fields = {
            "name",
            "description",
            "site_name",
            "site_description",
            "category",
            "concept",
            "comment_syntax",
            "repl_prompt",
        }

        if target_lang not in SUPPORTED_LANGS:
            return doc_data

        result = {}
        for k, v in doc_data.items():
            if k in translatable_fields and isinstance(v, str):
                # 尝试通过 t() 查找已有翻译
                translated = t(f"docs.{k}", lang=target_lang)
                # 如果 t() 返回了键名本身（说明没有找到翻译），保持原样
                if translated != f"docs.{k}":
                    result[k] = translated
                else:
                    result[k] = v
            elif isinstance(v, dict):
                result[k] = self.translate_doc(v, target_lang)
            elif isinstance(v, list):
                result[k] = [
                    self.translate_doc(item, target_lang) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                result[k] = v

        return result
