"""签名密钥与 Ed25519 支持

核心类：
- SigningKey: 签名密钥（公钥部分）
- CodeSignature: 代码签名

辅助：
- _HAS_CRYPTOGRAPHY: Ed25519 可用性标志
- _ed25519_available(): 检查 Ed25519 是否可用
"""

from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass, asdict


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
