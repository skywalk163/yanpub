# 言埠 YanPub

> 万言归埠，一站集成。

![Adapter Quality](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/skywalk163/yanpub/gh-pages/quality-badge.json) ![CI](https://github.com/skywalk163/yanpub/actions/workflows/ci.yml/badge.svg)

中文编程语言统一基础设施。一个框架，接入任意中文语言，即刻获得完整工具链。

详细变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 问题

当前 10+ 种中文编程语言各自独立开发工具链——Playground、REPL、包管理器、LSP、VSCode 扩展、文档站——大量重复劳动。

## 方案

**语言即插件**。每种语言只需实现一个轻量适配器，即可获得：

- **YanPlay** — 统一在线 IDE，一键切换语言
- **YanPkg** — 统一包管理器，跨语言依赖
- **YanLSP** — 统一语言服务协议，自动补全/诊断
- **YanREPL** — 统一交互式环境，语言热切换
- **YanDocs** — 统一文档站，语言对比
- **YanVSCode** — 一个扩展支持所有语言

## 快速开始

```bash
# 安装
pip install -e .

# 安装 Playground/LSP 可选依赖
pip install -e ".[playground,lsp]"

# 列出所有已支持语言
yanpub languages

# 运行段言代码
yanpub run duan hello.duan

# 启动 REPL（支持语法高亮和补全）
yanpub repl duan

# 启动 Playground（浏览器在线 IDE）
yanpub playground

# 安装包
yanpub pkg install duan:web-framework

# 启动 LSP 服务
yanpub lsp duan

# 生成文档站
yanpub docs --output ./site

# 语言对比
yanpub compare
yanpub compare --from duan --to yan
```

## 已接入语言（10种）

| 语言 | ID | 版本 | 关键字 | 适配方式 |
|------|----|------|--------|----------|
| 段言 Duan | duan | 1.3.8 | 162 | 子进程 |
| 言 Yan | yan | 3.0.0 | 47 | 子进程 |
| 墨言 Moyan | moyan | 3.0.0 | 25 | 子进程 |
| 心语 Xinyu | xinyu | 1.0.0 | 46 | 子进程 |
| 知行 Zhixing | zhixing | 1.0.0 | 37 | 子进程 |
| 言律 Yanlv | yanlv | 2.0.0 | 62 | 子进程 |
| 言知 Yanzhi | yanzhi | 1.0.0 | 52 | 子进程 |
| 明道 Mingdao | mingdao | 1.0.0 | 47 | 子进程(Racket) |
| 翰语 Hanyu | hanyu | 1.0.0 | 48 | 子进程(LLVM) |
| 趣言 Traeyan | traeyan | 1.0.0 | 119 | 子进程 |

## 架构

详见 [DESIGN.md](DESIGN.md)

```
yanpub
├── core/              # 核心抽象
│   ├── adapter/       # 适配器协议、注册中心、缓存、懒加载、兼容性、健康检查
│   ├── dev/           # 调试器、DAP、格式化、Linter、重构、导航
│   ├── perf/          # 基准测试、可视化、基线管理、性能分析、监控
│   ├── security/      # 沙箱、代码签名、审计
│   └── lifecycle/     # 热重载、热更新、插件、进程池、配置
├── adapters/          # 各语言适配器（10种）
├── pkg/               # 统一包管理器（语义发布、工作空间、版本约束）
├── playground/        # 统一 Playground（协作、分享、项目、AI辅助、挑战赛）
├── lsp/               # 统一 LSP 服务（补全、导航、重构、诊断、语义高亮、折叠）
├── repl/              # 统一 REPL（友好错误提示）
├── i18n_pkg/          # 国际化（中/英/日/韩）
├── docs/              # 统一文档系统 + 语言对比 + SEO
├── cli/               # CLI 命令（24模块）
└── vscode/            # VSCode 扩展
```

## CLI 命令一览

| 命令 | 说明 |
|------|------|
| `yanpub run <lang> <file>` | 运行指定语言的代码文件 |
| `yanpub repl [lang]` | 启动交互式 REPL |
| `yanpub languages` | 列出所有已注册语言 |
| `yanpub playground` | 启动在线 Playground |
| `yanpub lsp <lang>` | 启动 LSP 服务 |
| `yanpub pkg install <pkg>` | 安装包 |
| `yanpub pkg list` | 列出已安装包 |
| `yanpub pkg search <q>` | 搜索包 |
| `yanpub pkg publish <dir>` | 发布包 |
| `yanpub docs` | 生成文档站 |
| `yanpub compare` | 语言对比（相似度排行 + 语法对比表） |
| `yanpub compare --from X --to Y` | 迁移指南 |
| `yanpub compare <concept>` | 特定概念对比 |
| `yanpub compare --matrix` | 语法对比矩阵（15概念×10语言） |
| `yanpub compare --html out.html` | 生成对比矩阵 HTML 页面 |
| `yanpub examples [lang]` | 查看/运行各语言示例代码 |
| `yanpub examples <lang> -r <name>` | 运行指定示例 |
| `yanpub examples -S <keyword>` | 按关键字搜索示例 |
| `yanpub contribute <lang>` | 贡献示例到指定语言（交互式向导） |
| `yanpub validate-examples <lang>` | 验证示例元数据和代码 |
| `yanpub adapter create` | 创建新语言适配器（交互式模板） |
| `yanpub adapter check <lang>` | 检查适配器可发现性 |
| `yanpub health` | 检查语言后端健康状态 |
| `yanpub bench` | 运行性能基准测试 |
| `yanpub bench-visualize` | 性能基准可视化（HTML 报告） |
| `yanpub lint` | 代码风格检查 |
| `yanpub sandbox` | 沙箱执行代码 |
| `yanpub sign / verify` | 代码签名/验证 |
| `yanpub i18n` | 国际化管理 |
| `yanpub quality [lang]` | 适配器质量评分（5维度，0-100分） |
| `yanpub quality --html report.html` | 生成质量报告 HTML |
| `yanpub hot-update [lang]` | 适配器热更新 |
| `yanpub debug` | 调试相关命令 |
| `yanpub ai` | AI 辅助调试 |
| `yanpub refactor <lang>` | 代码重构 |
| `yanpub workspace init` | 初始化工作空间 |
| `yanpub workspace add <lang>` | 添加语言到工作空间 |
| `yanpub workspace status` | 查看工作空间状态 |
| `yanpub challenge list` | 列出代码挑战赛题目 |
| `yanpub challenge show <id>` | 查看挑战详情 |
| `yanpub challenge submit <id> <lang>` | 提交解答 |
| `yanpub challenge leaderboard` | 查看排行榜 |
| `yanpub private-registry init` | 初始化私有注册中心 |
| `yanpub private-registry publish <dir>` | 发布包 |
| `yanpub private-registry mirror add <name> <url>` | 添加镜像 |
| `yanpub private-registry mirror sync <name>` | 同步镜像 |

## 适配器开发

使用 `adapter create` 命令一键生成完整适配器目录：

```bash
yanpub adapter create              # 交互式创建
yanpub adapter create mylang 0.1.0 .my  # 参数式创建
yanpub adapter check mylang        # 验证适配器可发现性
```

或手动创建，最少只需 2 个文件：

```bash
adapters/mylang/
├── adapter.yaml    # 语言元信息
├── adapter.py      # 适配器实现（继承 SubprocessAdapter）
└── examples/       # 示例代码（可选）
    └── hello.my    # 带 YAML front matter
```

最小适配器示例：

```python
from yanpub.core.adapter import SubprocessAdapter

class MyLangAdapter(SubprocessAdapter):
    def __init__(self):
        super().__init__(
            name="我的语言",
            lang_id="mylang",
            version="0.1.0",
            extensions=[".my"],
            run_command=["python", "-m", "mylang", "run"],
            keywords=["定义", "如果", "否则", "当", "返回"],
            primary_color="#FF6600",
        )
```

适配器会被自动发现和加载，无需额外注册。详见 [适配器开发指南](docs/adapter-guide.md)。

## 示例贡献

任何人都可以为已接入语言贡献示例代码：

```bash
# 交互式创建示例（推荐）
yanpub contribute duan

# 参数式创建
yanpub contribute duan -n sort -t "排序" -c "打印('hi')"

# 从文件读取代码
yanpub contribute duan -n hello -f code.duan

# 仅预览不写入
yanpub contribute duan --dry-run

# 验证已有示例
yanpub validate-examples duan
```

## 私有注册中心

支持私有 Git 仓库作为包索引存储，可与公网镜像（GitHub/Gitee/GitCode）双向同步：

```bash
# 初始化私有注册中心
yanpub private-registry init --url https://git.example.com/registry.git

# 发布包
yanpub private-registry publish ./my-package

# 添加公网镜像（自动同步）
yanpub private-registry mirror add github https://github.com/org/registry.git --direction bidirectional
yanpub private-registry mirror add gitee https://gitee.com/org/registry.git --auth ssh

# 同步到所有镜像
yanpub private-registry mirror sync --all

# 权限管理（基于角色）
yanpub private-registry permission grant alice owner
yanpub private-registry permission grant bob developer --scope lang:duan
```

4 种角色：**owner**（全部权限）、**maintainer**（发布+镜像管理）、**developer**（发布）、**guest**（只读）。

## 代码挑战赛

内置 6 道挑战题，支持在线评判和排行榜：

```bash
# 列出挑战
yanpub challenge list

# 查看详情
yanpub challenge show hello-world

# 提交解答
yanpub challenge submit hello-world duan --code '打印("你好，世界！")'
yanpub challenge submit fibonacci duan -f fib.duan

# 查看排行榜
yanpub challenge leaderboard
```

Playground 也提供 Web 界面和 API：

- `/challenges` — 挑战赛独立页面（题目浏览/提交/排行榜）
- `/quality` — 适配器质量评分页面（5 维度进度条/等级/改进建议）
- `/api/challenges`、`/api/challenges/{id}/submit`、`/api/leaderboard`
- `/api/quality`

## 适配器质量评分

5 维度自动评分（总分 100），S/A/B/C/D/F 等级：

| 维度 | 满分 | 检查项 |
|------|------|--------|
| 基础完整度 | 25 | adapter.py/yaml 存在、类定义、可实例化 |
| 元数据质量 | 20 | 必需字段、版本号成熟度、扩展名、颜色 |
| 示例丰富度 | 20 | 数量、front matter、多样性 |
| 文档覆盖 | 15 | README、CONTRIBUTING、关键字文档、描述 |
| 功能验证 | 20 | 关键字丰富度梯度、capabilities 覆盖、eval/run/repl 可用性 |

```bash
# 查看所有适配器评分
yanpub quality

# 查看特定适配器
yanpub quality duan

# 生成 HTML 报告
yanpub quality --html quality-report.html

# JSON 输出
yanpub quality --json

# CI 模式（生成报告文件 + 徽章数据 + PR 评论）
yanpub quality --ci
```

CI 集成：推送到 main 后自动评分并部署徽章到 gh-pages，PR 自动评论评分结果。独立 `quality.yml` workflow 监听适配器变更并检测质量回归。

## 性能

- 启动时间 ~0.24s（10个适配器懒加载）
- 关键字首次访问 ~0.38s（动态从项目加载），缓存后 0s
- **1286 个测试全部通过**
- 测试覆盖率 29%（持续提升中）

## CI/CD

- **Lint**: Ruff check + format check
- **Type Check**: mypy（渐进式引入，continue-on-error）
- **Test**: 3 OS × 3 Python 版本矩阵 + coverage 报告
- **Build**: Hatch 构建 + twine 校验
- **Quality**: 适配器质量评分 + PR 自动评论 + 回归检测
- **Release**: 标签触发构建 + PyPI 发布

## 版本历史

### v0.1.0–v0.5.0 (基础架构)
- 适配器协议与自动发现
- Playground 在线 IDE + 代码分享
- LSP 补全/诊断 + 代码格式化
- REPL 交互环境 + 友好错误提示
- 包管理器 + 远程注册中心 + 依赖锁定
- 适配器健康检查 + 性能基准测试
- 国际化 i18n 框架（中英双语）

### v0.6.0 (语义高亮)
- LSP 语义高亮（17种 tokenTypes + delta 编码）

### v0.7.0 (协作与导航)
- Playground 实时协作（CRDT RGA 文档 + WebSocket）
- LSP 代码折叠 + 代码导航（Go to Definition / Find References / Call Hierarchy）
- 适配器热重载 + 性能分析器（Flame Graph）
- 包管理器版本工作集

### v0.8.0 (WASM + 调试)
- WASM 在线执行（多运行时 + Pyodide）
- 云端执行沙箱（Docker/Podman/FreeBSDJail/ProcessSandbox）
- Playground AI 辅助（智能补全 + 自然语言转代码 + 错误修复）
- DAP 调试器（DebugSession + LineTracer + DebugAdapter）

### v0.9.0 (监控与扩展)
- 性能监控面板（WebSocket 推送 + 回归检测 + 仪表板）
- VSCode 扩展增强（DAP 调试 + AI Webview + 沙箱按钮）
- 多语言文档国际化（zh/en/ja/ko 规则翻译）
- LSP 代码签名（HMAC-SHA256 / Ed25519 + 信任链 + 审计日志）

### v1.0.0 (多文件与测试)
- Playground 多文件项目（ProjectManager + 文件树 + 多标签编辑器）
- 适配器测试框架（兼容性验证 + 回归测试生成）
- LSP 增量同步（精确增量 + 版本追踪）
- 性能基线管理（BaselineSnapshot + PerformanceBudget + CI 回归检测）

### v1.1.0 (分享与重构)
- Playground 代码分享增强（短链接 + QR 码 + 社交分享）
- LSP 代码重构增强（Extract Function / Inline Variable / Safe Rename）
- 适配器性能优化（LRU 缓存 + 延迟加载 + 连接池）
- 文档站 SEO 优化（Sitemap + OpenGraph + JSON-LD）

### v1.2.0 (质量与搜索)
- LSP 代码风格检查
- Playground 协作增强
- 适配器热更新
- 文档站搜索增强
- 示例选择器（10语言×6示例=60个 + 语言对比矩阵 15概念×10语言）

### v1.3.0 (开发体验)
- 适配器开发模板（交互式/参数式创建 + 自动验证）
- 示例贡献流水线（contribute 命令 + validate-examples + 22 个新测试）

### v1.4.0 (质量诊断)
- 项目诊断（P0/P1/P2 问题分级 + 修复建议）

### v1.5.0 (架构卫生)
- core/ 子包化（5子包+8根模块，向后兼容 re-export）
- LSP server.py 拆分（1638行→7模块 mixin 模式）
- i18n.py 拆分（671行→3模块）
- 适配器版本升级（6个 0.1.0→合理版本）
- 前端 HTML 内联 CSS/JS 提取为独立文件

### v1.6.0 (质量补齐)
- CI coverage 报告 + mypy 类型检查
- 核心模块测试补全（75 个新测试覆盖 registry/quality/cache/lazy_loader/compat/health）
- Playground API 测试补全（85 个新测试覆盖 examples/wasm/ai/monitor/challenges/quality/collab/search）
- 10 个适配器文档编写（README.md + CONTRIBUTING.md）
- 适配器质量评分提升（平均 81→84，5 个 A 级）

## License

MIT
