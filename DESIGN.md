# 言埠 YanPub — 中文编程语言统一基础设施

> **言埠**：万言归埠，一站集成。

## 一、问题与动机

当前中文编程语言生态面临严重的**重复建设**问题：

| 共性需求 | 重复实现次数 | 现状 |
|----------|-------------|------|
| Playground/在线IDE | 8/10 项目各写一套 | Flask/纯前端/WASM 各异 |
| REPL | 7/10 项目各写一套 | prompt_toolkit/readline/自建 各异 |
| 包管理器 | 5/10 项目各写一套 | Git协议/本地注册表/发布流程 各异 |
| LSP 服务 | 4/10 项目各写一套 | 补全/诊断/格式化逻辑重复 |
| VSCode 扩展 | 6/10 项目各写一套 | 语法高亮+补全+代码片段模式雷同 |
| 文档系统 | 10/10 项目各写一套 | Markdown渲染+搜索 无共享 |
| 测试框架 | 10/10 项目各写一套 | pytest配置+运行器 无统一 |

**核心洞察**：这些语言只有**语法和语义**不同，而工具链的 80% 是完全相同的逻辑。

## 二、设计理念

### 核心原则

1. **语言即插件** — 每种中文语言只需实现一个轻量适配器，即可获得完整工具链
2. **约定优于配置** — 适配器只需声明差异，相同部分零配置
3. **渐进式采用** — 可以只用 Playground，也可以全套接入
4. **不侵入原有项目** — yanpub 是独立进程，通过适配器协议与语言后端通信

### 架构风格

```
┌─────────────────────────────────────────────┐
│                  yanpub                      │
│  ┌─────┐ ┌──────┐ ┌─────┐ ┌─────┐ ┌─────┐  │
│  │ Pkg │ │Playgr│ │ LSP │ │REPL │ │Docs │   │
│  │ Mgr │ │ ound │ │     │ │     │ │     │   │
│  └──┬──┘ └──┬───┘ └──┬──┘ └──┬──┘ └──┬──┘  │
│     └───────┴────────┴───────┴───────┘      │
│              Language Adapter Protocol        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  │ 言   │ │知行  │ │段言  │ │心语  │ ...     │
│  └──────┘ └──────┘ └──────┘ └──────┘        │
└─────────────────────────────────────────────┘
```

## 三、语言适配器协议（LAP）

这是整个项目最核心的设计。每种语言只需实现以下接口：

### 3.1 适配器接口（Python ABC）

```python
from yanpub.core.adapter import LanguageAdapter, SubprocessAdapter

class LanguageAdapter(ABC):
    """语言适配器抽象基类"""

    # 元信息（必须实现）
    name: str              # "段言"
    id: str                # "duan"
    version: str           # "1.3.8"
    file_extensions: list  # [".段", ".duan"]

    # 品牌（可选覆盖）
    description: str       # 语言简介
    primary_color: str     # 品牌主色 "#E85D3A"
    comment_syntax: str    # 注释语法 "#"

    # 执行（必须实现）
    def run(self, file_path, args=None) -> ExecutionResult: ...
    def eval(self, code) -> ExecutionResult: ...

    # LSP 支持（可选）
    def complete(self, code, line, column) -> list[CompletionItem]: ...
    def diagnose(self, code) -> list[Diagnostic]: ...

    # 关键字（推荐覆盖）
    keywords: list[str]    # 用于语法高亮和补全

    # REPL（可选）
    repl_prompt: str       # "段言> "
    repl_welcome: str      # 欢迎信息
```

### 3.2 SubprocessAdapter — 最常用基类

绝大多数适配器只需继承 `SubprocessAdapter`，声明运行命令即可：

```python
from yanpub.core.adapter import SubprocessAdapter

class DuanAdapter(SubprocessAdapter):
    def __init__(self):
        super().__init__(
            name="段言",
            lang_id="duan",
            version="1.3.8",
            extensions=[".段", ".duan"],
            run_command=["python", "cli/duan.py", "run"],
            eval_command=None,          # 无 eval 子命令，自动用临时文件 fallback
            eval_mode="stdin",          # "stdin"(默认) | "arg"(代码作为命令行参数)
            repl_command=None,
            keywords_loader=_load_keywords,  # 懒加载：首次访问时才执行
            primary_color="#E85D3A",
        )
```

**关键特性**：
- `keywords_loader` 支持懒加载，避免启动时加载所有关键字文件
- `eval_command=None` 时自动使用临时文件 fallback
- `eval_mode` 控制代码传递方式：`"stdin"` 通过标准输入，`"arg"` 追加为命令行参数
- 所有子进程调用统一处理编码（`utf-8` + `errors="replace"`）+ `PYTHONIOENCODING=utf-8`
- Racket 适配器（明道）需 override `eval()` 预置 `#lang mingdao` 行

### 3.3 适配器自动发现

适配器放在 `src/yanpub/adapters/<lang_id>/` 目录下，包含 `adapter.yaml` + `adapter.py` 即可被自动发现和加载。

排除框架基类（`BaseAdapter`/`SubprocessAdapter`/`InProcessAdapter`/`HTTPAdapter`），只取用户适配器子类。

### 3.4 适配器配置（adapter.yaml）

```yaml
name: 段言
id: duan
version: "1.3.8"

backend:
  type: subprocess
  command: "python"

syntax:
  file_extensions: [".段", ".duan"]
  comment_syntax: "#"

execution:
  run: "python cli/duan.py run {file}"
  eval: "python cli/duan.py eval {code}"
  repl: "python cli/duan.py repl"

capabilities:
  repl: true
  lsp: true
  package_manager: false

colors:
  primary: "#E85D3A"
  secondary: "#FFB347"
  accent: "#2C3E50"
```

## 四、六大共享模块

### 4.1 统一包管理器（YanPkg）

**实现文件**：`pkg/registry.py` + `pkg/resolver.py` + `pkg/installer.py` + `pkg/cache.py`

**核心特性**：
- **语言隔离**：每个语言的包独立命名空间 `duan:web-framework`、`yan:math-utils`
- **跨语言依赖**：`duan:web-framework` 可声明依赖 `yan:http-core`
- **依赖解析**：基于 semver 的解析器，支持 `>=` / `^` / `~` 版本约束
- **本地缓存**：包安装后缓存到 `~/.yanpub/cache/`

**包描述文件（yanpkg.toml）**：

```toml
[package]
name = "web-framework"
lang = "duan"
version = "0.2.0"
description = "段言Web开发框架"

[dependencies]
"duan:http-core" = ">=0.1.0"
"yan:json-utils" = "^1.0.0"
```

### 4.2 统一 Playground（YanPlay）

**实现文件**：`playground/server.py` + `playground/static/index.html`

**技术选型**：
- 后端：FastAPI + WebSocket
- 前端：CodeMirror 5（CDN 加载，无需构建）
- 自定义 `createChineseLangMode()` 函数，根据适配器 keywords 动态生成高亮模式

**核心交互**：

```
用户选择"段言" → 前端加载段言语法高亮+品牌主题
用户输入代码 → WebSocket 发送 {lang:"duan", code:"..."}
后端路由到 duan 适配器 → 执行 → 返回结果
用户切换到"言" → 语法高亮切换 → REPL 重置 → 代码保留
```

### 4.3 统一 LSP 服务（YanLSP）

**实现文件**：`lsp/server.py`

**技术选型**：pygls 2.x（`from pygls.lsp.server import LanguageServer`）

**支持能力**：
- 关键字补全（基于适配器 `keywords` 属性）
- 代码诊断（基于适配器 `eval` 结果）
- 文档追踪（`TEXT_DID_OPEN` / `TEXT_DID_CHANGE`）
- TCP 和 stdio 两种模式

### 4.4 统一 REPL（YanREPL）

**实现文件**：`repl/core.py`

**技术选型**：prompt_toolkit

**核心类**：
- `ChineseLangLexer` — 中文关键字语法高亮
- `REPLCompleter` — 命令补全（`:help`/`:langs`）+ 关键字补全
- `YanREPL` — REPL 主循环，支持 `:lang` 热切换

**内置命令**：
- `:help` — 帮助
- `:quit` / `:exit` — 退出
- `:langs` — 列出可用语言
- `:keywords` — 列出当前语言关键字
- `:lang <id>` — 切换语言

### 4.5 统一文档站（YanDocs）

**实现文件**：`docs/generator.py` + `docs/site_builder.py` + `docs/comparator.py`

**技术选型**：自建 HTML 生成器（非 MkDocs），暗色主题

**核心能力**：
- **文档生成器** — 从适配器提取关键字索引、语言概览、对比表
- **站点构建器** — 生成静态 HTML（首页 + 10个语言详情页 + data.json API）
- **语言对比器** — Jaccard 相似度计算、概念映射、迁移指南生成

**关键字自动分类**：16个概念分组（定义/函数/控制流/异常/模块/运算/IO/类与对象/函数式等）

### 4.6 统一 VSCode 扩展（YanVSCode）

**实现文件**：`vscode/src/extension.js` + `vscode/package.json` + `vscode/grammars/` + `vscode/snippets/`

**技术选型**：纯 JavaScript（无需 TypeScript 编译）

**核心设计**：
- 一个扩展注册所有 10 种语言
- 内置关键字补全作为 fallback（LSP 不可用时也能工作）
- LSP 作为增强层（TCP 模式）
- TextMate 语法文件：duan / yan / moyan
- 代码片段：duan（13个）

## 五、项目目录结构（v0.6.0 实际）

```
yanpub/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── .gitignore
│
├── src/yanpub/
│   ├── __init__.py              # 导出核心 API（9个符号）
│   ├── cli.py                   # 统一 CLI 入口（28个子命令 + 适配器热重载 + 工作空间）
│   │
│   ├── core/                    # 核心抽象
│   │   ├── adapter.py           # LanguageAdapter ABC + SubprocessAdapter + hover() + format() + rename()
│   │   ├── registry.py          # 语言注册中心 + 自动发现
│   │   ├── config.py            # 配置管理
│   │   ├── keyword_docs.py      # 关键字分类/描述/hover 文档
│   │   ├── formatter.py         # 代码格式化器
│   │   ├── health.py            # 适配器健康检查
│   │   ├── benchmark.py         # 性能基准测试
│   │   ├── compat.py            # 适配器兼容性矩阵（v0.4.0 新增）
│   │   ├── plugin.py            # 插件系统（v0.4.0 新增）
│   │   ├── bench_viz.py         # 性能调优面板（v0.5.0 新增）
│   │   ├── wasm.py              # WASM 执行器（v0.5.0 新增）
│   │   ├── hotreload.py         # 适配器热重载（v0.6.0 新增）
│   │   └── profiler.py          # 适配器性能分析器（v0.7.0 新增）
│   │
│   ├── adapters/                # 10个语言适配器
│   │   ├── _keywords_cache.py   #   关键字缓存工具
│   │   ├── duan/                #   adapter.yaml + adapter.py + keywords.json
│   │   ├── yan/                 #   adapter.yaml + adapter.py + keywords.json
│   │   ├── moyan/               #   adapter.yaml + adapter.py + keywords.json
│   │   ├── xinyu/               #   adapter.yaml + adapter.py + keywords.json
│   │   ├── zhixing/             #   adapter.yaml + adapter.py + keywords.json
│   │   ├── yanlv/               #   adapter.yaml + adapter.py + keywords.json
│   │   ├── yanzhi/              #   adapter.yaml + adapter.py + keywords.json
│   │   ├── mingdao/             #   adapter.yaml + adapter.py + keywords.json
│   │   ├── hanyu/               #   adapter.yaml + adapter.py + keywords.json
│   │   └── traeyan/             #   adapter.yaml + adapter.py + keywords.json
│   │
│   ├── pkg/                     # 统一包管理器
│   │   ├── registry.py          #   包注册中心
│   │   ├── resolver.py          #   依赖解析器
│   │   ├── installer.py         #   安装器
│   │   ├── cache.py             #   本地缓存
│   │   ├── remote.py            #   远程注册中心
│   │   ├── lockfile.py          #   依赖锁定管理（v0.4.0 新增）
│   │   ├── semantic_release.py  #   语义发布（v0.5.0 新增）
│   │   ├── workspace.py         #   工作空间管理（v0.6.0 新增）
│   │   └── versionset.py        #   版本工作集（v0.7.0 新增）
│   │
│   ├── playground/              # 统一 Playground
│   │   ├── server.py            #   FastAPI + WebSocket 后端（含分享API + WASM + 协作API）
│   │   ├── collab.py            #   实时协作 CRDT + 房间管理（v0.6.0 新增）
│   │   ├── static/index.html    #   CodeMirror 5 前端（含对比+分享+WASM+协作模式）
│   │   └── templates/           #   各语言示例模板
│   │
│   ├── lsp/                     # 统一 LSP 服务
│   │   └── server.py            #   pygls 2.x 服务端（含 hover + 格式化 + rename + codeAction + codeLens + 折叠 + 语义高亮）
│   │
│   ├── repl/                    # 统一 REPL
│   │   ├── core.py              #   prompt_toolkit REPL + 高亮 + 补全 + 多行续行
│   │   └── error_display.py     #   友好错误提示
│   │
│   ├── docs/                    # 统一文档系统
│   │   ├── generator.py         #   文档数据生成（使用公共 keyword_docs）
│   │   ├── site_builder.py      #   静态 HTML 站点构建
│   │   └── comparator.py        #   语言对比 + 相似度 + 迁移指南
│   │
│   ├── i18n.py                  #   国际化框架
│   │
│   └── vscode/                  # VSCode 扩展
│       ├── src/extension.js     #   纯 JS 扩展入口
│       ├── grammars/            #   TextMate 语法（10种语言）
│       ├── snippets/duan.json   #   段言代码片段
│       └── package.json         #   contributes 10种语言 + 10个语法
│
├── tests/                       # 494 个测试
│   ├── test_adapter.py          #   16 个
│   ├── test_integration.py      #   16 个
│   ├── test_pkg.py              #   25 个
│   ├── test_playground.py       #   11 个
│   ├── test_lsp.py              #   18 个
│   ├── test_repl.py             #   27 个
│   ├── test_docs.py             #   33 个
│   ├── test_e2e.py              #   26 个
│   ├── test_adapter_e2e.py      #   58 个（适配器端到端验证，1个traeyan skip）
│   ├── test_v020.py             #   26 个（v0.2.0 新增）
│   ├── test_v030.py             #   56 个（v0.3.0 新增）
│   ├── test_v040.py             #   40 个（v0.4.0 新增）
│   ├── test_v050.py             #   68 个（v0.5.0 新增）
│   ├── test_v060.py             #   38 个（v0.6.0 新增）
│   └── test_v070.py             #   31 个（v0.7.0 新增）
│
├── scripts/                     # 工具脚本
│   ├── cache_keywords.py        #   关键字预缓存
│   └── release.py               #   PyPI 发布
│
├── .github/workflows/           # CI/CD
│   └── ci.yml                   #   GitHub Actions
│
└── docs/
    └── adapter-guide.md         # 适配器开发指南
```

## 六、已接入语言（10种）

| 语言 | ID | 版本 | 关键字 | 适配方式 | eval模式 | 特色 |
|------|----|------|--------|----------|----------|------|
| 段言 Duan | duan | 1.3.8 | 162 | 子进程 | fallback | 段落式语法、类定义、模块系统 |
| 言 Yan | yan | 3.0.0 | 47 | 子进程 | arg(-e) | newlisp 自举、WASM 支持 |
| 墨言 Moyan | moyan | 0.1.0 | 25 | 子进程 | arg(--vm -e) | `--` 注释、`$"..."` 插值、并发 |
| 心语 Xinyu | xinyu | 0.1.0 | 46 | 子进程 | arg(-c) | 安全沙箱、双字/单字关键字 |
| 知行 Zhixing | zhixing | 0.1.0 | 37 | 子进程 | arg(-c) | 管道式语法 |
| 言律 YanLv | yanlv | 2.0.0 | 62 | 子进程 | fallback | 意合式编程、jieba 分词 |
| 言知 Yanzhi | yanzhi | 0.1.0 | 52 | 子进程 | arg(-c) | 字节码 VM、模式匹配、宏系统 |
| 明道 Mingdao | mingdao | 0.1.0 | 47 | 子进程(Racket) | fallback(#lang) | SVO 调用语法、卫生宏 |
| 翰语 Hanyu | hanyu | 0.1.0 | 47 | 子进程(LLVM) | fallback | LLVM IR、Tree-sitter、WASM |
| 知行语言 Traeyan | traeyan | 0.1.0 | 119 | 子进程 | fallback | THULAC 分词、动词吞噬、百家姓标识符 |

**语言相似度 TOP 5**：

1. 心语 ↔ 知行：38.3%（23个共享关键字）
2. 心语 ↔ 言知：28.9%（22个共享关键字）
3. 翰语 ↔ 明道：28.8%（21个共享关键字）
4. 翰语 ↔ 心语：27.4%（20个共享关键字）
5. 明道 ↔ 心语：27.4%（20个共享关键字）

## 七、技术选型

| 组件 | 技术选型 | 理由 |
|------|----------|------|
| 核心框架 | Python 3.10+ | 9/10 语言后端是 Python |
| CLI | Click | Python 生态主流，装饰器式 API |
| 包管理器 | toml + Git | 轻量、语言无关 |
| Playground 后端 | FastAPI + WebSocket | 异步、高性能 |
| Playground 前端 | CodeMirror 5（CDN） | 零构建、中文高亮易扩展、支持对比模式 |
| LSP | pygls 2.x | Python LSP 框架标准 |
| LSP hover | 关键字最长匹配 + 分类文档 | 中文语言无空格分词，需基于关键字表匹配 |
| REPL | prompt_toolkit | 功能最强，支持自定义 Lexer + 多行续行 |
| 文档站 | 自建 HTML 生成器 | 轻量无依赖，暗色主题 |
| VSCode 扩展 | 纯 JavaScript | 无需编译，LSP fallback |
| 关键字缓存 | JSON 预缓存 + 懒加载回退 | 减少对原项目路径依赖，缓存优先 |
| 代码格式化 | 关键字规则 + 缩进推断 | 中文语言通用格式化，基于块关键字推断缩进 |
| 错误提示 | parse_error + ANSI 高亮 | 解析 Python/中文语言错误，友好中文提示 |
| 远程注册中心 | Git 仓库索引 + 本地缓存 | 无需自建服务器，利用 Git 生态 |
| 健康检查 | 四维检查（命令/关键字/执行/LSP） | 一键诊断后端可用性 |
| 基准测试 | 四项基准（启动/关键字/执行/吞吐量） | 量化性能，对比优化 |
| 国际化 | 纯 dict + t() 函数 | 零依赖，中英双语 40+ 消息键 |
| 符号重命名 | CJK 单字符 + ASCII 双模式 | 统一 is_ident_char 扩展 | 中文编程语言中汉字是独立 token，不能链式扩展 |
| 依赖锁定 | LockManager + sha256 哈希 | 纯文本 lock 文件 | 保证可复现构建，哈希校验完整性 |
| 兼容性矩阵 | 四维检查（API/关键字/LSP/版本） | 单一版本检查 | 适配器质量分层，支持 partial 兼容 |
| 插件系统 | importlib 动态加载 + 7个钩子 | 静态注册 | 第三方扩展无需修改核心代码 |
| LSP 代码透镜 | pygls CodeLens + 行内操作按钮 | 无 | 编辑器内直接运行/查看输出 |
| 语义发布 | SemanticVersion + ConventionalCommits | 手动版本号 | 自动版本递增 + Changelog 生成 |
| 性能调优面板 | HTML 可视化 + 历史快照 + 回归检测 | 纯文本报告 | 交互式对比 + 自动检测性能回归 |
| WASM 执行 | WasmExecutor + Pyodide + 多运行时 | 仅子进程 | 浏览器端执行 + 降级策略 |
| 代码折叠 | 块关键字栈追踪 + 缩进推断 | 纯缩进 | 中文语言需语义识别块边界 |
| 适配器热重载 | watchdog + 轮询回退 | 手动重启 | 开发时实时反馈，零停机更新 |
| 工作空间 | workspace.toml + glob 发现 | 单包管理 | monorepo 多包统一管理 |
| 实时协作 | CRDT (RGA) + WebSocket | OT | 无中心服务器冲突解决，最终一致性 |
| 语义高亮 | LSP Semantic Tokens + delta 编码 | TextMate 语法 | 更精细的语义分类，支持适配器自定义 token |
| 性能分析器 | AdapterProfiler + FlameGraph + HotspotDetector | 纯计时 | 多维度统计 + 可视化 + 热点检测 |
| 版本工作集 | VersionConstraint + WorkspaceLock + TOML | 单包锁定 | 工作空间级别统一版本管理 |
| 构建打包 | Hatch | 现代 Python 打包工具 |
| CI/CD | GitHub Actions | 多平台（Ubuntu/Windows/macOS）多版本（3.10/3.11/3.12） |

## 八、开发里程碑

### Phase 1：基础框架 + 第一个适配器跑通 ✅

- [x] 核心抽象层：`LanguageAdapter` 协议 + 适配器加载器
- [x] CLI 框架：`yanpub run` / `yanpub repl`
- [x] 段言适配器：能通过 yanpub 运行段言代码
- [x] 验证：`yanpub run duan hello.duan` 成功执行

### Phase 2：包管理器 + Playground ✅

- [x] 统一包管理器核心：注册/安装/依赖解析/缓存
- [x] Playground 后端：FastAPI + WebSocket
- [x] Playground 前端：CodeMirror 编辑器 + 语言切换
- [x] CLI `yanpub pkg` 子命令

### Phase 3：LSP + REPL + VSCode ✅

- [x] 通用 LSP 服务：补全/诊断（pygls 2.x）
- [x] 统一 REPL：prompt_toolkit + 语法高亮 + 补全 + 语言热切换
- [x] VSCode 扩展：10种语言注册 + 3个语法文件 + 段言代码片段
- [x] TextMate 语法：duan / yan / moyan

### Phase 4：适配器扩展 + 文档站 ✅

- [x] 7个新适配器：心语/知行/言律/明道/言知/知行语言/翰语
- [x] 统一文档站：静态 HTML 生成 + 10个语言详情页
- [x] 语言对比：Jaccard 相似度 + 概念映射 + 迁移指南
- [x] CLI `yanpub compare` / `yanpub docs` 子命令

### Phase 5：打磨与发布 ✅

- [x] 端到端测试：26个（CLI全命令 + Playground + Docs + 性能）
- [x] ruff lint 零错误（15处未使用导入修复）
- [x] 适配器懒加载优化：启动 0.567s → 0.241s（-57%）
- [x] pyproject.toml 完善（classifiers / optional-deps all）
- [x] README 更新（10语言状态表 + CLI 命令一览）
- [x] __init__.py 导出核心 API
- [x] v0.1.0 发布就绪

### Phase 6：v0.2.0 功能增强 ✅

- [x] 关键字预缓存机制：adapters/<lang>/keywords.json + load_cached_keywords()
- [x] Playground 多语言对比模式：左右分栏 + 独立语言选择 + 同时运行
- [x] LSP hover 文档支持：基于关键字分类的最长匹配 + Markdown 文档
- [x] REPL 多行输入智能续行：未闭合引号/括号/块关键字自动续行
- [x] 包管理器发布验证：semver 格式检查 + 包名验证 + 版本降级检测
- [x] 7个新 TextMate 语法文件：xinyu/yanlv/yanzhi/zhixing/mingdao/hanyu/traeyan
- [x] CI/CD 自动化测试：GitHub Actions（3 OS × 3 Python 版本）
- [x] PyPI 发布准备：v0.2.0、发布脚本 scripts/release.py
- [x] 关键字分类公共模块：core/keyword_docs.py（供 LSP/docs/comparator 共用）
- [x] 203个测试全部通过（177原有 + 26新增）
- [x] ruff lint 零错误

### Phase 7：v0.3.0 功能增强 ✅

- [x] Playground 代码分享：URL hash 编码 + /api/share 端点 + 分享按钮 + 自动加载分享链接
- [x] LSP 代码格式化：LanguageAdapter.format() 基础格式化规则 + ChineseCodeFormatter 进阶格式化
- [x] REPL 语法错误友好提示：parse_error() 解析 Python/中文语言错误 + format_friendly_error() ANSI 高亮
- [x] 包管理器远程注册中心：RemoteRegistry 类 + Git 仓库索引同步 + pkg sync CLI 命令
- [x] 适配器健康检查：check_adapter_health() 命令可达/关键字/执行/LSP 四维检查 + health CLI 命令
- [x] 性能基准测试套件：run_benchmarks() 启动/关键字/执行/吞吐量四项基准 + bench CLI 命令 + JSON 输出
- [x] 国际化：i18n 框架（t/get_lang/set_lang）+ 中英双语 40+ 消息键 + CLI --lang 选项 + 环境变量
- [x] 259个测试全部通过（203原有 + 56新增）
- [x] ruff lint 零错误

### Phase 8：v0.4.0 功能增强 ✅

- [x] 包管理器依赖锁定：LockManager + yanpkg.lock + 哈希完整性校验 + pkg lock/verify/unlock CLI 命令
- [x] LSP 代码重构：adapter.rename() 符号重命名（CJK 单字符识别）+ LSP rename handler + codeAction 支持
- [x] 适配器兼容性矩阵：check_compatibility() API/LSP/关键字/版本四维检查 + 兼容性评级 + compat CLI 命令
- [x] 插件系统：PluginManager + 7个生命周期钩子 + plugin install/uninstall/enable/disable CLI 命令
- [x] 299个测试全部通过（259原有 + 40新增）
- [x] ruff lint 零错误

### Phase 9：v0.5.0 功能增强 ✅

- [x] LSP 代码透镜：CodeLens 行内提示（▶ 运行文件/段落、📋 输出语句）+ CodeLensResolve + _is_block_definition 块定义识别
- [x] 包管理器语义发布：SemanticVersion 解析/比较/递增 + ConventionalCommitParser + VersionBumper + ChangelogGenerator + semantic-release/changelog/bump-version CLI 命令
- [x] 适配器性能调优面板：BenchVisualizer 交互式 HTML 报告（柱状图+雷达图+详细表格）+ BenchHistory 历史快照 + RegressionDetector 回归检测 + bench-visualize/bench-regress/bench-history CLI 命令
- [x] WASM 在线执行：WasmExecutor 多运行时支持（wasmtime/wasmer/node）+ Pyodide 配置生成 + runner HTML 生成 + WasmBuilder 构建器 + Playground WASM 模式切换 + wasm check/build/run CLI 命令
- [x] 367个测试全部通过（299原有 + 68新增）
- [x] ruff lint 零错误

### Phase 10：适配器完善 ✅

- [x] 修复断裂适配器路径：yan/moyan 改用绝对路径 `G:\atomcode\atomyan\yan.py`，zhixing 改用绝对路径 cli.py
- [x] 添加 eval_mode 参数：SubprocessAdapter 新增 `eval_mode`（"stdin"|"arg"），5个适配器使用 arg 模式
- [x] 完善关键字动态加载：yan/moyan 从 `lexer.py` 的 `KEYWORDS` frozenset 动态提取
- [x] 修复明道 eval：override `eval()` 预置 `#lang mingdao` 行解决 Racket 模块声明问题
- [x] 修复编码问题：`_exec()` 为子进程设置 `PYTHONIOENCODING=utf-8` 环境
- [x] 修复 hanyu 关键字重复：去除重复的"负"关键字
- [x] 端到端验证测试：test_adapter_e2e.py 58个测试（注册/关键字/属性/eval模式/执行/健康检查）
- [x] 8/10 适配器 eval 可用（duan/yan/moyan/xinyu/zhixing/yanlv/yanzhi/mingdao/hanyu），traeyan 待上游修复
- [x] 425个测试全部通过（367原有 + 58新增），ruff lint 零错误

### Phase 11：v0.6.0 功能增强 ✅

- [x] LSP 代码折叠：基于块关键字（段落/函数/类/当/遍历/如果/尝试）+ 冒号结尾行识别折叠区域，栈追踪嵌套块 + 缩进推断未闭合块，FoldingRangeKind.Region，`TEXT_DOCUMENT_FOLDING_RANGE` 处理器
- [x] 适配器热重载：HotReloader 管理适配器热重载生命周期（卸载→重新加载→注册），AdapterWatcher 基于 watchdog 文件监控（不可用时回退轮询模式），ReloadEvent 事件回调通知 LSP/REPL 等，adapter watch/reload CLI 命令
- [x] 包管理器工作空间：Workspace 类管理 monorepo 多包，workspace.toml 配置 + glob 成员发现，WorkspaceMember 成员间交叉依赖解析，拓扑排序构建顺序，内部/外部依赖区分，workspace init/status/list/add CLI 命令
- [x] Playground 实时协作：CollabDocument 基于 RGA（Replicated Growable Array）的 CRDT 文档模型，CharId 全局唯一标识 + Lamport 时间戳排序，CollabRoom 协作房间管理 + 用户颜色分配 + 光标广播，CollabManager 房间管理器 + WebSocket 协作路由，/api/collab/create + /ws/collab/{id} API
- [x] 463个测试全部通过（425原有 + 38新增），ruff lint 零错误

### Phase 12：v0.7.0 功能增强 ✅

- [x] Playground 协作前端集成：index.html 新增"协作"按钮 + 协作模态框（创建/加入房间）+ WebSocket 连接(collabWs) + 远程光标(CodeMirror bookmark + widgetNode) + 远程选区(TextMarker markText) + 用户列表面板 + 编辑同步(change→ops发送，接收ops→应用编辑器)
- [x] LSP 语义高亮：`TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL` 处理器 + 17种 tokenTypes + 10种 tokenModifiers + `_compute_semantic_tokens` 方法（基于 adapter.tokenize + fallback 关键字/正则分析）+ delta 编码 [deltaLine, deltaStartChar, length, tokenType, tokenMod]
- [x] 适配器性能分析器：AdapterProfiler（profile_eval/run/tokenize/complete/all）+ ProfileReport（统计 avg/min/max/median/p95 + to_table）+ FlameGraphGenerator（generate_html/generate_svg）+ HotspotDetector（critical > 1000ms / warning > 500ms）+ adapter profile CLI 命令
- [x] 包管理器版本工作集：VersionConstraint（parse >=/^/~/*/范围，matches）+ ResolvedVersion + WorkspaceLock（to_toml/from_toml）+ VersionSetManager（resolve/save_lock/load_lock/check_freshness/upgrade/apply）+ workspace lock/check-lock CLI 命令
- [x] 494个测试全部通过（463原有 + 31新增），ruff lint 零错误

## 九、关键设计决策记录

| 决策 | 选择 | 备选 | 理由 |
|------|------|------|------|
| 通信方式 | 适配器协议（子进程为主） | 纯 HTTP API | 9/10是Python，子进程更通用 |
| 包命名空间 | `lang:package` | 统一无前缀 | 避免不同语言同名包冲突 |
| 前端框架 | CodeMirror 5 CDN | React+CM6 | 零构建、快速集成 |
| 文档站 | 自建 HTML 生成 | MkDocs | 无额外依赖、暗色主题定制 |
| VSCode 扩展 | 纯 JavaScript | TypeScript | 无需编译步骤 |
| 关键字加载 | 懒加载 keywords_loader | 启动时全加载 | 启动时间降低 57% |
| 明道适配 | 子进程 + #lang mingdao | 内嵌 | Racket 运行时无法嵌入 Python，需 #lang 声明 |
| eval 模式 | eval_mode="stdin"|"arg" | 仅 stdin | CLI 传参模式 `-e`/`-c` 需 arg 模式 |
| pygls 版本 | 2.x | 1.x | 导入路径变更：`pygls.lsp.server` |

## 十、与现有项目的关系

**非替代，而是增强**：

- 各语言项目继续独立发展语法和语义
- yanpub 不修改任何现有项目代码
- 各项目可选择是否使用 yanpub 的工具链
- 适配器是桥接层，不是侵入层

**退出机制**：

- 如果某个语言项目后来自己开发了更好的 Playground，可以不再使用 yanplay
- 适配器协议是松耦合的，随时可以脱离

## 十一、已完成（v0.7.0）

- [x] LSP 代码折叠（块关键字栈追踪 + 缩进推断 + FoldingRangeKind.Region）
- [x] 适配器热重载（HotReloader + AdapterWatcher watchdog/轮询 + adapter watch/reload CLI）
- [x] 包管理器工作空间（Workspace + workspace.toml + 依赖图 + 拓扑排序 + workspace CLI）
- [x] Playground 实时协作（CRDT RGA 文档 + CollabRoom + CollabManager + WebSocket 协作）
- [x] Playground 协作前端集成（CodeMirror 5 协作插件 + 光标/选区显示 + 用户列表 + 编辑同步）
- [x] LSP 语义高亮（Semantic Tokens + 17种 tokenTypes + delta 编码）
- [x] 适配器性能分析器（AdapterProfiler + FlameGraph + HotspotDetector + profile CLI）
- [x] 包管理器版本工作集（VersionConstraint + WorkspaceLock + VersionSetManager + lock/check-lock CLI）

## 十二、已完成（v0.8.0）

- [x] LSP 代码导航（Go to Definition / Find All References / Call Hierarchy + SymbolNavigator 基于文本分析 + adapter navigate CLI）
- [x] 云端执行沙箱（SandboxManager + DockerSandbox/Podman/FreeBSDJail/ProcessSandbox 多后端 + FreeBSD jail 支持 + sandbox CLI）
- [x] Playground AI 辅助（AIAssistEngine + 智能补全 + 自然语言转代码 + 错误修复建议 + /api/ai/* 路由 + ai CLI）
- [x] 适配器调试器集成（DebugSession + LineTracer + DebugAdapter DAP协议 + DAPServer JSON-RPC over TCP + debug/dap-server CLI）

## 十三、已完成（v0.9.0）

- [x] 性能监控面板（PerformanceMonitor + MetricSeries + WebSocket 实时推送 + 回归检测 + 仪表板 HTML + /api/monitor/* + /ws/monitor + monitor CLI）
- [x] VSCode 扩展增强（feature_debug.js 调试适配器 DAP socket 4711 + feature_ai.js AI辅助 Webview + feature_sandbox.js 沙箱执行按钮 OutputChannel + 状态栏）
- [x] 多语言文档国际化（I18nManager + RuleBasedTranslator + I18nDocsGenerator + zh/en/ja/ko 四语支持 + i18n/docs-i18n CLI）
- [x] LSP 代码签名（CodeSigner + TrustStore 信任链 + AuditLog 审计日志 + HMAC-SHA256/Ed25519 + sign/verify/trust/keygen/audit CLI）

## 十四、下一步（v1.0.0 规划）

- [ ] 桌面 GUI 封装（Electron/Tauri，离线桌面应用）
- [ ] 包管理器私有注册中心（自建 Git 仓库 + 镜像同步 + 权限管理）
- [ ] LSP 增量同步（TextDocumentSyncKind.Incremental + 仅传输变更部分）
- [ ] 适配器测试框架（自动化测试套件 + 适配器兼容性验证 + 回归测试生成）
- [ ] Playground 多文件项目（多文件编辑器 + 文件树 + 项目级执行）
- [ ] 性能基线管理（基线快照 + CI 回归检测 + 性能预算）
