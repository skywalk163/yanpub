"""安全审计 — 记录所有签名和验证操作

核心类：
- AuditEntry: 审计条目
- AuditLog: 审计日志管理器
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class AuditEntry:
    """审计条目"""

    timestamp: float = 0.0
    action: str = ""       # "sign" | "verify" | "trust_add" | "trust_remove" | "verify_fail"
    signer: str = ""
    key_id: str = ""
    details: dict = field(default_factory=dict)  # 附加信息

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AuditEntry:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class AuditLog:
    """审计日志 — 记录所有签名和验证操作

    日志默认存储在 ~/.yanpub/audit/ 目录下，
    按日期分割文件（audit_YYYY-MM-DD.jsonl）。
    """

    def __init__(self, log_dir: Path | None = None):
        if log_dir is None:
            log_dir = Path.home() / ".yanpub" / "audit"
        self._dir = log_dir

    @property
    def log_dir(self) -> Path:
        return self._dir

    def log(self, entry: AuditEntry) -> None:
        """记录审计条目"""
        self._dir.mkdir(parents=True, exist_ok=True)

        # 按日期分文件
        date_str = time.strftime("%Y-%m-%d", time.localtime(entry.timestamp))
        log_file = self._dir / f"audit_{date_str}.jsonl"

        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def query(
        self,
        action: str | None = None,
        signer: str | None = None,
        since: float | None = None,
    ) -> list[AuditEntry]:
        """查询审计日志

        Args:
            action: 按操作类型筛选
            signer: 按签名者筛选
            since: 起始时间戳（Unix 时间）

        Returns:
            匹配的审计条目列表（按时间倒序）
        """
        entries: list[AuditEntry] = []

        if not self._dir.exists():
            return entries

        for log_file in sorted(self._dir.glob("audit_*.jsonl")):
            try:
                lines = log_file.read_text(encoding="utf-8").strip().split("\n")
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        entry = AuditEntry.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        continue

                    # 筛选
                    if action and entry.action != action:
                        continue
                    if signer and entry.signer != signer:
                        continue
                    if since and entry.timestamp < since:
                        continue

                    entries.append(entry)
            except Exception:
                continue

        # 按时间倒序
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries

    def export(self, format: str = "json") -> str:
        """导出审计日志

        Args:
            format: "json" 或 "csv"

        Returns:
            格式化后的审计日志字符串
        """
        entries = self.query()

        if format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                "timestamp", "action", "signer", "key_id", "details",
            ])
            writer.writeheader()
            for entry in entries:
                row = entry.to_dict()
                row["details"] = json.dumps(row.get("details", {}), ensure_ascii=False)
                writer.writerow(row)
            return output.getvalue()

        # 默认 JSON
        return json.dumps(
            [e.to_dict() for e in entries],
            ensure_ascii=False,
            indent=2,
        )

    def get_stats(self) -> dict:
        """获取审计统计信息

        Returns:
            {
                "total": int,
                "by_action": {"sign": N, "verify": N, ...},
                "by_signer": {"alice": N, "bob": N, ...},
                "first_entry": float|None,
                "last_entry": float|None,
            }
        """
        entries = self.query()

        by_action: dict[str, int] = {}
        by_signer: dict[str, int] = {}
        first_ts: Optional[float] = None
        last_ts: Optional[float] = None

        for entry in entries:
            by_action[entry.action] = by_action.get(entry.action, 0) + 1
            if entry.signer:
                by_signer[entry.signer] = by_signer.get(entry.signer, 0) + 1

            ts = entry.timestamp
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        return {
            "total": len(entries),
            "by_action": by_action,
            "by_signer": by_signer,
            "first_entry": first_ts,
            "last_entry": last_ts,
        }
