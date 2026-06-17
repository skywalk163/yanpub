/**
 * 言埠 YanPub — AI 辅助面板
 *
 * 实现 Webview 面板，提供 AI 辅助功能：
 * - 智能补全：获取当前编辑器光标位置的补全建议
 * - 自然语言转代码：输入框 + "生成代码" 按钮
 * - 错误修复：检测当前文件错误，提供修复建议
 *
 * AI 辅助通过 HTTP 请求调用 Playground API：
 * - POST /api/ai/complete  — 智能补全
 * - POST /api/ai/nl2code   — 自然语言转代码
 * - POST /api/ai/fix       — 错误修复建议
 */

const vscode = require('vscode');
const http = require('http');
const https = require('https');

// 言埠品牌色
const BRAND_COLOR = '#E85D3A';
const BRAND_COLOR_LIGHT = '#FFF0EC';

class AIFeature {
    /**
     * @param {vscode.ExtensionContext} context
     */
    constructor(context) {
        this.context = context;
        this.panel = null;
    }

    register() {
        // 智能补全
        this.context.subscriptions.push(
            vscode.commands.registerCommand('yanpub.ai.complete', () => this.smartComplete())
        );

        // 自然语言转代码
        this.context.subscriptions.push(
            vscode.commands.registerCommand('yanpub.ai.nl2code', () => this.nl2code())
        );

        // 错误修复
        this.context.subscriptions.push(
            vscode.commands.registerCommand('yanpub.ai.fix', () => this.fixSuggestion())
        );
    }

    /**
     * 获取 Playground API 基础 URL
     * @returns {string}
     */
    getApiBaseUrl() {
        const config = vscode.workspace.getConfiguration('yanpub');
        return config.get('playground.url', 'http://127.0.0.1:8000');
    }

    /**
     * 获取当前活动编辑器的语言 ID 和代码
     * @returns {{ langId: string, code: string, line: number, column: number } | null}
     */
    getEditorContext() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return null;

        const langId = editor.document.languageId;
        const code = editor.document.getText();
        const line = editor.selection.active.line + 1;  // 1-based
        const column = editor.selection.active.character + 1;  // 1-based

        return { langId, code, line, column };
    }

    /**
     * 发送 HTTP POST 请求到 Playground API
     * @param {string} path
     * @param {object} body
     * @returns {Promise<object>}
     */
    async apiPost(path, body) {
        const baseUrl = this.getApiBaseUrl();
        const url = new URL(path, baseUrl);
        const isHttps = url.protocol === 'https:';
        const httpModule = isHttps ? https : http;

        const bodyStr = JSON.stringify(body);

        return new Promise((resolve, reject) => {
            const options = {
                hostname: url.hostname,
                port: url.port || (isHttps ? 443 : 80),
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(bodyStr, 'utf-8'),
                },
                timeout: 15000,
            };

            const req = httpModule.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        // 如果不是 JSON（比如本地 CLI 调用），返回原始文本
                        resolve({ raw: data });
                    }
                });
            });

            req.on('error', (err) => reject(err));
            req.on('timeout', () => {
                req.destroy();
                reject(new Error('请求超时'));
            });

            req.write(bodyStr);
            req.end();
        });
    }

    /**
     * 通过 CLI 调用 AI 辅助（fallback，当 Playground API 不可用时）
     * @param {string} type - "complete" | "nl2code" | "fix"
     * @param {object} params
     * @returns {Promise<string>}
     */
    async cliFallback(type, params) {
        const config = vscode.workspace.getConfiguration('yanpub');
        const yanpubPath = config.get('lsp.path', 'yanpub');
        const { spawn } = require('child_process');

        const args = ['ai', params.text || '', '--lang', params.langId, '--type', type];

        if (type === 'complete') {
            args.push('--line', String(params.line || 1));
            args.push('--column', String(params.column || 1));
        }
        if (type === 'fix' && params.error) {
            args.push('--error', params.error);
        }
        if (params.context) {
            args.push('--context', params.context);
        }

        return new Promise((resolve, reject) => {
            const proc = spawn(yanpubPath, args, { stdio: ['pipe', 'pipe', 'pipe'] });

            let stdout = '';
            let stderr = '';
            proc.stdout.on('data', (d) => { stdout += d.toString(); });
            proc.stderr.on('data', (d) => { stderr += d.toString(); });

            proc.on('close', (code) => {
                if (code === 0) {
                    resolve(stdout.trim());
                } else {
                    reject(new Error(stderr.trim() || `CLI 退出码: ${code}`));
                }
            });

            proc.on('error', (err) => reject(err));
        });
    }

    /**
     * 智能补全
     */
    async smartComplete() {
        const ctx = this.getEditorContext();
        if (!ctx) {
            vscode.window.showWarningMessage('没有打开的文件');
            return;
        }

        let results = [];
        try {
            // 优先尝试 Playground API
            const response = await this.apiPost('/api/ai/complete', {
                lang: ctx.langId,
                code: ctx.code,
                line: ctx.line,
                column: ctx.column,
            });
            results = response.suggestions || response.results || [];
        } catch (e) {
            // fallback 到 CLI
            try {
                const cliOutput = await this.cliFallback('complete', {
                    text: '',
                    langId: ctx.langId,
                    line: ctx.line,
                    column: ctx.column,
                });
                results = [{ label: 'CLI 补全', code: cliOutput, kind: 'cli' }];
            } catch (cliErr) {
                // 最终 fallback：使用内置关键字
                results = this._builtinComplete(ctx.langId);
            }
        }

        this._showPanel('ai-complete', 'AI 智能补全', results, ctx);
    }

    /**
     * 自然语言转代码
     */
    async nl2code() {
        const ctx = this.getEditorContext();
        if (!ctx) {
            vscode.window.showWarningMessage('没有打开的文件');
            return;
        }

        // 弹出输入框
        const naturalText = await vscode.window.showInputBox({
            prompt: '输入自然语言描述，转换为代码',
            placeHolder: '例如：定义一个加法函数',
            title: 'YanPub AI — 自然语言转代码',
        });

        if (!naturalText) return;

        let result = null;
        try {
            // 优先尝试 Playground API
            result = await this.apiPost('/api/ai/nl2code', {
                lang: ctx.langId,
                text: naturalText,
                context: ctx.code,
            });
        } catch (e) {
            // fallback 到 CLI
            try {
                const cliOutput = await this.cliFallback('nl2code', {
                    text: naturalText,
                    langId: ctx.langId,
                    context: ctx.code,
                });
                result = { code: cliOutput, confidence: 0.5, explanation: '通过 CLI 生成' };
            } catch (cliErr) {
                result = { code: `# 生成失败: ${cliErr.message}`, confidence: 0, explanation: cliErr.message };
            }
        }

        const results = [result];
        this._showPanel('ai-nl2code', '自然语言转代码', results, ctx, naturalText);
    }

    /**
     * 错误修复建议
     */
    async fixSuggestion() {
        const ctx = this.getEditorContext();
        if (!ctx) {
            vscode.window.showWarningMessage('没有打开的文件');
            return;
        }

        let results = [];
        try {
            // 优先尝试 Playground API
            const response = await this.apiPost('/api/ai/fix', {
                lang: ctx.langId,
                code: ctx.code,
                error: '',  // 让后端自动诊断
            });
            results = response.suggestions || response.results || [];
        } catch (e) {
            // fallback 到 CLI
            try {
                const cliOutput = await this.cliFallback('fix', {
                    text: '',
                    langId: ctx.langId,
                    error: '',
                });
                results = [{ title: 'CLI 修复建议', fix: cliOutput, confidence: 0.5 }];
            } catch (cliErr) {
                results = [{ title: '修复失败', fix: '', description: cliErr.message, confidence: 0 }];
            }
        }

        this._showPanel('ai-fix', '错误修复建议', results, ctx);
    }

    /**
     * 内置补全（当 API 和 CLI 都不可用时）
     * @param {string} langId
     * @returns {Array}
     */
    _builtinComplete(langId) {
        const KEYWORDS = {
            duan: ['设', '为', '段落', '参数', '返回', '结束', '如果', '那么', '否则', '当', '遍历', '类', '继承', '属性', '构造', '新建', '尝试', '捕获', '抛出', '最终', '导入', '从', '导出'],
            yan: ['定义', '定', '设', '如果', '那么', '否则', '当', '遍历', '函数', '返回', '打印', '加', '减', '乘', '除'],
            moyan: ['定义', '赋值', '如果', '那么', '否则', '每当', '遍历', '函数', '导入', '导出', '真值', '假值', '返回'],
        };
        const keywords = KEYWORDS[langId] || KEYWORDS.duan;
        return keywords.slice(0, 15).map(kw => ({
            label: kw,
            kind: 'keyword',
            detail: `${langId} 关键字`,
        }));
    }

    /**
     * 显示 AI 辅助 Webview 面板
     * @param {string} panelId - 面板唯一标识
     * @param {string} title - 面板标题
     * @param {Array} results - AI 结果
     * @param {object} ctx - 编辑器上下文
     * @param {string} [nlText] - 自然语言输入（nl2code 时使用）
     */
    _showPanel(panelId, title, results, ctx, nlText) {
        if (this.panel) {
            this.panel.reveal();
        } else {
            this.panel = vscode.window.createWebviewPanel(
                `yanpub-${panelId}`,
                `言埠 AI — ${title}`,
                vscode.ViewColumn.Beside,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true,
                }
            );
            this.panel.onDidDispose(() => { this.panel = null; });
        }

        this.panel.title = `言埠 AI — ${title}`;
        this.panel.webview.html = this._renderHtml(panelId, title, results, ctx, nlText);

        // 处理面板消息
        this.panel.webview.onDidReceiveMessage(async (message) => {
            if (message.command === 'insertCode') {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const position = editor.selection.active;
                    await editor.edit((editBuilder) => {
                        editBuilder.insert(position, message.code);
                    });
                    vscode.window.showInformationMessage('代码已插入');
                }
            } else if (message.command === 'replaceCode') {
                const editor = vscode.window.activeTextEditor;
                if (editor) {
                    const fullRange = new vscode.Range(
                        editor.document.positionAt(0),
                        editor.document.positionAt(editor.document.getText().length)
                    );
                    await editor.edit((editBuilder) => {
                        editBuilder.replace(fullRange, message.code);
                    });
                    vscode.window.showInformationMessage('代码已替换');
                }
            } else if (message.command === 'nl2code') {
                // 在面板内重新请求自然语言转代码
                const text = message.text;
                if (!text) return;
                try {
                    const result = await this.apiPost('/api/ai/nl2code', {
                        lang: ctx.langId,
                        text: text,
                        context: ctx.code,
                    });
                    this.panel.webview.postMessage({ command: 'nl2codeResult', result });
                } catch (e) {
                    this.panel.webview.postMessage({ command: 'nl2codeResult', result: { code: `# 请求失败: ${e.message}`, confidence: 0, explanation: e.message } });
                }
            }
        });
    }

    /**
     * 渲染 Webview HTML
     * @param {string} panelId
     * @param {string} title
     * @param {Array} results
     * @param {object} ctx
     * @param {string} [nlText]
     * @returns {string}
     */
    _renderHtml(panelId, title, results, ctx, nlText) {
        const langLabel = ctx.langId;
        const escapedNlText = this._escapeHtml(nlText || '');

        // 构建结果卡片
        let resultsHtml = '';
        if (panelId === 'ai-complete') {
            resultsHtml = this._renderCompleteResults(results);
        } else if (panelId === 'ai-nl2code') {
            resultsHtml = this._renderNl2CodeResults(results, escapedNlText);
        } else if (panelId === 'ai-fix') {
            resultsHtml = this._renderFixResults(results);
        }

        return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>言埠 AI — ${this._escapeHtml(title)}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #1a1a1a;
            background: #fafafa;
            padding: 16px;
            line-height: 1.6;
        }
        .header {
            display: flex;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid ${BRAND_COLOR};
        }
        .header h1 {
            font-size: 18px;
            font-weight: 600;
            color: ${BRAND_COLOR};
        }
        .header .lang-badge {
            margin-left: 10px;
            background: ${BRAND_COLOR};
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        .card {
            background: white;
            border: 1px solid #e8e8e8;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .card-title {
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .card-title .icon { color: ${BRAND_COLOR}; }
        .card-title .confidence {
            margin-left: auto;
            font-size: 12px;
            font-weight: 400;
            color: #888;
        }
        pre {
            background: #282c34;
            color: #abb2bf;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.5;
            font-family: "Fira Code", "JetBrains Mono", Consolas, monospace;
        }
        .btn-row {
            display: flex;
            gap: 8px;
            margin-top: 10px;
        }
        .btn {
            padding: 6px 14px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.85; }
        .btn-primary { background: ${BRAND_COLOR}; color: white; }
        .btn-secondary { background: #e8e8e8; color: #333; }
        .detail { color: #666; font-size: 13px; margin-top: 6px; }
        .nl-input-area {
            margin-bottom: 16px;
        }
        .nl-input-area textarea {
            width: 100%;
            min-height: 60px;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
            resize: vertical;
            font-family: inherit;
        }
        .nl-input-area textarea:focus {
            outline: none;
            border-color: ${BRAND_COLOR};
        }
        .empty-msg {
            text-align: center;
            color: #999;
            padding: 40px 0;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>${this._escapeHtml(title)}</h1>
        <span class="lang-badge">${this._escapeHtml(langLabel)}</span>
    </div>
    ${panelId === 'ai-nl2code' ? `
    <div class="nl-input-area">
        <textarea id="nlInput" placeholder="输入自然语言描述，按生成代码...">${escapedNlText}</textarea>
        <div class="btn-row" style="margin-top: 8px;">
            <button class="btn btn-primary" onclick="generateCode()">生成代码</button>
        </div>
    </div>
    ` : ''}
    <div id="results">
        ${resultsHtml || '<div class="empty-msg">暂无结果</div>'}
    </div>

    <script>
        const vscode = acquireVsCodeApi();

        function insertCode(code) {
            vscode.postMessage({ command: 'insertCode', code: code });
        }

        function replaceCode(code) {
            vscode.postMessage({ command: 'replaceCode', code: code });
        }

        function generateCode() {
            const text = document.getElementById('nlInput').value;
            if (!text.trim()) return;
            vscode.postMessage({ command: 'nl2code', text: text });
        }

        window.addEventListener('message', (event) => {
            const message = event.data;
            if (message.command === 'nl2codeResult') {
                const result = message.result;
                const resultsDiv = document.getElementById('results');
                const card = document.createElement('div');
                card.className = 'card';
                const confidence = Math.round((result.confidence || 0) * 100);
                card.innerHTML =
                    '<div class="card-title"><span class="icon">&#9889;</span> 生成结果 <span class="confidence">置信度: ' + confidence + '%</span></div>' +
                    '<pre>' + escapeHtml(result.code || '') + '</pre>' +
                    (result.explanation ? '<div class="detail">' + escapeHtml(result.explanation) + '</div>' : '') +
                    '<div class="btn-row">' +
                    '<button class="btn btn-primary" onclick="insertCode(' + escapeAttr(JSON.stringify(result.code || '')) + ')">插入代码</button>' +
                    '<button class="btn btn-secondary" onclick="replaceCode(' + escapeAttr(JSON.stringify(result.code || '')) + ')">替换全文</button>' +
                    '</div>';
                resultsDiv.prepend(card);
            }
        });

        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function escapeAttr(str) {
            return "'" + str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\\n/g, '\\n') + "'";
        }
    </script>
</body>
</html>`;
    }

    /**
     * 渲染智能补全结果
     */
    _renderCompleteResults(results) {
        if (!results || results.length === 0) return '<div class="empty-msg">未找到补全建议</div>';

        return results.map(r => {
            const label = this._escapeHtml(r.label || r.insert_text || '');
            const detail = this._escapeHtml(r.detail || r.kind || '');
            const code = this._escapeHtml(r.insert_text || r.code || label);
            const confidence = r.confidence ? `置信度: ${Math.round(r.confidence * 100)}%` : '';

            return `<div class="card">
                <div class="card-title">
                    <span class="icon">&#9889;</span> ${label}
                    <span class="confidence">${confidence}</span>
                </div>
                <div class="detail">${detail}</div>
                ${code !== label ? `<pre>${code}</pre>` : ''}
                <div class="btn-row">
                    <button class="btn btn-primary" onclick="insertCode('${this._escapeJs(r.insert_text || r.code || label)}')">插入代码</button>
                </div>
            </div>`;
        }).join('');
    }

    /**
     * 渲染自然语言转代码结果
     */
    _renderNl2CodeResults(results, nlText) {
        if (!results || results.length === 0) return '<div class="empty-msg">未生成代码</div>';

        return results.map(r => {
            const code = this._escapeHtml(r.code || '');
            const explanation = this._escapeHtml(r.explanation || '');
            const confidence = r.confidence ? `置信度: ${Math.round(r.confidence * 100)}%` : '';

            return `<div class="card">
                <div class="card-title">
                    <span class="icon">&#9889;</span> 生成结果
                    <span class="confidence">${confidence}</span>
                </div>
                <pre>${code}</pre>
                ${explanation ? `<div class="detail">${explanation}</div>` : ''}
                <div class="btn-row">
                    <button class="btn btn-primary" onclick="insertCode('${this._escapeJs(r.code || '')}')">插入代码</button>
                    <button class="btn btn-secondary" onclick="replaceCode('${this._escapeJs(r.code || '')}')">替换全文</button>
                </div>
            </div>`;
        }).join('');
    }

    /**
     * 渲染错误修复结果
     */
    _renderFixResults(results) {
        if (!results || results.length === 0) return '<div class="empty-msg">未发现需要修复的问题</div>';

        return results.map(r => {
            const title = this._escapeHtml(r.title || '修复建议');
            const description = this._escapeHtml(r.description || '');
            const fix = this._escapeHtml(r.fix || '');
            const confidence = r.confidence ? `置信度: ${Math.round(r.confidence * 100)}%` : '';

            return `<div class="card">
                <div class="card-title">
                    <span class="icon">&#128295;</span> ${title}
                    <span class="confidence">${confidence}</span>
                </div>
                ${description ? `<div class="detail">${description}</div>` : ''}
                ${fix ? `<pre>${fix}</pre>` : ''}
                <div class="btn-row">
                    ${fix ? `<button class="btn btn-primary" onclick="replaceCode('${this._escapeJs(r.fix || '')}')">应用修复</button>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    /**
     * HTML 转义
     */
    _escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * JS 字符串转义（用于 onclick 属性）
     */
    _escapeJs(str) {
        if (!str) return '';
        return String(str)
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/\n/g, '\\n')
            .replace(/\r/g, '\\r');
    }
}


module.exports = { AIFeature };
