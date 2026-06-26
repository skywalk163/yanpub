r"""明道 (Mingdao) 语言适配器

明道项目位于 G:\dumategithub\langbyracket
基于 Racket 实现，需子进程适配
CLI 入口: racket -S <项目路径> <file>
REPL: racket mingdao/repl.rkt
"""

from __future__ import annotations

import os

from yanpub.adapters._keywords_cache import load_cached_keywords
from yanpub.core.adapter.adapter import SubprocessAdapter


_MINGDAO_PROJECT_DIR = r"G:\dumategithub\langbyracket"


class MingdaoAdapter(SubprocessAdapter):
    """明道适配器 — 通过子进程调用 Racket 后端

    明道是基于 Racket 的中文编程语言，使用 #lang mingdao 机制。
    需要系统安装 Racket 运行时。
    """

    def __init__(self):
        super().__init__(
            name="明道",
            lang_id="mingdao",
            version="0.6.0",
            extensions=[".道", ".mingdao", ".rkt"],
            run_command=["racket", "-S", _MINGDAO_PROJECT_DIR],
            eval_command=None,  # Racket 无 eval 选项，使用临时文件 fallback（需 #lang 头）
            repl_command=["racket", os.path.join(_MINGDAO_PROJECT_DIR, "mingdao", "repl.rkt")],
            keywords_loader=_load_mingdao_keywords,
            primary_color="#8E44AD",
        )

    def eval(self, code: str):
        """执行代码片段 — Racket 需要 #lang 声明，临时文件需预置 #lang mingdao"""
        import tempfile

        # 如果代码没有 #lang 行，自动添加
        if not code.lstrip().startswith("#lang"):
            code = "#lang mingdao\n" + code

        with tempfile.NamedTemporaryFile(
            suffix=".rkt",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write(code)
            tmp = f.name
        try:
            return self._exec(self._run_command + [tmp])
        finally:
            from pathlib import Path

            Path(tmp).unlink(missing_ok=True)

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "明道> "

    @property
    def repl_welcome(self) -> str:
        return (
            f"明道 v{self.version} — 基于 Racket 的中文编程语言\n"
            "SVO 调用语法、卫生宏系统\n"
            "输入代码并回车执行，输入 :help 查看帮助"
        )

    @property
    def capabilities(self) -> dict[str, bool]:
        return {
            "repl": True,
            "lsp": len(self.keywords) > 0,
            "package_manager": False,
            "debug": False,
            "wasm": False,
            "racket_required": True,  # 声明需要 Racket 运行时
        }


def _load_mingdao_keywords() -> list[str]:
    """加载明道关键字（优先从缓存）"""
    return load_cached_keywords(
        "mingdao", _load_mingdao_keywords_dynamic, _fallback_mingdao_keywords()
    )


def _load_mingdao_keywords_dynamic() -> list[str]:
    """明道关键字动态加载（手动提取，因为 tokenizer.rkt 无法 exec）"""
    return _fallback_mingdao_keywords()


def _fallback_mingdao_keywords() -> list[str]:
    return [
        # 定义
        "定义",
        "常量",
        "就是",
        "就是函",
        "定义宏",
        "就是宏",
        # 控制流
        "如果",
        "那么",
        "否则",
        "否则若",
        "对于",
        "从",
        "到",
        "对于每个",
        "当满足",
        "跳出",
        "继续",
        "返回",
        # 数据
        "列表",
        "元组",
        "字典",
        "索引",
        "长度",
        # 比较
        "等于",
        "不等",
        "大于",
        "小于",
        "大于等于",
        "小于等于",
        # 运算
        "加",
        "减",
        "乘",
        "除",
        "模",
        "幂",
        # 逻辑
        "非",
        "与",
        "或",
        # 模块
        "导入",
        "导出",
        "模块",
        # 赋值与输出
        "赋值",
        "打印",
        "生成",
        # 异常
        "捕获",
        # 高级
        "匿名函数",
        "做当满足",
    ]
