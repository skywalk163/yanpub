"""语义发布 — 基于 Conventional Commits 的自动版本号和 Changelog 生成

核心能力：
1. SemanticVersion — 语义化版本号解析与比较
2. ConventionalCommitParser — 解析 Conventional Commits 格式
3. VersionBumper — 根据 commit 类型自动递增版本号
4. ChangelogGenerator — 生成结构化 CHANGELOG.md

命令:
  yanpub pkg semantic-release   — 自动版本号 + changelog 生成
  yanpub pkg changelog          — 仅生成 changelog
  yanpub pkg bump-version       — 仅递增版本号
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SemanticVersion:
    """语义化版本号（SemVer 2.0）"""
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: str = ""
    build: str = ""

    @classmethod
    def parse(cls, version_str: str) -> "SemanticVersion":
        """解析版本号字符串

        支持格式：
          1.0.0
          1.0.0-alpha
          1.0.0-alpha.1
          1.0.0+build.123
          1.0.0-alpha+build.123
        """
        version_str = version_str.lstrip("vV")
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$'
        m = re.match(pattern, version_str)
        if not m:
            raise ValueError(f"无效的语义版本号: {version_str}")

        return cls(
            major=int(m.group(1)),
            minor=int(m.group(2)),
            patch=int(m.group(3)),
            prerelease=m.group(4) or "",
            build=m.group(5) or "",
        )

    def __str__(self) -> str:
        v = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            v += f"-{self.prerelease}"
        if self.build:
            v += f"+{self.build}"
        return v

    def __lt__(self, other: "SemanticVersion") -> bool:
        return self._cmp_tuple() < other._cmp_tuple()

    def __le__(self, other: "SemanticVersion") -> bool:
        return self._cmp_tuple() <= other._cmp_tuple()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return self._cmp_tuple() == other._cmp_tuple()

    def __gt__(self, other: "SemanticVersion") -> bool:
        return self._cmp_tuple() > other._cmp_tuple()

    def __ge__(self, other: "SemanticVersion") -> bool:
        return self._cmp_tuple() >= other._cmp_tuple()

    def _cmp_tuple(self) -> tuple:
        """用于比较的元组（有预发布版本时排序更低）"""
        pre = (0, self.prerelease) if self.prerelease else (1, "")
        return (self.major, self.minor, self.patch, pre)

    def bump_major(self) -> "SemanticVersion":
        return SemanticVersion(major=self.major + 1, minor=0, patch=0)

    def bump_minor(self) -> "SemanticVersion":
        return SemanticVersion(major=self.major, minor=self.minor + 1, patch=0)

    def bump_patch(self) -> "SemanticVersion":
        return SemanticVersion(major=self.major, minor=self.minor, patch=self.patch + 1)


# ---- Conventional Commits ----

# 格式: type(scope): description
# type: feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert
COMMIT_PATTERN = re.compile(
    r'^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)'
    r'(?:\((?P<scope>[^)]+)\))?'
    r'(?P<breaking>!)?'
    r':\s*(?P<description>.+)$'
)

# 中文 commit 类型映射
COMMIT_TYPE_NAMES = {
    "feat": "新功能",
    "fix": "修复",
    "docs": "文档",
    "style": "样式",
    "refactor": "重构",
    "perf": "性能",
    "test": "测试",
    "build": "构建",
    "ci": "CI",
    "chore": "杂务",
    "revert": "回退",
}


@dataclass
class ConventionalCommit:
    """解析后的 Conventional Commit"""
    type: str               # feat, fix, docs, ...
    scope: str = ""         # 可选的作用域
    description: str = ""   # 描述
    breaking: bool = False  # 是否是破坏性变更
    body: str = ""          # commit body
    hash: str = ""          # commit hash
    date: str = ""          # commit date

    @classmethod
    def parse(cls, message: str, hash_str: str = "", date: str = "") -> Optional["ConventionalCommit"]:
        """解析 commit 消息

        Args:
            message: commit 消息（第一行）
            hash_str: commit hash
            date: commit 日期

        Returns:
            ConventionalCommit 或 None（不匹配时）
        """
        # 只取第一行
        first_line = message.split("\n")[0].strip()
        m = COMMIT_PATTERN.match(first_line)
        if not m:
            return None

        breaking = bool(m.group("breaking"))

        # 检查 body 中是否有 BREAKING CHANGE
        body = ""
        if "\n" in message:
            body = message.split("\n", 1)[1].strip()
            if "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body:
                breaking = True

        return cls(
            type=m.group("type"),
            scope=m.group("scope") or "",
            description=m.group("description"),
            breaking=breaking,
            body=body,
            hash=hash_str[:7] if hash_str else "",
            date=date,
        )

    @property
    def type_name(self) -> str:
        """中文类型名"""
        return COMMIT_TYPE_NAMES.get(self.type, self.type)


class VersionBumper:
    """版本号递增器

    根据 Conventional Commits 自动决定版本号递增方式：
    - feat → minor
    - fix → patch
    - feat! 或 BREAKING CHANGE → major
    """

    @staticmethod
    def determine_bump(commits: list[ConventionalCommit]) -> str:
        """根据 commit 列表决定版本递增类型

        Returns:
            "major" / "minor" / "patch" / "none"
        """
        if not commits:
            return "none"

        has_breaking = any(c.breaking for c in commits)
        has_feat = any(c.type == "feat" for c in commits)

        if has_breaking:
            return "major"
        if has_feat:
            return "minor"
        # 有 fix/docs 等也 bump patch
        if any(c.type in ("fix", "docs", "perf", "refactor") for c in commits):
            return "patch"

        return "none"

    @staticmethod
    def bump(current: SemanticVersion, bump_type: str) -> SemanticVersion:
        """递增版本号

        Args:
            current: 当前版本
            bump_type: "major" / "minor" / "patch"

        Returns:
            新版本号
        """
        if bump_type == "major":
            return current.bump_major()
        elif bump_type == "minor":
            return current.bump_minor()
        elif bump_type == "patch":
            return current.bump_patch()
        return current


class ChangelogGenerator:
    """Changelog 生成器

    根据 Conventional Commits 生成结构化的 CHANGELOG.md。
    遵循 Keep a Changelog 格式。
    """

    @staticmethod
    def generate(
        commits: list[ConventionalCommit],
        version: str = "Unreleased",
        date: str = "",
        previous_changelog: str = "",
    ) -> str:
        """生成 CHANGELOG.md 内容

        Args:
            commits: 解析后的 commit 列表
            version: 版本号
            date: 发布日期
            previous_changelog: 已有的 changelog 内容（新内容会插入前面）

        Returns:
            完整的 CHANGELOG.md 内容
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        # 按 type 分组
        groups: dict[str, list[ConventionalCommit]] = {
            "feat": [],
            "fix": [],
            "perf": [],
            "refactor": [],
            "docs": [],
            "test": [],
            "build": [],
            "ci": [],
            "chore": [],
            "revert": [],
        }
        breaking_commits = []

        for commit in commits:
            if commit.breaking:
                breaking_commits.append(commit)
            if commit.type in groups:
                groups[commit.type].append(commit)

        # 生成条目
        lines = []
        lines.append(f"## {version} - {date}")
        lines.append("")

        if breaking_commits:
            lines.append("### 💥 破坏性变更")
            lines.append("")
            for c in breaking_commits:
                scope_str = f"**{c.scope}**: " if c.scope else ""
                hash_str = f" (`{c.hash}`)" if c.hash else ""
                lines.append(f"- {scope_str}{c.description}{hash_str}")
            lines.append("")

        for commit_type, type_commits in groups.items():
            if not type_commits:
                continue
            # 跳过纯 chore 类（除非有内容）
            if commit_type == "chore" and not any(c.scope for c in type_commits):
                continue

            type_name = COMMIT_TYPE_NAMES.get(commit_type, commit_type)
            lines.append(f"### {type_name}")
            lines.append("")

            # 按作用域分组
            by_scope: dict[str, list[ConventionalCommit]] = {}
            for c in type_commits:
                scope = c.scope or "_default"
                by_scope.setdefault(scope, []).append(c)

            for scope, scope_commits in sorted(by_scope.items()):
                for c in scope_commits:
                    scope_str = f"**{c.scope}**: " if c.scope else ""
                    hash_str = f" (`{c.hash}`)" if c.hash else ""
                    lines.append(f"- {scope_str}{c.description}{hash_str}")
            lines.append("")

        new_entry = "\n".join(lines)

        # 与已有 changelog 合并
        if previous_changelog:
            # 在第一个 ## 版本标题前插入
            header_end = previous_changelog.find("\n## ")
            if header_end >= 0:
                return (
                    previous_changelog[:header_end + 1]
                    + "\n"
                    + new_entry
                    + "\n"
                    + previous_changelog[header_end + 1:]
                )
            return new_entry + "\n" + previous_changelog

        # 生成完整文件（含头部）
        header = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n"
        return header + new_entry


def parse_git_log(log_text: str) -> list[ConventionalCommit]:
    """从 git log 输出解析 Conventional Commits

    git log 格式: hash|||date|||message（由 %h|||%ad|||%s 分隔）

    Args:
        log_text: git log 输出

    Returns:
        解析后的 commit 列表
    """
    commits = []
    for line in log_text.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|||", 2)
        if len(parts) < 3:
            continue
        hash_str, date, message = parts[0].strip(), parts[1].strip(), parts[2].strip()
        commit = ConventionalCommit.parse(message, hash_str, date)
        if commit is not None:
            commits.append(commit)
    return commits


def semantic_release(
    project_dir: Path,
    dry_run: bool = False,
) -> dict:
    """执行语义发布

    1. 读取当前版本
    2. 解析 git log 中的 conventional commits
    3. 自动递增版本号
    4. 生成 changelog
    5. 更新项目文件

    Args:
        project_dir: 项目目录
        dry_run: 试运行（不修改文件）

    Returns:
        发布结果 {
            previous_version: str,
            new_version: str,
            bump_type: str,
            commits_count: int,
            changelog_path: str,
        }
    """
    # 读取 yanpkg.toml 中的版本
    toml_path = project_dir / "yanpkg.toml"
    if not toml_path.exists():
        return {
            "error": "未找到 yanpkg.toml",
            "previous_version": "0.0.0",
            "new_version": "0.0.0",
            "bump_type": "none",
            "commits_count": 0,
            "changelog_path": "",
        }

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    with open(toml_path, "rb") as f:
        config = tomllib.load(f)

    current_version_str = config.get("package", {}).get("version", "0.0.0")
    current_version = SemanticVersion.parse(current_version_str)

    # 获取 git log
    commits = _get_commits_since_tag(project_dir)

    if not commits:
        return {
            "previous_version": str(current_version),
            "new_version": str(current_version),
            "bump_type": "none",
            "commits_count": 0,
            "changelog_path": "",
        }

    # 决定版本递增
    bump_type = VersionBumper.determine_bump(commits)
    new_version = VersionBumper.bump(current_version, bump_type)

    # 生成 changelog
    changelog_path = project_dir / "CHANGELOG.md"
    previous_changelog = ""
    if changelog_path.exists():
        previous_changelog = changelog_path.read_text(encoding="utf-8")

    changelog_content = ChangelogGenerator.generate(
        commits,
        version=str(new_version),
        previous_changelog=previous_changelog,
    )

    result = {
        "previous_version": str(current_version),
        "new_version": str(new_version),
        "bump_type": bump_type,
        "commits_count": len(commits),
        "changelog_path": str(changelog_path),
    }

    if not dry_run and bump_type != "none":
        # 更新 yanpkg.toml 版本号
        _update_toml_version(toml_path, str(new_version))
        # 写入 changelog
        changelog_path.write_text(changelog_content, encoding="utf-8")

    return result


def _get_commits_since_tag(project_dir: Path) -> list[ConventionalCommit]:
    """获取自上次 tag 以来的 conventional commits"""
    import subprocess

    # 获取最新 tag
    try:
        latest_tag = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=10,
        )
        tag_ref = latest_tag.stdout.strip() if latest_tag.returncode == 0 else ""
    except Exception:
        tag_ref = ""

    # 获取 commit log
    try:
        log_range = f"{tag_ref}..HEAD" if tag_ref else "HEAD~50..HEAD"
        result = subprocess.run(
            ["git", "log", log_range, "--pretty=format:%h|||%ad|||%s", "--date=short"],
            capture_output=True, text=True,
            cwd=str(project_dir), timeout=10,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return []
        return parse_git_log(result.stdout)
    except Exception:
        return []


def _update_toml_version(toml_path: Path, new_version: str) -> None:
    """更新 yanpkg.toml 中的版本号（纯文本替换）"""
    content = toml_path.read_text(encoding="utf-8")
    # 替换 version = "x.y.z" 行
    content = re.sub(
        r'(^version\s*=\s*)"[^"]*"',
        f'\\g<1>"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    toml_path.write_text(content, encoding="utf-8")
