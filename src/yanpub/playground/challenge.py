"""代码挑战赛系统 — 题目提交、在线评判、排行榜

核心模型：
1. Challenge — 挑战题目（描述、测试用例、难度、标签）
2. Submission — 用户提交（代码、语言、结果、得分）
3. Leaderboard — 排行榜（按分数/时间排名）

API 路由:
  GET  /api/challenges                  列出挑战
  GET  /api/challenges/{id}             挑战详情
  POST /api/challenges/{id}/submit      提交解答
  GET  /api/challenges/{id}/leaderboard 排行榜
  GET  /api/leaderboard                 总排行榜

CLI:
  yanpub challenge list                 列出挑战
  yanpub challenge show <id>            查看详情
  yanpub challenge submit <id>          提交解答
  yanpub challenge leaderboard [id]     查看排行榜
  yanpub challenge create               创建挑战
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from yanpub.core.registry import get_registry


@dataclass
class TestCase:
    """测试用例"""

    input: str  # 输入数据
    expected_output: str  # 期望输出
    is_hidden: bool = False  # 是否隐藏（不展示给用户）


@dataclass
class Challenge:
    """挑战题目"""

    id: str  # 唯一标识
    title: str  # 标题
    description: str  # 描述（Markdown）
    difficulty: str = "中等"  # 入门/简单/中等/困难/地狱
    tags: list[str] = field(default_factory=list)  # 标签
    supported_langs: list[str] = field(default_factory=list)  # 支持的语言ID，空=全部
    test_cases: list[TestCase] = field(default_factory=list)
    time_limit_ms: int = 5000  # 执行时间限制（毫秒）
    memory_limit_mb: int = 256  # 内存限制（MB）
    score: int = 100  # 满分
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    submit_count: int = 0
    pass_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.supported_langs:
            self.supported_langs = []  # 空=全部语言

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Challenge":
        # 处理嵌套的 test_cases
        if "test_cases" in data and data["test_cases"]:
            tc_data = data["test_cases"]
            if isinstance(tc_data, list) and tc_data and isinstance(tc_data[0], dict):
                data["test_cases"] = [TestCase(**tc) for tc in tc_data]
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def pass_rate(self) -> float:
        if self.submit_count == 0:
            return 0.0
        return self.pass_count / self.submit_count

    @property
    def public_test_cases(self) -> list[TestCase]:
        """非隐藏的测试用例"""
        return [tc for tc in self.test_cases if not tc.is_hidden]


@dataclass
class Submission:
    """用户提交"""

    id: str  # 唯一标识
    challenge_id: str  # 挑战ID
    user: str  # 用户标识
    lang_id: str  # 语言ID
    code: str  # 提交的代码
    status: str = "pending"  # pending/running/passed/failed/error/timeout
    score: int = 0  # 得分
    passed_cases: int = 0  # 通过的测试用例数
    total_cases: int = 0  # 总测试用例数
    execution_time_ms: float = 0  # 执行时间
    error_message: str = ""  # 错误信息
    submitted_at: str = ""
    judged_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.sha256(
                f"{self.challenge_id}:{self.user}:{time.time()}".encode()
            ).hexdigest()[:12]
        if not self.submitted_at:
            self.submitted_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LeaderboardEntry:
    """排行榜条目"""

    rank: int
    user: str
    total_score: int
    challenges_passed: int
    total_submissions: int
    avg_time_ms: float
    best_lang: str = ""


class ChallengeJudge:
    """评判器 — 执行用户提交的代码并与测试用例对比"""

    def judge(self, submission: Submission, challenge: Challenge) -> Submission:
        """评判提交

        通过适配器执行代码，逐个运行测试用例，对比输出。
        """
        registry = get_registry()
        adapter = registry.get(submission.lang_id)
        if adapter is None:
            submission.status = "error"
            submission.error_message = f"未知语言: {submission.lang_id}"
            submission.judged_at = datetime.now().isoformat()
            return submission

        submission.status = "running"
        total_time = 0.0
        passed = 0

        for i, tc in enumerate(challenge.test_cases):
            # 构建测试代码：将输入注入到代码中
            test_code = self._inject_input(submission.code, tc.input, submission.lang_id)

            try:
                start = time.monotonic()
                result = adapter.eval(test_code)
                elapsed = (time.monotonic() - start) * 1000
                total_time += elapsed

                # 检查超时
                if elapsed > challenge.time_limit_ms:
                    submission.status = "timeout"
                    submission.error_message = f"测试用例 {i+1} 超时（{elapsed:.0f}ms > {challenge.time_limit_ms}ms）"
                    break

                if result.exit_code != 0:
                    submission.status = "error"
                    submission.error_message = f"测试用例 {i+1} 执行错误: {result.stderr.strip()}"
                    break

                # 对比输出
                actual = result.stdout.strip()
                expected = tc.expected_output.strip()

                if actual == expected:
                    passed += 1
                else:
                    submission.status = "failed"
                    submission.error_message = (
                        f"测试用例 {i+1} 输出不匹配\n"
                        f"期望: {expected}\n"
                        f"实际: {actual}"
                    )
                    # 继续运行剩余用例以统计通过数
                    continue

            except Exception as e:
                submission.status = "error"
                submission.error_message = f"测试用例 {i+1} 异常: {e}"
                break

        total = len(challenge.test_cases)
        submission.passed_cases = passed
        submission.total_cases = total
        submission.execution_time_ms = total_time

        if passed == total:
            submission.status = "passed"
            submission.score = challenge.score
        elif submission.status in ("running",):
            submission.status = "failed"
            submission.score = int(challenge.score * passed / total) if total > 0 else 0

        submission.judged_at = datetime.now().isoformat()
        return submission

    def _inject_input(self, code: str, input_data: str, lang_id: str) -> str:
        """将测试输入注入到代码中

        策略：在代码前添加输入数据变量声明。
        """
        if not input_data:
            return code

        # 转义输入中的特殊字符
        escaped = input_data.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        # 根据语言生成输入声明
        input_lines = [
            f'__test_input__ = "{escaped}"',
            code,
        ]
        return "\n".join(input_lines)


class ChallengeManager:
    """挑战赛管理器"""

    def __init__(self, data_dir: Optional[Path] = None):
        if data_dir is None:
            data_dir = Path.home() / ".yanpub" / "challenges"
        self._dir = data_dir
        self._challenges: dict[str, Challenge] = {}
        self._submissions: list[Submission] = []
        self._judge = ChallengeJudge()
        self._load()

    def _load(self) -> None:
        """从磁盘加载挑战和提交"""
        # 加载挑战
        challenges_dir = self._dir / "challenges"
        if challenges_dir.exists():
            for f in challenges_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    challenge = Challenge.from_dict(data)
                    self._challenges[challenge.id] = challenge
                except (json.JSONDecodeError, KeyError):
                    continue

        # 加载提交
        submissions_file = self._dir / "submissions.json"
        if submissions_file.exists():
            try:
                data = json.loads(submissions_file.read_text(encoding="utf-8"))
                for s_data in data.get("submissions", []):
                    self._submissions.append(Submission(**s_data))
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_challenges(self) -> None:
        """保存挑战到磁盘"""
        challenges_dir = self._dir / "challenges"
        challenges_dir.mkdir(parents=True, exist_ok=True)
        for challenge in self._challenges.values():
            f = challenges_dir / f"{challenge.id}.json"
            f.write_text(json.dumps(challenge.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_submissions(self) -> None:
        """保存提交到磁盘"""
        self._dir.mkdir(parents=True, exist_ok=True)
        submissions_file = self._dir / "submissions.json"
        data = {
            "version": "1",
            "updated_at": datetime.now().isoformat(),
            "submissions": [s.to_dict() for s in self._submissions],
        }
        submissions_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_challenge(self, challenge: Challenge) -> Challenge:
        """创建挑战"""
        self._challenges[challenge.id] = challenge
        self._save_challenges()
        return challenge

    def get_challenge(self, challenge_id: str) -> Optional[Challenge]:
        """获取挑战"""
        return self._challenges.get(challenge_id)

    def list_challenges(self, difficulty: Optional[str] = None, tag: Optional[str] = None) -> list[Challenge]:
        """列出挑战"""
        results = list(self._challenges.values())
        if difficulty:
            results = [c for c in results if c.difficulty == difficulty]
        if tag:
            results = [c for c in results if tag in c.tags]
        return results

    def submit(self, challenge_id: str, user: str, lang_id: str, code: str) -> Submission:
        """提交解答"""
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            raise ValueError(f"挑战不存在: {challenge_id}")

        # 检查语言支持
        if challenge.supported_langs and lang_id not in challenge.supported_langs:
            raise ValueError(f"挑战不支持语言: {lang_id}，支持: {', '.join(challenge.supported_langs)}")

        submission = Submission(
            id="",
            challenge_id=challenge_id,
            user=user,
            lang_id=lang_id,
            code=code,
        )

        # 评判
        submission = self._judge.judge(submission, challenge)

        # 更新统计
        challenge.submit_count += 1
        if submission.status == "passed":
            challenge.pass_count += 1

        self._submissions.append(submission)
        self._save_challenges()
        self._save_submissions()

        return submission

    def get_submissions(self, challenge_id: Optional[str] = None, user: Optional[str] = None) -> list[Submission]:
        """查询提交"""
        results = self._submissions
        if challenge_id:
            results = [s for s in results if s.challenge_id == challenge_id]
        if user:
            results = [s for s in results if s.user == user]
        return results

    def get_leaderboard(self, challenge_id: Optional[str] = None) -> list[LeaderboardEntry]:
        """获取排行榜"""
        # 聚合每个用户的分数
        user_stats: dict[str, dict] = {}

        for sub in self._submissions:
            if challenge_id and sub.challenge_id != challenge_id:
                continue
            if sub.status != "passed":
                continue

            if sub.user not in user_stats:
                user_stats[sub.user] = {
                    "total_score": 0,
                    "challenges_passed": set(),
                    "total_submissions": 0,
                    "total_time_ms": 0.0,
                    "lang_scores": {},
                }

            stats = user_stats[sub.user]
            stats["total_score"] += sub.score
            stats["challenges_passed"].add(sub.challenge_id)
            stats["total_submissions"] += 1
            stats["total_time_ms"] += sub.execution_time_ms
            stats["lang_scores"][sub.lang_id] = stats["lang_scores"].get(sub.lang_id, 0) + sub.score

        # 排序
        entries = []
        for user, stats in sorted(
            user_stats.items(),
            key=lambda x: (-x[1]["total_score"], x[1]["total_time_ms"]),
        ):
            best_lang = max(stats["lang_scores"], key=stats["lang_scores"].get) if stats["lang_scores"] else ""
            avg_time = stats["total_time_ms"] / stats["total_submissions"] if stats["total_submissions"] > 0 else 0
            entries.append(
                LeaderboardEntry(
                    rank=0,
                    user=user,
                    total_score=stats["total_score"],
                    challenges_passed=len(stats["challenges_passed"]),
                    total_submissions=stats["total_submissions"],
                    avg_time_ms=round(avg_time, 1),
                    best_lang=best_lang,
                )
            )

        # 设置排名
        for i, entry in enumerate(entries):
            entry.rank = i + 1

        return entries

    def delete_challenge(self, challenge_id: str) -> bool:
        """删除挑战"""
        if challenge_id in self._challenges:
            del self._challenges[challenge_id]
            self._save_challenges()
            # 同时删除文件
            f = self._dir / "challenges" / f"{challenge_id}.json"
            if f.exists():
                f.unlink()
            return True
        return False


# ---- 内置挑战 ----

def get_builtin_challenges() -> list[Challenge]:
    """获取内置挑战题目"""
    return [
        Challenge(
            id="hello-world",
            title="你好世界",
            description='编写一个程序，输出"你好，世界！"',
            difficulty="入门",
            tags=["入门", "输出"],
            test_cases=[
                TestCase(input="", expected_output="你好，世界！"),
            ],
            score=10,
            author="yanpub",
        ),
        Challenge(
            id="fibonacci",
            title="斐波那契数列",
            description="编写一个程序，输出斐波那契数列的前 10 项，每行一个数字。",
            difficulty="简单",
            tags=["递归", "算法", "数列"],
            test_cases=[
                TestCase(
                    input="",
                    expected_output="0\n1\n1\n2\n3\n5\n8\n13\n21\n34",
                ),
            ],
            score=30,
            author="yanpub",
        ),
        Challenge(
            id="factorial",
            title="阶乘计算",
            description="编写一个程序，计算 10 的阶乘并输出结果。",
            difficulty="简单",
            tags=["递归", "数学"],
            test_cases=[
                TestCase(input="", expected_output="3628800"),
            ],
            score=25,
            author="yanpub",
        ),
        Challenge(
            id="is-prime",
            title="素数判断",
            description="编写一个程序，判断 97 是否为素数，输出\"是素数\"或\"不是素数\"。",
            difficulty="中等",
            tags=["算法", "数学"],
            test_cases=[
                TestCase(input="", expected_output="是素数"),
                TestCase(input="", expected_output="是素数", is_hidden=True),
            ],
            score=50,
            author="yanpub",
        ),
        Challenge(
            id="bubble-sort",
            title="冒泡排序",
            description='编写一个程序，对列表 [5, 3, 8, 1, 9, 2, 7, 4, 6] 进行升序排序，输出排序后的列表。',
            difficulty="中等",
            tags=["排序", "算法"],
            test_cases=[
                TestCase(input="", expected_output="[1, 2, 3, 4, 5, 6, 7, 8, 9]"),
            ],
            score=50,
            author="yanpub",
        ),
        Challenge(
            id="reverse-string",
            title="字符串反转",
            description="编写一个程序，将字符串\"中文编程语言\"反转并输出。",
            difficulty="入门",
            tags=["字符串", "入门"],
            test_cases=[
                TestCase(input="", expected_output="言语程编文中"),
            ],
            score=15,
            author="yanpub",
        ),
    ]
