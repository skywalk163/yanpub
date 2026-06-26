(function() {
        'use strict';

        const API_BASE = '';
        let reports = [];

        // ---- Utility ----
        function showToast(msg, type) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.className = 'toast ' + type + ' show';
            setTimeout(() => { t.className = 'toast'; }, 2500);
        }

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s;
            return d.innerHTML;
        }

        function gradeColor(g) {
            const map = {'S':'#2ecc71','A':'#27ae60','B':'#3498db','C':'#f39c12','D':'#e67e22','F':'#e74c3c'};
            return map[g] || '#95a5a6';
        }

        function barColor(pct) {
            if (pct >= 80) return '#2ecc71';
            if (pct >= 50) return '#f39c12';
            return '#e74c3c';
        }

        function gradeRank(g) {
            const map = {'S':6,'A':5,'B':4,'C':3,'D':2,'F':1};
            return map[g] || 0;
        }

        // ---- Load ----
        function loadQuality() {
            fetch(API_BASE + '/api/quality')
                .then(r => r.json())
                .then(data => {
                    if (data.error) { showToast(data.error, 'error'); return; }
                    reports = data.reports || [];
                    renderOverview();
                    renderAdapters();
                })
                .catch(() => {
                    document.getElementById('adapter-list').innerHTML =
                        '<div style="text-align:center;padding:40px;color:var(--text-dim)">加载失败，请检查 Playground 是否正在运行</div>';
                });
        }

        // ---- Overview ----
        function renderOverview() {
            document.getElementById('ov-count').textContent = reports.length;

            if (reports.length === 0) {
                document.getElementById('ov-avg').textContent = '-';
                document.getElementById('ov-highest').textContent = '-';
                document.getElementById('ov-grades').textContent = '-';
                return;
            }

            const avg = reports.reduce((s, r) => s + r.total_score, 0) / reports.length;
            document.getElementById('ov-avg').textContent = avg.toFixed(1);

            const highest = reports.reduce((m, r) => r.total_score > m.total_score ? r : m, reports[0]);
            document.getElementById('ov-highest').textContent = highest.total_score;

            // Grade distribution
            const gradeCounts = {};
            reports.forEach(r => { gradeCounts[r.grade] = (gradeCounts[r.grade] || 0) + 1; });
            const gradeStr = Object.entries(gradeCounts)
                .sort((a, b) => gradeRank(b[0]) - gradeRank(a[0]))
                .map(([g, c]) => g + ':' + c)
                .join(' ');
            document.getElementById('ov-grades').textContent = gradeStr;
        }

        // ---- Adapter list ----
        window.renderAdapters = function() {
            const sortVal = document.getElementById('sort-select').value;
            let sorted = [...reports];

            switch (sortVal) {
                case 'score-desc': sorted.sort((a, b) => b.total_score - a.total_score); break;
                case 'score-asc': sorted.sort((a, b) => a.total_score - b.total_score); break;
                case 'name-asc': sorted.sort((a, b) => a.lang_name.localeCompare(b.lang_name, 'zh')); break;
                case 'grade-desc': sorted.sort((a, b) => gradeRank(b.grade) - gradeRank(a.grade) || b.total_score - a.total_score); break;
            }

            document.getElementById('adapter-count').textContent = sorted.length + ' 个适配器';

            const container = document.getElementById('adapter-list');
            if (sorted.length === 0) {
                container.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-dim)">暂无适配器数据</div>';
                return;
            }

            container.innerHTML = '';
            sorted.forEach((r, idx) => {
                const card = document.createElement('div');
                card.className = 'adapter-card';
                card.dataset.idx = idx;

                // Dimensions HTML
                let dimHtml = '';
                r.dimensions.forEach(d => {
                    const pct = d.max_score > 0 ? (d.score / d.max_score * 100) : 0;
                    dimHtml += `
                        <div class="dim-row">
                            <span class="dim-name">${escHtml(d.name)}</span>
                            <div class="dim-bar-bg">
                                <div class="dim-bar-fill" style="width:${pct}%;background:${barColor(pct)}"></div>
                            </div>
                            <span class="dim-score">${d.score}/${d.max_score}</span>
                        </div>`;
                });

                // Details HTML
                let detailsHtml = '';
                r.dimensions.forEach(d => {
                    const passItems = d.details.map(s => '<div class="detail-item pass">&#10003; ' + escHtml(s) + '</div>').join('');
                    const suggestItems = d.suggestions.map(s => '<div class="detail-item suggestion">&#9888; ' + escHtml(s) + '</div>').join('');
                    if (passItems || suggestItems) {
                        detailsHtml += `
                            <div class="detail-block">
                                <h4>${escHtml(d.name)}</h4>
                                ${passItems}${suggestItems}
                            </div>`;
                    }
                });

                const pct = r.max_score > 0 ? (r.total_score / r.max_score * 100) : 0;

                card.innerHTML = `
                    <div class="adapter-header">
                        <span class="grade-badge" style="background:${gradeColor(r.grade)}">${escHtml(r.grade)}</span>
                        <div class="adapter-info">
                            <div class="adapter-name">${escHtml(r.lang_name)} <small>${escHtml(r.lang_id)}</small></div>
                            <div class="adapter-score-text">${pct.toFixed(1)}% | ${r.dimensions.length} 个维度</div>
                        </div>
                        <div class="adapter-right">
                            <div>
                                <span class="score-big">${r.total_score}</span>
                                <span class="score-max">/${r.max_score}</span>
                            </div>
                            <span class="expand-icon">&#9660;</span>
                        </div>
                    </div>
                    <div class="adapter-detail">
                        ${dimHtml}
                        <div class="detail-section">
                            ${detailsHtml}
                        </div>
                    </div>`;

                card.addEventListener('click', function() {
                    this.classList.toggle('expanded');
                });

                container.appendChild(card);
            });
        };

        // ---- Init ----
        loadQuality();

    })();
