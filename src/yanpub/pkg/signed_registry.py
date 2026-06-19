"""签名包注册中心 — 验证包的完整性和来源

在包管理器中集成代码签名验证，确保包的来源可信和内容未被篡改。
"""

from __future__ import annotations

import json

from yanpub.core.signing import CodeSigner, CodeSignature
from yanpub.pkg.registry import PackageRegistry, PackageInfo


class SignedPackageRegistry:
    """签名包注册中心 — 验证包的完整性和来源

    包装 PackageRegistry，在发布和安装时自动处理签名验证。
    """

    def __init__(
        self,
        registry: PackageRegistry | None = None,
        signer: CodeSigner | None = None,
    ):
        self.registry = registry if registry is not None else PackageRegistry()
        self.signer = signer if signer is not None else CodeSigner()

    def publish_signed(
        self,
        package_data: dict,
        private_key: str,
        signer_name: str,
        algorithm: str = "ed25519",
    ) -> dict:
        """发布签名包

        Args:
            package_data: 包数据（至少包含 name, lang, version 等字段）
            private_key: Base64 编码的私钥
            signer_name: 签名者标识
            algorithm: 签名算法（应与密钥生成时使用的算法一致）

        Returns:
            {
                "package": PackageInfo,
                "signature": CodeSignature,
            }
        """
        # 创建包信息
        pkg = PackageInfo.from_dict(package_data)

        # 对包数据签名
        content = json.dumps(pkg.to_dict(), sort_keys=True, ensure_ascii=False)
        signature = self.signer.sign(content, private_key, signer_name, algorithm=algorithm)

        # 注册包
        self.registry.add(pkg)

        # 保存签名到注册中心目录
        sig_dir = self.registry.registry_dir / "signatures"
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig_file = sig_dir / f"{pkg.name.replace(':', '_')}.yanpub-sig"
        sig_file.write_text(
            json.dumps(signature.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "package": pkg,
            "signature": signature,
        }

    def install_verified(self, package_id: str) -> tuple[dict, tuple[bool, str]]:
        """安装并验证包签名

        Args:
            package_id: 包全名 (lang:package)

        Returns:
            (package_data_dict, (valid, message))
        """
        pkg = self.registry.get(package_id)
        if pkg is None:
            return {}, (False, f"未找到包: {package_id}")

        # 检查签名文件
        sig_dir = self.registry.registry_dir / "signatures"
        sig_file = sig_dir / f"{package_id.replace(':', '_')}.yanpub-sig"

        if not sig_file.exists():
            return pkg.to_dict(), (False, "包未签名")

        # 读取并验证签名
        try:
            sig_data = json.loads(sig_file.read_text(encoding="utf-8"))
            signature = CodeSignature.from_dict(sig_data)
        except (json.JSONDecodeError, KeyError) as e:
            return pkg.to_dict(), (False, f"签名文件格式错误: {e}")

        # 验证签名
        content = json.dumps(pkg.to_dict(), sort_keys=True, ensure_ascii=False)
        valid, message = self.signer.verify(content, signature)

        return pkg.to_dict(), (valid, message)

    def verify_package(self, package_id: str) -> tuple[bool, str]:
        """验证包签名

        Args:
            package_id: 包全名 (lang:package)

        Returns:
            (valid, message)
        """
        pkg = self.registry.get(package_id)
        if pkg is None:
            return False, f"未找到包: {package_id}"

        # 检查签名文件
        sig_dir = self.registry.registry_dir / "signatures"
        sig_file = sig_dir / f"{package_id.replace(':', '_')}.yanpub-sig"

        if not sig_file.exists():
            return False, "包未签名"

        try:
            sig_data = json.loads(sig_file.read_text(encoding="utf-8"))
            signature = CodeSignature.from_dict(sig_data)
        except (json.JSONDecodeError, KeyError) as e:
            return False, f"签名文件格式错误: {e}"

        content = json.dumps(pkg.to_dict(), sort_keys=True, ensure_ascii=False)
        return self.signer.verify(content, signature)
