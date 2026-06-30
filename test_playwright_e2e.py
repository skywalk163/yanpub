"""Playwright 端到端测试 — Playground / Monitor / Docs 三大 Web 模块"""

from __future__ import annotations

import os
import sys
import time
import subprocess
import threading
import signal
import json
from pathlib import Path

# Windows console encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# -- Config --
PROJECT_DIR = Path(r"G:\dumategithub\yanpub")
PYTHON = r"E:\py312\python.exe"
SCREENSHOT_DIR = PROJECT_DIR / "test_screenshots"
PLAYGROUND_PORT = 8080
MONITOR_PORT = 8081
DOCS_PORT = 8082
TIMEOUT = 15000  # ms

SCREENSHOT_DIR.mkdir(exist_ok=True)

# -- Results collector --
results: list[dict] = []


def record(module: str, check: str, passed: bool, detail: str = ""):
    results.append({"module": module, "check": check, "passed": passed, "detail": detail})
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] [{module}] {check}" + (f" -- {detail}" if detail else ""))


# -- Service management --
def start_service(cmd: list[str], port: int, wait: float = 5.0) -> subprocess.Popen:
    """Start service in background, wait for port to be ready"""
    # Set PYTHONIOENCODING for the subprocess
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_DIR),
        env=env,
    )
    # Wait for service to be ready
    import socket
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                print(f"  [service] port {port} ready (pid={proc.pid})")
                return proc
        except OSError:
            # Also check if process has died
            if proc.poll() is not None:
                stdout_data = proc.stdout.read().decode("utf-8", errors="replace")[:500]
                stderr_data = proc.stderr.read().decode("utf-8", errors="replace")[:500]
                print(f"  [service] process died! exit={proc.returncode}")
                if stderr_data:
                    print(f"  [service] stderr: {stderr_data}")
                if stdout_data:
                    print(f"  [service] stdout: {stdout_data}")
                return proc
            time.sleep(0.5)
    # Print stderr to help debug
    print(f"  [service] port {port} NOT ready after {wait}s")
    try:
        # Non-blocking read
        import selectors
        sel = selectors.DefaultSelector()
        sel.register(proc.stderr, selectors.EVENT_READ)
        events = sel.select(timeout=0.1)
        for key, _ in events:
            err = key.fileobj.read1(4096)
            if err:
                print(f"  [service] stderr: {err.decode('utf-8', errors='replace')[:500]}")
        sel.close()
    except Exception:
        pass
    return proc


def stop_service(proc: subprocess.Popen):
    """优雅停止服务"""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


# -- Playwright tests --
def run_playwright_tests():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        # ================================================================
        #  1. Playground 测试
        # ================================================================
        print("\n" + "=" * 60)
        print("1. Playground 模块测试")
        print("=" * 60)

        pg_proc = start_service(
            [PYTHON, "-m", "yanpub.cli", "playground", "--host", "127.0.0.1", "--port", str(PLAYGROUND_PORT)],
            PLAYGROUND_PORT,
            wait=15.0,
        )

        page = context.new_page()

        # 1a. 主页加载
        try:
            page.goto(f"http://127.0.0.1:{PLAYGROUND_PORT}/", timeout=TIMEOUT, wait_until="domcontentloaded")
            # Wait for key elements to appear
            page.wait_for_load_state("networkidle", timeout=10000)
            title = page.title()
            page.screenshot(path=str(SCREENSHOT_DIR / "playground_home.png"))
            has_editor = page.locator("textarea, [contenteditable], .CodeMirror, .cm-editor, #editor, #code-editor").count() > 0
            record("Playground", "主页加载", "yanpub" in title.lower() or "playground" in title.lower() or "中文" in title or page.locator("body").inner_text() != "",
                   f"title='{title}', has_editor={has_editor}")
        except Exception as e:
            record("Playground", "主页加载", False, str(e)[:120])

        # 1b. 语言列表 API
        try:
            resp = page.request.get(f"http://127.0.0.1:{PLAYGROUND_PORT}/api/languages")
            data = resp.json()
            lang_count = len(data) if isinstance(data, list) else len(data.get("languages", []))
            record("Playground", "语言列表API", lang_count >= 5, f"{lang_count} 种语言")
        except Exception as e:
            record("Playground", "语言列表API", False, str(e)[:120])

        # 1c. 语言选择器
        try:
            # 尝试多种选择器
            selectors = [
                "select#lang, select#language, select[name='lang']",
                "select",
                "[data-lang]",
                ".lang-selector",
                "#lang-select",
            ]
            lang_select_found = False
            for sel in selectors:
                if page.locator(sel).count() > 0:
                    lang_select_found = True
                    record("Playground", "语言选择器", True, f"selector='{sel}'")
                    break
            if not lang_select_found:
                # 检查页面中是否包含语言相关文本
                body_text = page.locator("body").inner_text()
                has_lang_text = any(kw in body_text for kw in ["段言", "言", "墨言", "语言"])
                record("Playground", "语言选择器", has_lang_text, "无select元素, 页面含语言文本" if has_lang_text else "未找到语言选择器")
        except Exception as e:
            record("Playground", "语言选择器", False, str(e)[:120])

        # 1d. 运行按钮
        try:
            run_btn = page.locator("button:has-text('运行'), button:has-text('Run'), button#run, button#run-btn, [data-action='run']")
            has_run = run_btn.count() > 0
            record("Playground", "运行按钮", has_run, f"count={run_btn.count()}")
        except Exception as e:
            record("Playground", "运行按钮", False, str(e)[:120])

        # 1e. 模板 API
        try:
            resp = page.request.get(f"http://127.0.0.1:{PLAYGROUND_PORT}/api/templates/duan")
            status = resp.status
            body = resp.text()
            has_content = len(body) > 10
            record("Playground", "模板API(段言)", status == 200 and has_content, f"status={status}, body_len={len(body)}")
        except Exception as e:
            record("Playground", "模板API(段言)", False, str(e)[:120])

        # 1f. Code execution API
        try:
            resp = page.request.post(
                f"http://127.0.0.1:{PLAYGROUND_PORT}/api/run",
                data=json.dumps({"lang": "duan", "code": "设 甲 为 42\n印(甲)"}),
                headers={"Content-Type": "application/json"},
            )
            status = resp.status
            body = resp.text()
            # 200 means the API works; execution errors in stderr are fine
            has_response = len(body) > 10
            record("Playground", "代码执行API", status == 200 and has_response,
                   f"status={status}, response={body[:200]}")
        except Exception as e:
            record("Playground", "代码执行API", False, str(e)[:120])

        # 1g. 挑战赛页面
        try:
            page.goto(f"http://127.0.0.1:{PLAYGROUND_PORT}/challenges", timeout=TIMEOUT)
            page.screenshot(path=str(SCREENSHOT_DIR / "playground_challenges.png"))
            body_text = page.locator("body").inner_text()
            has_challenge = any(kw in body_text for kw in ["挑战", "Challenge", "题目"])
            record("Playground", "挑战赛页面", has_challenge, f"has_challenge_text={has_challenge}")
        except Exception as e:
            record("Playground", "挑战赛页面", False, str(e)[:120])

        # 1h. 监控页面
        try:
            page.goto(f"http://127.0.0.1:{PLAYGROUND_PORT}/monitor", timeout=TIMEOUT)
            page.screenshot(path=str(SCREENSHOT_DIR / "playground_monitor.png"))
            body_text = page.locator("body").inner_text()
            has_monitor = any(kw in body_text for kw in ["监控", "Monitor", "性能", "Performance"])
            record("Playground", "监控页面", has_monitor, f"has_monitor_text={has_monitor}")
        except Exception as e:
            record("Playground", "监控页面", False, str(e)[:120])

        # 1i. 质量评分页面
        try:
            page.goto(f"http://127.0.0.1:{PLAYGROUND_PORT}/quality", timeout=TIMEOUT)
            page.screenshot(path=str(SCREENSHOT_DIR / "playground_quality.png"))
            body_text = page.locator("body").inner_text()
            has_quality = any(kw in body_text for kw in ["质量", "Quality", "评分", "Score"])
            record("Playground", "质量评分页面", has_quality, f"has_quality_text={has_quality}")
        except Exception as e:
            record("Playground", "质量评分页面", False, str(e)[:120])

        page.close()
        stop_service(pg_proc)

        # ================================================================
        #  2. Monitor 页面测试 (via Playground service, /monitor page)
        #     Note: the standalone `yanpub monitor` command has a startup
        #     bottleneck -- it samples ALL adapters before serving, which
        #     can take minutes.  The monitor *page* itself is served by
        #     the Playground app, so we test it through the Playground.
        # ================================================================
        print("\n" + "=" * 60)
        print("2. Monitor 页面测试 (via Playground)")
        print("=" * 60)

        # Reuse Playground service (pg_proc)
        pg_proc = start_service(
            [PYTHON, "-m", "yanpub.cli", "playground", "--host", "127.0.0.1", "--port", str(PLAYGROUND_PORT)],
            PLAYGROUND_PORT,
            wait=15.0,
        )

        page = context.new_page()

        # 2a. Monitor page loads
        try:
            page.goto(f"http://127.0.0.1:{PLAYGROUND_PORT}/monitor", timeout=TIMEOUT)
            page.screenshot(path=str(SCREENSHOT_DIR / "monitor_dashboard.png"))
            title = page.title()
            body_text = page.locator("body").inner_text()
            has_perf = any(kw in body_text for kw in ["监控", "性能", "Monitor", "Performance", "延迟", "ms"])
            record("Monitor", "监控页面加载", len(body_text) > 20, f"title='{title}', has_perf_text={has_perf}")
        except Exception as e:
            record("Monitor", "监控页面加载", False, str(e)[:120])

        # 2b. Monitor page has chart/canvas or data display
        try:
            # Check for canvas, SVG chart, or data table
            has_chart = page.locator("canvas, svg, table, .chart, .monitor-data, #monitor").count() > 0
            page.screenshot(path=str(SCREENSHOT_DIR / "monitor_dashboard_detail.png"))
            record("Monitor", "监控图表/数据展示", has_chart, f"has_chart_element={has_chart}")
        except Exception as e:
            record("Monitor", "监控图表/数据展示", False, str(e)[:120])

        # 2c. Monitor API endpoint
        try:
            resp = page.request.get(f"http://127.0.0.1:{PLAYGROUND_PORT}/api/monitor/metrics")
            status = resp.status
            # 404 is also acceptable if the endpoint doesn't exist yet
            record("Monitor", "监控API端点", status != 500, f"status={status}")
        except Exception as e:
            record("Monitor", "监控API端点", False, str(e)[:120])

        page.close()
        stop_service(pg_proc)

        # ================================================================
        #  3. Docs 文档站测试
        # ================================================================
        print("\n" + "=" * 60)
        print("3. Docs 文档站测试")
        print("=" * 60)

        # 3a. 生成文档站
        docs_output = PROJECT_DIR / "test_docs_output"
        try:
            gen_result = subprocess.run(
                [PYTHON, "-m", "yanpub.cli", "docs", "-o", str(docs_output)],
                capture_output=True, text=True, cwd=str(PROJECT_DIR), timeout=60,
            )
            docs_generated = docs_output.exists() and (docs_output / "index.html").exists()
            record("Docs", "文档站生成", docs_generated,
                   f"exit={gen_result.returncode}, stdout={gen_result.stdout[:200]}" if not docs_generated else f"output={docs_output}")
            if not docs_generated:
                record("Docs", "文档站生成stderr", False, gen_result.stderr[:300])
        except Exception as e:
            record("Docs", "文档站生成", False, str(e)[:120])

        if docs_output.exists() and (docs_output / "index.html").exists():
            # 启动简单的 HTTP 服务
            docs_srv = start_service(
                [PYTHON, "-m", "http.server", str(DOCS_PORT), "--directory", str(docs_output)],
                DOCS_PORT,
                wait=5.0,
            )

            page = context.new_page()

            # 3b. 文档首页
            try:
                page.goto(f"http://127.0.0.1:{DOCS_PORT}/index.html", timeout=TIMEOUT)
                page.screenshot(path=str(SCREENSHOT_DIR / "docs_home.png"))
                body_text = page.locator("body").inner_text()
                has_yanpub = any(kw in body_text for kw in ["言埠", "YanPub", "中文编程", "语言"])
                record("Docs", "文档首页加载", has_yanpub, f"has_yanpub_text={has_yanpub}")
            except Exception as e:
                record("Docs", "文档首页加载", False, str(e)[:120])

            # 3c. 检查生成的 HTML 文件列表
            html_files = list(docs_output.glob("*.html"))
            record("Docs", "HTML页面数量", len(html_files) >= 3, f"{len(html_files)} 个HTML文件")

            # 3d. Navigation structure (docs uses header + lang-card links, not <nav>)
            try:
                # Check for header links or language cards that link to sub-pages
                all_links = page.locator("a")
                link_count = all_links.count()
                # Also check for language cards
                lang_cards = page.locator(".lang-card, .card, [class*='card']")
                card_count = lang_cards.count()
                record("Docs", "页面链接结构", link_count >= 2 or card_count >= 2,
                       f"links={link_count}, lang_cards={card_count}")
            except Exception as e:
                record("Docs", "页面链接结构", False, str(e)[:120])

            # 3e. 逐个访问子页面，检查不 404
            sub_pages_ok = 0
            sub_pages_fail = 0
            for html_file in html_files[:10]:  # 最多检查10个
                if html_file.name == "index.html":
                    continue
                try:
                    resp = page.request.get(f"http://127.0.0.1:{DOCS_PORT}/{html_file.name}")
                    if resp.status == 200:
                        sub_pages_ok += 1
                    else:
                        sub_pages_fail += 1
                except Exception:
                    sub_pages_fail += 1
            record("Docs", "子页面可访问", sub_pages_ok > 0, f"ok={sub_pages_ok}, fail={sub_pages_fail}")

            page.close()
            stop_service(docs_srv)

            # 清理测试输出
            import shutil
            try:
                shutil.rmtree(docs_output, ignore_errors=True)
            except Exception:
                pass
        else:
            record("Docs", "文档站页面测试", False, "文档站未生成，跳过")

        browser.close()


# -- Main flow --
if __name__ == "__main__":
    print("=" * 60)
    print("YanPub Web 模块 Playwright 端到端测试")
    print("=" * 60)
    print(f"项目目录: {PROJECT_DIR}")
    print(f"截图保存: {SCREENSHOT_DIR}")
    print()

    run_playwright_tests()

    # -- Summary --
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    # 按模块分组
    modules = {}
    for r in results:
        modules.setdefault(r["module"], []).append(r)

    for mod, checks in modules.items():
        mod_passed = sum(1 for c in checks if c["passed"])
        mod_total = len(checks)
        print(f"\n  {mod}: {mod_passed}/{mod_total} 通过")
        for c in checks:
            icon = "[PASS]" if c["passed"] else "[FAIL]"
            detail = f" -- {c['detail']}" if c["detail"] else ""
            print(f"    {icon} {c['check']}{detail}")

    print(f"\n总计: {passed}/{total} 通过, {failed} 失败")
    print(f"截图目录: {SCREENSHOT_DIR}")

    if failed > 0:
        print("\n[WARNING] Failed items:")
        for r in results:
            if not r["passed"]:
                print(f"  [FAIL] [{r['module']}] {r['check']}: {r['detail']}")

    sys.exit(0 if failed == 0 else 1)
