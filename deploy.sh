#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# YanPub 一键部署脚本
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 从 gitcode 拿到 yanpub 后，只需三步即可部署：
#
#   1. ./deploy.sh sync    — 自动 git clone 11 种语言后端
#   2. ./deploy.sh build   — 构建 Docker 镜像
#   3. ./deploy.sh up      — 启动服务 → http://localhost:8080
#
# 前置条件：Docker + Docker Compose + Git

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 颜色 ─────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
step()  { echo -e "${CYAN}[STEP]${NC} $1"; }

ACTION="${1:-up}"
REPOS_CONF="${SCRIPT_DIR}/docker/lang-repos.conf"
LANGS_DIR="${SCRIPT_DIR}/langs"

# ── 读取仓库配置 ──────────────────────────────────────
# lang-repos.conf 格式: lang_id  git_url  subdir
read_repos_conf() {
    if [ ! -f "$REPOS_CONF" ]; then
        error "找不到仓库配置: $REPOS_CONF"
        exit 1
    fi
    # 返回非空非注释行
    grep -v '^\s*#' "$REPOS_CONF" | grep -v '^\s*$'
}

# ── 同步语言项目到 ./langs/ ──────────────────────────
# 从 gitcode 自动 git clone，已有则 git pull 更新
sync_langs() {
    info "从 Git 仓库同步语言项目到 ./langs/ ..."
    mkdir -p "$LANGS_DIR"

    local synced=0
    local failed=0

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
                (cd "$target" && git pull --ff-only 2>/dev/null) || {
                    warn "  $lang_id: git pull 失败，保留现有版本"
                }
            else
                step "  克隆 $lang_id <- $git_url"
                git clone --depth 1 "$git_url" "$target" 2>/dev/null || {
                    warn "  $lang_id: git clone 失败"
                    failed=$((failed + 1))
                    continue
                }
            fi
        else
            # 适配器路径 = 仓库内的子目录（如 yan）
            # 先 clone 整个仓库到临时位置，再符号链接或复制子目录
            local repo_cache="$LANGS_DIR/.repos/${lang_id}_repo"
            if [ -d "$repo_cache/.git" ]; then
                step "  更新 $lang_id 仓库 (git pull)..."
                (cd "$repo_cache" && git pull --ff-only 2>/dev/null) || {
                    warn "  $lang_id: git pull 失败，保留现有版本"
                }
            else
                step "  克隆 $lang_id 仓库 <- $git_url"
                mkdir -p "$LANGS_DIR/.repos"
                git clone --depth 1 "$git_url" "$repo_cache" 2>/dev/null || {
                    warn "  $lang_id: git clone 失败"
                    failed=$((failed + 1))
                    continue
                }
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
    done < <(read_repos_conf)

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
    if ! command -v docker &>/dev/null; then
        error "Docker 未安装，请先安装 Docker"
        echo "  https://docs.docker.com/get-docker/"
        exit 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        error "Docker daemon 未运行，请先启动 Docker"
        exit 1
    fi
}

# ── 检查语言项目 ─────────────────────────────────────
check_langs() {
    local found=0
    local total=0
    while IFS= read -r line; do
        lang_id=$(echo "$line" | awk '{print $1}')
        total=$((total + 1))
        [ -d "$LANGS_DIR/$lang_id" ] && found=$((found + 1))
    done < <(read_repos_conf)

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
        info "构建 Docker 镜像（首次构建约需 5-10 分钟）..."
        docker compose build
        info "构建完成!"
        ;;
    up|start)
        check_docker
        check_langs || exit 1
        info "启动 YanPub..."
        docker compose up -d
        echo ""
        info "YanPub 已启动!"
        echo ""
        echo -e "  ${CYAN}Playground${NC}:  http://localhost:8080"
        echo -e "  ${CYAN}挑战赛${NC}:      http://localhost:8080/challenges"
        echo -e "  ${CYAN}监控面板${NC}:    http://localhost:8080/monitor"
        echo -e "  ${CYAN}质量评分${NC}:    http://localhost:8080/quality"
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
        if curl -sf http://localhost:8080/api/languages > /dev/null 2>&1; then
            info "Playground 服务正常"
            echo ""
            curl -s http://localhost:8080/api/languages 2>/dev/null | \
                python3 -m json.tool 2>/dev/null || \
                curl -s http://localhost:8080/api/languages
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
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            rm -rf "$LANGS_DIR"
            info "./langs/ 已删除"
        fi
        ;;
    *)
        echo "言埠 YanPub — 一键部署"
        echo ""
        echo "用法: ./deploy.sh <命令>"
        echo ""
        echo "  sync     自动 git clone 11 种语言后端到 ./langs/"
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
        echo "首次部署（从 gitcode 拿到 yanpub 后）:"
        echo "  1. ./deploy.sh sync      # 自动克隆语言项目"
        echo "  2. ./deploy.sh build     # 构建镜像"
        echo "  3. ./deploy.sh up        # 启动服务"
        ;;
esac
