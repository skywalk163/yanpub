"""代码签名引擎 — 签名验证、信任链和安全审计

核心类：
- SigningKey: 签名密钥（公钥）
- CodeSignature: 代码签名
- TrustStore: 信任存储（管理受信任密钥）
- CodeSigner: 代码签名器（签名/验证）
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ---- 检测 Ed25519 支持 ----

_HAS_CRYPTOGRAPHY = False
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        PrivateFormat,
        NoEncryption,
    )

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


def _ed25519_available() -> bool:
    """检查 Ed25519 是否可用"""
    return _HAS_CRYPTOGRAPHY


# ============================================================
# SigningKey
# ============================================================


@dataclass
class SigningKey:
    """签名密钥（公钥部分）"""

    key_id: str  # 密钥标识（指纹前8位）
    algorithm: str  # "ed25519" | "hmac-sha256"
    public_key: str  # Base64 编码的公钥
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()

    @staticmethod
    def generate(algorithm: str = "ed25519") -> tuple[SigningKey, str]:
        """生成密钥对，返回 (SigningKey, 私钥 Base64)

        Args:
            algorithm: "ed25519" 或 "hmac-sha256"

        Returns:
            (公钥 SigningKey, 私钥 Base64 字符串)
        """
        if algorithm == "ed25519" and _ed25519_available():
            private_key = Ed25519PrivateKey.generate()
            pub_bytes = private_key.public_key().public_bytes(
                Encoding.Raw,
                PublicFormat.Raw,
            )
            priv_bytes = private_key.private_bytes(
                Encoding.Raw,
                PrivateFormat.Raw,
                NoEncryption(),
            )
            pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
            priv_b64 = base64.b64encode(priv_bytes).decode("ascii")
        else:
            # 降级到 HMAC-SHA256（对称密钥）
            algorithm = "hmac-sha256"
            import secrets

            priv_bytes = secrets.token_bytes(32)
            # 对称密钥：public_key = private_key（HMAC 验证需要相同密钥）
            pub_bytes = priv_bytes
            pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
            priv_b64 = base64.b64encode(priv_bytes).decode("ascii")

        # key_id = 公钥指纹前8位
        fingerprint = hashlib.sha256(pub_bytes).hexdigest()
        key_id = fingerprint[:8]

        signing_key = SigningKey(
            key_id=key_id,
            algorithm=algorithm,
            public_key=pub_b64,
        )
        return signing_key, priv_b64

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SigningKey:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ============================================================
# CodeSignature
# ============================================================


@dataclass
class CodeSignature:
    """代码签名"""

    signer: str  # 签名者标识
    key_id: str  # 使用的密钥 ID
    algorithm: str  # 签名算法
    signature: str  # Base64 编码的签名值
    timestamp: float  # 签名时间
    content_hash: str  # 签名的内容哈希（SHA-256）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> CodeSignature:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ============================================================
# TrustStore
# ============================================================


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


# ============================================================
# CodeSigner
# ============================================================


class CodeSigner:
    """代码签名器 — 对源代码文件进行签名和验证"""

    def __init__(self, trust_store: TrustStore | None = None):
        self.trust_store = trust_store if trust_store is not None else TrustStore()

    @staticmethod
    def compute_hash(content: str) -> str:
        """计算内容哈希（SHA-256）"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def sign(
        self,
        content: str,
        private_key: str,
        signer: str,
        algorithm: str = "ed25519",
    ) -> CodeSignature:
        """对内容进行签名

        Args:
            content: 要签名的内容
            private_key: Base64 编码的私钥
            signer: 签名者标识
            algorithm: 签名算法

        Returns:
            CodeSignature 签名对象
        """
        content_hash = self.compute_hash(content)

        # 确定实际可用的算法
        # 如果请求 ed25519 但不可用，降级到 hmac-sha256
        actual_algorithm = algorithm
        if algorithm == "ed25519" and not _ed25519_available():
            actual_algorithm = "hmac-sha256"

        if actual_algorithm == "ed25519":
            sig_bytes = self._sign_ed25519(content_hash, private_key)
        else:
            actual_algorithm = "hmac-sha256"
            sig_bytes = self._sign_hmac(content_hash, private_key)

        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

        # 从私钥推导 key_id（与 SigningKey.generate 保持一致）
        priv_bytes = base64.b64decode(private_key)
        if actual_algorithm == "ed25519" and _ed25519_available():
            priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
            pub_bytes = priv_key.public_key().public_bytes(
                Encoding.Raw,
                PublicFormat.Raw,
            )
        else:
            # HMAC-SHA256 对称密钥：public_key = private_key
            pub_bytes = priv_bytes
        key_id = hashlib.sha256(pub_bytes).hexdigest()[:8]

        return CodeSignature(
            signer=signer,
            key_id=key_id,
            algorithm=actual_algorithm,
            signature=sig_b64,
            timestamp=time.time(),
            content_hash=content_hash,
        )

    def verify(self, content: str, signature: CodeSignature) -> tuple[bool, str]:
        """验证签名

        Returns:
            (valid, message)
            - valid=True: 签名有效且密钥受信任
            - valid=False: 签名无效/密钥不受信任/内容被篡改
        """
        # 1. 检查内容哈希
        current_hash = self.compute_hash(content)
        if current_hash != signature.content_hash:
            return False, "内容被篡改"

        # 2. 验证签名
        sig_bytes = base64.b64decode(signature.signature)
        if signature.algorithm == "ed25519" and _ed25519_available():
            sig_valid = self._verify_ed25519(
                signature.content_hash,
                sig_bytes,
                signature.key_id,
            )
        else:
            sig_valid = self._verify_hmac(
                signature.content_hash,
                sig_bytes,
                signature.key_id,
            )

        if not sig_valid:
            return False, "签名无效"

        # 3. 检查密钥是否受信任
        trusted, trust_level = self.trust_store.is_trusted(signature.key_id)
        if not trusted:
            return False, "密钥不受信任"

        return True, f"签名有效（信任级别: {trust_level}）"

    def sign_file(
        self,
        file_path: str,
        private_key: str,
        signer: str,
        algorithm: str = "ed25519",
    ) -> CodeSignature:
        """对文件进行签名，并将签名写入 .yanpub-sig 伴随文件

        Args:
            file_path: 源代码文件路径
            private_key: Base64 编码的私钥
            signer: 签名者标识
            algorithm: 签名算法（应与密钥生成时使用的算法一致）
        """
        content = Path(file_path).read_text(encoding="utf-8")
        sig = self.sign(content, private_key, signer, algorithm=algorithm)

        # 写入伴随签名文件
        sig_path = Path(file_path).with_suffix(Path(file_path).suffix + ".yanpub-sig")
        sig_path.write_text(
            json.dumps(sig.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 记录审计日志
        self._audit_log(
            "sign",
            signer,
            sig.key_id,
            {
                "file": str(file_path),
                "algorithm": sig.algorithm,
                "content_hash": sig.content_hash,
            },
        )

        return sig

    def verify_file(self, file_path: str) -> tuple[bool, str]:
        """验证文件的签名

        Returns:
            (valid, message)
        """
        sig_path = Path(file_path).with_suffix(Path(file_path).suffix + ".yanpub-sig")

        if not sig_path.exists():
            return False, "未找到签名文件"

        # 读取签名
        try:
            sig_data = json.loads(sig_path.read_text(encoding="utf-8"))
            signature = CodeSignature.from_dict(sig_data)
        except (json.JSONDecodeError, KeyError) as e:
            return False, f"签名文件格式错误: {e}"

        # 读取内容
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            return False, f"无法读取文件: {e}"

        valid, message = self.verify(content, signature)

        # 记录审计日志
        action = "verify" if valid else "verify_fail"
        self._audit_log(
            action,
            signature.signer,
            signature.key_id,
            {
                "file": str(file_path),
                "result": message,
            },
        )

        return valid, message

    # ---- 内部签名/验证方法 ----

    @staticmethod
    def _sign_ed25519(content_hash: str, private_key_b64: str) -> bytes:
        """使用 Ed25519 签名"""
        priv_bytes = base64.b64decode(private_key_b64)
        private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
        return private_key.sign(content_hash.encode("utf-8"))

    @staticmethod
    def _sign_hmac(content_hash: str, private_key_b64: str) -> bytes:
        """使用 HMAC-SHA256 签名"""
        priv_bytes = base64.b64decode(private_key_b64)
        return hmac.new(
            priv_bytes,
            content_hash.encode("utf-8"),
            hashlib.sha256,
        ).digest()

    def _verify_ed25519(
        self,
        content_hash: str,
        sig_bytes: bytes,
        key_id: str,
    ) -> bool:
        """验证 Ed25519 签名"""
        key = self.trust_store.get_key(key_id)
        if key is None:
            return False

        try:
            pub_bytes = base64.b64decode(key.public_key)
            public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            public_key.verify(sig_bytes, content_hash.encode("utf-8"))
            return True
        except Exception:
            return False

    def _verify_hmac(
        self,
        content_hash: str,
        sig_bytes: bytes,
        key_id: str,
    ) -> bool:
        """验证 HMAC-SHA256 签名（对称密钥）"""
        key = self.trust_store.get_key(key_id)
        if key is None:
            return False

        # HMAC-SHA256 对称密钥：public_key = private_key
        sym_key = base64.b64decode(key.public_key)
        expected = hmac.new(
            sym_key,
            content_hash.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return hmac.compare_digest(sig_bytes, expected)

    # ---- 审计日志辅助 ----

    def _audit_log(
        self,
        action: str,
        signer: str,
        key_id: str,
        details: dict,
    ) -> None:
        """记录审计日志"""
        try:
            from yanpub.core.security.audit import AuditLog, AuditEntry

            log = AuditLog()
            entry = AuditEntry(
                action=action,
                signer=signer,
                key_id=key_id,
                details=details,
            )
            log.log(entry)
        except Exception:
            pass  # 审计日志失败不应阻塞签名操作
