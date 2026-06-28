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

from .crdt import CharId, CRDTChar, CollabDocument  # noqa: F401

logger = logging.getLogger("yanpub.playground.collab")


def __getattr__(name):
    _moved = {"CharId", "CRDTChar", "CollabDocument"}
    if name in _moved:
        import importlib
        mod = importlib.import_module(".crdt", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
