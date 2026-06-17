# 言埠 YanPub — VSCode 扩展

统一中文编程语言工具链：语法高亮、代码补全、诊断、格式化、调试、AI 辅助、沙箱执行。

一个扩展支持所有中文编程语言。

## 支持的语言

| 语言 ID   | 名称       | 扩展名              |
|-----------|-----------|---------------------|
| duan      | 段言       | `.段` `.duan`       |
| yan       | 言         | `.言` `.yan`        |
| moyan     | 墨言       | `.墨` `.moyan`      |
| xinyu     | 心语       | `.心` `.xinyu`      |
| zhixing   | 知行       | `.行` `.zhixing`    |
| yanlv     | 言律       | `.律` `.yanlv`      |
| yanzhi    | 言知       | `.知` `.yanzhi`     |
| mingdao   | 明道       | `.道` `.mingdao`    |
| hanyu     | 翰语       | `.翰` `.hanyu`      |
| traeyan   | 知行语言   | `.trae` `.traeyan`  |

## 功能

### 基础功能

- **语法高亮** — 所有支持语言的关键字、字符串、注释高亮
- **关键字补全** — 内置关键字自动补全
- **LSP 集成** — 连接言埠 LSP 服务器，提供补全/诊断/悬停
- **运行文件** — 编辑器标题栏运行按钮
- **REPL** — 启动交互式环境
- **代码片段** — 段言代码片段

### 调试适配器集成

连接 yanpub DAP 服务器，支持：

- 按 **F5** 启动调试
- 断点设置与命中
- 单步执行（步过/步入/步出）
- 变量查看与表达式求值
- 调用栈追踪

调试配置示例（`.vscode/launch.json`）：

```json
{
    "type": "yanpub",
    "request": "launch",
    "name": "调试当前文件",
    "program": "${file}",
    "stopOnEntry": false
}
```

### AI 辅助面板

- **智能补全** — 基于上下文的 AI 补全建议（`yanpub.ai.complete`）
- **自然语言转代码** — 输入中文描述生成代码（`yanpub.ai.nl2code`）
- **错误修复建议** — 检测错误并提供修复方案（`yanpub.ai.fix`）

AI 辅助优先使用 Playground API，不可用时自动 fallback 到 CLI，最终 fallback 到内置规则。

### 沙箱执行

在安全隔离环境中执行代码（`yanpub.sandbox.run`）：

- **Docker/Podman** — 容器化沙箱（推荐）
- **FreeBSD jail** — FreeBSD 系统沙箱
- **进程沙箱** — 无容器依赖的 fallback

## 配置

| 配置项                   | 类型     | 默认值                    | 说明                      |
|-------------------------|---------|--------------------------|--------------------------|
| `yanpub.lsp.enabled`    | boolean | `true`                   | 启用 LSP 语言服务          |
| `yanpub.lsp.path`       | string  | `"yanpub"`               | yanpub 可执行文件路径       |
| `yanpub.lsp.port`       | number  | `2087`                   | LSP 服务端口               |
| `yanpub.dap.port`       | number  | `4711`                   | DAP 调试端口               |
| `yanpub.sandbox.backend`| string  | `"auto"`                 | 沙箱后端（auto/docker/podman/freebsd_jail/process） |
| `yanpub.ai.provider`    | string  | `"local"`                | AI 辅助引擎提供者           |
| `yanpub.playground.url` | string  | `"http://127.0.0.1:8000"` | Playground 服务 URL        |

## 命令

| 命令                    | 说明              |
|------------------------|-------------------|
| `yanpub.runFile`       | 运行当前文件        |
| `yanpub.startREPL`     | 启动 REPL          |
| `yanpub.selectLanguage`| 选择语言            |
| `yanpub.sandbox.run`   | 在沙箱中执行        |
| `yanpub.ai.complete`   | AI 智能补全        |
| `yanpub.ai.nl2code`    | 自然语言转代码      |
| `yanpub.ai.fix`        | 错误修复建议       |
| `yanpub.debug.start`   | 启动调试           |

## 依赖

- **yanpub** CLI — 核心运行时和工具链
- **yanpub DAP 服务器** — 调试协议服务器（端口 4711）
- **Playground 服务**（可选）— AI 辅助 API 端点

## 安装

```bash
# 确保 yanpub 已安装
pip install yanpub

# 打包扩展
cd src/yanpub/vscode
npm install
npx vsce package

# 安装 .vsix 文件
code --install-extension yanpub-0.9.0.vsix
```

## 许可证

MIT
