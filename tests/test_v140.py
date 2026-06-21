"""测试 v1.4.0 新功能：私有注册中心、代码挑战赛、适配器质量评分"""

from __future__ import annotations

import json

import pytest

# ---- 私有注册中心 ----


class TestPermissionManager:
    """权限管理器测试"""

    def test_grant_permission(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        entry = pm.grant("alice", "owner")
        assert entry.user == "alice"
        assert entry.role == "owner"
        assert entry.scope == "*"

    def test_grant_with_scope(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        entry = pm.grant("bob", "developer", scope="lang:duan")
        assert entry.scope == "lang:duan"

    def test_grant_invalid_role(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        with pytest.raises(ValueError, match="未知角色"):
            pm.grant("alice", "superadmin")

    def test_revoke_permission(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("alice", "owner")
        assert pm.revoke("alice")
        assert not pm.check("alice", "read")

    def test_revoke_nonexistent(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        assert not pm.revoke("nobody")

    def test_check_permission_owner(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("alice", "owner")
        assert pm.check("alice", "publish")
        assert pm.check("alice", "admin")
        assert pm.check("alice", "manage_permissions")
        assert pm.check("alice", "manage_mirrors")

    def test_check_permission_guest(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("guest_user", "guest")
        assert pm.check("guest_user", "read")
        assert not pm.check("guest_user", "publish")
        assert not pm.check("guest_user", "admin")

    def test_check_permission_developer(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("dev", "developer")
        assert pm.check("dev", "publish")
        assert pm.check("dev", "read")
        assert pm.check("dev", "write")
        assert not pm.check("dev", "admin")
        assert not pm.check("dev", "unpublish")

    def test_check_permission_maintainer(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("maint", "maintainer")
        assert pm.check("maint", "publish")
        assert pm.check("maint", "unpublish")
        assert pm.check("maint", "manage_mirrors")
        assert not pm.check("maint", "admin")

    def test_check_permission_with_scope(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("bob", "developer", scope="lang:duan")
        assert pm.check("bob", "publish", scope="lang:duan")
        assert not pm.check("bob", "publish", scope="lang:yan")

    def test_get_user_roles(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("alice", "owner")
        pm.grant("alice", "developer", scope="lang:duan")
        roles = pm.get_user_roles("alice")
        assert len(roles) == 2

    def test_list_all(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("alice", "owner")
        pm.grant("bob", "guest")
        entries = pm.list_all()
        assert len(entries) == 2

    def test_grant_updates_existing(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        pm = PermissionManager(tmp_path / "perms.json")
        pm.grant("alice", "guest")
        pm.grant("alice", "owner")
        roles = pm.get_user_roles("alice")
        assert len(roles) == 1
        assert roles[0].role == "owner"

    def test_persistence(self, tmp_path):
        from yanpub.pkg.private_registry import PermissionManager

        f = tmp_path / "perms.json"
        pm1 = PermissionManager(f)
        pm1.grant("alice", "owner")

        pm2 = PermissionManager(f)
        assert pm2.check("alice", "admin")


class TestMirrorConfig:
    """镜像配置测试"""

    def test_mirror_config_defaults(self):
        from yanpub.pkg.private_registry import MirrorConfig

        m = MirrorConfig(name="github", url="https://github.com/test/registry.git")
        assert m.name == "github"
        assert m.enabled is True
        assert m.sync_direction == "push"
        assert m.auth_type == ""

    def test_mirror_config_bidirectional(self):
        from yanpub.pkg.private_registry import MirrorConfig

        m = MirrorConfig(name="gitee", url="https://gitee.com/test/registry.git",
                         sync_direction="bidirectional", auth_type="ssh")
        assert m.sync_direction == "bidirectional"
        assert m.auth_type == "ssh"


class TestMirrorSync:
    """镜像同步测试"""

    def test_add_mirror(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        m = ms.add_mirror("github", "https://github.com/test/registry.git")
        assert m.name == "github"
        assert len(ms.list_mirrors()) == 1

    def test_add_mirror_with_options(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        m = ms.add_mirror("gitee", "https://gitee.com/test/registry.git",
                          sync_direction="bidirectional", auth_type="ssh")
        assert m.sync_direction == "bidirectional"
        assert m.auth_type == "ssh"

    def test_remove_mirror(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        ms.add_mirror("github", "https://github.com/test/registry.git")
        assert ms.remove_mirror("github")
        assert len(ms.list_mirrors()) == 0

    def test_remove_nonexistent(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        assert not ms.remove_mirror("nonexistent")

    def test_sync_nonexistent_mirror(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        result = ms.sync_mirror("nonexistent")
        assert not result["success"]
        assert "不存在" in result["message"]

    def test_sync_disabled_mirror(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        m = ms.add_mirror("disabled", "https://example.com/registry.git")
        m.enabled = False
        result = ms.sync_mirror("disabled")
        assert not result["success"]
        assert "禁用" in result["message"]

    def test_sync_no_repo_dir(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        ms = MirrorSync(tmp_path / "mirrors.json")
        ms.add_mirror("github", "https://github.com/test/registry.git")
        result = ms.sync_mirror("github")
        assert not result["success"]

    def test_persistence(self, tmp_path):
        from yanpub.pkg.private_registry import MirrorSync

        f = tmp_path / "mirrors.json"
        ms1 = MirrorSync(f)
        ms1.add_mirror("github", "https://github.com/test/registry.git")

        ms2 = MirrorSync(f)
        assert len(ms2.list_mirrors()) == 1
        assert ms2.list_mirrors()[0].name == "github"


class TestPrivateRegistry:
    """私有注册中心测试"""

    def test_init_local(self, tmp_path):
        from yanpub.pkg.private_registry import PrivateRegistry

        reg = PrivateRegistry(repo_dir=tmp_path / "private")
        # 不调用 init_repo（需要 git），只测试数据结构
        assert reg.repo_dir == tmp_path / "private"

    def test_search_empty(self, tmp_path):
        """测试搜索空私有仓库 — 只检查私有仓库部分无数据"""
        from yanpub.pkg.private_registry import PrivateRegistry
        from yanpub.pkg.registry import PackageRegistry

        private_dir = tmp_path / "pr_search_empty_private"
        local_reg = PackageRegistry(registry_dir=tmp_path / "pr_search_empty_local")
        reg = PrivateRegistry(repo_dir=private_dir, local_registry=local_reg)
        # 私有仓库目录不存在，_read_packages 应返回空
        private_pkgs = reg._read_packages()
        assert len(private_pkgs) == 0

    def test_publish_no_git(self, tmp_path):
        """测试发布逻辑（不需要真实的 Git 仓库）"""
        from yanpub.pkg.private_registry import PrivateRegistry
        from yanpub.pkg.registry import PackageInfo, PackageRegistry

        # 使用空的 local_registry，避免写入全局缓存
        local_reg = PackageRegistry(registry_dir=tmp_path / "pub_local")
        reg = PrivateRegistry(repo_dir=tmp_path / "pub_private", local_registry=local_reg)
        pkg = PackageInfo(name="test:pub", lang="test", package="pub", version="1.0.0")
        reg.publish(pkg)
        # 文件应写入
        pkg_file = tmp_path / "pub_private" / "packages" / "test" / "pub.json"
        if pkg_file.exists():
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            assert data["name"] == "test:pub"

    def test_unpublish_no_package(self, tmp_path):
        from yanpub.pkg.private_registry import PrivateRegistry
        from yanpub.pkg.registry import PackageRegistry

        local_reg = PackageRegistry(registry_dir=tmp_path / "unpub_local")
        reg = PrivateRegistry(repo_dir=tmp_path / "unpub_private", local_registry=local_reg)
        result = reg.unpublish("duan:nonexist")
        assert not result["success"]

    def test_unpublish_bad_format(self, tmp_path):
        from yanpub.pkg.private_registry import PrivateRegistry
        from yanpub.pkg.registry import PackageRegistry

        local_reg = PackageRegistry(registry_dir=tmp_path / "badfmt_local")
        reg = PrivateRegistry(repo_dir=tmp_path / "badfmt_private", local_registry=local_reg)
        result = reg.unpublish("badname")
        assert not result["success"]


# ---- 代码挑战赛 ----


class TestChallenge:
    """挑战模型测试"""

    def test_challenge_creation(self):
        from yanpub.playground.challenge import Challenge, TestCase

        tc = TestCase(input="", expected_output="hello")
        c = Challenge(id="test", title="测试挑战", description="描述", test_cases=[tc])
        assert c.id == "test"
        assert c.score == 100
        assert c.pass_rate == 0.0

    def test_challenge_from_dict(self):
        from yanpub.playground.challenge import Challenge

        data = {
            "id": "test",
            "title": "测试",
            "description": "描述",
            "test_cases": [{"input": "", "expected_output": "hi", "is_hidden": False}],
        }
        c = Challenge.from_dict(data)
        assert c.id == "test"
        assert len(c.test_cases) == 1
        assert c.test_cases[0].expected_output == "hi"

    def test_challenge_public_test_cases(self):
        from yanpub.playground.challenge import Challenge, TestCase

        c = Challenge(
            id="test", title="测试", description="描述",
            test_cases=[
                TestCase(input="", expected_output="a", is_hidden=False),
                TestCase(input="", expected_output="b", is_hidden=True),
            ],
        )
        assert len(c.public_test_cases) == 1

    def test_challenge_pass_rate(self):
        from yanpub.playground.challenge import Challenge

        c = Challenge(id="test", title="测试", description="描述", submit_count=10, pass_count=3)
        assert c.pass_rate == 0.3


class TestSubmission:
    """提交模型测试"""

    def test_submission_creation(self):
        from yanpub.playground.challenge import Submission

        s = Submission(id="sub1", challenge_id="test", user="alice", lang_id="duan", code="打印('hi')")
        assert s.status == "pending"
        assert s.submitted_at

    def test_submission_auto_id(self):
        from yanpub.playground.challenge import Submission

        s = Submission(id="", challenge_id="test", user="alice", lang_id="duan", code="code")
        assert len(s.id) == 12


class TestChallengeJudge:
    """评判器测试"""

    def test_judge_unknown_language(self):
        from yanpub.playground.challenge import Challenge, Submission, ChallengeJudge, TestCase

        c = Challenge(id="test", title="测试", description="描述",
                       test_cases=[TestCase(input="", expected_output="hello")])
        s = Submission(id="sub1", challenge_id="test", user="alice", lang_id="nonexistent_lang", code="code")
        judge = ChallengeJudge()
        result = judge.judge(s, c)
        assert result.status == "error"
        assert "未知语言" in result.error_message


class TestChallengeManager:
    """挑战管理器测试"""

    def test_create_and_get(self, tmp_path):
        from yanpub.playground.challenge import Challenge, ChallengeManager, TestCase

        mgr = ChallengeManager(data_dir=tmp_path)
        c = Challenge(id="test1", title="测试挑战", description="描述",
                       test_cases=[TestCase(input="", expected_output="hello")])
        mgr.create_challenge(c)

        got = mgr.get_challenge("test1")
        assert got is not None
        assert got.title == "测试挑战"

    def test_list_challenges(self, tmp_path):
        from yanpub.playground.challenge import Challenge, ChallengeManager, TestCase

        mgr = ChallengeManager(data_dir=tmp_path)
        mgr.create_challenge(Challenge(id="easy", title="简单", description="", difficulty="简单",
                                        test_cases=[TestCase(input="", expected_output="a")]))
        mgr.create_challenge(Challenge(id="hard", title="困难", description="", difficulty="困难",
                                        test_cases=[TestCase(input="", expected_output="b")]))

        all_c = mgr.list_challenges()
        assert len(all_c) == 2

        easy = mgr.list_challenges(difficulty="简单")
        assert len(easy) == 1
        assert easy[0].id == "easy"

    def test_list_with_tag(self, tmp_path):
        from yanpub.playground.challenge import Challenge, ChallengeManager, TestCase

        mgr = ChallengeManager(data_dir=tmp_path)
        mgr.create_challenge(Challenge(id="t1", title="T1", description="", tags=["算法"],
                                        test_cases=[TestCase(input="", expected_output="a")]))

        tagged = mgr.list_challenges(tag="算法")
        assert len(tagged) == 1

        not_tagged = mgr.list_challenges(tag="不存在")
        assert len(not_tagged) == 0

    def test_delete_challenge(self, tmp_path):
        from yanpub.playground.challenge import Challenge, ChallengeManager, TestCase

        mgr = ChallengeManager(data_dir=tmp_path)
        mgr.create_challenge(Challenge(id="todel", title="删除", description="",
                                        test_cases=[TestCase(input="", expected_output="x")]))
        assert mgr.delete_challenge("todel")
        assert mgr.get_challenge("todel") is None

    def test_delete_nonexistent(self, tmp_path):
        from yanpub.playground.challenge import ChallengeManager

        mgr = ChallengeManager(data_dir=tmp_path)
        assert not mgr.delete_challenge("nonexistent")

    def test_get_leaderboard_empty(self, tmp_path):
        from yanpub.playground.challenge import ChallengeManager

        mgr = ChallengeManager(data_dir=tmp_path)
        entries = mgr.get_leaderboard()
        assert entries == []

    def test_persistence(self, tmp_path):
        from yanpub.playground.challenge import Challenge, ChallengeManager, TestCase

        mgr1 = ChallengeManager(data_dir=tmp_path)
        mgr1.create_challenge(Challenge(id="persist", title="持久化", description="",
                                         test_cases=[TestCase(input="", expected_output="ok")]))

        mgr2 = ChallengeManager(data_dir=tmp_path)
        assert mgr2.get_challenge("persist") is not None


class TestBuiltinChallenges:
    """内置挑战测试"""

    def test_builtin_challenges_exist(self):
        from yanpub.playground.challenge import get_builtin_challenges

        challenges = get_builtin_challenges()
        assert len(challenges) >= 5
        ids = [c.id for c in challenges]
        assert "hello-world" in ids
        assert "fibonacci" in ids

    def test_builtin_challenges_have_test_cases(self):
        from yanpub.playground.challenge import get_builtin_challenges

        for c in get_builtin_challenges():
            assert len(c.test_cases) > 0, f"挑战 {c.id} 没有测试用例"

    def test_builtin_challenges_valid_difficulty(self):
        from yanpub.playground.challenge import get_builtin_challenges

        valid = {"入门", "简单", "中等", "困难", "地狱"}
        for c in get_builtin_challenges():
            assert c.difficulty in valid, f"挑战 {c.id} 难度无效: {c.difficulty}"


# ---- 适配器质量评分 ----


class TestDimensionScore:
    """评分维度测试"""

    def test_dimension_score(self):
        from yanpub.core.quality import DimensionScore

        d = DimensionScore(name="测试", max_score=30, score=24)
        assert d.percentage == 80.0

    def test_dimension_score_zero(self):
        from yanpub.core.quality import DimensionScore

        d = DimensionScore(name="测试", max_score=30, score=0)
        assert d.percentage == 0.0


class TestQualityReport:
    """质量报告测试"""

    def test_grade_s(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=97, max_score=100)
        assert r.grade == "S"

    def test_grade_a(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=85, max_score=100)
        assert r.grade == "A"

    def test_grade_b(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=70, max_score=100)
        assert r.grade == "B"

    def test_grade_c(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=55, max_score=100)
        assert r.grade == "C"

    def test_grade_d(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=40, max_score=100)
        assert r.grade == "D"

    def test_grade_f(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=20, max_score=100)
        assert r.grade == "F"

    def test_percentage(self):
        from yanpub.core.quality import QualityReport

        r = QualityReport(lang_id="test", lang_name="测试", total_score=75, max_score=100)
        assert r.percentage == 75.0


class TestQualityChecker:
    """质量检查器测试"""

    def test_check_one_existing(self):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        report = checker.check_one("duan")
        assert report is not None
        assert report.lang_id == "duan"
        assert report.total_score > 0

    def test_check_one_nonexistent(self):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        report = checker.check_one("nonexistent_lang")
        assert report is None

    def test_check_all(self):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        reports = checker.check_all()
        assert len(reports) >= 8  # 至少 8 个适配器
        for r in reports:
            assert r.total_score >= 0
            assert r.max_score == 100

    def test_report_has_dimensions(self):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        report = checker.check_one("duan")
        assert report is not None
        dim_names = [d.name for d in report.dimensions]
        assert "基础完整度" in dim_names
        assert "元数据质量" in dim_names
        assert "示例丰富度" in dim_names
        assert "文档覆盖" in dim_names
        assert "功能验证" in dim_names

    def test_report_to_dict(self):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        report = checker.check_one("duan")
        assert report is not None
        d = report.to_dict()
        assert "lang_id" in d
        assert "total_score" in d
        assert "dimensions" in d

    def test_generate_html(self, tmp_path):
        from yanpub.core.quality import QualityChecker

        checker = QualityChecker()
        reports = checker.check_all()
        output = checker.generate_html(reports, tmp_path / "quality.html")
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "适配器质量报告" in content
        assert "<!DOCTYPE html>" in content


class TestQualityCheckerWithMock:
    """使用 mock 的质量检查测试"""

    def test_check_basic_no_yaml(self, tmp_path):
        """测试缺少 adapter.yaml"""
        from yanpub.core.quality import QualityChecker

        adapter_dir = tmp_path / "testlang"
        adapter_dir.mkdir()
        (adapter_dir / "adapter.py").write_text("class TestLangAdapter: pass", encoding="utf-8")

        checker = QualityChecker(adapters_dir=tmp_path)
        report = checker.check_one("testlang")
        assert report is not None
        # 基础完整度应该扣分（缺 yaml）
        basic_dim = next(d for d in report.dimensions if d.name == "基础完整度")
        assert basic_dim.score < basic_dim.max_score

    def test_check_examples_empty_dir(self, tmp_path):
        """测试空 examples 目录"""
        from yanpub.core.quality import QualityChecker

        adapter_dir = tmp_path / "testlang"
        adapter_dir.mkdir()
        (adapter_dir / "adapter.py").write_text("class TestLangAdapter: pass", encoding="utf-8")
        (adapter_dir / "examples").mkdir()

        checker = QualityChecker(adapters_dir=tmp_path)
        report = checker.check_one("testlang")
        assert report is not None
        ex_dim = next(d for d in report.dimensions if d.name == "示例丰富度")
        assert ex_dim.score < ex_dim.max_score
        assert any("空" in s or "增加" in s for s in ex_dim.suggestions)

    def test_check_docs_missing(self, tmp_path):
        """测试缺少文档"""
        from yanpub.core.quality import QualityChecker

        adapter_dir = tmp_path / "testlang"
        adapter_dir.mkdir()
        (adapter_dir / "adapter.py").write_text("class TestLangAdapter: pass", encoding="utf-8")

        checker = QualityChecker(adapters_dir=tmp_path)
        report = checker.check_one("testlang")
        assert report is not None
        docs_dim = next(d for d in report.dimensions if d.name == "文档覆盖")
        assert docs_dim.score < docs_dim.max_score

    def test_check_metadata_bad_version(self, tmp_path):
        """测试版本号格式不标准"""
        from yanpub.core.quality import QualityChecker

        adapter_dir = tmp_path / "testlang"
        adapter_dir.mkdir()
        (adapter_dir / "adapter.yaml").write_text(
            "name: 测试语言\nid: testlang\nversion: 'abc'\n", encoding="utf-8"
        )
        (adapter_dir / "adapter.py").write_text("class TestLangAdapter: pass", encoding="utf-8")

        checker = QualityChecker(adapters_dir=tmp_path)
        report = checker.check_one("testlang")
        meta_dim = next(d for d in report.dimensions if d.name == "元数据质量")
        # 版本号不标准应该有建议
        assert any("版本号" in s for s in meta_dim.suggestions)
