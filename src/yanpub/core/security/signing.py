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
from pathlib import Path
from typing import Optional

from .keys import _HAS_CRYPTOGRAPHY, _ed25519_available, SigningKey, CodeSignature  # noqa: F401
from .trust_store import TrustStore  # noqa: F401


def __getattr__(name):
    _moved = {"_HAS_CRYPTOGRAPHY", "_ed25519_available", "SigningKey", "CodeSignature", "TrustStore"}
    if name in _moved:
        import importlib
        if name in {"_HAS_CRYPTOGRAPHY", "_ed25519_available", "SigningKey", "CodeSignature"}:
            mod = importlib.import_module(".keys", __name__)
        else:
            mod = importlib.import_module(".trust_store", __name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Re-import for internal use in CodeSigner
from .keys import _ed25519_available as _ed25519_avail, SigningKey as _SigningKey, CodeSignature as _CodeSignature  # noqa: F811, E402
from .trust_store import TrustStore as _TrustStore  # noqa: F811, E402

# Re-import Ed25519 symbols if available for CodeSigner internal use
if _HAS_CRYPTOGRAPHY:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (  # noqa: E402
        Encoding,
        PublicFormat,
    )


# ============================================================
# CodeSigner
# ============================================================


class CodeSigner:
    """代码签名器 — 对源代码文件进行签名和验证"""

    def __init__(self, trust_store: _TrustStore | None = None):
        self.trust_store = trust_store if trust_store is not None else _TrustStore()

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
    ) -> _CodeSignature:
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
        if algorithm == "ed25519" and not _ed25519_avail():
            actual_algorithm = "hmac-sha256"

        if actual_algorithm == "ed25519":
            sig_bytes = self._sign_ed25519(content_hash, private_key)
        else:
            actual_algorithm = "hmac-sha256"
            sig_bytes = self._sign_hmac(content_hash, private_key)

        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

        # 从私钥推导 key_id（与 SigningKey.generate 保持一致）
        priv_bytes = base64.b64decode(private_key)
        if actual_algorithm == "ed25519" and _ed25519_avail():
            priv_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
            pub_bytes = priv_key.public_key().public_bytes(
                Encoding.Raw,
                PublicFormat.Raw,
            )
        else:
            # HMAC-SHA256 对称密钥：public_key = private_key
            pub_bytes = priv_bytes
        key_id = hashlib.sha256(pub_bytes).hexdigest()[:8]

        return _CodeSignature(
            signer=signer,
            key_id=key_id,
            algorithm=actual_algorithm,
            signature=sig_b64,
            timestamp=time.time(),
            content_hash=content_hash,
        )

    def verify(self, content: str, signature: _CodeSignature) -> tuple[bool, str]:
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
        if signature.algorithm == "ed25519" and _ed25519_avail():
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
    ) -> _CodeSignature:
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
            signature = _CodeSignature.from_dict(sig_data)
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
