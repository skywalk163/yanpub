"""v0.10.0 功能测试 — LSP 代码签名（签名验证、信任链、安全审计）"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest


# ============================================================
# 1. SigningKey 测试
# ============================================================


class TestSigningKey:
    """签名密钥"""

    def test_generate_hmac(self):
        """生成 HMAC-SHA256 密钥对"""
        from yanpub.core.signing import SigningKey

        key, priv = SigningKey.generate("hmac-sha256")
        assert key.algorithm == "hmac-sha256"
        assert len(key.key_id) == 8
        assert key.public_key  # non-empty
        assert priv  # non-empty private key
        assert key.created_at > 0

    def test_generate_default(self):
        """默认算法生成密钥"""
        from yanpub.core.signing import SigningKey

        key, priv = SigningKey.generate()
        assert key.algorithm in ("ed25519", "hmac-sha256")
        assert len(key.key_id) == 8

    def test_to_dict_from_dict(self):
        """密钥序列化/反序列化"""
        from yanpub.core.signing import SigningKey

        key, _ = SigningKey.generate("hmac-sha256")
        d = key.to_dict()
        key2 = SigningKey.from_dict(d)
        assert key2.key_id == key.key_id
        assert key2.algorithm == key.algorithm
        assert key2.public_key == key.public_key

    def test_key_id_deterministic(self):
        """同一密钥对的 key_id 是确定的"""
        from yanpub.core.signing import SigningKey

        key, _ = SigningKey.generate("hmac-sha256")
        # 再次从相同数据构造应得到相同 key_id
        d = key.to_dict()
        key2 = SigningKey.from_dict(d)
        assert key2.key_id == key.key_id

    def test_different_keys_have_different_ids(self):
        """不同密钥的 ID 不同"""
        from yanpub.core.signing import SigningKey

        key1, _ = SigningKey.generate("hmac-sha256")
        key2, _ = SigningKey.generate("hmac-sha256")
        assert key1.key_id != key2.key_id


# ============================================================
# 2. CodeSignature 测试
# ============================================================


class TestCodeSignature:
    """代码签名"""

    def test_to_dict_from_dict(self):
        """签名序列化/反序列化"""
        from yanpub.core.signing import CodeSignature

        sig = CodeSignature(
            signer="alice",
            key_id="abcd1234",
            algorithm="hmac-sha256",
            signature="base64sig==",
            timestamp=1000.0,
            content_hash="sha256hash",
        )
        d = sig.to_dict()
        sig2 = CodeSignature.from_dict(d)
        assert sig2.signer == "alice"
        assert sig2.key_id == "abcd1234"
        assert sig2.algorithm == "hmac-sha256"
        assert sig2.signature == "base64sig=="
        assert sig2.content_hash == "sha256hash"


# ============================================================
# 3. TrustStore 测试
# ============================================================


class TestTrustStore:
    """信任存储"""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def store(self, tmpdir):
        from yanpub.core.signing import TrustStore
        return TrustStore(store_dir=tmpdir / "trust")

    @pytest.fixture
    def key(self):
        from yanpub.core.signing import SigningKey
        return SigningKey.generate("hmac-sha256")[0]

    def test_add_trusted_key(self, store, key):
        """添加受信任的密钥"""
        store.add_trusted_key(key, "alice", "full")
        trusted, level = store.is_trusted(key.key_id)
        assert trusted
        assert level == "full"

    def test_is_trusted_unknown(self, store):
        """查询未知密钥"""
        trusted, level = store.is_trusted("unknown")
        assert not trusted
        assert level == ""

    def test_remove_key(self, store, key):
        """移除密钥"""
        store.add_trusted_key(key, "alice", "full")
        store.remove_key(key.key_id)
        trusted, _ = store.is_trusted(key.key_id)
        assert not trusted

    def test_list_keys(self, store, key):
        """列出密钥"""
        store.add_trusted_key(key, "alice", "full")
        keys = store.list_keys()
        assert len(keys) == 1
        assert keys[0]["key_id"] == key.key_id
        assert keys[0]["signer"] == "alice"

    def test_trust_levels(self, store):
        """不同信任级别"""
        from yanpub.core.signing import SigningKey

        key_full, _ = SigningKey.generate("hmac-sha256")
        key_ca, _ = SigningKey.generate("hmac-sha256")
        key_user, _ = SigningKey.generate("hmac-sha256")

        store.add_trusted_key(key_full, "root", "full")
        store.add_trusted_key(key_ca, "ca", "ca")
        store.add_trusted_key(key_user, "user", "user")

        _, level_full = store.is_trusted(key_full.key_id)
        _, level_ca = store.is_trusted(key_ca.key_id)
        _, level_user = store.is_trusted(key_user.key_id)

        assert level_full == "full"
        assert level_ca == "ca"
        assert level_user == "user"

    def test_verify_chain_root(self, store, key):
        """根信任锚的信任链"""
        store.add_trusted_key(key, "root", "full")
        chain = store.verify_chain(key.key_id)
        assert len(chain) == 1
        assert chain[0]["valid"]
        assert chain[0]["trust_level"] == "full"

    def test_verify_chain_ca_to_root(self, store):
        """CA → 根信任链"""
        from yanpub.core.signing import SigningKey

        root_key, _ = SigningKey.generate("hmac-sha256")
        ca_key, _ = SigningKey.generate("hmac-sha256")

        store.add_trusted_key(root_key, "root", "full")
        store.add_trusted_key(ca_key, "ca", "ca", signed_by=root_key.key_id)

        chain = store.verify_chain(ca_key.key_id)
        assert len(chain) == 2
        assert chain[0]["key_id"] == ca_key.key_id
        assert chain[1]["key_id"] == root_key.key_id

    def test_verify_chain_broken(self, store):
        """断裂的信任链"""
        from yanpub.core.signing import SigningKey

        user_key, _ = SigningKey.generate("hmac-sha256")
        store.add_trusted_key(user_key, "user", "user", signed_by="missing_key")

        chain = store.verify_chain(user_key.key_id)
        assert len(chain) == 2
        assert chain[0]["valid"]
        assert not chain[1]["valid"]

    def test_export_import(self, store, key):
        """导出/导入信任存储"""
        store.add_trusted_key(key, "alice", "full")
        exported = store.export_store()

        from yanpub.core.signing import TrustStore
        store2 = TrustStore(store_dir=store.store_dir.parent / "trust2")
        store2.import_store(exported)
        trusted, _ = store2.is_trusted(key.key_id)
        assert trusted

    def test_invalid_trust_level(self, store, key):
        """无效的信任级别"""
        with pytest.raises(ValueError):
            store.add_trusted_key(key, "alice", "invalid")

    def test_persistence(self, tmpdir, key):
        """信任存储持久化"""
        from yanpub.core.signing import TrustStore

        store1 = TrustStore(store_dir=tmpdir / "trust")
        store1.add_trusted_key(key, "alice", "full")

        # 重新加载
        store2 = TrustStore(store_dir=tmpdir / "trust")
        trusted, level = store2.is_trusted(key.key_id)
        assert trusted
        assert level == "full"


# ============================================================
# 4. CodeSigner 测试
# ============================================================


class TestCodeSigner:
    """代码签名器"""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def signer_with_key(self, tmpdir):
        """创建签名器和密钥"""
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "alice", "full")
        signer = CodeSigner(trust_store=store)
        return signer, key, priv

    def test_compute_hash(self):
        """计算内容哈希"""
        from yanpub.core.signing import CodeSigner

        h1 = CodeSigner.compute_hash("hello")
        h2 = CodeSigner.compute_hash("hello")
        h3 = CodeSigner.compute_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # SHA-256 hex length

    def test_sign_and_verify(self, signer_with_key):
        """签名和验证"""
        from yanpub.core.signing import CodeSigner

        signer, key, priv = signer_with_key
        sig = signer.sign("hello world", priv, "alice", algorithm=key.algorithm)
        assert sig.key_id == key.key_id
        assert sig.algorithm == key.algorithm
        assert sig.content_hash == CodeSigner.compute_hash("hello world")

        valid, msg = signer.verify("hello world", sig)
        assert valid

    def test_verify_tampered_content(self, signer_with_key):
        """检测内容篡改"""
        signer, key, priv = signer_with_key
        sig = signer.sign("hello world", priv, "alice", algorithm=key.algorithm)
        valid, msg = signer.verify("hello modified", sig)
        assert not valid
        assert "篡改" in msg

    def test_verify_untrusted_key(self, signer_with_key):
        """验证不受信任的密钥"""
        from yanpub.core.signing import CodeSignature, CodeSigner

        signer, key, priv = signer_with_key
        sig = CodeSignature(
            signer="unknown", key_id="deadbeef", algorithm="hmac-sha256",
            signature="AAAA", timestamp=0,
            content_hash=CodeSigner.compute_hash("hello"),
        )
        valid, msg = signer.verify("hello", sig)
        assert not valid
        # 无效签名或不受信任（密钥不在信任存储中时签名验证先失败）
        assert "无效" in msg or "不受信任" in msg

    def test_verify_invalid_signature(self, signer_with_key):
        """验证无效签名"""
        from yanpub.core.signing import CodeSignature, CodeSigner

        signer, key, priv = signer_with_key
        sig = CodeSignature(
            signer="alice", key_id=key.key_id, algorithm="hmac-sha256",
            signature="invalidsignature==", timestamp=0,
            content_hash=CodeSigner.compute_hash("hello"),
        )
        valid, msg = signer.verify("hello", sig)
        assert not valid
        assert "签名无效" in msg

    def test_sign_file_and_verify(self, signer_with_key, tmpdir):
        """文件签名和验证"""
        signer, key, priv = signer_with_key

        test_file = tmpdir / "test.duan"
        test_file.write_text("设甲为三", encoding="utf-8")

        signer.sign_file(str(test_file), priv, "alice", algorithm=key.algorithm)
        sig_file = test_file.with_suffix(test_file.suffix + ".yanpub-sig")
        assert sig_file.exists()

        valid, msg = signer.verify_file(str(test_file))
        assert valid

    def test_verify_file_tampered(self, signer_with_key, tmpdir):
        """文件篡改检测"""
        signer, key, priv = signer_with_key

        test_file = tmpdir / "test.duan"
        test_file.write_text("设甲为三", encoding="utf-8")
        signer.sign_file(str(test_file), priv, "alice", algorithm=key.algorithm)

        test_file.write_text("设甲为四", encoding="utf-8")
        valid, msg = signer.verify_file(str(test_file))
        assert not valid
        assert "篡改" in msg

    def test_verify_file_no_signature(self, signer_with_key, tmpdir):
        """验证无签名文件"""
        signer, key, priv = signer_with_key

        test_file = tmpdir / "nosig.duan"
        test_file.write_text("hello", encoding="utf-8")

        valid, msg = signer.verify_file(str(test_file))
        assert not valid
        assert "签名文件" in msg


# ============================================================
# 5. AuditLog 测试
# ============================================================


class TestAuditLog:
    """安全审计日志"""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def audit_log(self, tmpdir):
        from yanpub.core.audit import AuditLog
        return AuditLog(log_dir=tmpdir / "audit")

    def test_log_entry(self, audit_log):
        """记录审计条目"""
        from yanpub.core.audit import AuditEntry

        entry = AuditEntry(action="sign", signer="alice", key_id="abcd1234")
        audit_log.log(entry)

        entries = audit_log.query()
        assert len(entries) == 1
        assert entries[0].action == "sign"

    def test_query_by_action(self, audit_log):
        """按操作类型查询"""
        from yanpub.core.audit import AuditEntry

        audit_log.log(AuditEntry(action="sign", signer="alice", key_id="a"))
        audit_log.log(AuditEntry(action="verify", signer="alice", key_id="a"))
        audit_log.log(AuditEntry(action="verify_fail", signer="bob", key_id="b"))

        sign_entries = audit_log.query(action="sign")
        assert len(sign_entries) == 1

    def test_query_by_signer(self, audit_log):
        """按签名者查询"""
        from yanpub.core.audit import AuditEntry

        audit_log.log(AuditEntry(action="sign", signer="alice", key_id="a"))
        audit_log.log(AuditEntry(action="sign", signer="bob", key_id="b"))

        alice_entries = audit_log.query(signer="alice")
        assert len(alice_entries) == 1
        assert alice_entries[0].signer == "alice"

    def test_get_stats(self, audit_log):
        """获取统计信息"""
        from yanpub.core.audit import AuditEntry

        audit_log.log(AuditEntry(action="sign", signer="alice", key_id="a"))
        audit_log.log(AuditEntry(action="verify", signer="alice", key_id="a"))
        audit_log.log(AuditEntry(action="verify_fail", signer="bob", key_id="b"))

        stats = audit_log.get_stats()
        assert stats["total"] == 3
        assert stats["by_action"]["sign"] == 1
        assert stats["by_action"]["verify"] == 1
        assert stats["by_action"]["verify_fail"] == 1
        assert stats["by_signer"]["alice"] == 2
        assert stats["by_signer"]["bob"] == 1

    def test_export_json(self, audit_log):
        """导出 JSON 格式"""
        from yanpub.core.audit import AuditEntry

        audit_log.log(AuditEntry(action="sign", signer="alice", key_id="a"))
        exported = audit_log.export(format="json")
        data = json.loads(exported)
        assert len(data) == 1

    def test_export_csv(self, audit_log):
        """导出 CSV 格式"""
        from yanpub.core.audit import AuditEntry

        audit_log.log(AuditEntry(action="sign", signer="alice", key_id="a"))
        exported = audit_log.export(format="csv")
        assert "timestamp" in exported
        assert "sign" in exported

    def test_empty_stats(self, audit_log):
        """空日志统计"""
        stats = audit_log.get_stats()
        assert stats["total"] == 0
        assert stats["by_action"] == {}
        assert stats["first_entry"] is None

    def test_entry_serialization(self):
        """审计条目序列化"""
        from yanpub.core.audit import AuditEntry

        entry = AuditEntry(action="sign", signer="alice", key_id="abcd1234", details={"file": "test.duan"})
        d = entry.to_dict()
        entry2 = AuditEntry.from_dict(d)
        assert entry2.action == entry.action
        assert entry2.signer == entry.signer
        assert entry2.details == entry.details


# ============================================================
# 6. SignedPackageRegistry 测试
# ============================================================


class TestSignedPackageRegistry:
    """签名包注册中心"""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def signed_registry(self, tmpdir):
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner
        from yanpub.pkg.registry import PackageRegistry
        from yanpub.pkg.signed_registry import SignedPackageRegistry

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "publisher", "full")
        signer = CodeSigner(trust_store=store)
        registry = PackageRegistry(registry_dir=tmpdir / "registry")

        return SignedPackageRegistry(registry=registry, signer=signer), key, priv

    def test_publish_signed(self, signed_registry):
        """发布签名包"""
        reg, key, priv = signed_registry
        result = reg.publish_signed(
            {"name": "duan:utils", "lang": "duan", "package": "utils", "version": "1.0.0"},
            priv, "publisher", algorithm=key.algorithm,
        )
        assert result["package"].name == "duan:utils"
        assert result["signature"].key_id == key.key_id

    def test_install_verified(self, signed_registry):
        """安装并验证签名包"""
        reg, key, priv = signed_registry
        reg.publish_signed(
            {"name": "duan:utils", "lang": "duan", "package": "utils", "version": "1.0.0"},
            priv, "publisher", algorithm=key.algorithm,
        )
        pkg_dict, (valid, msg) = reg.install_verified("duan:utils")
        assert valid
        assert pkg_dict["name"] == "duan:utils"

    def test_verify_unsigned_package(self, signed_registry):
        """验证未签名包"""
        from yanpub.pkg.registry import PackageInfo

        reg, key, priv = signed_registry
        unsigned_pkg = PackageInfo(name="duan:unsigned", lang="duan", package="unsigned", version="0.1.0")
        reg.registry.add(unsigned_pkg)

        valid, msg = reg.verify_package("duan:unsigned")
        assert not valid
        assert "签名" in msg

    def test_verify_nonexistent_package(self, signed_registry):
        """验证不存在的包"""
        reg, key, priv = signed_registry
        valid, msg = reg.verify_package("duan:nonexistent")
        assert not valid


# ============================================================
# 7. LSP 签名诊断测试
# ============================================================


class TestLSPSignatureDiagnostics:
    """LSP 签名诊断"""

    def test_import(self):
        """模块可导入"""
        from yanpub.core.signing import CodeSigner
        from yanpub.core.audit import AuditLog
        assert CodeSigner is not None
        assert AuditLog is not None

    def test_core_init_exports(self):
        """核心模块导出签名类"""
        from yanpub.core import SigningKey, CodeSignature, TrustStore, CodeSigner
        from yanpub.core import AuditEntry, AuditLog
        assert SigningKey is not None
        assert CodeSignature is not None
        assert TrustStore is not None
        assert CodeSigner is not None
        assert AuditEntry is not None
        assert AuditLog is not None


# ============================================================
# 8. 边界条件和集成测试
# ============================================================


class TestEdgeCases:
    """边界条件"""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    def test_empty_content_signing(self, tmpdir):
        """签名空内容"""
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "alice", "full")
        signer = CodeSigner(trust_store=store)

        sig = signer.sign("", priv, "alice", algorithm=key.algorithm)
        valid, msg = signer.verify("", sig)
        assert valid

    def test_unicode_content_signing(self, tmpdir):
        """签名 Unicode 内容"""
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "alice", "full")
        signer = CodeSigner(trust_store=store)

        content = "设甲为三。段落 求和(甲, 乙)。返回 甲加乙。结束。"
        sig = signer.sign(content, priv, "alice", algorithm=key.algorithm)
        valid, msg = signer.verify(content, sig)
        assert valid

    def test_large_content_signing(self, tmpdir):
        """签名大内容"""
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "alice", "full")
        signer = CodeSigner(trust_store=store)

        content = "设甲为三。\n" * 10000
        sig = signer.sign(content, priv, "alice", algorithm=key.algorithm)
        valid, msg = signer.verify(content, sig)
        assert valid

    def test_signature_file_format(self, tmpdir):
        """签名文件格式验证"""
        from yanpub.core.signing import SigningKey, TrustStore, CodeSigner

        key, priv = SigningKey.generate("hmac-sha256")
        store = TrustStore(store_dir=tmpdir / "trust")
        store.add_trusted_key(key, "alice", "full")
        signer = CodeSigner(trust_store=store)

        test_file = tmpdir / "test.duan"
        test_file.write_text("hello", encoding="utf-8")
        signer.sign_file(str(test_file), priv, "alice", algorithm=key.algorithm)

        sig_file = test_file.with_suffix(test_file.suffix + ".yanpub-sig")
        sig_data = json.loads(sig_file.read_text(encoding="utf-8"))

        # 验证签名文件包含必要字段
        assert "signer" in sig_data
        assert "key_id" in sig_data
        assert "algorithm" in sig_data
        assert "signature" in sig_data
        assert "timestamp" in sig_data
        assert "content_hash" in sig_data

    def test_trust_store_concurrent_import(self, tmpdir):
        """信任存储合并导入"""
        from yanpub.core.signing import SigningKey, TrustStore

        key1, _ = SigningKey.generate("hmac-sha256")
        key2, _ = SigningKey.generate("hmac-sha256")

        store1 = TrustStore(store_dir=tmpdir / "trust1")
        store1.add_trusted_key(key1, "alice", "full")

        store2 = TrustStore(store_dir=tmpdir / "trust2")
        store2.add_trusted_key(key2, "bob", "user")

        # 合并
        exported = store2.export_store()
        store1.import_store(exported)

        trusted1, _ = store1.is_trusted(key1.key_id)
        trusted2, _ = store1.is_trusted(key2.key_id)
        assert trusted1
        assert trusted2

    def test_audit_log_persistence(self, tmpdir):
        """审计日志持久化"""
        from yanpub.core.audit import AuditLog, AuditEntry

        log1 = AuditLog(log_dir=tmpdir / "audit")
        log1.log(AuditEntry(action="sign", signer="alice", key_id="abcd1234"))

        log2 = AuditLog(log_dir=tmpdir / "audit")
        entries = log2.query()
        assert len(entries) == 1
        assert entries[0].action == "sign"
