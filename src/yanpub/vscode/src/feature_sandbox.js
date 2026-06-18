/**
 * 言埠 YanPub — 沙箱执行按钮
 *
 * 实现沙箱执行命令，通过 `yanpub sandbox <lang> <file>` CLI 命令
 * 在安全隔离的环境中执行代码，并在 OutputChannel 中显示结果。
 * 状态栏显示沙箱图标和后端类型。
 */

const vscode = require('vscode');
const { spawn } = require('child_process');

const SUPPORTED_LANGUAGES = [
    'duan', 'yan', 'moyan', 'xinyu', 'zhixing',
    'yanlv', 'yanzhi', 'mingdao', 'hanyu', 'traeyan',
];

const LANG_NAMES = {
    duan: '段言', yan: '言', moyan: '墨言', xinyu: '心语',
    zhixing: '知行', yanlv: '言律', yanzhi: '言知', mingdao: '明道',
    hanyu: '翰语', traeyan: '趣言',
};

class SandboxFeature {
    /**
     * @param {vscode.ExtensionContext} context
     */
    constructor(context) {
        this.context = context;
        this.outputChannel = vscode.window.createOutputChannel('言埠沙箱');
        this.statusBarItem = null;
        this.isRunning = false;
    }

    register() {
        // 注册沙箱执行命令
        this.context.subscriptions.push(
            vscode.commands.registerCommand('yanpub.sandbox.run', () => this.run())
        );

        // 创建状态栏项
        this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 99);
        this.statusBarItem.text = '$(shield) 沙箱';
        this.statusBarItem.tooltip = '言埠沙箱 — 点击查看后端状态';
        this.statusBarItem.command = 'yanpub.sandbox.run';
        this.statusBarItem.show();
        this.context.subscriptions.push(this.statusBarItem);

        // 检测可用后端并更新状态栏
        this.detectBackend();
    }

    /**
     * 检测可用的沙箱后端
     */
    async detectBackend() {
        const config = vscode.workspace.getConfiguration('yanpub');
        const yanpubPath = config.get('lsp.path', 'yanpub');

        try {
            const result = await this._execCommand(yanpubPath, ['sandbox', 'check']);
            // 解析输出中的后端信息
            const lines = result.split('\n');
            let activeBackend = 'process';

            for (const line of lines) {
                if (line.includes('✓') || line.includes('可用')) {
                    // 取第一个可用的非 process 后端
                    if (line.includes('docker')) { activeBackend = 'docker'; break; }
                    if (line.includes('podman')) { activeBackend = 'podman'; break; }
                    if (line.includes('freebsd_jail')) { activeBackend = 'freebsd_jail'; break; }
                }
            }

            this.statusBarItem.text = `$(shield) ${activeBackend}`;
            this.statusBarItem.tooltip = `言埠沙箱 — 后端: ${activeBackend}`;
        } catch (e) {
            this.statusBarItem.text = '$(shield) 沙箱';
            this.statusBarItem.tooltip = '言埠沙箱 — 后端检测失败，将使用进程沙箱';
        }
    }

    /**
     * 执行沙箱运行
     */
    async run() {
        if (this.isRunning) {
            vscode.window.showWarningMessage('沙箱正在执行中，请等待完成');
            return;
        }

        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('没有打开的文件');
            return;
        }

        const filePath = editor.document.uri.fsPath;
        const langId = editor.document.languageId;

        if (!SUPPORTED_LANGUAGES.includes(langId)) {
            vscode.window.showWarningMessage(`不支持的语言: ${langId}`);
            return;
        }

        // 先保存文件
        await editor.document.save();

        const config = vscode.workspace.getConfiguration('yanpub');
        const yanpubPath = config.get('lsp.path', 'yanpub');
        const backend = config.get('sandbox.backend', 'auto');
        const langName = LANG_NAMES[langId] || langId;

        this.isRunning = true;
        this.statusBarItem.text = `$(loading~spin) 沙箱执行中...`;

        this.outputChannel.show(true);
        this.outputChannel.appendLine('');
        this.outputChannel.appendLine(`════════════════════════════════════════`);
        this.outputChannel.appendLine(`言埠沙箱 — ${langName} (${langId})`);
        this.outputChannel.appendLine(`文件: ${filePath}`);
        this.outputChannel.appendLine(`后端: ${backend}`);
        this.outputChannel.appendLine(`时间: ${new Date().toLocaleString()}`);
        this.outputChannel.appendLine(`════════════════════════════════════════`);
        this.outputChannel.appendLine('');

        try {
            const startTime = Date.now();

            // 构建 sandbox run 命令参数
            const args = ['sandbox', 'run', langId, filePath, '--backend', backend];

            await new Promise((resolve, reject) => {
                const proc = spawn(yanpubPath, args, {
                    stdio: ['ignore', 'pipe', 'pipe'],
                    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
                });

                proc.stdout.on('data', (data) => {
                    this.outputChannel.append(data.toString());
                });

                proc.stderr.on('data', (data) => {
                    const text = data.toString();
                    // 将元信息输出到频道（但不以错误形式显示）
                    if (text.includes('沙箱执行:') || text.includes('后端:')) {
                        this.outputChannel.append(text);
                    } else {
                        this.outputChannel.append(text);
                    }
                });

                proc.on('close', (code) => {
                    const elapsed = Date.now() - startTime;
                    this.outputChannel.appendLine('');
                    this.outputChannel.appendLine(`────────────────────────────────────────`);
                    this.outputChannel.appendLine(`执行完成 | 退出码: ${code} | 耗时: ${elapsed}ms`);
                    this.outputChannel.appendLine(`────────────────────────────────────────`);

                    if (code === 0) {
                        vscode.window.setStatusBarMessage(`沙箱执行完成 (${elapsed}ms)`, 3000);
                    } else {
                        vscode.window.showWarningMessage(`沙箱执行失败 (退出码: ${code})`);
                    }
                    resolve();
                });

                proc.on('error', (err) => {
                    this.outputChannel.appendLine(`错误: ${err.message}`);
                    reject(err);
                });
            });

        } catch (err) {
            this.outputChannel.appendLine(`沙箱执行错误: ${err.message}`);

            // 如果 CLI 执行失败，尝试直接提示
            if (err.code === 'ENOENT') {
                vscode.window.showErrorMessage(
                    `未找到 yanpub 命令。请确认已安装 yanpub 并配置路径。`,
                    '配置路径'
                ).then(choice => {
                    if (choice === '配置路径') {
                        vscode.commands.executeCommand('workbench.action.openSettings', 'yanpub.lsp.path');
                    }
                });
            } else {
                vscode.window.showErrorMessage(`沙箱执行失败: ${err.message}`);
            }
        } finally {
            this.isRunning = false;
            const config = vscode.workspace.getConfiguration('yanpub');
            const currentBackend = config.get('sandbox.backend', 'auto');
            this.statusBarItem.text = `$(shield) ${currentBackend === 'auto' ? '沙箱' : currentBackend}`;
        }
    }

    /**
     * 执行命令并返回输出
     * @param {string} command
     * @param {string[]} args
     * @returns {Promise<string>}
     */
    _execCommand(command, args) {
        return new Promise((resolve, reject) => {
            const proc = spawn(command, args, {
                stdio: ['ignore', 'pipe', 'pipe'],
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
            });

            let stdout = '';
            let stderr = '';

            proc.stdout.on('data', (data) => { stdout += data.toString(); });
            proc.stderr.on('data', (data) => { stderr += data.toString(); });

            proc.on('close', (code) => {
                if (code === 0 || code === null) {
                    resolve(stdout + stderr);
                } else {
                    reject(new Error(stderr || `退出码: ${code}`));
                }
            });

            proc.on('error', (err) => reject(err));
        });
    }
}


module.exports = { SandboxFeature };
