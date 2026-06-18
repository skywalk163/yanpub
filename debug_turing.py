"""调试 turing.txt 的执行错误"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path

YAN_CLI = r"G:\atomcode\atomyan\yan.py"
template = Path(__file__).parent / "src" / "yanpub" / "playground" / "templates" / "yan" / "turing.txt"
code = template.read_text(encoding="utf-8")

with tempfile.NamedTemporaryFile(suffix=".yan", mode="w", encoding="utf-8", delete=False) as f:
    f.write(code)
    tmp_path = f.name

try:
    result = subprocess.run(
        [sys.executable, YAN_CLI, "-v", tmp_path],
        capture_output=True,
        text=True,
        timeout=15,
    )
    print(f"exit_code: {result.returncode}")
    print(f"stdout:\n{result.stdout[:2000]}")
    print(f"stderr:\n{result.stderr[:3000]}")
finally:
    os.unlink(tmp_path)