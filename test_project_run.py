#!/usr/bin/env python
"""Test: simulate project mode execution flow"""

import sys, os, tempfile

sys.path.insert(0, r'G:\dumategithub\yanpub\src')
sys.path.insert(0, r'G:\dumategithub\duan\src')
sys.path.insert(0, r'G:\dumategithub\duan')

from yanpub.core.adapter.registry import get_registry
from yanpub.playground.project import get_project_manager

# Create a project and run it
pm = get_project_manager()

# Test duan
print("=== Testing Duan ===")
try:
    proj = pm.create_project("Test", "duan")
    print(f"Project created: {proj.language}, main: {proj.main_file}")
    
    registry = get_registry()
    adapter = registry.get("duan")
    print(f"Adapter: {adapter.name}")
    
    result = pm.execute_project(proj.id, adapter)
    print(f"stdout: {result.stdout[:200]}")
    print(f"stderr: {result.stderr[:500]}")
    print(f"exit: {result.exit_code}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("\n=== Testing Hanyu ===")
try:
    proj = pm.create_project("Test2", "hanyu")
    print(f"Project created: {proj.language}, main: {proj.main_file}")
    
    adapter = registry.get("hanyu")
    print(f"Adapter: {adapter.name}")
    
    result = pm.execute_project(proj.id, adapter)
    print(f"stdout: {result.stdout[:200]}")
    print(f"stderr: {result.stderr[:500]}")
    print(f"exit: {result.exit_code}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")

print("\n=== Testing Yan ===")
try:
    proj = pm.create_project("Test3", "yan")
    print(f"Project created: {proj.language}, main: {proj.main_file}")
    
    adapter = registry.get("yan")
    print(f"Adapter: {adapter.name}")
    
    result = pm.execute_project(proj.id, adapter)
    print(f"stdout: {result.stdout[:200]}")
    print(f"stderr: {result.stderr[:500]}")
    print(f"exit: {result.exit_code}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
