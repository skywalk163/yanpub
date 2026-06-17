/**
 * 言埠 YanPub — 调试适配器集成
 *
 * 实现 VSCode Debug Adapter Protocol 集成，连接 yanpub DAPServer（TCP 端口 4711）。
 * 当用户按 F5 时，自动启动 `yanpub dap-server <lang>` 进程，
 * 通过 socket 连接到 DAPServer，实现断点、单步、变量查看等调试功能。
 */

const vscode = require('vscode');
const { spawn } = require('child_process');
const net = require('net');

const LANGUAGES = [
    'duan', 'yan', 'moyan', 'xinyu', 'zhixing',
    'yanlv', 'yanzhi', 'mingdao', 'hanyu', 'traeyan',
];

class DebugFeature {
    /**
     * @param {vscode.ExtensionContext} context
     */
    constructor(context) {
        this.context = context;
        this.dapProcess = null;
        this.outputChannel = vscode.window.createOutputChannel('言埠调试');
    }

    register() {
        // 注册调试适配器工厂
        const factory = new YanpubDebugAdapterDescriptorFactory(this);
        this.context.subscriptions.push(
            vscode.debug.registerDebugAdapterDescriptorFactory('yanpub', factory)
        );

        // 注册调试适配器追踪器工厂（用于日志）
        const trackerFactory = new YanpubDebugAdapterTrackerFactory();
        this.context.subscriptions.push(
            vscode.debug.registerDebugAdapterTrackerFactory('yanpub', trackerFactory)
        );

        // 注册调试启动命令
        this.context.subscriptions.push(
            vscode.commands.registerCommand('yanpub.debug.start', () => this.startDebug())
        );
    }

    /**
     * 启动调试当前文件
     */
    startDebug() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('没有打开的文件');
            return;
        }

        const langId = editor.document.languageId;
        if (!LANGUAGES.includes(langId)) {
            vscode.window.showWarningMessage(`不支持的语言: ${langId}`);
            return;
        }

        const filePath = editor.document.uri.fsPath;

        vscode.debug.startDebugging(undefined, {
            type: 'yanpub',
            request: 'launch',
            name: `调试 ${filePath}`,
            program: filePath,
            stopOnEntry: false,
        });
    }

    /**
     * 启动 DAP 服务器进程
     * @param {string} langId
     * @returns {Promise<number>} 端口号
     */
    async startDapServer(langId) {
        const config = vscode.workspace.getConfiguration('yanpub');
        const yanpubPath = config.get('lsp.path', 'yanpub');
        const port = config.get('dap.port', 4711);

        return new Promise((resolve, reject) => {
            try {
                const proc = spawn(yanpubPath, ['dap-server', langId, '--port', String(port)], {
                    stdio: ['ignore', 'pipe', 'pipe'],
                });

                this.dapProcess = proc;

                proc.stdout.on('data', (data) => {
                    const text = data.toString();
                    this.outputChannel.append(`[DAP stdout] ${text}`);
                });

                proc.stderr.on('data', (data) => {
                    const text = data.toString();
                    this.outputChannel.append(`[DAP stderr] ${text}`);
                    // 检测服务器启动成功的标志
                    if (text.includes('DAP 服务器启动') || text.includes('启动')) {
                        resolve(port);
                    }
                });

                proc.on('error', (err) => {
                    this.outputChannel.append(`[DAP error] ${err.message}\n`);
                    reject(new Error(`启动 DAP 服务器失败: ${err.message}`));
                });

                proc.on('exit', (code) => {
                    this.outputChannel.append(`[DAP] 进程退出 (code=${code})\n`);
                    this.dapProcess = null;
                });

                // 超时保护：3秒后如果未检测到启动标志，仍尝试连接
                setTimeout(() => {
                    resolve(port);
                }, 3000);

            } catch (err) {
                reject(new Error(`启动 DAP 服务器失败: ${err.message}`));
            }
        });
    }

    /**
     * 停止 DAP 服务器进程
     */
    stopDapServer() {
        if (this.dapProcess) {
            try {
                this.dapProcess.kill();
            } catch (e) {
                // 忽略
            }
            this.dapProcess = null;
        }
    }
}


class YanpubDebugAdapterDescriptorFactory {
    /**
     * @param {DebugFeature} debugFeature
     */
    constructor(debugFeature) {
        this.debugFeature = debugFeature;
    }

    /**
     * 创建调试适配器描述符
     * @param {vscode.DebugSession} session
     * @returns {Promise<vscode.DebugAdapterDescriptor>}
     */
    async createDebugAdapterDescriptor(session) {
        // 从调试配置中推断语言类型
        const program = session.configuration.program || '';
        const langId = this._inferLangId(program);

        if (!langId) {
            throw new Error('无法推断语言类型，请在 yanpub 支持的文件中启动调试');
        }

        // 启动 DAP 服务器
        const port = await this.debugFeature.startDapServer(langId);

        // 返回服务器类型的调试适配器描述符（通过 TCP socket 连接）
        return new vscode.DebugAdapterServer(port);
    }

    /**
     * 从文件路径推断语言 ID
     * @param {string} filePath
     * @returns {string|null}
     */
    _inferLangId(filePath) {
        // 优先使用活动编辑器的语言 ID
        const editor = vscode.window.activeTextEditor;
        if (editor && LANGUAGES.includes(editor.document.languageId)) {
            return editor.document.languageId;
        }

        // 从文件扩展名推断
        const ext = require('path').extname(filePath).toLowerCase();
        const extMap = {
            '.duan': 'duan', '.段': 'duan',
            '.yan': 'yan', '.言': 'yan',
            '.moyan': 'moyan', '.墨': 'moyan',
            '.xinyu': 'xinyu', '.心': 'xinyu',
            '.zhixing': 'zhixing', '.行': 'zhixing',
            '.yanlv': 'yanlv', '.律': 'yanlv',
            '.yanzhi': 'yanzhi', '.知': 'yanzhi',
            '.mingdao': 'mingdao', '.道': 'mingdao',
            '.hanyu': 'hanyu', '.翰': 'hanyu',
            '.traeyan': 'traeyan', '.trae': 'traeyan',
        };
        return extMap[ext] || null;
    }
}


class YanpubDebugAdapterTrackerFactory {
    createDebugAdapterTracker(session) {
        return new YanpubDebugAdapterTracker();
    }
}


class YanpubDebugAdapterTracker {
    onWillStartSession() {
        // 调试会话即将开始
    }

    onWillReceiveMessage(message) {
        // 即将发送给 DAP 服务器的消息
    }

    onDidSendMessage(message) {
        // 从 DAP 服务器收到的消息
        if (message.type === 'event') {
            const event = message.event;
            if (event === 'stopped') {
                const reason = message.body?.reason || 'unknown';
                vscode.window.setStatusBarMessage(`调试暂停: ${reason}`, 3000);
            } else if (event === 'exited') {
                vscode.window.setStatusBarMessage('程序已退出', 3000);
            }
        }
    }

    onError(error) {
        vscode.window.showErrorMessage(`调试错误: ${error.message}`);
    }

    onExit(code, signal) {
        if (code && code !== 0) {
            vscode.window.showWarningMessage(`DAP 服务器退出 (code=${code})`);
        }
    }
}


module.exports = { DebugFeature, YanpubDebugAdapterDescriptorFactory, YanpubDebugAdapterTrackerFactory };
