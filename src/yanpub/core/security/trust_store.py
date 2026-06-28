"""信任存储 — 管理受信任的签名密钥

核心类：
- TrustStore: 信任存储（管理受信任密钥）

信任级别：
- full: 完全信任（项目官方密钥，作为根信任锚）
- ca: 证书颁发机构（可签发子密钥）
- user: 用户级信任
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .keys import SigningKey


class TrustStore:
    """信任存储 — 管理受信任的签名密钥

    信任级别：
    - full: 完全信任（项目官方密钥，作为根信任锚）
    - ca: 证书颁发机构（可签发子密钥）
    - user: 用户级信任
    """

    def __init__(self, store_dir: Path | None = None):
        if store_dir is None:
            store_dir = Path.home() / ".yanpub" / "trust"
        self._dir = store_dir
        # key_id → {key: SigningKey, signer: str, trust_level: str, signed_by: str|None}
        self._keys: dict[str, dict] = {}
        self._load()

    @property
    def store_dir(self) -> Path:
        return self._dir

    def _load(self) -> None:
        """从磁盘加载信任存储"""
        store_file = self._dir / "trust_store.json"
        if store_file.exists():
            try:
                data = json.loads(store_file.read_text(encoding="utf-8"))
                for entry in data.get("keys", []):
                    key_data = entry.get("key", {})
                    key = SigningKey.from_dict(key_data)
                    self._keys[key.key_id] = {
                        "key": key,
                        "signer": entry.get("signer", ""),
                        "trust_level": entry.get("trust_level", "user"),
                        "signed_by": entry.get("signed_by"),
                    }
            except (json.JSONDecodeError, KeyError):
                self._keys = {}

    def _save(self) -> None:
        """保存信任存储到磁盘"""
        self._dir.mkdir(parents=True, exist_ok=True)
        store_file = self._dir / "trust_store.json"
        data = {
            "version": "1",
            "updated_at": time.time(),
            "keys": [
                {
                    "key": entry["key"].to_dict(),
                    "signer": entry["signer"],
                    "trust_level": entry["trust_level"],
                    "signed_by": entry.get("signed_by"),
                }
                for entry in self._keys.values()
            ],
        }
        store_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_trusted_key(
        self,
        key: SigningKey,
        signer: str,
        trust_level: str = "full",
        signed_by: str | None = None,
    ) -> None:
        """添加受信任的密钥

        Args:
            key: 签名密钥（公钥）
            signer: 签名者标识
            trust_level: "full" | "ca" | "user"
            signed_by: 签发此密钥的 CA 的 key_id（信任链）
        """
        if trust_level not in ("full", "ca", "user"):
            raise ValueError(f"无效的信任级别: {trust_level}")

        self._keys[key.key_id] = {
            "key": key,
            "signer": signer,
            "trust_level": trust_level,
            "signed_by": signed_by,
        }
        self._save()

    def remove_key(self, key_id: str) -> None:
        """移除受信任的密钥"""
        if key_id in self._keys:
            del self._keys[key_id]
            self._save()

    def is_trusted(self, key_id: str) -> tuple[bool, str]:
        """检查密钥是否受信任

        Returns:
            (trusted, trust_level) — trusted=False 时 trust_level 为空字符串
        """
        entry = self._keys.get(key_id)
        if entry is None:
            return False, ""
        return True, entry["trust_level"]

    def get_key(self, key_id: str) -> Optional[SigningKey]:
        """获取受信任的密钥"""
        entry = self._keys.get(key_id)
        if entry is None:
            return None
        return entry["key"]

    def list_keys(self) -> list[dict]:
        """列出所有受信任的密钥"""
        result = []
        for key_id, entry in self._keys.items():
            result.append(
                {
                    "key_id": key_id,
                    "algorithm": entry["key"].algorithm,
                    "signer": entry["signer"],
                    "trust_level": entry["trust_level"],
                    "signed_by": entry.get("signed_by"),
                    "created_at": entry["key"].created_at,
                }
            )
        return result

    def verify_chain(self, key_id: str) -> list[dict]:
        """验证信任链 — 从 key_id 回溯到根信任锚

        Returns:
            信任链列表，从 key_id 开始到根信任锚
            每个元素: {"key_id": str, "signer": str, "trust_level": str, "signed_by": str|None}
        """
        chain = []
        visited = set()
        current_id = key_id

        while current_id and current_id not in visited:
            visited.add(current_id)
            entry = self._keys.get(current_id)
            if entry is None:
                # 密钥不在信任存储中，链断裂
                chain.append(
                    {
                        "key_id": current_id,
                        "signer": "",
                        "trust_level": "",
                        "signed_by": None,
                        "valid": False,
                        "reason": "密钥不在信任存储中",
                    }
                )
                break

            chain.append(
                {
                    "key_id": current_id,
                    "signer": entry["signer"],
                    "trust_level": entry["trust_level"],
                    "signed_by": entry.get("signed_by"),
                    "valid": True,
                    "reason": "",
                }
            )

            # full 级别的密钥是根信任锚，链终止
            if entry["trust_level"] == "full":
                break

            # 向上追溯
            current_id = entry.get("signed_by")

        return chain

    def export_store(self) -> dict:
        """导出信任存储为字典"""
        return {
            "version": "1",
            "keys": [
                {
                    "key": entry["key"].to_dict(),
                    "signer": entry["signer"],
                    "trust_level": entry["trust_level"],
                    "signed_by": entry.get("signed_by"),
                }
                for entry in self._keys.values()
            ],
        }

    def import_store(self, data: dict) -> None:
        """从字典导入信任存储（合并）"""
        for entry in data.get("keys", []):
            key_data = entry.get("key", {})
            key = SigningKey.from_dict(key_data)
            if key.key_id not in self._keys:
                self._keys[key.key_id] = {
                    "key": key,
                    "signer": entry.get("signer", ""),
                    "trust_level": entry.get("trust_level", "user"),
                    "signed_by": entry.get("signed_by"),
                }
        self._save()
