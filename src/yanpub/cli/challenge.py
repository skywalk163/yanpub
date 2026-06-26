"""挑战赛命令"""

from __future__ import annotations

import click

from yanpub.cli import main

@click.group("challenge")
def challenge():
    """代码挑战赛 — 题目/评判/排行榜"""
    pass

@challenge.command("list")
@click.option("--difficulty", "-d", default=None, help="按难度筛选")
@click.option("--tag", "-t", default=None, help="按标签筛选")
def challenge_list(difficulty, tag):
    """列出所有挑战"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    challenges = mgr.list_challenges(difficulty=difficulty, tag=tag)
    if not challenges:
        click.echo("暂无挑战")
        return
    click.echo(f"共 {len(challenges)} 个挑战:")
    for c in challenges:
        rate = f"{c.pass_rate:.0%}" if c.pass_rate else "N/A"
        click.echo(f"  [{c.difficulty}] {c.title} ({c.id}) — {c.score}分 通过率:{rate}")

@challenge.command("show")
@click.argument("challenge_id")
def challenge_show(challenge_id):
    """查看挑战详情"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    c = mgr.get_challenge(challenge_id)
    if c is None:
        click.echo(f"挑战不存在: {challenge_id}", err=True)
        return
    click.echo(f"标题: {c.title}")
    click.echo(f"难度: {c.difficulty}  分值: {c.score}分")
    click.echo(f"标签: {', '.join(c.tags) if c.tags else '无'}")
    click.echo(f"描述: {c.description}")
    click.echo(f"时间限制: {c.time_limit_ms}ms  内存限制: {c.memory_limit_mb}MB")
    if c.supported_langs:
        click.echo(f"支持语言: {', '.join(c.supported_langs)}")
    else:
        click.echo("支持语言: 全部")
    click.echo(f"提交数: {c.submit_count}  通过数: {c.pass_count}")
    if c.public_test_cases:
        click.echo(f"公开测试用例: {len(c.public_test_cases)} 个")
        for i, tc in enumerate(c.public_test_cases, 1):
            click.echo(f"  用例{i}: 输入={tc.input!r} 期望输出={tc.expected_output!r}")

@challenge.command("submit")
@click.argument("challenge_id")
@click.argument("lang_id")
@click.option("--user", "-u", default="anonymous", help="用户名")
@click.option("--file", "-f", default=None, help="代码文件路径")
@click.option("--code", "-c", default=None, help="直接传入代码")
def challenge_submit(challenge_id, lang_id, user, file, code):
    """提交挑战解答"""
    from yanpub.playground.challenge import ChallengeManager

    if file:
        from pathlib import Path as PathLib
        code = PathLib(file).read_text(encoding="utf-8")
    elif not code:
        click.echo("请通过 --file 或 --code 提供代码", err=True)
        return

    mgr = ChallengeManager()
    try:
        submission = mgr.submit(challenge_id, user=user, lang_id=lang_id, code=code)
    except ValueError as e:
        click.echo(str(e), err=True)
        return

    status_icons = {
        "passed": "通过", "failed": "未通过", "error": "错误",
        "timeout": "超时", "pending": "等待中", "running": "运行中",
    }
    icon = status_icons.get(submission.status, submission.status)
    click.echo(f"提交结果: {icon}")
    click.echo(f"  通过用例: {submission.passed_cases}/{submission.total_cases}")
    click.echo(f"  得分: {submission.score}")
    click.echo(f"  执行时间: {submission.execution_time_ms:.1f}ms")
    if submission.error_message:
        click.echo(f"  错误: {submission.error_message}")

@challenge.command("leaderboard")
@click.argument("challenge_id", required=False)
def challenge_leaderboard(challenge_id):
    """查看排行榜"""
    from yanpub.playground.challenge import ChallengeManager

    mgr = ChallengeManager()
    entries = mgr.get_leaderboard(challenge_id=challenge_id)
    if not entries:
        click.echo("暂无排行数据")
        return
    scope = f"挑战 {challenge_id}" if challenge_id else "总排行"
    click.echo(f"{'='*50}")
    click.echo(f"  {scope} 排行榜")
    click.echo(f"{'='*50}")
    click.echo(f"{'排名':>4}  {'用户':<12}  {'总分':>6}  {'通过':>4}  {'平均耗时':>10}  {'常用语言':<8}")
    click.echo(f"{'-'*50}")
    for e in entries:
        click.echo(f"{e.rank:>4}  {e.user:<12}  {e.total_score:>6}  {e.challenges_passed:>4}  {e.avg_time_ms:>8.1f}ms  {e.best_lang:<8}")

@challenge.command("create")
@click.option("--id", "challenge_id", default=None, help="挑战ID")
@click.option("--title", "-t", default=None, help="标题")
@click.option("--difficulty", "-d", type=click.Choice(["入门", "简单", "中等", "困难", "地狱"]), default="中等", help="难度")
@click.option("--description", "-D", default=None, help="描述")
@click.option("--expected-output", "-o", default=None, help="期望输出（快速创建单测试用例）")
@click.option("--score", "-s", default=100, type=int, help="满分")
@click.option("--author", "-a", default="", help="作者")
def challenge_create(challenge_id, title, difficulty, description, expected_output, score, author):
    """创建新挑战"""
    from yanpub.playground.challenge import Challenge, TestCase, ChallengeManager

    if not title:
        title = click.prompt("标题")
    if not description:
        description = click.prompt("描述")

    if not challenge_id:
        challenge_id = title.lower().replace(" ", "-").replace("，", "-")

    test_cases = []
    if expected_output:
        test_cases.append(TestCase(input="", expected_output=expected_output))
    else:
        # 交互式添加测试用例
        click.echo("添加测试用例（空行结束）:")
        idx = 1
        while True:
            inp = click.prompt(f"  用例{idx} 输入", default="", show_default=False)
            out = click.prompt(f"  用例{idx} 期望输出", default="", show_default=False)
            if not out:
                break
            hidden = click.confirm(f"  用例{idx} 是否隐藏", default=False)
            test_cases.append(TestCase(input=inp, expected_output=out, is_hidden=hidden))
            idx += 1

    c = Challenge(
        id=challenge_id,
        title=title,
        description=description,
        difficulty=difficulty,
        test_cases=test_cases,
        score=score,
        author=author,
    )

    mgr = ChallengeManager()
    mgr.create_challenge(c)
    click.echo(f"挑战已创建: {c.id} ({c.title}), {len(c.test_cases)} 个测试用例")

main.add_command(challenge)
