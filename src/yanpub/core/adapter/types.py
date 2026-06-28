"""语言适配器数据类型

执行结果、补全项、诊断信息、词法 Token 等共享数据类。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecutionResult:
    """代码执行结果"""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class CompletionItem:
    """补全项"""

    label: str
    kind: str = "keyword"  # keyword | function | variable | type | module
    detail: str = ""
    documentation: str = ""
    insert_text: str = ""  # 默认等于 label

    def __post_init__(self):
        if not self.insert_text:
            self.insert_text = self.label


@dataclass
class Diagnostic:
    """诊断信息"""

    line: int  # 1-based
    column: int  # 1-based
    severity: str  # error | warning | info | hint
    message: str
    source: str = ""  # 来源语言


@dataclass
class TokenInfo:
    """词法分析结果"""

    type: str  # keyword | identifier | number | string | operator | comment | punctuation
    value: str
    line: int = 0
    column: int = 0
