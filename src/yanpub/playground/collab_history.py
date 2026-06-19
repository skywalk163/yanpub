"""Playground 协作增强 — 文档历史 + 冲突解决 + 离线编辑

核心类:
- DocumentSnapshot: 文档快照
- DocumentHistory: 文档历史版本管理
- ConflictResolution: 冲突检测与解决
- OfflineEdit: 离线编辑缓冲
- CollabEnhancer: 协作增强管理器
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum


class ResolutionStrategy(str, Enum):
    OURS = "ours"
    THEIRS = "theirs"
    MERGE = "merge"
    MANUAL = "manual"


@dataclass
class DocumentSnapshot:
    """文档快照"""

    content: str
    version: int
    author: str = ""
    timestamp: float = field(default_factory=time.time)
    checksum: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.checksum:
            self.checksum = hashlib.md5(self.content.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "version": self.version,
            "author": self.author,
            "timestamp": self.timestamp,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DocumentSnapshot:
        return cls(
            content=data["content"],
            version=data["version"],
            author=data.get("author", ""),
            timestamp=data.get("timestamp", 0),
            checksum=data.get("checksum", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConflictRegion:
    """冲突区域"""

    start_line: int  # 1-based
    end_line: int
    our_content: str
    their_content: str
    base_content: str = ""
    resolution: ResolutionStrategy = ResolutionStrategy.MANUAL
    resolved_content: str = ""

    def to_dict(self) -> dict:
        return {
            "start_line": self.start_line,
            "end_line": self.end_line,
            "our_content": self.our_content,
            "their_content": self.their_content,
            "base_content": self.base_content,
            "resolution": self.resolution.value,
            "resolved_content": self.resolved_content,
        }


@dataclass
class OfflineOperation:
    """离线操作记录"""

    op_type: str  # "insert" | "delete" | "replace"
    position: int  # 字符偏移
    content: str = ""
    length: int = 0
    timestamp: float = field(default_factory=time.time)
    lamport: int = 0

    def to_dict(self) -> dict:
        return {
            "op_type": self.op_type,
            "position": self.position,
            "content": self.content,
            "length": self.length,
            "timestamp": self.timestamp,
            "lamport": self.lamport,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OfflineOperation:
        return cls(
            op_type=data["op_type"],
            position=data["position"],
            content=data.get("content", ""),
            length=data.get("length", 0),
            timestamp=data.get("timestamp", 0),
            lamport=data.get("lamport", 0),
        )


class DocumentHistory:
    """文档历史版本管理

    - 维护文档的版本快照链
    - 支持按版本号或时间戳检索
    - 支持差异对比
    """

    MAX_HISTORY = 100

    def __init__(self, room_id: str):
        self._room_id = room_id
        self._snapshots: list[DocumentSnapshot] = []
        self._current_version = 0

    @property
    def room_id(self) -> str:
        return self._room_id

    @property
    def current_version(self) -> int:
        return self._current_version

    def save_snapshot(
        self, content: str, author: str = "", metadata: dict | None = None
    ) -> DocumentSnapshot:
        """保存文档快照"""
        self._current_version += 1
        snap = DocumentSnapshot(
            content=content,
            version=self._current_version,
            author=author,
            metadata=metadata or {},
        )
        self._snapshots.append(snap)
        # 限制历史长度
        if len(self._snapshots) > self.MAX_HISTORY:
            self._snapshots = self._snapshots[-self.MAX_HISTORY :]
        return snap

    def get_snapshot(self, version: int) -> DocumentSnapshot | None:
        for snap in self._snapshots:
            if snap.version == version:
                return snap
        return None

    def get_latest(self) -> DocumentSnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    def list_versions(self, limit: int = 20) -> list[dict]:
        """列出最近的版本"""
        result = []
        for snap in reversed(self._snapshots[-limit:]):
            result.append(
                {
                    "version": snap.version,
                    "author": snap.author,
                    "timestamp": snap.timestamp,
                    "checksum": snap.checksum,
                }
            )
        return result

    def diff(self, v1: int, v2: int) -> dict:
        """比较两个版本的差异"""
        s1 = self.get_snapshot(v1)
        s2 = self.get_snapshot(v2)
        if not s1 or not s2:
            return {"error": "版本不存在"}
        lines1 = s1.content.split("\n")
        lines2 = s2.content.split("\n")
        # 简单行级差异
        added = []
        removed = []
        lines2_set = set(lines2)
        lines1_set = set(lines1)
        for i, line in enumerate(lines2):
            if line not in lines1_set:
                added.append({"line": i + 1, "content": line})
        for i, line in enumerate(lines1):
            if line not in lines2_set:
                removed.append({"line": i + 1, "content": line})
        return {
            "v1": v1,
            "v2": v2,
            "added": added,
            "removed": removed,
            "added_count": len(added),
            "removed_count": len(removed),
        }

    def restore(self, version: int) -> str | None:
        """恢复到指定版本"""
        snap = self.get_snapshot(version)
        return snap.content if snap else None


class ConflictResolution:
    """冲突检测与解决

    - 三方对比检测冲突区域（基于行）
    - 提供自动/半自动/手动解决策略
    """

    @staticmethod
    def detect_conflicts(base: str, ours: str, theirs: str) -> list[ConflictRegion]:
        """三方对比检测冲突区域"""
        base_lines = base.split("\n")
        our_lines = ours.split("\n")
        their_lines = theirs.split("\n")

        conflicts = []
        max_len = max(len(base_lines), len(our_lines), len(their_lines))

        # 逐行对比，寻找双方都修改的行
        i = 0
        while i < max_len:
            b = base_lines[i] if i < len(base_lines) else None
            o = our_lines[i] if i < len(our_lines) else None
            t = their_lines[i] if i < len(their_lines) else None

            our_changed = o != b
            their_changed = t != b
            both_changed = our_changed and their_changed

            if both_changed and o != t:
                # 冲突行 — 收集连续冲突行
                start = i + 1  # 1-based
                our_block = []
                their_block = []
                base_block = []
                while i < max_len:
                    b2 = base_lines[i] if i < len(base_lines) else None
                    o2 = our_lines[i] if i < len(our_lines) else None
                    t2 = their_lines[i] if i < len(their_lines) else None
                    if o2 != t2 and (o2 != b2 or t2 != b2):
                        if o2 is not None:
                            our_block.append(o2)
                        if t2 is not None:
                            their_block.append(t2)
                        if b2 is not None:
                            base_block.append(b2)
                        i += 1
                    else:
                        break
                conflicts.append(
                    ConflictRegion(
                        start_line=start,
                        end_line=i,
                        our_content="\n".join(our_block),
                        their_content="\n".join(their_block),
                        base_content="\n".join(base_block),
                    )
                )
            else:
                i += 1
        return conflicts

    @staticmethod
    def resolve(conflict: ConflictRegion, strategy: ResolutionStrategy) -> ConflictRegion:
        """根据策略解决单个冲突"""
        if strategy == ResolutionStrategy.OURS:
            conflict.resolved_content = conflict.our_content
        elif strategy == ResolutionStrategy.THEIRS:
            conflict.resolved_content = conflict.their_content
        elif strategy == ResolutionStrategy.MERGE:
            # 简单合并：两者都保留，用标记分隔
            conflict.resolved_content = (
                f"<<<<<<< ours\n{conflict.our_content}\n"
                f"=======\n{conflict.their_content}\n"
                f">>>>>>> theirs"
            )
        conflict.resolution = strategy
        return conflict

    @staticmethod
    def apply_resolutions(content: str, conflicts: list[ConflictRegion]) -> str:
        """将冲突解决结果应用到文档"""
        if not conflicts:
            return content
        lines = content.split("\n")
        # 从后往前替换，避免行号偏移
        for conflict in reversed(conflicts):
            if not conflict.resolved_content:
                continue
            resolved_lines = conflict.resolved_content.split("\n")
            start_idx = conflict.start_line - 1  # 转为 0-based
            end_idx = conflict.end_line
            lines[start_idx:end_idx] = resolved_lines
        return "\n".join(lines)


class OfflineEditBuffer:
    """离线编辑缓冲

    - 在离线状态下暂存编辑操作
    - 恢复连接后按序重放
    """

    def __init__(self, user_id: str, room_id: str):
        self._user_id = user_id
        self._room_id = room_id
        self._operations: list[OfflineOperation] = []
        self._lamport_counter = 0
        self._is_offline = False

    @property
    def is_offline(self) -> bool:
        return self._is_offline

    @property
    def pending_count(self) -> int:
        return len(self._operations)

    def go_offline(self) -> None:
        self._is_offline = True

    def go_online(self) -> None:
        self._is_offline = False

    def record(
        self, op_type: str, position: int, content: str = "", length: int = 0
    ) -> OfflineOperation:
        """记录一个离线编辑操作"""
        self._lamport_counter += 1
        op = OfflineOperation(
            op_type=op_type,
            position=position,
            content=content,
            length=length,
            lamport=self._lamport_counter,
        )
        self._operations.append(op)
        return op

    def record_insert(self, position: int, text: str) -> OfflineOperation:
        return self.record("insert", position, content=text, length=len(text))

    def record_delete(self, position: int, length: int) -> OfflineOperation:
        return self.record("delete", position, length=length)

    def record_replace(self, position: int, length: int, new_text: str) -> OfflineOperation:
        return self.record("replace", position, content=new_text, length=length)

    def flush(self) -> list[OfflineOperation]:
        """取出所有待重放操作（按 lamport 排序）"""
        ops = sorted(self._operations, key=lambda o: o.lamport)
        self._operations = []
        return ops

    def apply_to_document(self, content: str) -> str:
        """将缓冲操作应用到文档内容（离线预览）"""
        result = content
        for op in sorted(self._operations, key=lambda o: o.lamport):
            if op.op_type == "insert":
                result = result[: op.position] + op.content + result[op.position :]
            elif op.op_type == "delete":
                end = min(op.position + op.length, len(result))
                result = result[: op.position] + result[end:]
            elif op.op_type == "replace":
                end = min(op.position + op.length, len(result))
                result = result[: op.position] + op.content + result[end:]
        return result

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "room_id": self._room_id,
            "is_offline": self._is_offline,
            "pending_count": len(self._operations),
            "operations": [op.to_dict() for op in self._operations],
        }


class CollabEnhancer:
    """协作增强管理器

    集成文档历史、冲突解决、离线编辑
    """

    def __init__(self):
        self._histories: dict[str, DocumentHistory] = {}
        self._offline_buffers: dict[str, OfflineEditBuffer] = {}  # key: room_id:user_id
        self._conflict_cache: dict[str, list[ConflictRegion]] = {}

    # ---- 文档历史 ----

    def get_history(self, room_id: str) -> DocumentHistory:
        if room_id not in self._histories:
            self._histories[room_id] = DocumentHistory(room_id)
        return self._histories[room_id]

    def save_version(self, room_id: str, content: str, author: str = "") -> DocumentSnapshot:
        return self.get_history(room_id).save_snapshot(content, author)

    def list_versions(self, room_id: str, limit: int = 20) -> list[dict]:
        return self.get_history(room_id).list_versions(limit)

    def get_version(self, room_id: str, version: int) -> DocumentSnapshot | None:
        return self.get_history(room_id).get_snapshot(version)

    def diff_versions(self, room_id: str, v1: int, v2: int) -> dict:
        return self.get_history(room_id).diff(v1, v2)

    def restore_version(self, room_id: str, version: int) -> str | None:
        return self.get_history(room_id).restore(version)

    # ---- 冲突解决 ----

    def detect_conflicts(self, base: str, ours: str, theirs: str) -> list[ConflictRegion]:
        return ConflictResolution.detect_conflicts(base, ours, theirs)

    def resolve_conflict(
        self, conflict: ConflictRegion, strategy: ResolutionStrategy
    ) -> ConflictRegion:
        return ConflictResolution.resolve(conflict, strategy)

    def apply_resolutions(self, content: str, conflicts: list[ConflictRegion]) -> str:
        return ConflictResolution.apply_resolutions(content, conflicts)

    # ---- 离线编辑 ----

    def get_offline_buffer(self, room_id: str, user_id: str) -> OfflineEditBuffer:
        key = f"{room_id}:{user_id}"
        if key not in self._offline_buffers:
            self._offline_buffers[key] = OfflineEditBuffer(user_id, room_id)
        return self._offline_buffers[key]

    def go_offline(self, room_id: str, user_id: str) -> None:
        buf = self.get_offline_buffer(room_id, user_id)
        buf.go_offline()

    def go_online(self, room_id: str, user_id: str) -> list[OfflineOperation]:
        buf = self.get_offline_buffer(room_id, user_id)
        buf.go_online()
        return buf.flush()

    # ---- 统计 ----

    def stats(self) -> dict:
        return {
            "rooms_with_history": len(self._histories),
            "offline_buffers": len(self._offline_buffers),
            "total_pending_ops": sum(b.pending_count for b in self._offline_buffers.values()),
        }


# 全局单例
_enhancer: CollabEnhancer | None = None


def get_collab_enhancer() -> CollabEnhancer:
    global _enhancer
    if _enhancer is None:
        _enhancer = CollabEnhancer()
    return _enhancer
