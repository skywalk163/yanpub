#!/bin/sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# YanPub 一键部署脚本
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 从 gitcode/github 拿到 yanpub 后，只需三步即可部署：
#
#   1. ./deploy.sh sync    — 自动 git clone 13 种语言后端
#   2. ./deploy.sh build   — 构建 Docker 镜像
#   3. ./deploy.sh up      — 启动服务 → http://localhost:8080
#
# 前置条件：Docker + Docker Compose + Git + Python3 (PyYAML)
#
# 镜像选择（环境变量 REPO_SOURCE）:
#   auto      自动检测（默认）：GitHub 3s 超时则回退 GitCode
#   gitcode   固定使用 GitCode（国内推荐）
#   github    固定使用 GitHub（海外推荐）
#   internal  固定使用内网 Gitea（仅局域网）
#
# 示例:
#   REPO_SOURCE=github ./deploy.sh sync   # 海外用户
#   REPO_SOURCE=internal ./deploy.sh sync # 内网用户

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色（用 printf 替代 echo -e，POSIX 兼容） ───────
# 所有日志输出到 stderr，避免污染 stdout（函数返回值走 stdout）
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { printf '%b[INFO]%b %s\n' "$GREEN" "$NC" "$1" >&2; }
warn()  { printf '%b[WARN]%b %s\n' "$YELLOW" "$NC" "$1" >&2; }
error() { printf '%b[ERROR]%b %s\n' "$RED" "$NC" "$1" >&2; }
step()  { printf '%b[STEP]%b %s\n' "$CYAN" "$NC" "$1" >&2; }

ACTION="${1:-up}"
REPOS_CONF="${SCRIPT_DIR}/docker/lang-repos.conf"
LANGS_YAML="${SCRIPT_DIR}/languages.yaml"
LANGS_DIR="${SCRIPT_DIR}/langs"

# ── 镜像选择 ──────────────────────────────────────────
# REPO_SOURCE: auto | gitcode | github | internal
REPO_SOURCE="${REPO_SOURCE:-auto}"

resolve_repo_source() {
    if [ "$REPO_SOURCE" != "auto" ]; then
        echo "$REPO_SOURCE"
        return
    fi
    # auto 模式: 尝试连接 github.com（3s 超时）
    if curl -sf --connect-timeout 3 -o /dev/null https://github.com 2>/dev/null; then
        echo "github"
    else
        echo "gitcode"
    fi
}

# ── 构建参数 ──────────────────────────────────────────
# 优先从 .env 或环境变量读取 Python 镜像
load_build_env() {
    if [ -f "${SCRIPT_DIR}/.env" ]; then
        # shellcheck disable=SC1090
        . "${SCRIPT_DIR}/.env"
    fi
    export PYTHON_IMAGE="${PYTHON_IMAGE:-docker.m.daocloud.io/library/python:3.12-slim}"
    export INSTALL_RACKET="${INSTALL_RACKET:-0}"
    export INSTALL_LLVM="${INSTALL_LLVM:-0}"
}

# ── 读取仓库配置 ──────────────────────────────────────
# 优先从 languages.yaml 读取（支持多镜像），回退到 lang-repos.conf
read_repos_conf() {
    local resolved_source
    resolved_source=$(resolve_repo_source)

    # 优先使用 languages.yaml + select-mirror.py
    if [ -f "$LANGS_YAML" ] && python3 -c "import yaml" 2>/dev/null; then
        python3 "${SCRIPT_DIR}/docker/select-mirror.py" "$resolved_source"
        return
    fi

    # 回退: 使用 lang-repos.conf（仅含 gitcode 镜像）
    if [ ! -f "$REPOS_CONF" ]; then
        error "找不到仓库配置: $REPOS_CONF 或 $LANGS_YAML"
        exit 1
    fi
    warn "回退到 lang-repos.conf（仅 gitcode 镜像）。安装 PyYAML 可启用多镜像支持。"
    # 返回非空非注释行（POSIX 兼容：用 [[:space:]] 替代 \s）
    grep -v '^[[:space:]]*#' "$REPOS_CONF" | grep -v '^[[:space:]]*$'
}

# ── 同步语言项目到 ./langs/ ──────────────────────────
# 从 gitcode 自动 git clone，已有则 git pull 更新
sync_langs() {
    local resolved_source
    resolved_source=$(resolve_repo_source)
    info "同步语言项目到 ./langs/ (镜像: $resolved_source) ..."
    mkdir -p "$LANGS_DIR"

    local synced=0
    local failed=0

    # 写入临时文件再读取（POSIX 兼容，避免 bash 的 < <() 进程替换）
    local repos_tmp
    repos_tmp=$(mktemp)
    read_repos_conf > "$repos_tmp"

    while IFS= read -r line; do
        # 解析: lang_id  git_url  subdir
        lang_id=$(echo "$line" | awk '{print $1}')
        git_url=$(echo "$line" | awk '{print $2}')
        subdir=$(echo "$line" | awk '{print $3}')
        [ -z "$subdir" ] && subdir="."

        local target="$LANGS_DIR/$lang_id"

        if [ "$subdir" = "." ]; then
            # 适配器路径 = 仓库根，直接 clone 到 langs/$lang_id
            if [ -d "$target/.git" ]; then
                step "  更新 $lang_id (git pull)..."
                (cd "$target" && git pull --ff-only) || {
                    warn "  $lang_id: git pull 失败，保留现有版本"
                }
            else
                step "  克隆 $lang_id <- $git_url"
                if git clone --depth 1 "$git_url" "$target" 2>&1; then
                    :
                else
                    warn "  $lang_id: git clone 失败"
                    failed=$((failed + 1))
                    continue
                fi
            fi
        else
            # 适配器路径 = 仓库内的子目录（如 yan）
            # 先 clone 整个仓库到临时位置，再符号链接或复制子目录
            local repo_cache="$LANGS_DIR/.repos/${lang_id}_repo"
            if [ -d "$repo_cache/.git" ]; then
                step "  更新 $lang_id 仓库 (git pull)..."
                (cd "$repo_cache" && git pull --ff-only) || {
                    warn "  $lang_id: git pull 失败，保留现有版本"
                }
            else
                step "  克隆 $lang_id 仓库 <- $git_url"
                mkdir -p "$LANGS_DIR/.repos"
                if git clone --depth 1 "$git_url" "$repo_cache" 2>&1; then
                    :
                else
                    warn "  $lang_id: git clone 失败"
                    failed=$((failed + 1))
                    continue
                fi
            fi
            # 复制子目录到目标位置
            if [ -d "$repo_cache/$subdir" ]; then
                rm -rf "$target"
                cp -r "$repo_cache/$subdir" "$target"
            else
                warn "  $lang_id: 仓库内子目录 '$subdir' 不存在"
                failed=$((failed + 1))
                continue
            fi
        fi

        synced=$((synced + 1))
    done < "$repos_tmp"
    rm -f "$repos_tmp"

    echo ""
    if [ $synced -gt 0 ]; then
        info "$synced 个语言已就绪"
    fi
    if [ $failed -gt 0 ]; then
        warn "$failed 个语言同步失败（对应适配器将不可用）"
    fi
}

# ── 检查 Docker ──────────────────────────────────────
check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        error "Docker 未安装，请先安装 Docker"
        echo "  https://docs.docker.com/get-docker/"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        error "Docker daemon 未运行，请先启动 Docker"
        exit 1
    fi
}

# ── 检查语言项目 ─────────────────────────────────────
check_langs() {
    local found=0
    local total=0
    local repos_tmp
    repos_tmp=$(mktemp)
    read_repos_conf > "$repos_tmp"
    while IFS= read -r line; do
        lang_id=$(echo "$line" | awk '{print $1}')
        total=$((total + 1))
        [ -d "$LANGS_DIR/$lang_id" ] && found=$((found + 1))
    done < "$repos_tmp"
    rm -f "$repos_tmp"

    if [ $found -lt $total ]; then
        warn "仅 $found/$total 个语言项目就绪"
        warn "请先运行: ./deploy.sh sync"
        return 1
    fi
    return 0
}

# ── 主逻辑 ──────────────────────────────────────────
case "$ACTION" in
    sync)
        sync_langs
        ;;
    build)
        check_docker
        sync_langs
        load_build_env
        info "构建 Docker 镜像（基础镜像: ${PYTHON_IMAGE}）..."
        info "首次构建约需 5-10 分钟，后续构建利用缓存更快"
        docker compose build \
            --build-arg PYTHON_IMAGE="$PYTHON_IMAGE" \
            --build-arg INSTALL_RACKET="$INSTALL_RACKET" \
            --build-arg INSTALL_LLVM="$INSTALL_LLVM"
        info "构建完成!"
        ;;
    up|start)
        check_docker
        check_langs || exit 1
        load_build_env
        info "启动 YanPub..."
        docker compose up -d
        echo ""
        info "YanPub 已启动!"
        echo ""
        printf '%b  %bPlayground%b:  http://localhost:%s\n' "$NC" "$CYAN" "$NC" "${YANPUB_PORT:-8080}" >&2
        printf '%b  %b挑战赛%b:      http://localhost:%s/challenges\n' "$NC" "$CYAN" "$NC" "${YANPUB_PORT:-8080}" >&2
        printf '%b  %b监控面板%b:    http://localhost:%s/monitor\n' "$NC" "$CYAN" "$NC" "${YANPUB_PORT:-8080}" >&2
        printf '%b  %b质量评分%b:    http://localhost:%s/quality\n' "$NC" "$CYAN" "$NC" "${YANPUB_PORT:-8080}" >&2
        echo ""
        echo "  查看日志:  ./deploy.sh logs"
        echo "  进入容器:  ./deploy.sh shell"
        echo "  健康检查:  ./deploy.sh health"
        ;;
    down|stop)
        docker compose down
        info "已停止"
        ;;
    restart)
        check_docker
        docker compose restart
        info "YanPub 已重启!"
        ;;
    logs)
        docker compose logs -f --tail=100
        ;;
    health)
        info "检查服务状态..."
        if curl -sf http://localhost:${YANPUB_PORT:-8080}/api/languages > /dev/null 2>&1; then
            info "Playground 服务正常"
            echo ""
            curl -s http://localhost:${YANPUB_PORT:-8080}/api/languages 2>/dev/null | \
                python3 -m json.tool 2>/dev/null || \
                curl -s http://localhost:${YANPUB_PORT:-8080}/api/languages
        else
            error "Playground 服务未响应"
            echo "  查看日志: ./deploy.sh logs"
        fi
        ;;
    shell)
        docker compose exec yanpub bash
        ;;
    test)
        check_docker
        info "在容器中运行测试..."
        docker compose exec yanpub python -m pytest -p no:kotti -q "${2:-tests/}"
        ;;
    clean)
        warn "清理 Docker 资源..."
        docker compose down -v --rmi local 2>/dev/null || true
        info "Docker 资源已清理"
        read -p "是否同时删除 ./langs/ (含克隆的语言项目)? [y/N] " confirm
        case "$confirm" in
            [Yy]*)
            rm -rf "$LANGS_DIR"
            info "./langs/ 已删除"
            ;;
        esac
        ;;
    *)
        echo "言埠 YanPub — 一键部署"
        echo ""
        echo "用法: ./deploy.sh <命令>"
        echo ""
        echo "  sync     自动 git clone 13 种语言后端到 ./langs/"
        echo "  build    同步 + 构建 Docker 镜像"
        echo "  up       启动服务（默认命令）"
        echo "  down     停止服务"
        echo "  restart  重启服务"
        echo "  logs     查看实时日志"
        echo "  health   检查服务健康状态"
        echo "  shell    进入容器 Shell"
        echo "  test     在容器中运行测试"
        echo "  clean    清理 Docker 资源 + 可选删除 langs/"
        echo ""
        echo "首次部署（从 gitcode/github 拿到 yanpub 后）:"
        echo "  1. ./deploy.sh sync      # 自动克隆语言项目"
        echo "  2. ./deploy.sh build     # 构建镜像"
        echo "  3. ./deploy.sh up        # 启动服务"
        echo ""
        echo "镜像选择:"
        echo "  REPO_SOURCE=auto ./deploy.sh sync       # 自动检测（默认）"
        echo "  REPO_SOURCE=gitcode ./deploy.sh sync     # 国内"
        echo "  REPO_SOURCE=github ./deploy.sh sync       # 海外"
        echo "  REPO_SOURCE=internal ./deploy.sh sync     # 内网"
        echo ""
        echo "自定义构建:"
        echo "  PYTHON_IMAGE=python:3.12-slim ./deploy.sh build  # 用官方镜像"
        echo "  INSTALL_RACKET=1 ./deploy.sh build               # 启用明道语言(Racket)"
        echo "  INSTALL_LLVM=1 ./deploy.sh build                 # 启用翰语JIT(LLVM)"
        echo "  YANPUB_PORT=9090 ./deploy.sh up                  # 自定义端口"
        ;;
esac
