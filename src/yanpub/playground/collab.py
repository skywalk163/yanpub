"""Playground 实时协作 — 多用户同屏编辑

核心设计：
1. 协作房间（CollabRoom）：管理一个文档的协作会话
2. CRDT 文档模型（CollabDocument）：基于 RGA（Replicated Growable Array）的 CRDT，
   支持无冲突并发编辑
3. WebSocket 房间管理器（CollabManager）：管理所有协作房间和用户连接

通信协议：
- 客户端 → 服务器：加入房间、发送编辑操作、光标位置更新
- 服务器 → 客户端：广播编辑操作、用户列表更新、光标位置广播

WebSocket 消息格式：
  {"type": "join", "roomId": "xxx", "userId": "user1"}
  {"type": "edit", "roomId": "xxx", "userId": "user1", "op": {"type": "insert", ...}}
  {"type": "cursor", "roomId": "xxx", "userId": "user1", "position": {"line": 1, "col": 5}}
  {"type": "leave", "roomId": "xxx", "userId": "user1"}
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("yanpub.playground.collab")


# ---- CRDT 核心数据结构 ----


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


# ---- 协作房间 ----


@dataclass
class CollabUser:
    """协作用户"""

    user_id: str
    display_name: str = ""
    color: str = "#3498DB"
    cursor_line: int = 0
    cursor_col: int = 0
    selection_start: Optional[dict] = None
    selection_end: Optional[dict] = None
    joined_at: float = field(default_factory=time.time)


class CollabRoom:
    """协作房间 — 管理一个文档的协作会话

    功能：
    - 管理参与用户
    - 维护 CRDT 文档
    - 广播操作
    - 处理用户加入/离开
    """

    # 用户颜色池
    COLORS = [
        "#E74C3C",
        "#3498DB",
        "#2ECC71",
        "#F39C12",
        "#9B59B6",
        "#1ABC9C",
        "#E67E22",
        "#34495E",
    ]

    def __init__(self, room_id: str, lang: str = "duan"):
        self._room_id = room_id
        self._lang = lang
        self._doc = CollabDocument(site_id=f"room-{room_id}")
        self._users: dict[str, CollabUser] = {}
        self._connections: dict[str, Any] = {}  # user_id → WebSocket
        self._created_at = time.time()
        self._color_idx = 0

    @property
    def room_id(self) -> str:
        return self._room_id

    @property
    def lang(self) -> str:
        return self._lang

    @property
    def document(self) -> CollabDocument:
        return self._doc

    @property
    def users(self) -> dict[str, CollabUser]:
        return dict(self._users)

    @property
    def user_count(self) -> int:
        return len(self._users)

    def _next_color(self) -> str:
        """分配下一个用户颜色"""
        color = self.COLORS[self._color_idx % len(self.COLORS)]
        self._color_idx += 1
        return color

    async def join(self, user_id: str, display_name: str, websocket: Any) -> dict:
        """用户加入房间

        Returns:
            房间状态（文档内容、用户列表等）
        """
        color = self._next_color()
        user = CollabUser(
            user_id=user_id,
            display_name=display_name,
            color=color,
        )
        self._users[user_id] = user
        self._connections[user_id] = websocket

        # 通知其他用户
        await self._broadcast(
            {
                "type": "user_joined",
                "roomId": self._room_id,
                "user": {
                    "userId": user_id,
                    "displayName": display_name,
                    "color": color,
                },
            },
            exclude=user_id,
        )

        # 返回房间状态
        return {
            "roomId": self._room_id,
            "lang": self._lang,
            "document": self._doc.get_text(),
            "users": [
                {
                    "userId": u.user_id,
                    "displayName": u.display_name,
                    "color": u.color,
                }
                for u in self._users.values()
            ],
        }

    async def leave(self, user_id: str) -> None:
        """用户离开房间"""
        self._users.pop(user_id, None)
        self._connections.pop(user_id, None)

        await self._broadcast(
            {
                "type": "user_left",
                "roomId": self._room_id,
                "userId": user_id,
            }
        )

    async def apply_edit(self, user_id: str, ops: list[dict]) -> None:
        """应用编辑操作并广播"""
        for op in ops:
            self._doc.apply_remote(op)

        await self._broadcast(
            {
                "type": "edit",
                "roomId": self._room_id,
                "userId": user_id,
                "ops": ops,
            },
            exclude=user_id,
        )

    async def update_cursor(
        self, user_id: str, line: int, col: int, selection: Optional[dict] = None
    ) -> None:
        """更新用户光标位置"""
        user = self._users.get(user_id)
        if user is None:
            return

        user.cursor_line = line
        user.cursor_col = col
        if selection:
            user.selection_start = selection.get("start")
            user.selection_end = selection.get("end")

        await self._broadcast(
            {
                "type": "cursor",
                "roomId": self._room_id,
                "userId": user_id,
                "position": {"line": line, "col": col},
                "selection": selection,
                "color": user.color,
                "displayName": user.display_name,
            },
            exclude=user_id,
        )

    async def _broadcast(self, message: dict, exclude: str | None = None) -> None:
        """广播消息给房间内所有用户"""
        message_json = json.dumps(message, ensure_ascii=False)
        disconnected = []

        for uid, ws in self._connections.items():
            if uid == exclude:
                continue
            try:
                await ws.send_text(message_json)
            except Exception:
                disconnected.append(uid)

        # 清理断开连接的用户
        for uid in disconnected:
            self._users.pop(uid, None)
            self._connections.pop(uid, None)


class CollabManager:
    """协作房间管理器 — 管理所有协作房间和 WebSocket 连接

    API 端点：
    - POST /api/collab/create   创建房间
    - GET  /api/collab/{id}     获取房间信息
    - WS   /ws/collab/{id}      WebSocket 协作连接
    """

    def __init__(self):
        self._rooms: dict[str, CollabRoom] = {}
        self._room_ttl = 3600 * 4  # 房间过期时间（4小时）

    def create_room(self, lang: str = "duan", code: str = "") -> dict:
        """创建协作房间"""
        room_id = self._generate_room_id()
        room = CollabRoom(room_id=room_id, lang=lang)

        # 如果有初始代码，插入到文档
        if code:
            room._doc.insert(0, code)

        self._rooms[room_id] = room

        return {
            "roomId": room_id,
            "lang": lang,
            "url": f"/ws/collab/{room_id}",
        }

    def get_room(self, room_id: str) -> Optional[CollabRoom]:
        """获取房间"""
        return self._rooms.get(room_id)

    def list_rooms(self) -> list[dict]:
        """列出所有活跃房间"""
        return [
            {
                "roomId": room.room_id,
                "lang": room.lang,
                "users": room.user_count,
                "created_at": room._created_at,
            }
            for room in self._rooms.values()
        ]

    def cleanup_expired(self) -> int:
        """清理过期房间

        Returns:
            清理的房间数量
        """
        now = time.time()
        expired = [
            rid
            for rid, room in self._rooms.items()
            if now - room._created_at > self._room_ttl and room.user_count == 0
        ]
        for rid in expired:
            del self._rooms[rid]
        return len(expired)

    def _generate_room_id(self) -> str:
        """生成唯一的房间ID"""
        raw = f"{uuid.uuid4().hex}{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ---- FastAPI 路由注册 ----


def register_collab_routes(app: Any) -> CollabManager:
    """为 FastAPI 应用注册协作路由

    Args:
        app: FastAPI 应用实例

    Returns:
        CollabManager 实例
    """
    from fastapi import WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse

    manager = CollabManager()

    @app.post("/api/collab/create")
    async def create_collab_room(body: dict):
        """创建协作房间"""
        lang = body.get("lang", "duan")
        code = body.get("code", "")
        result = manager.create_room(lang=lang, code=code)
        return result

    @app.get("/api/collab/{room_id}")
    async def get_collab_room(room_id: str):
        """获取房间信息"""
        room = manager.get_room(room_id)
        if room is None:
            return JSONResponse({"error": "房间不存在"}, status_code=404)

        return {
            "roomId": room.room_id,
            "lang": room.lang,
            "users": room.user_count,
            "document": room.document.get_text(),
        }

    @app.get("/api/collab")
    async def list_collab_rooms():
        """列出所有协作房间"""
        return manager.list_rooms()

    @app.websocket("/ws/collab/{room_id}")
    async def collab_websocket(websocket: WebSocket, room_id: str):
        """协作 WebSocket 连接"""
        room = manager.get_room(room_id)
        if room is None:
            await websocket.close(code=4004, reason="房间不存在")
            return

        await websocket.accept()

        # 等待 join 消息
        try:
            join_msg = await websocket.receive_json()
        except Exception:
            await websocket.close(code=4000, reason="连接异常")
            return

        if join_msg.get("type") != "join":
            await websocket.close(code=4001, reason="必须先发送 join 消息")
            return

        user_id = join_msg.get("userId", str(uuid.uuid4())[:8])
        display_name = join_msg.get("displayName", f"用户{user_id[:4]}")

        # 加入房间
        state = await room.join(user_id, display_name, websocket)

        # 发送房间状态
        await websocket.send_text(
            json.dumps(
                {
                    "type": "room_state",
                    **state,
                },
                ensure_ascii=False,
            )
        )

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "edit":
                    ops = data.get("ops", [])
                    await room.apply_edit(user_id, ops)

                elif msg_type == "cursor":
                    position = data.get("position", {})
                    selection = data.get("selection")
                    await room.update_cursor(
                        user_id,
                        line=position.get("line", 0),
                        col=position.get("col", 0),
                        selection=selection,
                    )

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("协作 WebSocket 异常: %s", e)
        finally:
            await room.leave(user_id)

            # 清理空房间
            if room.user_count == 0:
                manager.cleanup_expired()

    return manager
