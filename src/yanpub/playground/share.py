"""Playground 代码分享服务

提供短链接分享、二维码生成、过期清理等功能。
存储使用内存字典 + JSON 文件持久化。
"""

from __future__ import annotations

import json
import logging
import random
import string
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("yanpub.playground.share")


@dataclass
class ShareRecord:
    """分享记录"""

    id: str
    lang: str
    code: str
    title: str = ""
    author: str = ""
    created_at: float = 0.0
    views: int = 0
    expires_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lang": self.lang,
            "code": self.code,
            "title": self.title,
            "author": self.author,
            "created_at": self.created_at,
            "views": self.views,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ShareRecord:
        return cls(
            id=data["id"],
            lang=data["lang"],
            code=data["code"],
            title=data.get("title", ""),
            author=data.get("author", ""),
            created_at=data.get("created_at", 0.0),
            views=data.get("views", 0),
            expires_at=data.get("expires_at"),
        )


class ShareManager:
    """分享管理器

    使用内存字典保存活跃分享记录，定期持久化到 JSON 文件。
    """

    def __init__(self, storage_dir: Path | None = None):
        self._shares: dict[str, ShareRecord] = {}
        self._storage_dir = storage_dir or Path.home() / ".yanpub" / "shares"
        self._storage_file = self._storage_dir / "shares.json"
        self._load()

    def create_share(
        self,
        lang: str,
        code: str,
        title: str = "",
        author: str = "",
        ttl_hours: int | None = None,
    ) -> ShareRecord:
        """创建分享链接

        生成 6 字符随机 ID，存储分享记录。
        """
        share_id = self.generate_short_id()
        # 确保不重复
        while share_id in self._shares:
            share_id = self.generate_short_id()

        now = time.time()
        expires_at = None
        if ttl_hours is not None and ttl_hours > 0:
            expires_at = now + ttl_hours * 3600

        record = ShareRecord(
            id=share_id,
            lang=lang,
            code=code,
            title=title,
            author=author,
            created_at=now,
            views=0,
            expires_at=expires_at,
        )
        self._shares[share_id] = record
        self._save()
        return record

    def get_share(self, share_id: str) -> Optional[ShareRecord]:
        """获取分享记录"""
        record = self._shares.get(share_id)
        if record is None:
            return None
        # 检查是否过期
        if record.expires_at is not None and time.time() > record.expires_at:
            del self._shares[share_id]
            self._save()
            return None
        return record

    def increment_views(self, share_id: str) -> None:
        """增加访问计数"""
        record = self._shares.get(share_id)
        if record is not None:
            record.views += 1
            self._save()

    def list_shares(self, limit: int = 50) -> list[ShareRecord]:
        """列出最近的分享（按创建时间倒序）"""
        shares = sorted(
            self._shares.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )
        # 过滤已过期的
        now = time.time()
        result = []
        for s in shares:
            if s.expires_at is not None and now > s.expires_at:
                continue
            result.append(s)
            if len(result) >= limit:
                break
        return result

    def delete_share(self, share_id: str) -> bool:
        """删除分享"""
        if share_id in self._shares:
            del self._shares[share_id]
            self._save()
            return True
        return False

    def cleanup_expired(self) -> int:
        """清理过期分享，返回清理数量"""
        now = time.time()
        expired_ids = [
            sid
            for sid, record in self._shares.items()
            if record.expires_at is not None and now > record.expires_at
        ]
        for sid in expired_ids:
            del self._shares[sid]
        if expired_ids:
            self._save()
        return len(expired_ids)

    def generate_qrcode_svg(self, url: str) -> str:
        """生成二维码 SVG（纯 Python 实现，不依赖第三方库）

        使用简化的矩阵模式，将 URL 编码为二维码 SVG。
        基于 QR 码 Version 1-3 的简化实现。
        """
        # 简化版 QR 码：使用固定矩阵模式
        # 将 URL 字符转为二进制位，填充到矩阵中
        data = url.encode("utf-8")

        # 确定矩阵大小（根据数据长度）
        if len(data) <= 17:
            size = 21  # Version 1
        elif len(data) <= 32:
            size = 25  # Version 2
        else:
            size = 29  # Version 3

        # 创建空白矩阵
        matrix = [[0] * size for _ in range(size)]

        # 绘制定位图案 (Finder Pattern) - 7x7 方块在三个角
        def draw_finder(row: int, col: int) -> None:
            for r in range(7):
                for c in range(7):
                    if 0 <= row + r < size and 0 <= col + c < size:
                        # 外框、内框、中心
                        if r in (0, 6) or c in (0, 6):
                            matrix[row + r][col + c] = 1
                        elif 2 <= r <= 4 and 2 <= c <= 4:
                            matrix[row + r][col + c] = 1
                        else:
                            matrix[row + r][col + c] = 0

        draw_finder(0, 0)
        draw_finder(0, size - 7)
        draw_finder(size - 7, 0)

        # 绘制定时图案 (Timing Pattern)
        for i in range(8, size - 8):
            matrix[6][i] = 1 if i % 2 == 0 else 0
            matrix[i][6] = 1 if i % 2 == 0 else 0

        # 将数据编码到矩阵中（简化版：直接按行填充数据位）
        data_bits = []
        for byte in data:
            for bit_pos in range(7, -1, -1):
                data_bits.append((byte >> bit_pos) & 1)

        # 填充数据区域（跳过已绘制区域）
        data_idx = 0
        # 从右下角开始，两列一组，从下往上
        col = size - 1
        upward = True
        while col >= 0 and data_idx < len(data_bits):
            if col == 6:
                col -= 1
                continue
            row_range = range(size - 1, -1, -1) if upward else range(size)
            for row in row_range:
                for dc in (0, -1):
                    c = col + dc
                    if c < 0 or c >= size:
                        continue
                    # 跳过定位图案区域
                    if (row < 9 and c < 9) or (row < 9 and c >= size - 8) or (row >= size - 8 and c < 9):
                        continue
                    # 跳过定时图案
                    if row == 6 or c == 6:
                        continue
                    if matrix[row][c] == 0 and data_idx < len(data_bits):
                        matrix[row][c] = data_bits[data_idx]
                        data_idx += 1
            col -= 2
            upward = not upward

        # 生成 SVG
        cell_size = 8
        margin = 4
        svg_size = size * cell_size + 2 * margin

        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{svg_size}" height="{svg_size}" '
            f'viewBox="0 0 {svg_size} {svg_size}">',
            f'<rect width="{svg_size}" height="{svg_size}" fill="white"/>',
        ]

        for row in range(size):
            for col in range(size):
                if matrix[row][col]:
                    x = margin + col * cell_size
                    y = margin + row * cell_size
                    svg_parts.append(
                        f'<rect x="{x}" y="{y}" '
                        f'width="{cell_size}" height="{cell_size}" fill="black"/>'
                    )

        svg_parts.append("</svg>")
        return "\n".join(svg_parts)

    @staticmethod
    def generate_short_id(length: int = 6) -> str:
        """生成短链接 ID（字母+数字）"""
        return "".join(
            random.choices(string.ascii_lowercase + string.digits, k=length)
        )

    # ---- 持久化 ----

    def _load(self) -> None:
        """从 JSON 文件加载分享数据"""
        if not self._storage_file.exists():
            return
        try:
            data = json.loads(self._storage_file.read_text(encoding="utf-8"))
            for item in data:
                record = ShareRecord.from_dict(item)
                self._shares[record.id] = record
            logger.info("已加载 %d 条分享记录", len(self._shares))
        except Exception as e:
            logger.warning("加载分享数据失败: %s", e)

    def _save(self) -> None:
        """保存分享数据到 JSON 文件"""
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            data = [record.to_dict() for record in self._shares.values()]
            self._storage_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("保存分享数据失败: %s", e)


# 全局单例
_share_manager: ShareManager | None = None


def get_share_manager() -> ShareManager:
    """获取全局分享管理器实例"""
    global _share_manager
    if _share_manager is None:
        _share_manager = ShareManager()
    return _share_manager
