# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.9.0] - 2026-06-28

### Changed

- 架构卫生重构（第三轮）：9 个 600+ 行文件科学拆分，最大文件从 862 行降至 830 行
  - `core/adapter/adapter.py` (739行) → 294 行主文件 + `types.py` (4个数据类) + `base.py` (LanguageAdapter ABC)
  - `core/ai_assist.py` (832行) → 692 行主文件 + `ai_data.py` (175行配置/模板/规则数据)
  - `core/dev/navigator.py` + `core/dev/refactor.py` → 提取 `_ident_utils.py` 共享标识符工具（消除 3 个重复函数 + 4 个常量集）
  - `playground/collab.py` (679行) → 400 行主文件 + `crdt.py` (278行 CRDT 数据模型)
  - `core/wasm.py` (652行) → 155 行主文件 + `wasm_executor.py` (263行) + `wasm_pyodide.py` (235行)
  - `pkg/versionset.py` (648行) → 328 行主文件 + `version_constraint.py` (175行) + `workspace_lock.py` (148行)
  - `core/security/signing.py` (623行) → 222 行主文件 + `keys.py` (140行) + `trust_store.py` (268行)
  - `core/perf/bench_viz.py` (667行) → 514 行主文件 + `bench_history.py` (183行)
- 所有拆分保留向后兼容（`__getattr__` re-export），公共 API 不变
- 消除 `navigator.py` 与 `refactor.py` 之间约 70 行代码重复
- 1284 测试全部通过

## [1.8.0] - 2026-06-28

### Changed

- 架构卫生重构（第二轮）：7 个 800+ 行文件科学拆分，800+ 行文件从 7 个降至 0 个
  - `core/syntax_matrix.py` (1123行) → 250 行主文件 + `syntax_matrix_data.py` (642行数据) + `syntax_matrix_html.py` (280行HTML)
  - `playground/server.py` (1115行) → 410 行主文件 + `routes_ai.py` + `routes_project.py` + `routes_share.py` + `routes_challenge.py` + `routes_monitor.py`
  - `core/perf/profiler.py` (948行) → 422 行主文件 + `flamegraph.py` (587行)
  - `core/security/sandbox.py` (939行) → 423 行主文件 + `sandbox_backends/` (docker/freebsd/process 3个后端)
  - `core/dev/debugger.py` (936行) → 310 行主文件 + `line_tracer.py` (416行) + `dap_adapter.py`
  - `docs/site_builder.py` (903行) → 270 行主文件 + `seo.py` (428行) + `site_templates.py`
  - `core/adapter_test.py` (899行) → 407 行主文件 + `adapter_test_builtin.py` + `adapter_test_report.py` + `adapter_compat.py` + `adapter_regression.py`
- 所有拆分保留向后兼容（re-export），公共 API 不变
- 1284 测试全部通过

## [1.7.0] - 2026-06-28

### Added

- 新增华语（华码/Hua）语言适配器：`adapters/hua/`
  - 适配器 `HuaAdapter` 继承 `SubprocessAdapter`，调用 `华码.py` 后端
  - 69 个关键字从 `词法.py` 动态加载 + 缓存 fallback
  - 支持 run（文件执行）、eval（临时文件）、repl（交互模式）
  - 注释语法 `//`，扩展名 `.华` / `.hua`
  - 主色 `#E67E22`
- 6 个示例文件：hello、variables、condition、loop、function、data
- 7 个 Playground 模板（6 个专题 + default）
- 语法对比矩阵新增华语 15 个概念条目（hello → higher_order）
- Playground 多文件项目新增华语默认模板

## [1.6.1] - 2026-06-27

### Fixed

- Fix 7 test failures on Windows where `echo` is a cmd builtin (not a standalone executable): `shutil.which("echo")` unreachable, `subprocess.run(["echo", "mock"])` behavior inconsistent
- Test adapters (`MockAdapter`, `EmptyKeywordsAdapter`) now override `eval()`/`run()` to return in-memory results, no longer depend on real subprocess execution
- Health test adapters (`FailingEvalAdapter`, `CrashingAdapter`, `NoLSPAdapter`, `SlashCommentAdapter`) changed from `SubprocessAdapter` to `LanguageAdapter`, avoiding command reachability check interference
- Fix Playground CSS/JS 404: HTML files referenced `index.css`/`index.js` (relative path), but static files are mounted at `/static/` — changed all 4 HTML files to use `/static/` prefix

## [1.5.0] - 2026-06-18

### Security

- Add Playground security middleware: CORS, rate limiting, code length limits, WebSocket origin validation, sandbox parameter validation (`playground/security.py`)
- Rate limiting: 60 req/min for general API, 10 req/min for execution endpoints (`/api/run`, `/api/sandbox/run`, `/ws/run`)
- Code length limit: max 65536 characters per request
- Request body size limit: max 512 KB
- Sandbox parameter validation: backend whitelist, timeout/memory upper bounds, network must be boolean
- WebSocket connection limit: max 50 concurrent connections
- All security limits configurable via environment variables

### Testing

- Add 27 security middleware tests (`test_playground_security.py`)

## [1.4.0] - 2026-06-17

### Added

- Project diagnostic report: P0/P1/P2 issue classification and improvement plan
- Adapter development template: `AdapterSpec`, `AdapterTemplateEngine`, CLI `adapter create` (interactive/parameterized/dry-run), `adapter check` (directory/class/instantiation/YAML validation)
- Example contribution pipeline: `ExampleInfo.author`, `validate_example_meta`, `contribute_example`, CLI `contribute` (interactive/parameterized/dry-run), CLI `validate-examples`
- Language comparison matrix: `core/syntax_matrix.py`, 15 syntax concepts × 10 languages = 150 code snippets, syntax style auto-analysis, HTML visualization, CLI `compare --matrix/--html`
- Examples system: `core/examples.py`, dual-source priority (adapter examples > playground templates), 10 languages × 6 examples = 60 total, YAML front matter metadata

### Fixed

- Fix duan adapter broken path, add `SubprocessAdapter.eval_mode` parameter (stdin|arg)
- Fix mingdao adapter eval, set `PYTHONIOENCODING=utf-8` in `_exec()`
- Fix hanyu adapter duplicate keywords
- Fix 段言 (duan) adapter ANTLR ATN version mismatch (`--backend src`)
- Fix 段言 parser `_parse_paragraph_v2` INDENT not consumed causing subsequent code ignored
- Fix 段言 parser `_parse_while_stmt` DEDENT level judgment logic error
- Fix 段言 parser "结束" keyword recognized as IDENTIFIER instead of KEYWORD (dual-path consumption)
- Fix 段言 parser `_parse_if_stmt` "结束" incorrectly consumed in if-else structure
- Fix 段言 `code_generator.py` missing `RangeExpr` support (`遍历 i 之 1至10`)

## [1.3.0] - 2026-06-15

### Added

- LSP code navigation: Go to Definition, Find All References, Call Hierarchy, `SymbolNavigator`
- Cloud execution sandbox: Docker/Podman/FreeBSDJail/ProcessSandbox 4 backends
- Playground AI assistance: smart completion, natural language to code, error fix suggestions
- DAP debugger: `DebugSession`, `LineTracer`, `DebugAdapter`, `DAPServer`

## [1.2.0] - 2026-06-13

### Added

- LSP code style checking: lint rules for formatting, naming, complexity
- Playground collaboration enhancement: user list, cursor awareness, edit synchronization
- Adapter hot update: `HotReloader` with watchdog/polling, CLI command
- Documentation site search enhancement: full-text search with ranking
- Example selector: language-aware template/examples picker in Playground

## [1.1.0] - 2026-06-11

### Added

- Playground share enhancement: `ShareManager`, short links, QR code SVG, `/api/share/*` routes, social sharing
- LSP code refactoring enhancement: `RefactoringEngine`, Extract Function, Inline Variable, Safe Rename, CodeAction
- Adapter performance optimization: `LRUCache`, `AdapterCache` 3-level cache, `LazyAdapter` lazy loading, `ProcessPool` connection pool
- Documentation site SEO optimization: `SEOOptimizer`, `SitemapGenerator`, `OpenGraphBuilder`, JSON-LD, `robots.txt`

## [1.0.0] - 2026-06-09

### Added

- Playground multi-file projects: `ProjectManager`, `Project`, file tree, multi-tab editor, `/api/project/*` routes
- Adapter test framework: `AdapterTestSuite`, `AdapterCompatibilityValidator`, `RegressionTestGenerator`, built-in test cases
- LSP incremental sync: `apply_change` precise incremental, Incremental mode, version tracking, change callbacks
- Performance baseline management: `BaselineManager`, `BaselineSnapshot`, `PerformanceBudget`, CI regression detection

## [0.9.0] - 2026-06-07

### Added

- Performance monitoring dashboard: `PerformanceMonitor`, `MetricSeries`, WebSocket push, regression detection, dashboard HTML
- VSCode extension enhancement: DAP debug, AI Webview, sandbox buttons, 8 commands, 1 debugger, 7 configuration items
- Multi-language documentation i18n: `I18nManager`, `RuleBasedTranslator` (zh/en/ja/ko), `I18nDocsGenerator`
- LSP code signing: `CodeSigner` HMAC-SHA256/Ed25519, `TrustStore` trust chain, `AuditLog` audit

## [0.8.0] - 2026-06-05

### Added

- LSP CodeLens: inline run button, output hint, CodeLensResolve
- Package manager semantic release: `SemanticVersion`, `ConventionalCommits`, `ChangelogGenerator`, 3 CLI commands
- Adapter performance tuning panel: `BenchVisualizer` HTML report, `BenchHistory`, `RegressionDetector`, 3 CLI commands
- WASM online execution: `WasmExecutor` multi-runtime, Pyodide config, `WasmBuilder`, Playground WASM mode, 3 CLI commands

## [0.7.0] - 2026-06-03

### Added

- LSP code folding: block keyword stack tracking, indent inference, FoldingRange
- Adapter hot reload: `HotReloader`, `AdapterWatcher` (watchdog/polling), CLI command
- Package manager workspace: `Workspace`, `workspace.toml`, dependency graph, topological sort, CLI commands
- Playground real-time collaboration: CRDT RGA document, `CollabRoom`, `CollabManager`, WebSocket collaboration API

## [0.6.0] - 2026-06-01

### Added

- Playground collaboration frontend: CodeMirror collaboration, remote cursor/selection, user list, edit sync
- LSP semantic highlighting: Semantic Tokens, 17 token types, delta encoding
- Adapter performance profiler: `AdapterProfiler`, FlameGraph, `HotspotDetector`, `profile` CLI
- Package manager version workset: `VersionConstraint`, `WorkspaceLock`, `VersionSetManager`, `lock`/`check-lock` CLI

## [0.5.0] - 2026-05-30

### Added

- LSP code navigation: Go to Definition, Find All References, Call Hierarchy
- Cloud execution sandbox: Docker/Podman/FreeBSDJail/ProcessSandbox 4 backends
- Playground AI assistance: smart completion, NL-to-code, error fix
- DAP debugger: `DebugSession`, `LineTracer`, `DebugAdapter`, `DAPServer`

## [0.4.0] - 2026-05-28

### Added

- LSP CodeLens: inline run button, output hint, CodeLensResolve
- Package manager semantic release: `SemanticVersion`, `ConventionalCommits`, `ChangelogGenerator`
- Adapter performance tuning panel: `BenchVisualizer`, `BenchHistory`, `RegressionDetector`
- WASM online execution: `WasmExecutor`, Pyodide, `WasmBuilder`

## [0.3.0] - 2026-05-26

### Added

- Playground code sharing: URL hash + `/api/share` endpoint
- LSP code formatting: `adapter.format`, `ChineseCodeFormatter`
- REPL friendly error messages: `parse_error`, `format_friendly_error`
- Remote registry: `RemoteRegistry`, `pkg sync`
- Adapter health check: `health` CLI command
- Performance benchmarking: `bench` CLI command
- Internationalization: i18n framework + Chinese/English bilingual support

## [0.2.0] - 2026-05-24

### Added

- Package manager dependency locking: `LockManager`, `yanpkg.lock`
- LSP code refactoring: rename, CodeAction (CJK single-char + ASCII dual-mode identifier recognition)
- Adapter compatibility matrix: `check_compatibility` four-dimension check
- Plugin system: `PluginManager`, 7 hooks

## [0.1.0] - 2026-05-22

### Added

- Core framework: LanguageAdapter protocol, adapter registry, 10 language adapters (duan, yan, moyan, mingdao, zhixing, xinyu, traeyan, hanyu, yanlv, yanzhi)
- Package manager (YanPkg): install, publish, search, dependencies
- Playground (YanPlay): web-based code editor with CodeMirror, code execution, multi-language support
- Language Server Protocol (YanLSP): completion, hover, diagnostics, formatting
- Interactive REPL (YanREPL): prompt-toolkit based, multi-language switching
- Documentation site (YanDocs): static site generator, multi-language docs
- VSCode extension (YanVSCode): syntax highlighting, language configuration, basic LSP integration
- CLI: unified `yanpub` command-line interface
