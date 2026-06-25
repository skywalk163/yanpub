# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
