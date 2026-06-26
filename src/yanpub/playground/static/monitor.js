var ws = null;
var metricsData = {};
var chartColors = [
    '#E85D3A', '#4CAF50', '#2196F3', '#FF9800',
    '#9C27B0', '#00BCD4', '#FFEB3B', '#E91E63'
];

function connectWebSocket() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = proto + '//' + location.host + '/ws/monitor';
    ws = new WebSocket(url);

    ws.onopen = function() {
        document.getElementById('statusDot').classList.add('connected');
        document.getElementById('statusText').textContent = '已连接';
    };

    ws.onclose = function() {
        document.getElementById('statusDot').classList.remove('connected');
        document.getElementById('statusText').textContent = '已断开';
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = function() {
        document.getElementById('statusDot').classList.remove('connected');
        document.getElementById('statusText').textContent = '连接错误';
    };

    ws.onmessage = function(event) {
        var msg = JSON.parse(event.data);
        if (msg.type === 'metric') {
            handleMetric(msg.data);
        } else if (msg.type === 'dashboard') {
            handleDashboard(msg.data);
        }
    };
}

function handleMetric(data) {
    var key = data.adapter_id + ':' + data.metric;
    if (!metricsData[key]) {
        metricsData[key] = [];
    }
    metricsData[key].push(data);
    // 保留最近 100 个点
    if (metricsData[key].length > 100) {
        metricsData[key] = metricsData[key].slice(-100);
    }
    updateChart();
}

function handleDashboard(data) {
    // 更新概览卡片
    document.getElementById('activeAdapters').textContent = data.active_adapters || 0;
    document.getElementById('totalSamples').textContent = data.total_samples || 0;

    // 计算平均执行耗时
    var totalAvg = 0;
    var avgCount = 0;
    var totalErrorRate = 0;
    var errorCount = 0;

    var adapters = data.adapters || {};
    var gridHtml = '';

    for (var aid in adapters) {
        var adapter = adapters[aid];
        var metrics = adapter.metrics || {};
        var adapterHtml = '<div class="adapter-card">';
        adapterHtml += '<h3>' + aid + '</h3>';

        for (var metricName in metrics) {
            var m = metrics[metricName];
            var val = m.avg || 0;
            var cls = '';
            var unit = '';

            if (metricName.indexOf('duration') >= 0) {
                unit = ' ms';
                if (val < 100) cls = 'fast';
                else if (val < 500) cls = 'medium';
                else cls = 'slow';
                totalAvg += val;
                avgCount++;
            } else if (metricName === 'error_rate') {
                unit = '%';
                if (val < 5) cls = 'fast';
                else if (val < 20) cls = 'medium';
                else cls = 'slow';
                totalErrorRate += val;
                errorCount++;
            }

            adapterHtml += '<div class="metric-row">';
            adapterHtml += '<span class="label">' + formatMetricName(metricName) + '</span>';
            adapterHtml += '<span class="val ' + cls + '">' + val.toFixed(1) + unit + '</span>';
            adapterHtml += '</div>';
        }

        adapterHtml += '</div>';
        gridHtml += adapterHtml;
    }

    document.getElementById('adapterGrid').innerHTML = gridHtml || '<div class="no-data">暂无适配器数据</div>';

    // 更新概览
    var avgDurEl = document.getElementById('avgDuration');
    if (avgCount > 0) {
        var avg = totalAvg / avgCount;
        avgDurEl.textContent = avg.toFixed(1) + ' ms';
        avgDurEl.className = 'value ' + (avg < 100 ? 'good' : avg < 500 ? 'warn' : 'bad');
    }

    var avgErrEl = document.getElementById('avgErrorRate');
    if (errorCount > 0) {
        var errRate = totalErrorRate / errorCount;
        avgErrEl.textContent = errRate.toFixed(1) + '%';
        avgErrEl.className = 'value ' + (errRate < 5 ? 'good' : errRate < 20 ? 'warn' : 'bad');
    }

    // 更新趋势分析表格
    updateTrendTable(adapters);
}

function updateTrendTable(adapters) {
    var tbody = document.getElementById('trendBody');
    var rows = '';
    var hasData = false;

    for (var aid in adapters) {
        var metrics = adapters[aid].metrics || {};
        var durationMetrics = ['eval_duration', 'run_duration', 'tokenize_duration', 'complete_duration'];

        for (var i = 0; i < durationMetrics.length; i++) {
            var mn = durationMetrics[i];
            if (!metrics[mn]) continue;
            hasData = true;
            var m = metrics[mn];
            var sampleCount = m.sample_count || 0;
            var avg = m.avg || 0;
            var status = 'ok';
            var statusText = '正常';
            var changeText = '--';

            // 简单趋势判断
            if (sampleCount >= 20) {
                var key = aid + ':' + mn;
                var points = metricsData[key] || [];
                if (points.length >= 10) {
                    var recent = points.slice(-5);
                    var previous = points.slice(-10, -5);
                    var recentAvg = recent.reduce(function(s, p) { return s + p.value; }, 0) / recent.length;
                    var prevAvg = previous.reduce(function(s, p) { return s + p.value; }, 0) / previous.length;
                    if (prevAvg > 0) {
                        var change = ((recentAvg - prevAvg) / prevAvg) * 100;
                        changeText = (change >= 0 ? '+' : '') + change.toFixed(1) + '%';
                        if (change > 50) {
                            status = 'alert';
                            statusText = '回归';
                        }
                    }
                }
            }

            rows += '<tr>';
            rows += '<td>' + aid + '</td>';
            rows += '<td>' + formatMetricName(mn) + '</td>';
            rows += '<td>' + avg.toFixed(2) + ' ms</td>';
            rows += '<td>' + changeText + '</td>';
            rows += '<td>' + changeText + '</td>';
            rows += '<td><span class="regression-badge ' + status + '">' + statusText + '</span></td>';
            rows += '</tr>';
        }
    }

    if (!hasData) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;">等待数据...</td></tr>';
    } else {
        tbody.innerHTML = rows;
    }
}

function formatMetricName(name) {
    var map = {
        'eval_duration': 'eval 执行',
        'run_duration': 'run 执行',
        'tokenize_duration': 'tokenize',
        'complete_duration': 'complete',
        'error_rate': '错误率',
        'memory_used': '内存使用',
    };
    return map[name] || name;
}

function updateChart() {
    var selectedMetric = document.getElementById('metricSelect').value;
    var linesGroup = document.getElementById('chartLines');
    var dotsGroup = document.getElementById('chartDots');
    var yMaxEl = document.getElementById('yMax');

    // 收集所有适配器的该指标数据
    var allSeries = {};
    var maxVal = 0;
    var maxLen = 0;

    for (var key in metricsData) {
        var parts = key.split(':');
        var aid = parts[0];
        var metric = parts.slice(1).join(':');
        if (metric === selectedMetric) {
            allSeries[aid] = metricsData[key];
            var points = metricsData[key];
            if (points.length > maxLen) maxLen = points.length;
            for (var i = 0; i < points.length; i++) {
                if (points[i].value > maxVal) maxVal = points[i].value;
            }
        }
    }

    if (maxVal === 0) maxVal = 100;
    maxVal = maxVal * 1.2; // 留顶部空间
    yMaxEl.textContent = maxVal.toFixed(0) + (selectedMetric.indexOf('duration') >= 0 ? 'ms' : '%');

    var chartLeft = 50;
    var chartRight = 790;
    var chartTop = 10;
    var chartBottom = 230;
    var chartWidth = chartRight - chartLeft;
    var chartHeight = chartBottom - chartTop;

    var linesHtml = '';
    var dotsHtml = '';
    var colorIdx = 0;

    for (var aid in allSeries) {
        var color = chartColors[colorIdx % chartColors.length];
        colorIdx++;
        var points = allSeries[aid];
        var len = points.length;
        if (len < 2) continue;

        var pathParts = [];
        for (var j = 0; j < len; j++) {
            var x = chartLeft + (j / (len - 1)) * chartWidth;
            var y = chartBottom - (points[j].value / maxVal) * chartHeight;
            if (j === 0) {
                pathParts.push('M' + x.toFixed(1) + ',' + y.toFixed(1));
            } else {
                pathParts.push('L' + x.toFixed(1) + ',' + y.toFixed(1));
            }
        }

        linesHtml += '<path d="' + pathParts.join(' ') + '" fill="none" stroke="' + color + '" stroke-width="2" opacity="0.8"/>';

        // 最后一个点
        var lastPoint = points[len - 1];
        var lastX = chartLeft + ((len - 1) / (len - 1)) * chartWidth;
        var lastY = chartBottom - (lastPoint.value / maxVal) * chartHeight;
        dotsHtml += '<circle cx="' + lastX.toFixed(1) + '" cy="' + lastY.toFixed(1) + '" r="4" fill="' + color + '"/>';
        dotsHtml += '<text x="' + (lastX + 8) + '" y="' + (lastY + 4) + '" fill="' + color + '" font-size="11">' + aid + '</text>';
    }

    linesGroup.innerHTML = linesHtml;
    dotsGroup.innerHTML = dotsHtml;
}

function fetchDashboard() {
    fetch('/api/monitor/metrics')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            handleDashboard(data);
        })
        .catch(function() {});
}

// 定期刷新仪表板数据
setInterval(fetchDashboard, 5000);

// 监听度量选择变化
document.getElementById('metricSelect').addEventListener('change', updateChart);

// 初始连接
connectWebSocket();
fetchDashboard();
