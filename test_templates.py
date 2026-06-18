"""验证 Yan 语言模板是否能被 atomyan 解析和执行"""

import subprocess
import sys
import os
import tempfile
from pathlib import Path

# atomyan CLI
YAN_CLI = r"G:\atomcode\atomyan\yan.py"

# 模板目录
TEMPLATES_DIR = Path(__file__).parent / "src" / "yanpub" / "playground" / "templates" / "yan"

def test_tokenize(name: str, code: str) -> bool:
    """测试分词（写入临时文件）"""
    with tempfile.NamedTemporaryFile(suffix=".yan", mode="w", encoding="utf-8", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, YAN_CLI, "--tokens", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"  ❌ 分词失败: {result.stderr[:200]}")
            return False
        token_count = len(result.stdout.strip().split('\n'))
        print(f"  ✅ 分词成功 ({token_count} tokens)")
        return True
    finally:
        os.unlink(tmp_path)

def test_parse(name: str, code: str) -> bool:
    """测试解析"""
    with tempfile.NamedTemporaryFile(suffix=".yan", mode="w", encoding="utf-8", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, YAN_CLI, "--ast", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"  ❌ 解析失败: {result.stderr[:300]}")
            return False
        print(f"  ✅ 解析成功")
        return True
    finally:
        os.unlink(tmp_path)

def test_execute(name: str, code: str) -> bool:
    """测试执行"""
    with tempfile.NamedTemporaryFile(suffix=".yan", mode="w", encoding="utf-8", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, YAN_CLI, tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"  ❌ 执行失败 (exit={result.returncode}): {result.stderr[:500]}")
            return False
        print(f"  ✅ 执行成功")
        output = result.stdout.strip()
        if output:
            for line in output.split('\n')[:5]:
                print(f"     {line}")
            if output.count('\n') > 5:
                print(f"     ... (共 {output.count(chr(10))+1} 行)")
        return True
    finally:
        os.unlink(tmp_path)

# 测试所有模板
template_files = sorted(TEMPLATES_DIR.glob("*.txt"))
print(f"找到 {len(template_files)} 个 Yan 模板文件\n")

results = {}
for tf in template_files:
    name = tf.stem
    code = tf.read_text(encoding="utf-8")
    print(f"\n{'='*60}")
    print(f"模板: {name}")
    print(f"{'='*60}")
    
    ok = True
    if not test_tokenize(name, code):
        ok = False
    if not test_parse(name, code):
        ok = False
    if not test_execute(name, code):
        ok = False
    results[name] = ok

print(f"\n{'='*60}")
print("结果汇总:")
all_ok = True
for name, ok in results.items():
    status = "✅" if ok else "❌"
    print(f"  {status} {name}")
    if not ok:
        all_ok = False

print(f"\n{'='*60}")
if all_ok:
    print("所有模板测试通过! ✅")
else:
    print("部分模板测试失败 ❌")