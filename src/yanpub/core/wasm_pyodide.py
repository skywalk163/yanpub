"""Pyodide 配置生成 — 浏览器端 WASM 执行

核心函数：
- generate_pyodide_config(): 生成 Pyodide 前端执行配置
- generate_pyodide_runner_html(): 生成 Pyodide 执行器 HTML 页面
"""

from __future__ import annotations

import json

from yanpub.core.adapter.adapter import LanguageAdapter


def generate_pyodide_config(adapter: LanguageAdapter) -> dict:
    """生成 Pyodide 前端执行配置

    用于 Playground 前端在浏览器端通过 Pyodide 执行中文编程语言代码。

    Args:
        adapter: 语言适配器

    Returns:
        Pyodide 配置字典
    """
    return {
        "lang_id": adapter.id,
        "lang_name": adapter.name,
        "version": adapter.version,
        "comment_syntax": adapter.comment_syntax,
        "keywords": adapter.keywords[:100] if len(adapter.keywords) > 100 else adapter.keywords,
        "primary_color": adapter.primary_color,
        "file_extensions": adapter.file_extensions,
        "capabilities": adapter.capabilities,
        # Pyodide 执行参数
        "pyodide": {
            "version": "0.24.1",
            "index_url": "https://cdn.jsdelivr.net/pyodide/v0.24.1/full/",
        },
        # 执行模式
        "execution_mode": "pyodide",  # pyodide | wasm | native
        # 预加载的 Python 包
        "preload_packages": ["micropip"],
    }


def generate_pyodide_runner_html(adapter: LanguageAdapter) -> str:
    """生成 Pyodide 执行器 HTML 页面

    可嵌入 Playground 的 iframe 中。

    Args:
        adapter: 语言适配器

    Returns:
        HTML 字符串
    """
    config = generate_pyodide_config(adapter)
    config_json = json.dumps(config, ensure_ascii=False, indent=2)

    # 使用 string.Template 避免与 JS 的 {} 冲突
    from string import Template

    tpl = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${lang_name} WASM 执行器</title>
<style>
body {
    font-family: 'Microsoft YaHei', monospace;
    background: #1a1a2e;
    color: #e0e0e0;
    margin: 0;
    padding: 10px;
}
#output {
    white-space: pre-wrap;
    font-family: 'Consolas', monospace;
    font-size: 14px;
    line-height: 1.5;
}
.error { color: #f44336; }
.success { color: #4CAF50; }
.loading { color: #FF9800; }
</style>
</head>
<body>
<div id="status" class="loading">正在加载 Pyodide 运行时...</div>
<div id="output"></div>
<script>
// Pyodide 执行器配置
const CONFIG = ${config_json};

let pyodide = null;

async function initPyodide() {
    try {
        pyodide = await loadPyodide({
            indexURL: CONFIG.pyodide.index_url
        });
        document.getElementById('status').className = 'success';
        document.getElementById('status').textContent = 'Pyodide 已加载 (' + CONFIG.lang_name + ')';
        // 通知父页面
        if (window.parent !== window) {
            window.parent.postMessage({ type: 'wasm-ready', langId: CONFIG.lang_id }, '*');
        }
    } catch(e) {
        document.getElementById('status').className = 'error';
        document.getElementById('status').textContent = 'Pyodide 加载失败: ' + e.message;
    }
}

async function executeCode(code) {
    if (!pyodide) {
        return { stdout: '', stderr: 'Pyodide 未加载', exitCode: -1 };
    }
    const output = document.getElementById('output');
    output.textContent = '';
    try {
        // 重定向 stdout/stderr
        pyodide.runPython(`
import sys, io
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
`);
        pyodide.runPython(code);
        const stdout = pyodide.runPython('sys.stdout.getvalue()');
        const stderr = pyodide.runPython('sys.stderr.getvalue()');
        output.textContent = stdout;
        if (stderr) {
            const errDiv = document.createElement('div');
            errDiv.className = 'error';
            errDiv.textContent = stderr;
            output.appendChild(errDiv);
        }
        return { stdout, stderr, exitCode: 0 };
    } catch(e) {
        const errDiv = document.createElement('div');
        errDiv.className = 'error';
        errDiv.textContent = e.message;
        output.appendChild(errDiv);
        return { stdout: '', stderr: e.message, exitCode: 1 };
    }
}

// 监听来自父页面的执行请求
window.addEventListener('message', async function(event) {
    if (event.data.type === 'execute') {
        const result = await executeCode(event.data.code);
        window.parent.postMessage({
            type: 'execute-result',
            langId: CONFIG.lang_id,
            result: result,
            id: event.data.id
        }, '*');
    }
});

// 加载 Pyodide CDN
const script = document.createElement('script');
script.src = CONFIG.pyodide.index_url + 'pyodide.js';
script.onload = initPyodide;
document.head.appendChild(script);
</script>
</body>
</html>""")

    return tpl.substitute(lang_name=adapter.name, config_json=config_json)
