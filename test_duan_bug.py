#!/usr/bin/env python
"""Test if the duan template from YanPub causes 'return' outside function"""

import sys
import os

# Set up paths for duan
sys.path.insert(0, r'G:\dumategithub\duan\src')
sys.path.insert(0, r'G:\dumategithub\duan')

from duan_parser_v3 import DuanParser
from code_generator import PythonCodeGenerator

# Simpler test
code = '''# 段言 (Duan) 示例
打印("你好，世界！")。
'''

parser = DuanParser()
module = parser.parse(code)

generator = PythonCodeGenerator()
py_code = generator.generate(module)

print("=== Generated Python Code ===")
for i, line in enumerate(py_code.split('\n'), 1):
    print(f"{i:3d}: {line}")
print("=== End ===")

# Try to execute
print("\n=== Execution ===")
output_lines = []
def _capture_print(*args, **kwargs):
    line = ' '.join(str(a) for a in args)
    output_lines.append(line)

namespace = {'print': _capture_print, '__name__': '__main__'}
try:
    exec(py_code, namespace)
    print('\n'.join(output_lines))
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    print(f"  Line: {e.lineno}")
    print(f"  Text: {e.text}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
