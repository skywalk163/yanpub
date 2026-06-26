"""多语言文档生成器 — 适配器文档的国际化生成

在 DocsGenerator 基础上，扩展支持按目标语言翻译文档内容，
包括语言概览、API 参考和关键字文档。
"""

from __future__ import annotations

from pathlib import Path

from yanpub.core.keyword_docs import CATEGORY_DESCRIPTIONS, KEYWORD_EXAMPLES
from yanpub.core.adapter.registry import LanguageRegistry, get_registry
from yanpub.docs.generator import DocsGenerator, KeywordDoc
from yanpub.docs.translator import RuleBasedTranslator
from yanpub.i18n import I18nManager, SUPPORTED_LANGS, t


class I18nDocsGenerator:
    """多语言文档生成器

    基于 DocsGenerator 扩展，支持按目标语言翻译适配器文档。
    """

    def __init__(
        self,
        registry: LanguageRegistry | None = None,
        i18n_manager: I18nManager | None = None,
    ):
        self.registry = registry if registry is not None else get_registry()
        self.i18n_manager = i18n_manager or I18nManager()
        self.docs_generator = DocsGenerator(self.registry)
        self.translator = RuleBasedTranslator()

    def generate_language_overview(self, lang_id: str, target_lang: str = "zh") -> dict:
        """生成指定语言的适配器文档（按目标语言翻译）

        Args:
            lang_id: 语言适配器 ID
            target_lang: 目标语言（默认 "zh"）

        Returns:
            翻译后的 LanguageOverview dict
        """
        overview = self.docs_generator.get_language_overview(lang_id)
        if overview is None:
            return {}

        result = {
            "lang_id": overview.lang_id,
            "name": overview.name,
            "version": overview.version,
            "extensions": overview.extensions,
            "primary_color": overview.primary_color,
            "description": self.translator.translate(overview.description, target_lang=target_lang),
            "comment_syntax": overview.comment_syntax,
            "repl_prompt": overview.repl_prompt,
            "capabilities": overview.capabilities,
            "keyword_count": len(overview.keywords),
            "keywords": [self._translate_keyword_doc(kd, target_lang) for kd in overview.keywords],
        }

        return result

    def generate_multilang_site(
        self,
        output_dir: Path,
        languages: list[str] | None = None,
    ) -> dict[str, dict]:
        """生成多语言文档站数据

        Args:
            output_dir: 输出目录
            languages: 目标语言列表（默认所有 SUPPORTED_LANGS）

        Returns:
            {"zh": {...site_data...}, "en": {...}, ...}
        """
        target_langs = languages or SUPPORTED_LANGS
        result: dict[str, dict] = {}

        site_data = self.docs_generator.generate_site_data()

        for lang in target_langs:
            translated = self._translate_site_data(site_data, lang)
            result[lang] = translated

            # 写入文件
            lang_dir = output_dir / lang
            lang_dir.mkdir(parents=True, exist_ok=True)

            import json

            data_file = lang_dir / "site_data.json"
            data_file.write_text(
                json.dumps(translated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return result

    def generate_api_reference(self, lang_id: str, target_lang: str = "zh") -> dict:
        """生成适配器 API 参考文档（多语言）

        包含：
        - 语言基本信息
        - 关键字列表（按分类，含翻译后的描述）
        - 语法示例（含翻译后的注释）
        - 支持的操作
        - 能力矩阵

        Args:
            lang_id: 语言适配器 ID
            target_lang: 目标语言

        Returns:
            API 参考文档 dict
        """
        adapter = self.registry.get(lang_id)
        if adapter is None:
            return {}

        overview = self.docs_generator.get_language_overview(lang_id)
        if overview is None:
            return {}

        # 按分类组织关键字
        keyword_index = self.docs_generator.generate_keyword_index(lang_id)

        # 翻译关键字索引
        translated_index: dict[str, list[dict]] = {}
        for category, kw_docs in keyword_index.items():
            translated_category = self.translator.translate(category, target_lang=target_lang)
            translated_category_desc = self.translator.translate(
                CATEGORY_DESCRIPTIONS.get(category, ""),
                target_lang=target_lang,
            )
            translated_kws = []
            for kd in kw_docs:
                translated_kw = self._translate_keyword_doc(kd, target_lang)
                # 添加语法示例
                example = KEYWORD_EXAMPLES.get(kd.keyword, "")
                if example:
                    translated_kw["syntax_example"] = example
                translated_kws.append(translated_kw)

            translated_index[translated_category] = translated_kws
            # 在列表头部插入分类描述
            if translated_category_desc:
                translated_index[translated_category + "_desc"] = translated_category_desc

        # 能力矩阵
        capabilities = adapter.capabilities
        capability_labels = {
            "repl": t("repl.welcome", lang=target_lang).split("!")[0]
            if target_lang != "zh"
            else "REPL",
            "lsp": "LSP",
            "package_manager": t("docs.category", lang=target_lang),
            "debug": "Debug" if target_lang != "zh" else "调试",
            "wasm": "WASM",
        }

        return {
            "lang_id": adapter.id,
            "name": adapter.name,
            "version": adapter.version,
            "description": self.translator.translate(overview.description, target_lang=target_lang),
            "extensions": adapter.file_extensions,
            "comment_syntax": adapter.comment_syntax,
            "repl_prompt": adapter.repl_prompt,
            "keywords_by_category": translated_index,
            "keyword_count": len(overview.keywords),
            "capabilities": {capability_labels.get(k, k): v for k, v in capabilities.items()},
            "primary_color": adapter.primary_color,
        }

    def translate_keyword_doc(self, keyword_doc: KeywordDoc, target_lang: str) -> KeywordDoc:
        """翻译关键字文档条目

        Args:
            keyword_doc: 原始 KeywordDoc
            target_lang: 目标语言

        Returns:
            翻译后的 KeywordDoc
        """
        return KeywordDoc(
            keyword=keyword_doc.keyword,
            lang_id=keyword_doc.lang_id,
            lang_name=keyword_doc.lang_name,
            category=self.translator.translate(keyword_doc.category, target_lang=target_lang),
            syntax_example=keyword_doc.syntax_example,
            description=self.translator.translate(keyword_doc.description, target_lang=target_lang),
        )

    # ---- 内部方法 ----

    def _translate_keyword_doc(self, kd: KeywordDoc, target_lang: str) -> dict:
        """翻译 KeywordDoc 并返回 dict"""
        translated = self.translate_keyword_doc(kd, target_lang)
        return {
            "keyword": translated.keyword,
            "keyword_display": self.translator.translate(
                translated.keyword, target_lang=target_lang
            ),
            "lang_id": translated.lang_id,
            "lang_name": translated.lang_name,
            "category": translated.category,
            "syntax_example": translated.syntax_example,
            "description": translated.description,
        }

    def _translate_site_data(self, site_data: dict, target_lang: str) -> dict:
        """翻译文档站全部数据

        Args:
            site_data: 原始文档站数据
            target_lang: 目标语言

        Returns:
            翻译后的文档站数据
        """
        result = {
            "site_name": t("docs.title", lang=target_lang)
            if target_lang != "zh"
            else site_data.get("site_name", ""),
            "site_description": t("app.tagline", lang=target_lang),
            "languages": [],
            "comparison": [],
            "stats": site_data.get("stats", {}),
        }

        # 翻译语言列表
        for lang_data in site_data.get("languages", []):
            translated_lang = dict(lang_data)
            if "description" in translated_lang:
                translated_lang["description"] = self.translator.translate(
                    translated_lang["description"],
                    target_lang=target_lang,
                )

            # 翻译关键字分类
            translated_kws_by_cat: dict[str, list[dict]] = {}
            for cat, kws in translated_lang.get("keywords_by_category", {}).items():
                translated_cat = self.translator.translate(cat, target_lang=target_lang)
                translated_kws = [
                    self.translator.translate_keyword_doc(kw, target_lang) for kw in kws
                ]
                translated_kws_by_cat[translated_cat] = translated_kws
            translated_lang["keywords_by_category"] = translated_kws_by_cat

            result["languages"].append(translated_lang)

        # 翻译对比表
        for comp in site_data.get("comparison", []):
            translated_comp = dict(comp)
            if "concept" in translated_comp:
                translated_comp["concept"] = self.translator.translate(
                    translated_comp["concept"],
                    target_lang=target_lang,
                )
            result["comparison"].append(translated_comp)

        return result
