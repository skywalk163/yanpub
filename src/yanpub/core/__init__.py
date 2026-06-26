"""言埠核心 — 适配器协议、注册中心与基础设施"""

from __future__ import annotations

from yanpub.core.adapter.adapter import CompletionItem, Diagnostic, ExecutionResult, HTTPAdapter, InProcessAdapter, LanguageAdapter, SubprocessAdapter, TokenInfo  # noqa: F401
from yanpub.core.adapter.cache import AdapterCache, COMPLETION_TTL, CacheEntry, DIAGNOSTIC_TTL, EVAL_TTL, LRUCache, get_adapter_cache  # noqa: F401
from yanpub.core.adapter.compat import CompatResult, check_all_compatibility, check_compatibility, format_compat_detail, format_compat_matrix  # noqa: F401
from yanpub.core.adapter.health import HealthCheckResult, check_adapter_health, check_all_adapters, format_health_report  # noqa: F401
from yanpub.core.adapter.lazy_loader import LazyAdapter, LazyRegistry  # noqa: F401
from yanpub.core.adapter.registry import LanguageRegistry, get_registry  # noqa: F401
from yanpub.core.dev.dap_server import DAPServer  # noqa: F401
from yanpub.core.dev.debugger import Breakpoint, DebugAdapter, DebugEvent, DebugSession, LineTracer, StackFrame, Variable  # noqa: F401
from yanpub.core.dev.formatter import ChineseCodeFormatter, FormatterConfig  # noqa: F401
from yanpub.core.dev.linter import LintCategory, LintResult, LintRule, LintRuleEngine, LintSeverity  # noqa: F401
from yanpub.core.dev.navigator import SymbolNavigator  # noqa: F401
from yanpub.core.dev.refactor import RefactoringEngine  # noqa: F401
from yanpub.core.lifecycle.config import YanPubConfig  # noqa: F401
from yanpub.core.lifecycle.hotreload import AdapterWatcher, HotReloader, ReloadCallback, ReloadEvent  # noqa: F401
from yanpub.core.lifecycle.hotupdate import AdapterState, HotUpdateManager, VersionRecord  # noqa: F401
from yanpub.core.lifecycle.plugin import Plugin, PluginInfo, PluginManager, SUPPORTED_HOOKS, format_plugin_list, get_plugin_manager  # noqa: F401
from yanpub.core.lifecycle.pool import PooledProcess, ProcessPool, get_process_pool  # noqa: F401
from yanpub.core.perf.baseline import BaselineManager, BaselineSnapshot, PerformanceBudget  # noqa: F401
from yanpub.core.perf.bench_viz import BENCH_HISTORY_DIR, BenchHistory, BenchSnapshot, BenchVisualizer, REGRESSION_THRESHOLD, RegressionDetector, RegressionInfo, run_bench_with_regression  # noqa: F401
from yanpub.core.perf.benchmark import AdapterBenchResult, BenchResult, format_bench_report, run_all_benchmarks, run_benchmarks  # noqa: F401
from yanpub.core.perf.monitor import MetricSample, MetricSeries, PerformanceMonitor, get_monitor  # noqa: F401
from yanpub.core.perf.profiler import AdapterProfiler, FlameGraphGenerator, HOTSPOT_CRITICAL_MS, HOTSPOT_WARNING_MS, Hotspot, HotspotDetector, ProfileRecord, ProfileReport  # noqa: F401
from yanpub.core.security.audit import AuditEntry, AuditLog  # noqa: F401
from yanpub.core.security.sandbox import DockerSandbox, FreeBSDJailSandbox, ProcessSandbox, SandboxBackend, SandboxConfig, SandboxManager, SandboxResult  # noqa: F401
from yanpub.core.security.signing import CodeSignature, CodeSigner, SigningKey, TrustStore  # noqa: F401
from yanpub.core.adapter_template import AdapterSpec, AdapterTemplateEngine, interactive_wizard  # noqa: F401
from yanpub.core.adapter_test import AdapterCompatibilityValidator, AdapterTestCase, AdapterTestReport, AdapterTestResult, AdapterTestSuite, RegressionTestGenerator, get_builtin_suite  # noqa: F401
from yanpub.core.ai_assist import AIAssistConfig, AIAssistEngine  # noqa: F401
from yanpub.core.examples import ExampleInfo, ExampleManager, get_example_manager, validate_example_meta  # noqa: F401
from yanpub.core.keyword_docs import categorize_keyword, get_keyword_doc  # noqa: F401
from yanpub.core.quality import DimensionScore, QualityChecker, QualityReport  # noqa: F401
from yanpub.core.syntax_matrix import SnippetEntry, SyntaxConcept, SyntaxMatrix  # noqa: F401
from yanpub.core.wasm import WASM_OUTPUT_DIR, WasmBuildResult, WasmBuilder, WasmExecutor, WasmRuntimeInfo, detect_wasm_runtime, generate_pyodide_config, generate_pyodide_runner_html  # noqa: F401
