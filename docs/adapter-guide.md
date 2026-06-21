# 适配器开发指南

本文档介绍如何为一种中文编程语言创建 yanpub 适配器。

## 快速创建（推荐）

使用 `adapter create` 命令一键生成完整适配器目录：

```bash
# 交互式创建（推荐新手使用）
yanpub adapter create

# 参数式创建
yanpub adapter create mylang 0.1.0 .my

# 预览生成的文件（不写入磁盘）
yanpub adapter create mylang 0.1.0 .my --dry-run
```

自动生成完整目录结构：

```
adapters/mylang/
├── adapter.py          # 适配器实现（继承 SubprocessAdapter）
├── adapter.yaml        # 语言元信息
├── examples/           # 示例代码
│   └── hello.my        # 入门示例
└── CONTRIBUTING.md     # 贡献指南
```

创建后验证适配器是否可被发现：

```bash
yanpub adapter check mylang
```

## 手动创建

### 最小适配器（2 个文件）

### 1. adapter.yaml — 语言元信息

```yaml
name: 你的语言名
id: yourlang          # 唯一标识，小写英文
version: "1.0.0"

backend:
  type: subprocess    # subprocess | python | http
  command: "python"

syntax:
  file_extensions: [".your", ".yl"]
  comment_syntax: "#"

execution:
  run: "python -m yourlang run {file}"
  eval: "python -m yourlang eval {code}"
  repl: "python -m yourlang repl"

capabilities:
  repl: true
  lsp: false
  package_manager: false

colors:
  primary: "#E74C3C"
  secondary: "#3498DB"
```

### 2. adapter.py — 适配器实现

最简方式：继承 `SubprocessAdapter`

```python
from yanpub.core.adapter import SubprocessAdapter

class YourLangAdapter(SubprocessAdapter):
    def __init__(self):
        super().__init__(
            name="你的语言",
            lang_id="yourlang",
            version="1.0.0",
            extensions=[".your", ".yl"],
            run_command=["python", "-m", "yourlang", "run"],
            eval_command=["python", "-m", "yourlang", "eval"],  # 可选
            repl_command=["python", "-m", "yourlang", "repl"],  # 可选
            keywords=["定义", "如果", "返回", "循环"],           # 内联关键字
            primary_color="#E74C3C",
        )

    @property
    def comment_syntax(self) -> str:
        return "#"

    @property
    def repl_prompt(self) -> str:
        return "你的语言> "

    @property
    def repl_welcome(self) -> str:
        return f"你的语言 v{self.version} — 输入 :help 查看帮助"
```

## 关键字加载方式

### 方式一：内联关键字列表（最简单）

适用于关键字少且固定的语言：

```python
keywords=["定义", "如果", "否则", "当", "返回"],
```

### 方式二：懒加载（推荐）

适用于关键字多、需要从外部文件动态加载的语言。使用 `keywords_loader` 参数，关键字在首次访问时才加载：

```python
from pathlib import Path

_PROJECT_DIR = r"G:\path\to\yourlang"

class YourLangAdapter(SubprocessAdapter):
    def __init__(self):
        super().__init__(
            name="你的语言",
            lang_id="yourlang",
            version="1.0.0",
            extensions=[".your", ".yl"],
            run_command=["python", "-m", "yourlang", "run"],
            keywords_loader=_load_keywords,  # 传入函数引用，不调用
            primary_color="#E74C3C",
        )

def _load_keywords() -> list[str]:
    """从项目的关键字文件动态加载，首次访问时执行，之后缓存"""
    keywords_file = Path(_PROJECT_DIR) / "src" / "keywords.py"
    if not keywords_file.exists():
        return ["定义", "如果", "返回"]  # fallback

    try:
        ns: dict = {}
        exec(keywords_file.read_text(encoding="utf-8"), ns)
        return sorted(ns.get("ALL_KEYWORDS", set()))
    except Exception:
        return ["定义", "如果", "返回"]  # fallback
```

**懒加载优势**：
- 启动时不执行 `exec()` 和文件 I/O，启动速度提升 57%
- 首次访问 `adapter.keywords` 后自动缓存，后续访问零开销
- 加载失败时自动降级到 fallback 列表

## 关键字动态加载的常见模式

各语言项目的关键字存储位置不同，以下是已适配的 10 种语言的实际做法：

| 语言 | 关键字来源 | 加载方式 |
|------|-----------|---------|
| 段言 | `src/keywords.py` 的 `ALL_KEYWORDS` + `BUILTIN_TYPES` + `VERB_ARITY` | `exec` + 合并 |
| 心语 | `src/lexer/keywords.py` 的 `KEYWORDS` + `BUILTIN_FUNCTIONS` | `exec` + dict keys |
| 知行 | `src/yan/compiler/pre_tokenizer.py` 的 `KEYWORDS` + `VERBS` | `exec` + set |
| 言律 | `src/yanlv/lexer/constants.py` 的 `KEYWORDS` + `VERB_CATEGORIES` | `exec` + dict keys |
| 言知 | `src/yanzhi/compiler/pre_tokenizer.py` 的 `KEYWORDS` + `VERBS` | `exec` + set |
| 趣言 | `traeyan/parser.py` 的 `TokenType` + `traeyan/lexer.py` 的 `VERB_ARITY` | `exec` + 多文件 |
| 翰语 | `src/hanyu/lexer.py` 的 `KEYWORDS` + `SINGLE_CJK_KEYWORDS` + `BUILTIN_FUNCTIONS` | `exec` + dict keys |
| 明道 | Racket tokenizer 无法 `exec` | 硬编码 fallback 列表 |
| 言 / 墨言 | 关键字少且稳定 | 内联列表 |

## eval 和 repl 的 fallback 行为

- `eval_command=None`：`eval()` 方法自动将代码写入临时文件（`.duan` 等 ASCII 扩展名），通过 `run_command` 执行
- `repl_command=None`：`YanREPL` 使用通用简易 REPL（`stdin` 逐行输入 + `eval`）

## 测试适配器

```bash
# 列出已注册语言（验证适配器被自动发现）
yanpub languages

# 查看适配器关键字（验证关键字加载）
yanpub repl yourlang
# 然后输入 :keywords

# 运行代码
yanpub run yourlang example.yl

# 启动 REPL
yanpub repl yourlang

# 简易模式（无 prompt_toolkit 依赖）
yanpub repl yourlang --simple
```

## 高级适配器

如果需要更精细的控制，可以直接实现 `LanguageAdapter` 抽象基类：

```python
from yanpub.core.adapter import LanguageAdapter, ExecutionResult, CompletionItem

class AdvancedAdapter(LanguageAdapter):
    @property
    def name(self) -> str:
        return "高级语言"

    @property
    def id(self) -> str:
        return "advanced"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def file_extensions(self) -> list[str]:
        return [".adv"]

    def run(self, file_path: str, args=None) -> ExecutionResult:
        # 自定义执行逻辑
        ...

    def eval(self, code: str) -> ExecutionResult:
        # 自定义代码执行
        ...

    def complete(self, code: str, line: int, column: int) -> list[CompletionItem]:
        # 自定义补全逻辑
        ...
```

## 适配器自动发现机制

1. `src/yanpub/adapters/` 下的每个子目录视为一个适配器
2. 目录中必须包含 `adapter.yaml` 和 `adapter.py`
3. `registry.py` 扫描所有子目录，加载 `adapter.py` 中的适配器子类
4. 自动排除框架基类（`BaseAdapter`/`SubprocessAdapter`/`InProcessAdapter`/`HTTPAdapter`）
5. 类名遵循 `{LangId}Adapter` 命名约定（如 `DuanAdapter`、`YanAdapter`）

无需手动注册，放入目录即可使用。

## 示例代码

每个适配器可在自己的 `examples/` 目录下放置示例代码文件，供 `yanpub examples` 命令查看和运行。

### 目录结构

```
adapters/duan/
├── adapter.py
├── adapter.yaml
└── examples/
    ├── hello.duan        # 带 YAML front matter
    ├── fibonacci.duan
    ├── bubble.duan
    └── hanoi.duan
```

### YAML Front Matter 格式

每个示例文件开头可包含 YAML 元数据：

```
---
title: '你好世界'
tags: ['入门', '基础']
difficulty: '入门'
description: '最简单的入门示例'
author: '张三'
---
打印("你好，段言！")
```

支持的字段：
- `title`（必需）：显示标题
- `tags`：标签列表
- `difficulty`：难度（入门/简单/中等/困难）
- `description`：简短描述
- `author`：作者署名

### 示例发现优先级

示例有双来源发现机制：
1. **适配器 examples/ 目录**（优先）：`adapters/<lang>/examples/`
2. **Playground 模板**（回退）：`playground/templates/<lang>/`

### 查看和运行示例

```bash
# 列出所有语言的示例
yanpub examples

# 列出段言的示例
yanpub examples duan

# 显示示例代码
yanpub examples duan -s

# 运行指定示例
yanpub examples duan -r hello

# 按关键字搜索示例
yanpub examples -S 递归
```

## 示例贡献

任何人都可以为已接入的语言贡献示例代码，无需修改适配器源码：

```bash
# 交互式创建示例（推荐）
yanpub contribute duan

# 参数式创建
yanpub contribute duan -n sort -t "排序算法" --tags "算法,排序" -d 简单 -a "张三" -c "打印('hello')"

# 从文件读取代码
yanpub contribute duan -n hello -f code.duan

# 仅预览不写入
yanpub contribute duan --dry-run

# 从 stdin 读取代码
echo "打印('hi')" | yanpub contribute duan -n hello
```

贡献的示例会自动写入适配器的 `examples/` 目录，并附带 YAML front matter 元数据。

### 验证示例

```bash
# 验证某语言所有示例的元数据
yanpub validate-examples duan

# 验证指定示例
yanpub validate-examples duan hello
```

验证检查项：
- 示例名称格式（安全字符）
- 标题和代码非空
- 语言 ID 存在
- 难度取值合法
- 标签格式正确
