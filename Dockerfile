# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# YanPub Docker — 一键部署含 11 种中文编程语言
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# 构建流程:
#   1. ./deploy.sh sync   — 复制语言项目到 ./langs/
#   2. docker compose build
#
# 多阶段构建:
#   stage1 (deps): 安装系统依赖 + pip 包（变化少，缓存好）
#   stage2 (langs): 安装 11 种语言后端（语言项目独立变化）
#   stage3 (app):   安装 YanPub 自身（变化最频繁，缓存最差）
#
# 国内加速:
#   - Docker 基础镜像: docker.m.daocloud.io
#   - apt 源: 清华大学镜像站
#   - pip 源: 清华大学镜像站
#   - Racket: 清华大学镜像站
#   - Git 仓库: gitcode.com（国内托管）

# ── Stage 1: 系统依赖 + Python 包 ─────────────────────
# 国内加速镜像；如能直连 Docker Hub 可改为 python:3.12-slim
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim
FROM ${PYTHON_IMAGE} AS deps

# 1. 替换为清华 Debian 源 (Trixie/Bookworm 自动适配)
# Debian 13 Trixie 使用 DEB822 格式 /etc/apt/sources.list.d/debian.sources
# Debian 12 Bookworm 使用传统 /etc/apt/sources.list
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list; \
        sed -i 's|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn

# 系统依赖 + Racket（清华镜像加速）
# 注意: Racket 安装脚本用 --in-place 避免交互
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates \
    default-jre-headless \
    clang llvm \
    && curl -fSL https://mirrors.tuna.tsinghua.edu.cn/racket-installers/9.2/racket-9.2-x86_64-linux-buster-cs.sh \
       -o /tmp/racket-install.sh \
    && sh /tmp/racket-install.sh --in-place --dest /usr/racket \
    && ln -s /usr/racket/bin/racket /usr/local/bin/racket \
    && ln -s /usr/racket/bin/raco /usr/local/bin/raco \
    && rm /tmp/racket-install.sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# pip 升级 + 全局配置清华源（ENV 已设 PIP_INDEX_URL，这里额外设置 pip config 做冗余）
RUN pip install --no-cache-dir --upgrade pip \
    && pip config set global.index-url https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

# Python 依赖 — 先安装不变的第三方包，利用 Docker 缓存
# 清华源通过 ENV PIP_INDEX_URL 自动生效，无需每行 -i
RUN pip install --no-cache-dir \
    "antlr4-python3-runtime==4.13.2" \
    "flask>=3.0.0" "flask-cors>=4.0.0" \
    "requests>=2.25.0" \
    "jieba>=0.42.1" \
    "ply==3.11" "RestrictedPython>=7.0,<8.0" "psutil>=5.9.0" "objgraph>=3.5.0" \
    "typing-extensions>=4.0.0" \
    "prompt-toolkit>=3.0.0" \
    llvmlite tree-sitter \
    "uvicorn[standard]>=0.20.0" "fastapi>=0.100.0" \
    "pydantic>=2.0.0" "websockets>=11.0" "jinja2>=3.1.0"

# ── Stage 2: 安装语言后端 ──────────────────────────────
FROM deps AS langs

ARG LANGS_DIR=/opt/langs
RUN mkdir -p ${LANGS_DIR}

# 逐个 COPY + install，利用 Docker 层缓存
# 某个语言变化时只重建该层及其后
# pip 清华源通过 ENV PIP_INDEX_URL 自动生效

# 1. 言语言 yan
COPY ./langs/yan ${LANGS_DIR}/yan
RUN cd ${LANGS_DIR}/yan && pip install --no-cache-dir -e . 2>/dev/null || true

# 2. 知行 zhixing
COPY ./langs/zhixing ${LANGS_DIR}/zhixing
RUN cd ${LANGS_DIR}/zhixing && pip install --no-cache-dir -e . 2>/dev/null || true

# 3. 知行语言 traeyan
COPY ./langs/traeyan ${LANGS_DIR}/traeyan
RUN cd ${LANGS_DIR}/traeyan && pip install --no-cache-dir -e . 2>/dev/null || true

# 4. 言知 yanzhi
COPY ./langs/yanzhi ${LANGS_DIR}/yanzhi
RUN cd ${LANGS_DIR}/yanzhi && pip install --no-cache-dir -e . 2>/dev/null || true

# 5. 心语 xinyu
COPY ./langs/xinyu ${LANGS_DIR}/xinyu
RUN cd ${LANGS_DIR}/xinyu && pip install --no-cache-dir -e . 2>/dev/null || true

# 6. 墨言 moyan
COPY ./langs/moyan ${LANGS_DIR}/moyan
RUN cd ${LANGS_DIR}/moyan && pip install --no-cache-dir -e . 2>/dev/null || true

# 7. 言律 yanlv
COPY ./langs/yanlv ${LANGS_DIR}/yanlv
RUN cd ${LANGS_DIR}/yanlv && pip install --no-cache-dir -e . 2>/dev/null || true

# 8. 明道 mingdao (Racket 语言)
COPY ./langs/mingdao ${LANGS_DIR}/mingdao
RUN raco pkg install --auto --link ${LANGS_DIR}/mingdao 2>/dev/null || true

# 9. 翰语 hanyu
COPY ./langs/hanyu ${LANGS_DIR}/hanyu
RUN cd ${LANGS_DIR}/hanyu && pip install --no-cache-dir -e . 2>/dev/null || true

# 10. 段言 duan
COPY ./langs/duan ${LANGS_DIR}/duan
RUN cd ${LANGS_DIR}/duan && pip install --no-cache-dir -e . 2>/dev/null || true

# 11. 华语 hua（无标准 pyproject.toml，依赖已在 Stage 1 安装）
COPY ./langs/hua ${LANGS_DIR}/hua

# ── Stage 3: 安装 YanPub 自身 ──────────────────────────
FROM langs AS app

WORKDIR /opt/yanpub
COPY . .
RUN pip install --no-cache-dir -e .

# ── 环境变量 ──────────────────────────────────────────
# _path_resolver.py 优先读取 YANPUB_LANG_DIR，自动派生 /opt/langs/<lang_id>
# 无需为每个语言单独设环境变量
ENV YANPUB_LANG_DIR=/opt/langs

EXPOSE 8080

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["playground"]
