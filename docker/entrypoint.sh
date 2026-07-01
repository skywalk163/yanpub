#!/bin/bash
# YanPub Docker 入口脚本
# 根据命令参数启动不同服务
#
# 用法: docker run yanpub [playground|monitor|repl|lsp|health|languages|bash]

set -e

# 默认启动 Playground
SERVICE="${1:-playground}"

# 健康检查快捷方式（用于 docker healthcheck）
if [ "$SERVICE" = "healthcheck" ]; then
    if curl -sf http://localhost:8080/api/languages > /dev/null 2>&1; then
        echo "OK"
        exit 0
    else
        echo "FAIL"
        exit 1
    fi
fi

case "$SERVICE" in
    playground)
        echo "============================================"
        echo "  言埠 YanPub — 中文编程语言 Playground"
        echo "  http://0.0.0.0:8080"
        echo "============================================"
        echo ""
        echo "已注册语言: $(python -c "
from yanpub.adapters._path_resolver import get_all_lang_dirs
import os
dirs = get_all_lang_dirs()
available = [k for k, v in dirs.items() if os.path.isdir(v)]
print(', '.join(available) if available else '无（请检查语言项目路径）')
" 2>/dev/null || echo "检测失败")"
        echo ""
        exec python -m yanpub.cli playground --host 0.0.0.0 --port 8080
        ;;
    monitor)
        echo "============================================"
        echo "  言埠 YanPub — 性能监控仪表板"
        echo "  http://0.0.0.0:8080/monitor"
        echo "============================================"
        exec python -m yanpub.cli playground --host 0.0.0.0 --port 8080
        ;;
    repl)
        LANG_ID="${2:-duan}"
        echo "启动 $LANG_ID REPL..."
        exec python -m yanpub.cli repl "$LANG_ID"
        ;;
    lsp)
        echo "启动 LSP 服务..."
        exec python -m yanpub.cli lsp
        ;;
    health)
        echo "检查语言后端健康状态..."
        exec python -m yanpub.cli health
        ;;
    languages)
        echo "已注册语言列表："
        exec python -m yanpub.cli languages
        ;;
    test)
        echo "运行 YanPub 测试..."
        exec python -m pytest -p no:kotti -q "${2:-tests/}"
        ;;
    bash|sh)
        exec /bin/bash
        ;;
    *)
        echo "言埠 YanPub Docker"
        echo ""
        echo "用法: yanpub [命令]"
        echo ""
        echo "  playground       启动 Playground（默认）"
        echo "  monitor          启动 Playground + 监控仪表板"
        echo "  repl <lang>      启动指定语言 REPL"
        echo "  lsp              启动 LSP 服务"
        echo "  health           检查语言后端状态"
        echo "  languages        列出已注册语言"
        echo "  test [path]      运行测试"
        echo "  bash             进入 Shell"
        ;;
esac
