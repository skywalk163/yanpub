"""Playground 路由 — 代码挑战赛、适配器质量评分"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import JSONResponse


def _as_dict_tc(tc):
    """TestCase 转字典"""
    return asdict(tc)


def register_challenge_routes(app: FastAPI) -> None:
    """注册代码挑战赛路由"""
    from yanpub.playground.challenge import ChallengeManager, get_builtin_challenges

    _challenge_mgr = ChallengeManager()

    # 加载内置挑战（如果尚未创建）
    for c in get_builtin_challenges():
        if _challenge_mgr.get_challenge(c.id) is None:
            _challenge_mgr.create_challenge(c)

    @app.get("/api/challenges")
    async def list_challenges(difficulty: str | None = None, tag: str | None = None):
        """列出挑战"""
        challenges = _challenge_mgr.list_challenges(difficulty=difficulty, tag=tag)
        return {
            "challenges": [
                {
                    "id": c.id,
                    "title": c.title,
                    "difficulty": c.difficulty,
                    "tags": c.tags,
                    "score": c.score,
                    "supported_langs": c.supported_langs,
                    "submit_count": c.submit_count,
                    "pass_count": c.pass_count,
                    "pass_rate": round(c.pass_rate, 3),
                }
                for c in challenges
            ]
        }

    @app.get("/api/challenges/{challenge_id}")
    async def get_challenge(challenge_id: str):
        """获取挑战详情"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        result = c.to_dict()
        # 只返回非隐藏的测试用例
        result["public_test_cases"] = [_as_dict_tc(tc) for tc in c.public_test_cases]
        result["hidden_test_count"] = sum(1 for tc in c.test_cases if tc.is_hidden)
        return result

    @app.post("/api/challenges/{challenge_id}/submit")
    async def submit_challenge(challenge_id: str, body: dict):
        """提交挑战解答"""
        lang_id = body.get("lang", "")
        code = body.get("code", "")
        user = body.get("user", "anonymous")

        if not lang_id or not code.strip():
            return JSONResponse({"error": "缺少 lang 或 code 参数"}, status_code=400)

        try:
            submission = _challenge_mgr.submit(challenge_id, user=user, lang_id=lang_id, code=code)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        return submission.to_dict()

    @app.get("/api/challenges/{challenge_id}/leaderboard")
    async def challenge_leaderboard(challenge_id: str, limit: int = 20):
        """挑战排行榜"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        entries = _challenge_mgr.get_leaderboard(challenge_id=challenge_id)
        return {
            "challenge_id": challenge_id,
            "leaderboard": [
                {
                    "rank": e.rank,
                    "user": e.user,
                    "total_score": e.total_score,
                    "challenges_passed": e.challenges_passed,
                    "avg_time_ms": e.avg_time_ms,
                    "best_lang": e.best_lang,
                }
                for e in entries[:limit]
            ],
        }

    @app.get("/api/leaderboard")
    async def global_leaderboard(limit: int = 50):
        """总排行榜"""
        entries = _challenge_mgr.get_leaderboard()
        return {
            "leaderboard": [
                {
                    "rank": e.rank,
                    "user": e.user,
                    "total_score": e.total_score,
                    "challenges_passed": e.challenges_passed,
                    "total_submissions": e.total_submissions,
                    "avg_time_ms": e.avg_time_ms,
                    "best_lang": e.best_lang,
                }
                for e in entries[:limit]
            ],
        }

    @app.get("/api/challenges/{challenge_id}/submissions")
    async def list_submissions(challenge_id: str, user: str | None = None, limit: int = 20):
        """查询提交记录"""
        c = _challenge_mgr.get_challenge(challenge_id)
        if c is None:
            return JSONResponse({"error": "挑战不存在"}, status_code=404)
        submissions = _challenge_mgr.get_submissions(challenge_id=challenge_id, user=user)
        return {
            "submissions": [s.to_dict() for s in submissions[-limit:]],
        }


def register_quality_routes(app: FastAPI) -> None:
    """注册适配器质量评分路由"""

    @app.get("/api/quality")
    async def quality_reports(lang_id: str | None = None):
        """适配器质量评分报告"""
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        if lang_id:
            report = checker.check_one(lang_id)
            if report is None:
                return JSONResponse({"error": f"适配器 {lang_id} 不存在"}, status_code=404)
            return {"reports": [report.to_dict()]}
        reports = checker.check_all()
        return {"reports": [r.to_dict() for r in reports]}
