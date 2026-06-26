(function() {
        'use strict';

        const API_BASE = '';
        let languages = [];
        let currentChallenge = null;

        // ---- Utility ----
        function showToast(msg, type) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast ' + type + ' show';
            setTimeout(() => { t.className = 'toast'; }, 2500);
        }

        function difficultyClass(d) {
            const map = {'入门':'badge-entry','简单':'badge-easy','中等':'badge-medium','困难':'badge-hard','地狱':'badge-hell'};
            return map[d] || 'badge-medium';
        }

        function statusClass(s) {
            const map = {'passed':'passed','failed':'failed','error':'error','timeout':'timeout'};
            return map[s] || '';
        }
        function statusLabel(s) {
            const map = {'passed':'通过','failed':'未通过','error':'错误','timeout':'超时','running':'运行中','pending':'等待中'};
            return map[s] || s;
        }

        function getUsername() {
            return document.getElementById('username').value.trim() || 'anonymous';
        }

        // ---- Languages ----
        function loadLanguages() {
            fetch(API_BASE + '/api/languages')
                .then(r => r.json())
                .then(data => {
                    languages = data;
                    const sel = document.getElementById('submit-lang');
                    sel.innerHTML = '<option value="">选择语言</option>';
                    data.forEach(lang => {
                        const opt = document.createElement('option');
                        opt.value = lang.id;
                        opt.textContent = lang.name + ' (' + lang.id + ')';
                        sel.appendChild(opt);
                    });
                })
                .catch(() => {});
        }

        // ---- Challenge List ----
        window.loadChallenges = function() {
            const diff = document.getElementById('filter-difficulty').value;
            let url = API_BASE + '/api/challenges';
            const params = [];
            if (diff) params.push('difficulty=' + encodeURIComponent(diff));
            if (params.length) url += '?' + params.join('&');

            fetch(url)
                .then(r => r.json())
                .then(data => {
                    const grid = document.getElementById('challenge-grid');
                    const challenges = data.challenges || [];
                    document.getElementById('challenge-count').textContent = challenges.length + ' 道题目';

                    if (challenges.length === 0) {
                        grid.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#128203;</div><div class="empty-state-text">暂无题目</div></div>';
                        return;
                    }

                    grid.innerHTML = '';
                    challenges.forEach(c => {
                        const card = document.createElement('div');
                        card.className = 'challenge-card';
                        card.onclick = () => showDetail(c.id);

                        const passRate = c.submit_count > 0 ? Math.round(c.pass_rate * 100) : 0;
                        card.innerHTML = `
                            <div class="challenge-card-header">
                                <span class="challenge-title">${escHtml(c.title)}</span>
                                <span class="challenge-score">${c.score} 分</span>
                            </div>
                            <div class="challenge-meta">
                                <span class="badge ${difficultyClass(c.difficulty)}">${escHtml(c.difficulty)}</span>
                                ${c.tags.map(t => '<span class="badge badge-tag">' + escHtml(t) + '</span>').join('')}
                                <span class="challenge-stats">${c.submit_count} 次提交 &middot; 通过率 ${passRate}%</span>
                            </div>
                        `;
                        grid.appendChild(card);
                    });
                })
                .catch(() => {
                    document.getElementById('challenge-grid').innerHTML =
                        '<div class="empty-state"><div class="empty-state-icon">&#9888;</div><div class="empty-state-text">加载失败，请检查 Playground 是否正在运行</div></div>';
                });
        };

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        // ---- Detail View ----
        function showDetail(id) {
            fetch(API_BASE + '/api/challenges/' + encodeURIComponent(id))
                .then(r => r.json())
                .then(data => {
                    if (data.error) { showToast(data.error, 'error'); return; }
                    currentChallenge = data;

                    document.getElementById('detail-title').textContent = data.title;
                    const diffBadge = document.getElementById('detail-difficulty');
                    diffBadge.textContent = data.difficulty;
                    diffBadge.className = 'badge ' + difficultyClass(data.difficulty);
                    document.getElementById('detail-score').textContent = data.score + ' 分';
                    document.getElementById('detail-desc').textContent = data.description;

                    // Test cases
                    const tcContainer = document.getElementById('detail-test-cases');
                    const publicTCs = data.public_test_cases || [];
                    if (publicTCs.length === 0) {
                        tcContainer.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">暂无公开测试用例</div>';
                    } else {
                        tcContainer.innerHTML = '';
                        publicTCs.forEach((tc, i) => {
                            const div = document.createElement('div');
                            div.className = 'test-case';
                            div.innerHTML = `
                                <div class="test-case-label">测试用例 #${i + 1}</div>
                                <div class="test-case-value">输入: ${escHtml(tc.input || '(无)')}</div>
                                <div class="test-case-value">期望输出: ${escHtml(tc.expected_output)}</div>
                            `;
                            tcContainer.appendChild(div);
                        });
                    }

                    const hiddenCount = data.hidden_test_count || 0;
                    document.getElementById('detail-hidden-info').textContent =
                        hiddenCount > 0 ? '另有 ' + hiddenCount + ' 个隐藏测试用例' : '';

                    // Filter submit lang to supported_langs if specified
                    const sel = document.getElementById('submit-lang');
                    if (data.supported_langs && data.supported_langs.length > 0) {
                        Array.from(sel.options).forEach(opt => {
                            opt.hidden = opt.value !== '' && !data.supported_langs.includes(opt.value);
                        });
                    } else {
                        Array.from(sel.options).forEach(opt => { opt.hidden = false; });
                    }

                    // Clear previous result
                    const resultEl = document.getElementById('submit-result');
                    resultEl.className = 'submit-result';
                    resultEl.innerHTML = '';
                    document.getElementById('submit-code').value = '';

                    // Load my submissions
                    loadMySubmissions(id);

                    // Switch view
                    document.getElementById('list-view').classList.remove('active');
                    document.getElementById('detail-view').classList.add('active');
                    document.querySelector('.tab-nav').style.display = 'none';
                    document.querySelector('.filter-bar').style.display = 'none';
                })
                .catch(() => showToast('加载失败', 'error'));
        }

        function loadMySubmissions(challengeId) {
            const user = getUsername();
            fetch(API_BASE + '/api/challenges/' + encodeURIComponent(challengeId) + '/submissions?user=' + encodeURIComponent(user) + '&limit=10')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('my-submissions');
                    const subs = data.submissions || [];
                    if (subs.length === 0) {
                        container.innerHTML = '<div style="color:var(--text-dim);font-size:13px;">暂无提交记录</div>';
                        return;
                    }
                    container.innerHTML = '';
                    subs.reverse().forEach(s => {
                        const div = document.createElement('div');
                        div.className = 'submission-item';
                        div.innerHTML = `
                            <span class="submission-status ${statusClass(s.status)}">${statusLabel(s.status)}</span>
                            <span style="color:var(--text-dim)">${escHtml(s.lang_id)}</span>
                            <span style="color:var(--text-dim)">${s.passed_cases || 0}/${s.total_cases || 0} 用例</span>
                            <span style="color:var(--text-dim)">${s.execution_time_ms || 0}ms</span>
                        `;
                        container.appendChild(div);
                    });
                })
                .catch(() => {});
        }

        window.backToList = function() {
            document.getElementById('detail-view').classList.remove('active');
            document.getElementById('list-view').classList.add('active');
            document.querySelector('.tab-nav').style.display = '';
            document.querySelector('.filter-bar').style.display = '';
            currentChallenge = null;
        };

        // ---- Submit ----
        window.submitSolution = function() {
            const langId = document.getElementById('submit-lang').value;
            const code = document.getElementById('submit-code').value;
            const user = getUsername();

            if (!langId) { showToast('请选择编程语言', 'error'); return; }
            if (!code.trim()) { showToast('请编写代码', 'error'); return; }
            if (!currentChallenge) return;

            const btn = document.getElementById('submit-btn');
            btn.disabled = true;
            btn.textContent = '提交中...';

            const resultEl = document.getElementById('submit-result');
            resultEl.className = 'submit-result';
            resultEl.innerHTML = '';

            fetch(API_BASE + '/api/challenges/' + encodeURIComponent(currentChallenge.id) + '/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lang: langId, code: code, user: user }),
            })
            .then(r => r.json())
            .then(data => {
                btn.disabled = false;
                btn.textContent = '提交';

                if (data.error) {
                    resultEl.className = 'submit-result show error';
                    resultEl.innerHTML = '<div class="result-status" style="color:var(--error)">提交失败</div><div class="result-detail">' + escHtml(data.error) + '</div>';
                    return;
                }

                const isPass = data.status === 'passed';
                resultEl.className = 'submit-result show ' + (isPass ? 'passed' : 'failed');
                resultEl.innerHTML = `
                    <div class="result-status" style="color:${isPass ? 'var(--success)' : 'var(--error)'}">${isPass ? '恭喜，全部通过！' : '未通过'}</div>
                    <div class="result-detail">
                        状态: ${statusLabel(data.status)} &middot;
                        通过: ${data.passed_cases || 0}/${data.total_cases || 0} 用例 &middot;
                        耗时: ${data.execution_time_ms || 0}ms
                        ${data.error_message ? '<br>错误: ' + escHtml(data.error_message) : ''}
                    </div>
                `;

                // Refresh my submissions
                loadMySubmissions(currentChallenge.id);
                // Refresh list stats
                loadChallenges();
            })
            .catch(() => {
                btn.disabled = false;
                btn.textContent = '提交';
                showToast('提交失败，请检查网络', 'error');
            });
        };

        // ---- Tab switching ----
        window.switchTab = function(tab) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
            document.getElementById('list-view').classList.toggle('active', tab === 'list');
            document.getElementById('detail-view').classList.remove('active');
            document.getElementById('leaderboard-view').classList.toggle('active', tab === 'leaderboard');

            if (tab === 'leaderboard') loadLeaderboard();
            if (tab === 'list') loadChallenges();
        };

        // ---- Leaderboard ----
        function loadLeaderboard() {
            fetch(API_BASE + '/api/leaderboard?limit=50')
                .then(r => r.json())
                .then(data => {
                    const container = document.getElementById('global-leaderboard');
                    const entries = data.leaderboard || [];
                    if (entries.length === 0) {
                        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#127942;</div><div class="empty-state-text">暂无排行数据，快去提交挑战吧！</div></div>';
                        return;
                    }
                    let html = '<table class="leaderboard-table"><thead><tr><th>排名</th><th>用户</th><th>总分</th><th>通过题数</th><th>提交次数</th><th>平均耗时</th><th>常用语言</th></tr></thead><tbody>';
                    entries.forEach(e => {
                        const rankClass = e.rank <= 3 ? ' rank-' + e.rank : '';
                        const rankSymbol = e.rank === 1 ? '&#129351;' : e.rank === 2 ? '&#129352;' : e.rank === 3 ? '&#129353;' : e.rank;
                        html += `<tr><td class="${rankClass}">${rankSymbol}</td><td>${escHtml(e.user)}</td><td style="color:var(--primary);font-weight:bold">${e.total_score}</td><td>${e.challenges_passed}</td><td>${e.total_submissions}</td><td>${e.avg_time_ms ? e.avg_time_ms.toFixed(0) + 'ms' : '-'}</td><td>${escHtml(e.best_lang || '-')}</td></tr>`;
                    });
                    html += '</tbody></table>';
                    container.innerHTML = html;
                })
                .catch(() => {
                    document.getElementById('global-leaderboard').innerHTML =
                        '<div class="empty-state"><div class="empty-state-icon">&#9888;</div><div class="empty-state-text">加载失败</div></div>';
                });
        }

        // ---- Init ----
        loadLanguages();
        loadChallenges();

    })();
