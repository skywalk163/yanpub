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

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# 当前语言
_current_lang: str = "zh"

# 支持的语言列表
SUPPORTED_LANGS = ["zh", "en", "ja", "ko"]


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
        # 文档系统
        "docs.title": "言埠文档站",
        "docs.search": "搜索关键字...",
        "docs.languages": "支持的语言",
        "docs.comparison": "语言对比",
        "docs.keyword_index": "关键字索引",
        "docs.api_reference": "API 参考",
        "docs.overview": "概览",
        "docs.category": "分类",
        "docs.syntax": "语法",
        "docs.example": "示例",
        "docs.description": "描述",
        "docs.no_results": "未找到匹配结果",
        # 监控
        "monitor.title": "性能监控",
        "monitor.dashboard": "仪表板",
        "monitor.trend": "趋势",
        "monitor.regression": "回归检测",
        # AI 辅助
        "ai.title": "AI 辅助",
        "ai.complete": "智能补全",
        "ai.nl2code": "自然语言转代码",
        "ai.fix": "错误修复",
        # 沙箱
        "sandbox.title": "沙箱执行",
        "sandbox.running": "正在执行...",
        "sandbox.result": "执行结果",
        "sandbox.backend": "后端",
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
        # Docs
        "docs.title": "YanPub Documentation",
        "docs.search": "Search keywords...",
        "docs.languages": "Supported Languages",
        "docs.comparison": "Language Comparison",
        "docs.keyword_index": "Keyword Index",
        "docs.api_reference": "API Reference",
        "docs.overview": "Overview",
        "docs.category": "Category",
        "docs.syntax": "Syntax",
        "docs.example": "Example",
        "docs.description": "Description",
        "docs.no_results": "No matching results",
        # Monitor
        "monitor.title": "Performance Monitor",
        "monitor.dashboard": "Dashboard",
        "monitor.trend": "Trend",
        "monitor.regression": "Regression Detection",
        # AI Assist
        "ai.title": "AI Assist",
        "ai.complete": "Smart Complete",
        "ai.nl2code": "Natural Language to Code",
        "ai.fix": "Error Fix",
        # Sandbox
        "sandbox.title": "Sandbox Execution",
        "sandbox.running": "Executing...",
        "sandbox.result": "Execution Result",
        "sandbox.backend": "Backend",
    },
    "ja": {
        # 一般
        "app.name": "言埠 YanPub",
        "app.tagline": "中国語プログラミング言語統合インフラ",
        "app.version": "バージョン {version}",
        # エラー
        "error.syntax": "構文エラー",
        "error.runtime": "ランタイムエラー",
        "error.name": "名前エラー",
        "error.type": "型エラー",
        "error.import": "インポートエラー",
        "error.not_found": "見つかりません: {name}",
        "error.unknown_lang": "不明な言語: {lang_id}",
        "error.no_adapter": "利用可能な言語アダプタがありません",
        "error.command_failed": "コマンド実行失敗: {command}",
        # REPL
        "repl.welcome": "{name} v{version}へようこそ！ :help でヘルプを表示。",
        "repl.prompt": "{name}> ",
        "repl.continuation": "... ",
        "repl.goodbye": "さようなら！",
        "repl.cancel": "  (キャンセル)",
        "repl.switched": "{name} に切り替えました",
        "repl.command_help": "組み込みコマンド：",
        "repl.command_langs": "利用可能な言語一覧",
        "repl.command_keywords": "現在の言語キーワードを表示",
        "repl.command_quit": "終了",
        "repl.unknown_command": "不明なコマンド: {cmd}、:help でヘルプを表示",
        "repl.keywords_count": "{name} キーワード（{count}個）：",
        "repl.no_keywords": "キーワードが提供されていません",
        # パッケージ管理
        "pkg.install_start": "{name} をインストール中...",
        "pkg.install_ok": "[OK] {name} インストール成功",
        "pkg.install_fail": "[FAIL] {name} インストール失敗",
        "pkg.publish_ok": "[OK] {name} v{version} をローカルレジストリに公開",
        "pkg.not_found": "yanpkg.toml が見つかりません: {path}",
        "pkg.version_downgrade": "バージョンがアップグレードされていません: 現在 {current} -> 公開 {new}",
        "pkg.search_empty": "'{query}' に一致するパッケージがありません。",
        "pkg.no_packages": "レジストリにパッケージがありません。",
        "pkg.no_installed": "インストール済みパッケージがありません。",
        "pkg.sync_start": "リモートレジストリを同期中...",
        "pkg.sync_done": "同期完了：{count} パッケージ",
        # LSP
        "lsp.starting": "YanLSP 起動: {host}:{port}",
        "lsp.starting_stdio": "YanLSP 起動 (stdio)",
        # Playground
        "playground.starting": "Playground 起動: http://{host}:{port}",
        # ヘルスチェック
        "health.title": "アダプタヘルスチェックレポート",
        "health.healthy": "正常",
        "health.degraded": "縮退",
        "health.unhealthy": "利用不可",
        # ベンチマーク
        "bench.title": "パフォーマンスベンチマークレポート",
        "bench.running": "ベンチマーク実行中...",
        "bench.startup": "起動時間",
        "bench.keyword_load": "キーワード読み込み",
        "bench.execution": "コード実行",
        "bench.throughput": "スループット",
        # アダプタ
        "adapter.loaded": "アダプタ '{name}' 読み込み成功",
        "adapter.load_failed": "アダプタ '{name}' 読み込み失敗: {error}",
        # ドキュメント
        "docs.title": "言埠ドキュメント",
        "docs.search": "キーワードを検索...",
        "docs.languages": "対応言語",
        "docs.comparison": "言語比較",
        "docs.keyword_index": "キーワードインデックス",
        "docs.api_reference": "API リファレンス",
        "docs.overview": "概要",
        "docs.category": "カテゴリ",
        "docs.syntax": "構文",
        "docs.example": "例",
        "docs.description": "説明",
        "docs.no_results": "一致する結果がありません",
        # モニター
        "monitor.title": "パフォーマンスモニター",
        "monitor.dashboard": "ダッシュボード",
        "monitor.trend": "トレンド",
        "monitor.regression": "回帰検出",
        # AI支援
        "ai.title": "AI 支援",
        "ai.complete": "スマート補完",
        "ai.nl2code": "自然言語からコード",
        "ai.fix": "エラー修正",
        # サンドボックス
        "sandbox.title": "サンドボックス実行",
        "sandbox.running": "実行中...",
        "sandbox.result": "実行結果",
        "sandbox.backend": "バックエンド",
    },
    "ko": {
        # 일반
        "app.name": "言埠 YanPub",
        "app.tagline": "중국어 프로그래밍 언어 통합 인프라",
        "app.version": "버전 {version}",
        # 오류
        "error.syntax": "구문 오류",
        "error.runtime": "런타임 오류",
        "error.name": "이름 오류",
        "error.type": "타입 오류",
        "error.import": "임포트 오류",
        "error.not_found": "찾을 수 없음: {name}",
        "error.unknown_lang": "알 수 없는 언어: {lang_id}",
        "error.no_adapter": "사용 가능한 언어 어댑터가 없습니다",
        "error.command_failed": "명령 실행 실패: {command}",
        # REPL
        "repl.welcome": "{name} v{version}에 오신 것을 환영합니다! :help 로 도움말을 보세요.",
        "repl.prompt": "{name}> ",
        "repl.continuation": "... ",
        "repl.goodbye": "안녕히 가세요!",
        "repl.cancel": "  (취소됨)",
        "repl.switched": "{name}(으)로 전환됨",
        "repl.command_help": "내장 명령:",
        "repl.command_langs": "사용 가능한 언어 목록",
        "repl.command_keywords": "현재 언어 키워드 표시",
        "repl.command_quit": "종료",
        "repl.unknown_command": "알 수 없는 명령: {cmd}, :help 로 도움말을 보세요",
        "repl.keywords_count": "{name} 키워드 ({count}개):",
        "repl.no_keywords": "키워드가 제공되지 않았습니다",
        # 패키지 관리
        "pkg.install_start": "{name} 설치 중...",
        "pkg.install_ok": "[OK] {name} 설치 성공",
        "pkg.install_fail": "[FAIL] {name} 설치 실패",
        "pkg.publish_ok": "[OK] {name} v{version} 로컬 레지스트리에 게시됨",
        "pkg.not_found": "yanpkg.toml을 찾을 수 없음: {path}",
        "pkg.version_downgrade": "버전이 업그레이드되지 않음: 현재 {current} -> 게시 {new}",
        "pkg.search_empty": "'{query}'와 일치하는 패키지가 없습니다.",
        "pkg.no_packages": "레지스트리에 패키지가 없습니다.",
        "pkg.no_installed": "설치된 패키지가 없습니다.",
        "pkg.sync_start": "원격 레지스트리 동기화 중...",
        "pkg.sync_done": "동기화 완료: {count} 패키지",
        # LSP
        "lsp.starting": "YanLSP 시작: {host}:{port}",
        "lsp.starting_stdio": "YanLSP 시작 (stdio)",
        # Playground
        "playground.starting": "Playground 시작: http://{host}:{port}",
        # 상태 확인
        "health.title": "어댑터 상태 확인 보고서",
        "health.healthy": "정상",
        "health.degraded": "성능 저하",
        "health.unhealthy": "사용 불가",
        # 벤치마크
        "bench.title": "성능 벤치마크 보고서",
        "bench.running": "벤치마크 실행 중...",
        "bench.startup": "시작 시간",
        "bench.keyword_load": "키워드 로드",
        "bench.execution": "코드 실행",
        "bench.throughput": "처리량",
        # 어댑터
        "adapter.loaded": "어댑터 '{name}' 로드 성공",
        "adapter.load_failed": "어댑터 '{name}' 로드 실패: {error}",
        # 문서
        "docs.title": "言埠 문서 사이트",
        "docs.search": "키워드 검색...",
        "docs.languages": "지원 언어",
        "docs.comparison": "언어 비교",
        "docs.keyword_index": "키워드 인덱스",
        "docs.api_reference": "API 참조",
        "docs.overview": "개요",
        "docs.category": "분류",
        "docs.syntax": "구문",
        "docs.example": "예제",
        "docs.description": "설명",
        "docs.no_results": "일치하는 결과가 없습니다",
        # 모니터
        "monitor.title": "성능 모니터",
        "monitor.dashboard": "대시보드",
        "monitor.trend": "트렌드",
        "monitor.regression": "회귀 감지",
        # AI 보조
        "ai.title": "AI 보조",
        "ai.complete": "스마트 완성",
        "ai.nl2code": "자연어에서 코드로",
        "ai.fix": "오류 수정",
        # 샌드박스
        "sandbox.title": "샌드박스 실행",
        "sandbox.running": "실행 중...",
        "sandbox.result": "실행 결과",
        "sandbox.backend": "백엔드",
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


class I18nManager:
    """国际化管理器 — 扩展 i18n 支持

    提供翻译文件导入导出、缺失键检查、自动翻译建议、文档翻译等功能。
    I18nManager 是可选的增强层，原有的 t() 函数仍然可用。
    """

    def __init__(self):
        self._custom_messages: dict[str, dict[str, str]] = {}

    # ---- 翻译文件管理 ----

    def load_translations(self, lang_dir: Path) -> None:
        """从目录加载自定义翻译文件（YAML 格式）

        扫描 lang_dir 下的 {lang}.yaml 文件，合并到 _MESSAGES 中。
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
                    _MESSAGES.setdefault(lang_id, {}).update(data)
            except Exception:
                pass

    def export_translations(self, lang: str, output_path: Path) -> None:
        """导出指定语言的翻译为 YAML 文件

        Args:
            lang: 语言代码（如 "en", "ja"）
            output_path: 输出文件路径
        """
        import yaml

        messages = _MESSAGES.get(lang, {})
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
        source_keys = set(_MESSAGES.get(source_lang, {}).keys())
        target_keys = set(_MESSAGES.get(target_lang, {}).keys())
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
            source_msg = _MESSAGES.get(source_lang, {}).get(key, "")
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
