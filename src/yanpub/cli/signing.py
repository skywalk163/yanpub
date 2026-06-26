"""签名、信任和审计命令"""

from __future__ import annotations

import sys
import time

import click

from yanpub.cli import main

# ============================================================
# 代码签名 CLI 命令
# ============================================================

@main.command("sign")
@click.argument("file", type=click.Path(exists=True))
@click.option("--key", "-k", required=True, help="私钥文件路径")
@click.option("--signer", "-s", required=True, help="签名者标识")
@click.option(
    "--algorithm", "-a", type=click.Choice(["ed25519", "hmac-sha256"]), default="hmac-sha256"
)
def sign_file(file: str, key: str, signer: str, algorithm: str):
    """对源代码文件进行签名"""
    from pathlib import Path as P
    from yanpub.core.signing import CodeSigner

    # 读取私钥
    key_path = P(key)
    if not key_path.exists():
        click.echo(f"私钥文件不存在: {key}", err=True)
        sys.exit(1)
    private_key = key_path.read_text(encoding="utf-8").strip()

    # 签名
    code_signer = CodeSigner()
    try:
        signature = code_signer.sign_file(file, private_key, signer, algorithm=algorithm)
    except Exception as e:
        click.echo(f"签名失败: {e}", err=True)
        sys.exit(1)

    sig_path = P(file).with_suffix(P(file).suffix + ".yanpub-sig")
    click.echo("[OK] 签名成功")
    click.echo(f"  签名者: {signature.signer}")
    click.echo(f"  密钥ID: {signature.key_id}")
    click.echo(f"  算法:   {signature.algorithm}")
    click.echo(f"  哈希:   {signature.content_hash[:16]}...")
    click.echo(f"  签名文件: {sig_path}")

@main.command("verify")
@click.argument("file", type=click.Path(exists=True))
def verify_file(file: str):
    """验证源代码文件签名"""
    from yanpub.core.signing import CodeSigner

    code_signer = CodeSigner()
    valid, message = code_signer.verify_file(file)

    if valid:
        click.echo(f"[OK] {message}")
    else:
        click.echo(f"[FAIL] {message}", err=True)
        sys.exit(1)

@click.group("trust")
def trust_group():
    """信任密钥管理"""
    pass

@trust_group.command("add")
@click.argument("key_file", type=click.Path(exists=True))
@click.option("--signer", "-s", required=True)
@click.option("--level", type=click.Choice(["full", "ca", "user"]), default="user")
def trust_add(key_file: str, signer: str, level: str):
    """添加受信任的密钥"""
    import json
    from pathlib import Path as P
    from yanpub.core.signing import SigningKey, TrustStore

    # 读取密钥文件（JSON 格式）
    key_path = P(key_file)
    try:
        key_data = json.loads(key_path.read_text(encoding="utf-8"))
        key = SigningKey.from_dict(key_data)
    except Exception as e:
        click.echo(f"密钥文件格式错误: {e}", err=True)
        sys.exit(1)

    store = TrustStore()
    store.add_trusted_key(key, signer, level)
    click.echo("[OK] 已添加受信任密钥")
    click.echo(f"  密钥ID: {key.key_id}")
    click.echo(f"  算法:   {key.algorithm}")
    click.echo(f"  签名者: {signer}")
    click.echo(f"  信任级别: {level}")

@trust_group.command("list")
def trust_list():
    """列出受信任的密钥"""
    from yanpub.core.signing import TrustStore

    store = TrustStore()
    keys = store.list_keys()

    if not keys:
        click.echo("没有受信任的密钥。")
        return

    click.echo(f"受信任密钥 ({len(keys)} 个)：\n")
    for k in keys:
        click.echo(f"  {k['key_id']:10s} {k['algorithm']:14s} {k['signer']:20s} {k['trust_level']}")

@trust_group.command("remove")
@click.argument("key_id")
def trust_remove(key_id: str):
    """移除受信任的密钥"""
    from yanpub.core.signing import TrustStore

    store = TrustStore()
    trusted, level = store.is_trusted(key_id)
    if not trusted:
        click.echo(f"未找到密钥: {key_id}", err=True)
        sys.exit(1)

    store.remove_key(key_id)
    click.echo(f"[OK] 已移除密钥: {key_id}")

@main.command("keygen")
@click.option(
    "--algorithm", "-a", type=click.Choice(["ed25519", "hmac-sha256"]), default="hmac-sha256"
)
@click.option("--output", "-o", default=None, help="输出目录")
def generate_key(algorithm: str, output: str):
    """生成签名密钥对"""
    import json
    from pathlib import Path as P
    from yanpub.core.signing import SigningKey

    key, private_key = SigningKey.generate(algorithm)

    # 确定输出目录
    out_dir = P(output) if output else P.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 写入公钥文件
    pub_path = out_dir / f"yanpub_{key.key_id}.pub"
    pub_path.write_text(
        json.dumps(key.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 写入私钥文件
    priv_path = out_dir / f"yanpub_{key.key_id}.key"
    priv_path.write_text(private_key, encoding="utf-8")

    actual_algo = key.algorithm
    click.echo("[OK] 密钥对已生成")
    click.echo(f"  密钥ID: {key.key_id}")
    click.echo(f"  算法:   {actual_algo}")
    if actual_algo != algorithm:
        click.echo(f"  注意: Ed25519 不可用，已降级到 {actual_algo}")
    click.echo(f"  公钥:   {pub_path}")
    click.echo(f"  私钥:   {priv_path}")
    click.echo()
    click.echo("  请妥善保管私钥文件，不要提交到版本控制！")

@main.command("audit")
@click.option("--action", type=click.Choice(["list", "stats", "export"]), default="list")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
def audit_log(action: str, fmt: str):
    """查看安全审计日志"""
    from yanpub.core.audit import AuditLog

    log = AuditLog()

    if action == "list":
        entries = log.query()
        if not entries:
            click.echo("没有审计记录。")
            return

        click.echo(f"审计记录 ({len(entries)} 条)：\n")
        for entry in entries:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.timestamp))
            click.echo(f"  [{ts}] {entry.action:14s} signer={entry.signer} key={entry.key_id}")
            if entry.details:
                for k, v in entry.details.items():
                    click.echo(f"    {k}: {v}")

    elif action == "stats":
        stats = log.get_stats()
        click.echo("审计统计：")
        click.echo(f"  总记录数: {stats['total']}")
        if stats["by_action"]:
            click.echo("  按操作类型:")
            for act, count in stats["by_action"].items():
                click.echo(f"    {act}: {count}")
        if stats["by_signer"]:
            click.echo("  按签名者:")
            for signer, count in stats["by_signer"].items():
                click.echo(f"    {signer}: {count}")

    elif action == "export":
        content = log.export(format=fmt)
        click.echo(content)

main.add_command(trust_group)
