"""版本约束解析 — 支持 >=, ^, ~, 精确, *, 逗号分隔组合

核心类：
- VersionConstraint: 版本约束解析与匹配

辅助函数：
- _parse_version(): 版本字符串解析
- _same_major(): 主版本相同检查
- _same_minor(): 主+次版本相同检查
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class VersionConstraint:
    """版本约束

    支持格式：
      ">=1.0.0"       大于等于
      "^1.0.0"        兼容版本（主版本相同）
      "~1.0.0"        近似版本（主+次版本相同）
      "1.0.0"         精确版本
      "*"             任意版本
      ">=1.0.0,<2.0.0" 逗号分隔的与（AND）约束
    """

    raw: str
    parts: list[tuple[str, str]] = field(default_factory=list)
    """每个元素为 (operator, target_version)"""

    @classmethod
    def parse(cls, spec: str) -> VersionConstraint:
        """解析版本约束字符串"""
        spec = spec.strip()
        if not spec:
            spec = "*"

        parts: list[tuple[str, str]] = []

        if spec == "*":
            parts.append(("*", "*"))
        elif "," in spec:
            # 组合约束：">=1.0.0,<2.0.0"
            for segment in spec.split(","):
                segment = segment.strip()
                parts.append(cls._parse_single(segment))
        else:
            parts.append(cls._parse_single(spec))

        return cls(raw=spec, parts=parts)

    @staticmethod
    def _parse_single(segment: str) -> tuple[str, str]:
        """解析单条约束，返回 (operator, target)"""
        segment = segment.strip()
        if segment == "*":
            return ("*", "*")
        if segment.startswith(">="):
            return (">=", segment[2:].strip())
        if segment.startswith(">"):
            return (">", segment[1:].strip())
        if segment.startswith("<="):
            return ("<=", segment[2:].strip())
        if segment.startswith("<"):
            return ("<", segment[1:].strip())
        if segment.startswith("^"):
            return ("^", segment[1:].strip())
        if segment.startswith("~"):
            return ("~", segment[1:].strip())
        # 精确版本
        return ("==", segment)

    def matches(self, version: str) -> bool:
        """检查版本是否满足约束"""
        return all(self._match_single(op, target, version) for op, target in self.parts)

    @staticmethod
    def _match_single(op: str, target: str, version: str) -> bool:
        """匹配单条约束"""
        if op == "*":
            return True
        if op == "==":
            return _parse_version(version) == _parse_version(target)
        if op == ">=":
            return _parse_version(version) >= _parse_version(target)
        if op == ">":
            return _parse_version(version) > _parse_version(target)
        if op == "<=":
            return _parse_version(version) <= _parse_version(target)
        if op == "<":
            return _parse_version(version) < _parse_version(target)
        if op == "^":
            # 兼容版本：主版本相同且 version >= target
            vv = _parse_version(version)
            tv = _parse_version(target)
            return vv >= tv and _same_major(version, target)
        if op == "~":
            # 近似版本：主+次版本相同且 version >= target
            vv = _parse_version(version)
            tv = _parse_version(target)
            return vv >= tv and _same_minor(version, target)
        return False


# ---------------------------------------------------------------------------
# 辅助函数（简单字符串分割 + 整数比较）
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?.*$")


def _parse_version(v: str) -> tuple[int, ...]:
    """将版本字符串解析为可比较的整数元组"""
    m = _VERSION_RE.match(v.strip())
    if not m:
        return (0,)
    parts = []
    for i in range(1, 4):
        group = m.group(i)
        parts.append(int(group) if group is not None else 0)
    return tuple(parts)


def _same_major(a: str, b: str) -> bool:
    va = _parse_version(a)
    vb = _parse_version(b)
    return va[0] == vb[0] if va and vb else False


def _same_minor(a: str, b: str) -> bool:
    va = _parse_version(a)
    vb = _parse_version(b)
    return va[:2] == vb[:2] if len(va) >= 2 and len(vb) >= 2 else False
