/**
 * 言埠 YanPub VSCode 扩展
 *
 * 统一中文编程语言支持：语法高亮、代码补全、诊断、格式化。
 * 一个扩展支持所有中文编程语言。
 */

const vscode = require('vscode');
const { execSync, spawn } = require('child_process');
const path = require('path');

// ---- 语言注册表 ----

const LANGUAGES = [
    { id: 'duan', name: '段言', extensions: ['.段', '.duan'] },
    { id: 'yan', name: '言', extensions: ['.言', '.yan'] },
    { id: 'moyan', name: '墨言', extensions: ['.墨', '.moyan'] },
    { id: 'xinyu', name: '心语', extensions: ['.心', '.xinyu'] },
    { id: 'zhixing', name: '知行', extensions: ['.行', '.zhixing'] },
    { id: 'yanlv', name: '言律', extensions: ['.律', '.yanlv'] },
    { id: 'yanzhi', name: '言知', extensions: ['.知', '.yanzhi'] },
    { id: 'mingdao', name: '明道', extensions: ['.道', '.mingdao'] },
    { id: 'hanyu', name: '翰语', extensions: ['.翰', '.hanyu'] },
    { id: 'traeyan', name: '知行语言', extensions: ['.trae', '.traeyan'] },
];

// ---- LSP 客户端 ----

let lspClient = null;

function startLSP(context) {
    const config = vscode.workspace.getConfiguration('yanpub');
    if (!config.get('lsp.enabled', true)) {
        return;
    }

    const yanpubPath = config.get('lsp.path', 'yanpub');
    const port = config.get('lsp.port', 2087);

    // 检测当前文件语言
    const editor = vscode.window.activeTextEditor;
    if (!editor) return;

    const langId = editor.document.languageId;
    const langInfo = LANGUAGES.find(l => l.id === langId);
    if (!langInfo) return;

    // 使用内置关键字补全（无需 LSP 也可工作）
    // LSP 服务作为增强层
    try {
        const { LanguageClient, TransportKind } = require('vscode-languageclient/node');

        const serverOptions = {
            command: yanpubPath,
            args: ['lsp', langId, '--port', String(port)],
            transport: TransportKind.tcp,
        };

        const clientOptions = {
            documentSelector: LANGUAGES.map(l => ({ scheme: 'file', language: l.id })),
        };

        lspClient = new LanguageClient(
            'yanlsp',
            `言埠 LSP — ${langInfo.name}`,
            serverOptions,
            clientOptions
        );

        lspClient.start();
    } catch (e) {
        // vscode-languageclient 未安装，使用内置补全
        console.log('LSP 客户端不可用，使用内置补全');
    }
}

// ---- 内置关键字补全 ----

// 各语言关键字（从适配器同步）
const KEYWORDS = {
    duan: [
        '设', '为', '段落', '参数', '返回', '结束',
        '如果', '那么', '否则', '否则若', '当', '遍历', '在',
        '类', '继承', '属性', '构造', '新建', '接口', '实现',
        '尝试', '捕获', '抛出', '最终',
        '导入', '从', '导出', '模块', '标准库',
        '定义', '常量', '类型', '匹配', '情况',
        '使用', '标注', '抽象',
        '真', '假', '空',
        '且', '或', '非', '与',
        '并', '之', '的', '己', '父',
        '打印', '长度', '类型',
        '跳出', '跳过',
    ],
    yan: [
        '定义', '定', '设', '求值',
        '如果', '那么', '否则', '若', '当', '当时', '遍历',
        '函数', '返回', '结构', '套',
        '引', '导', '出',
        '打印', '印', '印数', '印浮', '读', '写', '行', '读行', '输出',
        '测',
        '加', '减', '乘', '除', '取',
        '长', '列', '列表', '连', '添', '含', '首个', '其余', '入',
        '反转', '排序', '映射', '过滤', '归约',
    ],
    moyan: [
        '定义', '赋值',
        '如果', '那么', '否则', '每当', '时候', '遍历', '于中',
        '函数', '宏定',
        '导入', '来自', '导出',
        '真值', '假值', '空值',
        '返回', '跳出', '继续',
        '试', '捕获', '则',
        '断点', '产生',
    ],
    xinyu: [
        '定义', '定', '函数', '函', '如果', '若', '那么', '否则', '可选',
        '循环', '当满足', '遍历', '返回', '继续', '跳出', '结束',
        '尝试', '捕获', '最终', '抛出',
        '导入', '从',
        '真值', '假值', '真', '假',
        '皆', '只', '归',
        '相加', '加', '相减', '减', '相乘', '乘', '相除', '除',
        '等于', '等', '大于', '大', '小于', '小',
        '且', '或', '非',
    ],
    zhixing: [
        '定', '设', '函', '若', '则', '否则', '当', '遍历', '入', '于',
        '真', '假', '空',
        '尝试', '捕获', '结束', '完毕',
        '导入', '导出', '模块', '从', '为',
        '加', '减', '乘', '除', '模', '幂',
        '大', '小', '等', '不等',
        '皆', '只', '归', '并',
        '返回',
    ],
    yanlv: [
        '定', '定义', '设', '设置', '变量',
        '如果', '要是', '否则', '不然', '否则如果', '否则要是',
        '当', '一直', '对于', '遍历', '每个', '直到',
        '函数', '参数', '调用', '返回', '结束', '循环',
        '输出', '打印', '显示',
        '尝试', '捕获', '抛出', '异常', '最终',
        '定义模块', '导入', '导出', '从', '作为', '命名空间', '结束模块',
        '加', '减', '乘', '除', '余',
        '等于', '大于', '小于', '大于等于', '小于等于', '不等于',
        '绝对值', '平方根', '幂', '正弦', '余弦', '正切', '自然对数', '阶乘',
        '读取文件', '写入文件', '追加文件', '文件存在', '文件大小',
    ],
    yanzhi: [
        '定义', '赋值', '函数', '结构', '方法', '宏', '模块',
        '如果', '那么', '否则', '遍历', '循环当',
        '对于', '每次', '算', '从', '到', '每隔',
        '要是', '就', '不然', '是',
        '真', '假', '空',
        '尝试', '捕获', '结束', '完毕', '返回', '抛出',
        '导入', '导出', '于',
        '匹配', '情况',
        '启用', '策略', '引用', '模板', '嵌入', '展开嵌入', '执行',
        '相加', '相减', '相乘', '相除',
        '大于', '小于', '等于',
        '打印', '读取',
    ],
    mingdao: [
        '定义', '常量', '就是', '就是函', '定义宏', '就是宏',
        '如果', '那么', '否则', '否则若', '对于', '从', '到',
        '对于每个', '当满足', '跳出', '继续', '返回',
        '列表', '元组', '字典', '索引', '长度',
        '等于', '不等', '大于', '小于', '大于等于', '小于等于',
        '加', '减', '乘', '除', '模', '幂',
        '非', '与', '或',
        '导入', '导出', '模块',
        '赋值', '打印', '生成', '捕获',
        '匿名函数', '做当满足',
    ],
    hanyu: [
        '定义', '函数', '返回', '如果', '那么', '否则',
        '循环', '当满', '对于', '跳出', '继续', '导入',
        '宏用', '结构',
        '空值', '整数', '实数', '字符串', '布尔', '产出',
        '在', '真', '假', '负', '为',
        '小于等于', '大于等于',
        '等于', '不等', '大于', '小于', '大于等', '小于等',
        '并且', '或者', '右移', '左移',
        '加', '减', '乘', '除', '余', '等', '负', '取',
        '打印', '长度', '调用',
    ],
    traeyan: [
        '定', '设', '函', '若', '则', '否则', '否则若',
        '当', '每', '遍历', '重复', '从', '到',
        '真', '假', '空',
        '尝试', '捕获', '最终', '抛出', '异常',
        '导入', '匹配', '例', '其他',
        '返回', '断', '继', '结束', '完',
        '加', '减', '乘', '除', '模', '幂',
        '大', '小', '等', '不等于',
        '且', '或', '非', '负',
        '加等于', '减等于', '乘等于', '除等于', '模等于', '幂等于',
        '数', '符', '串', '布', '列', '集',
        '印', '结构体',
    ],
};

function registerCompletionProviders(context) {
    for (const [langId, keywords] of Object.entries(KEYWORDS)) {
        if (keywords.length === 0) continue;

        const provider = vscode.languages.registerCompletionItemProvider(
            { scheme: 'file', language: langId },
            {
                provideCompletionItems(document, position) {
                    return keywords.map(kw => {
                        const item = new vscode.CompletionItem(kw, vscode.CompletionItemKind.Keyword);
                        item.detail = `${LANGUAGES.find(l => l.id === langId)?.name || langId} 关键字`;
                        return item;
                    });
                },
            },
            ' ', '.', '（'
        );

        context.subscriptions.push(provider);
    }
}

// ---- 运行文件 ----

function runFile() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showWarningMessage('没有打开的文件');
        return;
    }

    const filePath = editor.document.uri.fsPath;
    const langId = editor.document.languageId;
    const langInfo = LANGUAGES.find(l => l.id === langId);

    if (!langInfo) {
        vscode.window.showWarningMessage(`不支持的语言: ${langId}`);
        return;
    }

    const terminal = vscode.window.createTerminal(`言埠 — ${langInfo.name}`);
    terminal.show();
    terminal.sendText(`yanpub run ${langId} "${filePath}"`);
}

// ---- 启动 REPL ----

function startREPL() {
    const editor = vscode.window.activeTextEditor;
    const langId = editor ? editor.document.languageId : null;
    const langInfo = langId ? LANGUAGES.find(l => l.id === langId) : null;

    const items = LANGUAGES.map(l => ({
        label: `${l.name} (${l.id})`,
        id: l.id,
    }));

    if (langInfo) {
        const quickPick = vscode.window.createQuickPick();
        quickPick.items = items;
        quickPick.placeholder = `当前语言: ${langInfo.name}，选择要启动 REPL 的语言`;
        quickPick.onDidAccept(() => {
            const selected = quickPick.selectedItems[0];
            if (selected) {
                const terminal = vscode.window.createTerminal(`言埠 REPL — ${selected.label}`);
                terminal.show();
                terminal.sendText(`yanpub repl ${selected.id}`);
            }
            quickPick.hide();
        });
        quickPick.show();
    } else {
        const terminal = vscode.window.createTerminal('言埠 REPL');
        terminal.show();
        terminal.sendText('yanpub repl');
    }
}

// ---- 选择语言 ----

function selectLanguage() {
    const items = LANGUAGES.map(l => ({
        label: l.name,
        description: l.id,
        detail: l.extensions.join(', '),
    }));

    vscode.window.showQuickPick(items, {
        placeHolder: '选择中文编程语言',
    }).then(item => {
        if (item) {
            vscode.window.showInformationMessage(`已选择 ${item.label} (${item.description})`);
        }
    });
}

// ---- 激活 ----

function activate(context) {
    // 注册命令
    context.subscriptions.push(
        vscode.commands.registerCommand('yanpub.runFile', runFile),
        vscode.commands.registerCommand('yanpub.startREPL', startREPL),
        vscode.commands.registerCommand('yanpub.selectLanguage', selectLanguage),
    );

    // 注册内置关键字补全
    registerCompletionProviders(context);

    // 启动 LSP（如果可用）
    startLSP(context);

    // 状态栏
    const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusItem.text = '言埠';
    statusItem.tooltip = '言埠 YanPub — 中文编程语言工具链';
    statusItem.command = 'yanpub.selectLanguage';
    statusItem.show();
    context.subscriptions.push(statusItem);
}

function deactivate() {
    if (lspClient) {
        return lspClient.stop();
    }
}

module.exports = { activate, deactivate };
