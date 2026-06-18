# 言埠 YanPub

> 万言归埠，一站集成。

中文编程语言统一基础设施。一个框架，接入任意中文语言，即刻获得完整工具链。

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
| 言 Yan | yan | 1.0.0 | 47 | 子进程 |
| 墨言 Moyan | moyan | 0.1.0 | 25 | 子进程 |
| 心语 Xinyu | xinyu | 0.1.0 | 46 | 子进程 |
| 知行 Zhixing | zhixing | 0.1.0 | 37 | 子进程 |
| 言律 Yanlv | yanlv | 2.0.0 | 62 | 子进程 |
| 言知 Yanzhi | yanzhi | 0.1.0 | 52 | 子进程 |
| 明道 Mingdao | mingdao | 0.1.0 | 47 | 子进程(Racket) |
| 翰语 Hanyu | hanyu | 0.1.0 | 48 | 子进程(LLVM) |
| 趣言 traeyan | traeyan | 0.1.0 | 119 | 子进程 |

## 架构

详见 [DESIGN.md](DESIGN.md)

```
yanpub
├── core/          # 核心抽象：适配器协议、注册中心
├── adapters/      # 各语言适配器（10种）
├── pkg/           # 统一包管理器
├── playground/    # 统一 Playground
├── lsp/           # 统一 LSP 服务
├── repl/          # 统一 REPL
├── docs/          # 统一文档系统 + 语言对比
└── vscode/        # VSCode 扩展
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

## 适配器开发

创建一个新适配器只需 2 个文件：

```bash
adapters/mylang/
├── adapter.yaml    # 语言元信息
└── adapter.py      # 适配器实现（继承 SubprocessAdapter）
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

适配器会被自动发现和加载，无需额外注册。

## 性能

- 启动时间 ~0.24s（10个适配器懒加载）
- 关键字首次访问 ~0.38s（动态从项目加载），缓存后 0s
- 932 个测试全部通过

## License

MIT
