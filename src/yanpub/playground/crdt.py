"""CRDT 文档模型 — 基于 RGA（Replicated Growable Array）

核心数据结构：
- CharId: CRDT 字符标识
- CRDTChar: CRDT 中的单个字符
- CollabDocument: CRDT 协作文档

特性：
- 最终一致性：所有站点收到相同操作后状态一致
- 交换律和结合律：操作的应用顺序不影响最终结果
- 增量同步：只传输操作，不传输完整文档
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CharId:
    """CRDT 字符标识 — 用于全局唯一标识和排序"""

    site_id: str  # 站点ID（用户ID）
    seq: int  # 序列号
    lamport: int = 0  # Lamport 时间戳

    def __lt__(self, other: CharId) -> bool:
        if self.lamport != other.lamport:
            return self.lamport < other.lamport
        if self.site_id != other.site_id:
            return self.site_id < other.site_id
        return self.seq < other.seq

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CharId):
            return NotImplemented
        return (
            self.site_id == other.site_id
            and self.seq == other.seq
            and self.lamport == other.lamport
        )

    def __hash__(self) -> int:
        return hash((self.site_id, self.seq, self.lamport))

    def to_dict(self) -> dict:
        return {"siteId": self.site_id, "seq": self.seq, "lamport": self.lamport}

    @classmethod
    def from_dict(cls, data: dict) -> CharId:
        return cls(
            site_id=data["siteId"],
            seq=data["seq"],
            lamport=data.get("lamport", 0),
        )


@dataclass
class CRDTChar:
    """CRDT 中的单个字符"""

    id: CharId
    value: str
    left_id: Optional[CharId] = None  # 左邻居ID
    right_id: Optional[CharId] = None  # 右邻居ID
    deleted: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id.to_dict(),
            "value": self.value,
            "leftId": self.left_id.to_dict() if self.left_id else None,
            "rightId": self.right_id.to_dict() if self.right_id else None,
            "deleted": self.deleted,
        }


class CollabDocument:
    """CRDT 协作文档 — 基于 RGA（Replicated Growable Array）

    支持操作：
    - insert(site_id, index, text) — 在指定位置插入文本
    - delete(site_id, index, length) — 删除指定范围的文本
    - apply_remote(op) — 应用远程操作

    特性：
    - 最终一致性：所有站点收到相同操作后状态一致
    - 交换律和结合律：操作的应用顺序不影响最终结果
    - 增量同步：只传输操作，不传输完整文档
    """

    BEGIN = CharId(site_id="__begin__", seq=-1, lamport=-1)
    END = CharId(site_id="__end__", seq=-2, lamport=-2)

    def __init__(self, site_id: str):
        self._site_id = site_id
        self._lamport = 0
        self._seq = 0
        # 有序字符列表
        self._chars: list[CRDTChar] = []
        # ID → 字符索引映射
        self._id_index: dict[CharId, int] = {}

    @property
    def site_id(self) -> str:
        return self._site_id

    def _next_id(self) -> CharId:
        """生成下一个唯一 ID"""
        self._seq += 1
        self._lamport += 1
        return CharId(site_id=self._site_id, seq=self._seq, lamport=self._lamport)

    def _rebuild_index(self) -> None:
        """重建 ID → 索引映射"""
        self._id_index.clear()
        for i, ch in enumerate(self._chars):
            self._id_index[ch.id] = i

    def get_text(self) -> str:
        """获取当前文档文本"""
        return "".join(ch.value for ch in self._chars if not ch.deleted)

    def insert(self, index: int, text: str) -> list[dict]:
        """在指定位置插入文本，返回操作列表

        Args:
            index: 插入位置（0-based，相对于可见字符）
            text: 要插入的文本

        Returns:
            操作列表，可发送给远程站点
        """
        ops = []
        current_index = index  # 当前插入位置（相对可见字符）

        for char_value in text:
            # 每次插入后需要重新获取可见字符
            visible_chars = [ch for ch in self._chars if not ch.deleted]

            left_id = self.BEGIN
            right_id = self.END

            if current_index > 0 and current_index - 1 < len(visible_chars):
                left_id = visible_chars[current_index - 1].id
            elif current_index == 0 and len(visible_chars) > 0:
                right_id = visible_chars[0].id

            new_id = self._next_id()
            new_char = CRDTChar(
                id=new_id,
                value=char_value,
                left_id=left_id,
                right_id=right_id,
            )

            # 插入到正确位置
            self._insert_char(new_char)
            current_index += 1

            ops.append(
                {
                    "type": "insert",
                    "char": new_char.to_dict(),
                }
            )

        return ops

    def _insert_char(self, new_char: CRDTChar) -> None:
        """将字符插入到有序列表中的正确位置（RGA 算法）"""
        # 找到左邻居的位置
        left_idx = -1
        if new_char.left_id and new_char.left_id in self._id_index:
            left_idx = self._id_index[new_char.left_id]

        # 从左邻居之后开始，找到正确的插入位置
        insert_idx = left_idx + 1 if left_idx >= 0 else 0

        # 扫描右邻居，同时处理并发插入的排序
        while insert_idx < len(self._chars):
            ch = self._chars[insert_idx]
            # 如果当前字符的左邻居在 new_char 左边，需要继续
            if (
                ch.left_id
                and new_char.left_id
                and ch.left_id in self._id_index
                and self._id_index.get(ch.left_id, -1) <= left_idx
            ):
                # 比较并发插入的 ID（Lamport 时间戳）
                if ch.id < new_char.id:
                    insert_idx += 1
                    continue
            break

        self._chars.insert(insert_idx, new_char)
        self._rebuild_index()

    def delete(self, index: int, length: int = 1) -> list[dict]:
        """删除指定范围的文本，返回操作列表

        Args:
            index: 删除起始位置（0-based，相对于可见字符）
            length: 删除长度

        Returns:
            操作列表，可发送给远程站点
        """
        ops = []
        visible_chars = [ch for ch in self._chars if not ch.deleted]

        for i in range(length):
            if index + i >= len(visible_chars):
                break

            char = visible_chars[index + i]
            char.deleted = True
            self._lamport += 1

            ops.append(
                {
                    "type": "delete",
                    "charId": char.id.to_dict(),
                    "lamport": self._lamport,
                }
            )

        return ops

    def apply_remote(self, op: dict) -> None:
        """应用远程操作"""
        if op["type"] == "insert":
            char_data = op["char"]
            new_char = CRDTChar(
                id=CharId.from_dict(char_data["id"]),
                value=char_data["value"],
                left_id=CharId.from_dict(char_data["leftId"]) if char_data.get("leftId") else None,
                right_id=CharId.from_dict(char_data["rightId"])
                if char_data.get("rightId")
                else None,
                deleted=char_data.get("deleted", False),
            )

            # 更新 Lamport 时间戳
            self._lamport = max(self._lamport, new_char.id.lamport) + 1

            # 检查是否已存在
            if new_char.id not in self._id_index:
                self._insert_char(new_char)

        elif op["type"] == "delete":
            char_id = CharId.from_dict(op["charId"])
            if char_id in self._id_index:
                idx = self._id_index[char_id]
                self._chars[idx].deleted = True

            self._lamport = max(self._lamport, op.get("lamport", 0)) + 1

    def to_dict(self) -> dict:
        """序列化文档状态"""
        return {
            "siteId": self._site_id,
            "lamport": self._lamport,
            "chars": [ch.to_dict() for ch in self._chars],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CollabDocument:
        """从序列化数据恢复文档"""
        doc = cls(site_id=data["siteId"])
        doc._lamport = data.get("lamport", 0)

        for ch_data in data.get("chars", []):
            char = CRDTChar(
                id=CharId.from_dict(ch_data["id"]),
                value=ch_data["value"],
                left_id=CharId.from_dict(ch_data["leftId"]) if ch_data.get("leftId") else None,
                right_id=CharId.from_dict(ch_data["rightId"]) if ch_data.get("rightId") else None,
                deleted=ch_data.get("deleted", False),
            )
            doc._chars.append(char)

        doc._rebuild_index()
        return doc
