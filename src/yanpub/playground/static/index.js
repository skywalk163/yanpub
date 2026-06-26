(function() {
        'use strict';

        // ---- DOM ----
        const langSelect = document.getElementById('lang-select');
        const exampleSelect = document.getElementById('example-select');
        const runBtn = document.getElementById('run-btn');
        const outputEl = document.getElementById('output');
        const statusEl = document.getElementById('status');
        const langInfo = document.getElementById('lang-info');
        const langBadge = document.getElementById('lang-badge');
        const editorLang = document.getElementById('editor-lang');
        const clearBtn = document.getElementById('clear-output');
        const modeToggle = document.getElementById('mode-toggle');
        const singleMode = document.getElementById('single-mode');
        const compareMode = document.getElementById('compare-mode');
        const langLeft = document.getElementById('lang-left');
        const langRight = document.getElementById('lang-right');
        const badgeLeft = document.getElementById('badge-left');
        const badgeRight = document.getElementById('badge-right');
        const outputLeft = document.getElementById('output-left');
        const outputRight = document.getElementById('output-right');
        const shareBtn = document.getElementById('share-btn');
        const shareToast = document.getElementById('share-toast');
        const wasmToggle = document.getElementById('wasm-toggle');
        const collabBtn = document.getElementById('collab-btn');
        const collabStatusEl = document.getElementById('collab-status');
        const collabModalOverlay = document.getElementById('collab-modal-overlay');
        const collabModalJoin = document.getElementById('collab-modal-join');
        const collabModalConnected = document.getElementById('collab-modal-connected');
        const collabDisplayNameInput = document.getElementById('collab-display-name');
        const collabRoomIdInput = document.getElementById('collab-room-id-input');
        const collabCreateBtn = document.getElementById('collab-create-btn');
        const collabJoinBtn = document.getElementById('collab-join-btn');
        const collabCancelBtn = document.getElementById('collab-cancel-btn');
        const collabLeaveBtn = document.getElementById('collab-leave-btn');
        const collabCloseModalBtn = document.getElementById('collab-close-modal-btn');
        const collabRoomIdDisplay = document.getElementById('collab-room-id-display');
        const collabRoomUserCount = document.getElementById('collab-room-user-count');
        const collabCopyRoomBtn = document.getElementById('collab-copy-room-btn');
        const collabUserListEl = document.getElementById('collab-userlist');
        const collabUserListItems = document.getElementById('collab-userlist-items');

        // ---- State ----
        let languages = [];
        let currentLang = null;
        let editor = null;        // single mode
        let editorLeft = null;    // compare mode left
        let editorRight = null;   // compare mode right
        let ws = null;
        let requestId = 0;
        let isCompareMode = false;
        let isWasmMode = false;

        // ---- Collab State ----
        let collabWs = null;
        let collabRoomId = null;
        let collabUserId = null;
        let collabDisplayName = '';
        let collabUsers = {};           // userId -> {displayName, color, position, selection}
        let collabCursors = {};         // userId -> bookmark handle
        let collabSelections = {};      // userId -> [textMarker]
        let collabApplyingRemote = false;
        let collabSyncTimer = null;
        let collabCursorTimer = null;

        // ---- CodeMirror init ----
        function createCM(textareaId, extraOpts) {
            return CodeMirror.fromTextArea(document.getElementById(textareaId), Object.assign({
                mode: 'javascript',
                theme: 'dracula',
                lineNumbers: true,
                lineWrapping: true,
                indentUnit: 4,
                tabSize: 4,
                indentWithTabs: false,
                autoCloseBrackets: true,
                matchBrackets: true,
                styleActiveLine: true,
                extraKeys: {
                    'Ctrl-Enter': runCurrentMode,
                    'Cmd-Enter': runCurrentMode,
                    'Ctrl-/': toggleCommentForActive,
                },
            }, extraOpts || {}));
        }

        function initEditors() {
            editor = createCM('code-editor');
            editor.setValue('# 选择一种语言开始编写代码...');
            editor.focus();

            editorLeft = createCM('editor-left');
            editorLeft.setValue('# 左侧语言代码');
            editorRight = createCM('editor-right');
            editorRight.setValue('# 右侧语言代码');

            // Collab: listen for changes and cursor activity on the main editor
            editor.on('change', onCollabChange);
            editor.on('cursorActivity', onCollabCursorActivity);
        }

        // ---- Language Management ----
        function loadLanguages() {
            fetch('/api/languages')
                .then(r => r.json())
                .then(data => {
                    languages = data;
                    populateSelect(langSelect, data);
                    populateSelect(langLeft, data);
                    populateSelect(langRight, data);
                    // Check for shared code in URL hash first
                    if (!loadFromShare() && data.length > 0) {
                        selectLanguage(data[0].id);
                    }
                    // Default: first two languages for compare
                    if (data.length > 0) {
                        langLeft.value = data[0].id;
                        selectCompareLang('left', data[0].id);
                    }
                    if (data.length > 1) {
                        langRight.value = data[1].id;
                        selectCompareLang('right', data[1].id);
                    }
                })
                .catch(() => {
                    langSelect.innerHTML = '<option>加载失败</option>';
                });
        }

        function populateSelect(select, data) {
            select.innerHTML = '';
            data.forEach(lang => {
                const opt = document.createElement('option');
                opt.value = lang.id;
                opt.textContent = lang.name + ' (' + lang.id + ')';
                select.appendChild(opt);
            });
        }

        function selectLanguage(langId) {
            const lang = languages.find(l => l.id === langId);
            if (!lang) return;
            currentLang = lang;
            langInfo.textContent = lang.name + ' v' + lang.version;
            langBadge.textContent = lang.name;
            langBadge.style.background = lang.primaryColor || '#2C3E50';
            editorLang.textContent = lang.name;
            document.documentElement.style.setProperty('--primary', lang.primaryColor || '#2C3E50');
            updateEditorMode(editor, lang);
            loadExamples(langId);
            loadTemplate(langId, '', function(code) { editor.setValue(code); editor.clearHistory(); });
        }

        function selectCompareLang(side, langId) {
            const lang = languages.find(l => l.id === langId);
            if (!lang) return;
            const badge = side === 'left' ? badgeLeft : badgeRight;
            badge.textContent = lang.name;
            badge.style.background = lang.primaryColor || '#2C3E50';
            const cm = side === 'left' ? editorLeft : editorRight;
            updateEditorMode(cm, lang);
            loadTemplate(langId, '', function(code) { cm.setValue(code); cm.clearHistory(); });
        }

        function updateEditorMode(cm, lang) {
            if (lang.keywords && lang.keywords.length > 0) {
                const modeName = 'yanpub-' + lang.id;
                if (!CodeMirror.modes[modeName]) {
                    CodeMirror.defineMode(modeName, function(config) {
                        return createChineseLangMode(config, lang.keywords, lang.commentSyntax);
                    });
                }
                cm.setOption('mode', modeName);
            } else {
                cm.setOption('mode', 'javascript');
            }
        }

        // ---- 自定义中文语言高亮模式 ----
        function createChineseLangMode(config, keywords, commentSyntax) {
            const keywordSet = new Set(keywords);
            const isCommentChar = commentSyntax === '#' ? /^#/ : /^\/\//;

            return {
                token: function(stream) {
                    if (isCommentChar.test(stream.peek()) && (commentSyntax === '#' || stream.string.slice(stream.pos).startsWith('//'))) {
                        stream.skipToEnd();
                        return 'comment';
                    }
                    if (stream.match(/[\u4e00-\u9fff]+/)) {
                        const word = stream.current();
                        if (keywordSet.has(word)) return 'keyword';
                        return 'variable-2';
                    }
                    if (stream.match(/"[^"]*"/) || stream.match(/'[^']*'/)) {
                        return 'string';
                    }
                    if (stream.match(/\d+(\.\d+)?/)) {
                        return 'number';
                    }
                    if (stream.match(/[+\-*/%=<>!&|^~]+/)) {
                        return 'operator';
                    }
                    if (stream.match(/[a-zA-Z_]\w*/)) {
                        const word = stream.current();
                        if (keywordSet.has(word)) return 'keyword';
                        return 'variable';
                    }
                    stream.next();
                    return null;
                },
                startState: function() { return {}; },
                indent: function() { return 0; }
            };
        }

        // ---- Template Loading ----
        function loadTemplate(langId, exampleName, callback) {
            let url = '/api/templates/' + langId;
            if (exampleName) url += '?example=' + encodeURIComponent(exampleName);
            fetch(url)
                .then(r => r.json())
                .then(data => {
                    if (data.code && callback) callback(data.code);
                })
                .catch(() => {});
        }

        function loadExamples(langId) {
            fetch('/api/examples/' + langId)
                .then(r => r.json())
                .then(data => {
                    exampleSelect.innerHTML = '<option value="">选择示例</option>';
                    if (data && data.length > 0) {
                        data.forEach(function(ex) {
                            const opt = document.createElement('option');
                            opt.value = ex.id;
                            opt.textContent = ex.name;
                            exampleSelect.appendChild(opt);
                        });
                        exampleSelect.style.display = '';
                    } else {
                        exampleSelect.style.display = 'none';
                    }
                })
                .catch(() => { exampleSelect.style.display = 'none'; });
        }

        // ---- Code Execution ----
        function runCode(lang, code, outputTarget) {
            if (!lang || !code.trim()) return;
            const id = String(++requestId);
            outputTarget.innerHTML = '';
            appendToOutput(outputTarget, 'info', '执行中...');
            statusEl.textContent = '执行中...';

            const payload = { lang: lang.id, code: code, id: id };

            function handleResult(data) {
                outputTarget.innerHTML = '';
                if (data.type === 'error') {
                    appendToOutput(outputTarget, 'stderr', data.message);
                    statusEl.textContent = '错误';
                    return;
                }
                if (data.stdout) {
                    data.stdout.split('\n').forEach(line => { if (line) appendToOutput(outputTarget, 'stdout', line); });
                }
                if (data.stderr) {
                    data.stderr.split('\n').forEach(line => { if (line) appendToOutput(outputTarget, 'stderr', line); });
                }
                if (data.exitCode !== 0 && !data.stderr) {
                    appendToOutput(outputTarget, 'stderr', '退出码: ' + data.exitCode);
                }
                appendToOutput(outputTarget, 'meta', '[' + (data.durationMs || 0).toFixed(0) + 'ms]');
                statusEl.textContent = data.exitCode === 0 ? '完成' : '错误';
            }

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(payload));
                // Store handler for this request
                pendingRequests[id] = { outputTarget, handler: handleResult };
            } else {
                // Choose endpoint based on WASM mode
                let endpoint, fetchPayload;
                if (isWasmMode && lang) {
                    endpoint = '/api/wasm/' + lang.id + '/run';
                    fetchPayload = { code: code, id: id };
                } else {
                    endpoint = '/api/run';
                    fetchPayload = payload;
                }

                fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(fetchPayload),
                })
                .then(r => r.json())
                .then(data => handleResult(data))
                .catch(err => {
                    outputTarget.innerHTML = '';
                    appendToOutput(outputTarget, 'stderr', '请求失败: ' + err.message);
                    statusEl.textContent = '失败';
                });
            }
        }

        let pendingRequests = {};

        function runCurrentMode() {
            if (isCompareMode) {
                // Run both sides
                const leftLang = languages.find(l => l.id === langLeft.value);
                const rightLang = languages.find(l => l.id === langRight.value);
                if (leftLang) runCode(leftLang, editorLeft.getValue(), outputLeft);
                if (rightLang) runCode(rightLang, editorRight.getValue(), outputRight);
            } else {
                if (!currentLang) { alert('请先选择语言'); return; }
                runCode(currentLang, editor.getValue(), outputEl);
            }
        }

        function appendToOutput(target, type, text) {
            const line = document.createElement('div');
            line.className = 'out-line out-' + type;
            line.textContent = text;
            target.appendChild(line);
            target.scrollTop = target.scrollHeight;
        }

        // ---- Comment Toggle ----
        function toggleCommentForActive(cm) {
            const lang = isCompareMode
                ? (cm === editorLeft ? languages.find(l => l.id === langLeft.value) : languages.find(l => l.id === langRight.value))
                : currentLang;
            if (!lang) return;
            const cs = lang.commentSyntax || '#';
            const cursor = cm.getCursor('from');
            const line = cm.getLine(cursor.line);
            if (line.trimStart().startsWith(cs)) {
                const idx = line.indexOf(cs);
                cm.replaceRange(line.slice(0, idx) + line.slice(idx + cs.length), {line: cursor.line, ch: 0}, {line: cursor.line, ch: line.length});
            } else {
                const indent = line.match(/^(\s*)/)[1];
                cm.replaceRange(indent + cs + line.slice(indent.length), {line: cursor.line, ch: 0}, {line: cursor.line, ch: line.length});
            }
        }

        // ---- Mode Toggle ----
        modeToggle.addEventListener('click', function() {
            isCompareMode = !isCompareMode;
            modeToggle.classList.toggle('active', isCompareMode);
            modeToggle.textContent = isCompareMode ? '单语言模式' : '对比模式';
            singleMode.classList.toggle('hidden', isCompareMode);
            compareMode.classList.toggle('active', isCompareMode);

            if (isCompareMode) {
                // Refresh editors after display change
                setTimeout(function() {
                    editorLeft.refresh();
                    editorRight.refresh();
                }, 50);
            } else {
                setTimeout(function() { editor.refresh(); }, 50);
            }
        });

        // ---- WebSocket (execution) ----
        function connectWS() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(protocol + '//' + location.host + '/ws/run');
            ws.onopen = () => { statusEl.textContent = '已连接'; };
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                const id = data.id;
                if (id && pendingRequests[id]) {
                    pendingRequests[id].handler(data);
                    delete pendingRequests[id];
                } else {
                    // Single mode fallback
                    handleResultSingle(data);
                }
            };
            ws.onclose = () => {
                statusEl.textContent = 'WebSocket 断开';
                setTimeout(connectWS, 3000);
            };
            ws.onerror = () => {};
        }

        function handleResultSingle(data) {
            outputEl.innerHTML = '';
            if (data.type === 'error') {
                appendToOutput(outputEl, 'stderr', data.message);
                statusEl.textContent = '错误';
                return;
            }
            if (data.stdout) data.stdout.split('\n').forEach(l => { if (l) appendToOutput(outputEl, 'stdout', l); });
            if (data.stderr) data.stderr.split('\n').forEach(l => { if (l) appendToOutput(outputEl, 'stderr', l); });
            appendToOutput(outputEl, 'meta', '[' + (data.durationMs || 0).toFixed(0) + 'ms]');
            statusEl.textContent = data.exitCode === 0 ? '完成' : '错误';
        }

        // ---- Clear Output ----
        clearBtn.addEventListener('click', () => {
            outputEl.innerHTML = '<span class="placeholder">输出已清空</span>';
        });
        document.querySelectorAll('.clear-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const target = document.getElementById(this.dataset.target);
                if (target) target.innerHTML = '<span class="placeholder">输出已清空</span>';
            });
        });

        // ---- Share (URL hash encoding + enhanced share) ----
        const shareModalOverlay = document.getElementById('share-modal-overlay');
        const shareTitleInput = document.getElementById('share-title-input');
        const shareCreateBtn = document.getElementById('share-create-btn');
        const shareResultEl = document.getElementById('share-result');
        const shareUrlText = document.getElementById('share-url-text');
        const shareCopyBtn = document.getElementById('share-copy-btn');
        const shareQrImg = document.getElementById('share-qr-img');
        const shareWeiboBtn = document.getElementById('share-weibo-btn');
        const shareWechatBtn = document.getElementById('share-wechat-btn');
        const shareCloseBtn = document.getElementById('share-close-btn');

        let currentShareId = null;

        function encodeShareData(langId, code) {
            // Format: #lang=<id>&code=<base64url-encoded-code>
            try {
                const encoded = btoa(unescape(encodeURIComponent(code)));
                return '#lang=' + encodeURIComponent(langId) + '&code=' + encoded;
            } catch(e) { return ''; }
        }

        function decodeShareData() {
            const hash = location.hash.slice(1);
            if (!hash) return null;
            const params = new URLSearchParams(hash);
            const langId = params.get('lang');
            const codeB64 = params.get('code');
            if (!langId || !codeB64) return null;
            try {
                const code = decodeURIComponent(escape(atob(codeB64)));
                return { langId, code };
            } catch(e) { return null; }
        }

        function openShareModal() {
            shareResultEl.classList.remove('show');
            shareTitleInput.value = '';
            shareCreateBtn.disabled = false;
            currentShareId = null;
            shareModalOverlay.classList.add('show');
        }

        function closeShareModal() {
            shareModalOverlay.classList.remove('show');
        }

        shareBtn.addEventListener('click', openShareModal);
        shareCloseBtn.addEventListener('click', closeShareModal);
        shareModalOverlay.addEventListener('click', function(e) {
            if (e.target === shareModalOverlay) closeShareModal();
        });

        shareCreateBtn.addEventListener('click', function() {
            var langId, code;
            if (isCompareMode) {
                langId = langLeft.value;
                code = editorLeft.getValue();
            } else {
                if (!currentLang) { alert('请先选择语言'); return; }
                langId = currentLang.id;
                code = editor.getValue();
            }

            shareCreateBtn.disabled = true;
            shareCreateBtn.textContent = '创建中...';

            var payload = {
                lang: langId,
                code: code,
                title: shareTitleInput.value.trim(),
            };

            fetch('/api/share/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                shareCreateBtn.disabled = false;
                shareCreateBtn.textContent = '创建分享链接';

                if (data.error) {
                    alert('创建失败: ' + data.error);
                    return;
                }

                currentShareId = data.id;
                var fullUrl = location.origin + data.url;
                shareUrlText.textContent = fullUrl;

                // Load QR code
                shareQrImg.src = data.qr_url;
                shareQrImg.style.display = 'inline';

                shareResultEl.classList.add('show');
            })
            .catch(function(err) {
                shareCreateBtn.disabled = false;
                shareCreateBtn.textContent = '创建分享链接';
                alert('创建失败: ' + err.message);
            });
        });

        shareCopyBtn.addEventListener('click', function() {
            var url = shareUrlText.textContent;
            try {
                navigator.clipboard.writeText(url).then(function() {
                    shareCopyBtn.textContent = '已复制';
                    setTimeout(function() { shareCopyBtn.textContent = '复制'; }, 1500);
                });
            } catch(e) {
                var ta = document.createElement('textarea');
                ta.value = url;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                shareCopyBtn.textContent = '已复制';
                setTimeout(function() { shareCopyBtn.textContent = '复制'; }, 1500);
            }
        });

        shareWeiboBtn.addEventListener('click', function() {
            var url = shareUrlText.textContent;
            var title = shareTitleInput.value.trim() || '中文编程代码分享';
            window.open('https://service.weibo.com/share/share.php?url=' + encodeURIComponent(url) + '&title=' + encodeURIComponent(title), '_blank', 'width=600,height=400');
        });

        shareWechatBtn.addEventListener('click', function() {
            var url = shareUrlText.textContent;
            try {
                navigator.clipboard.writeText(url).then(function() {
                    showToast('链接已复制，可粘贴到微信分享');
                });
            } catch(e) {
                showToast('请手动复制链接分享到微信');
            }
        });

        function loadFromShare() {
            // Check for #share= short link format first
            var hash = location.hash.slice(1);
            var shareParams = new URLSearchParams(hash);
            var shareId = shareParams.get('share');
            if (shareId) {
                fetch('/api/share/' + shareId)
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.error) {
                            showToast('分享加载失败: ' + data.error);
                            return;
                        }
                        var lang = languages.find(function(l) { return l.id === data.lang; });
                        if (lang) {
                            selectLanguage(data.lang);
                        }
                        editor.setValue(data.code);
                        editor.clearHistory();
                        if (data.title) {
                            document.title = data.title + ' — 言埠 YanPlay';
                        }
                        showToast('已加载分享: ' + (data.title || data.id));
                    })
                    .catch(function(err) {
                        showToast('分享加载失败');
                    });
                return true;
            }

            // Fallback: old #lang=&code= format
            var shared = decodeShareData();
            if (!shared) return false;
            var lang = languages.find(l => l.id === shared.langId);
            if (!lang) return false;
            selectLanguage(shared.langId);
            editor.setValue(shared.code);
            editor.clearHistory();
            return true;
        }

        // Listen for hash changes to load shares
        window.addEventListener('hashchange', function() {
            var hash = location.hash.slice(1);
            var params = new URLSearchParams(hash);
            if (params.get('share')) {
                loadFromShare();
            }
        });

        function showToast(msg) {
            shareToast.textContent = msg;
            shareToast.classList.add('show');
            setTimeout(function() { shareToast.classList.remove('show'); }, 2000);
        }

        // ---- WASM Mode Toggle ----
        wasmToggle.addEventListener('click', function() {
            isWasmMode = !isWasmMode;
            wasmToggle.classList.toggle('active', isWasmMode);
            wasmToggle.style.background = isWasmMode ? 'var(--primary)' : '#2d2d2d';
            wasmToggle.style.color = isWasmMode ? 'white' : 'var(--text-dim)';
            wasmToggle.style.borderColor = isWasmMode ? 'var(--primary)' : 'var(--border)';
            statusEl.textContent = isWasmMode ? 'WASM 模式' : '';
        });

        // ---- Collab: Helper Functions ----

        function generateUserId() {
            return 'u_' + Math.random().toString(36).substr(2, 6);
        }

        function generateRandomName() {
            const names = ['墨客', '书生', '侠客', '琴师', '画匠', '诗人', '词人', '骚客',
                           '竹隐', '兰亭', '松风', '梅影', '云栖', '鹤鸣', '龙吟', '凤舞'];
            return names[Math.floor(Math.random() * names.length)] + Math.floor(Math.random() * 100);
        }

        function getActiveEditor() {
            return isCompareMode ? editorLeft : editor;
        }

        // ---- Collab: Modal ----

        function openCollabModal() {
            // Pre-fill display name if empty
            if (!collabDisplayNameInput.value) {
                collabDisplayNameInput.value = generateRandomName();
            }
            // Show appropriate panel
            if (collabRoomId && collabWs && collabWs.readyState === WebSocket.OPEN) {
                collabModalJoin.style.display = 'none';
                collabModalConnected.style.display = 'block';
                collabRoomIdDisplay.textContent = collabRoomId;
                collabRoomUserCount.textContent = Object.keys(collabUsers).length;
            } else {
                collabModalJoin.style.display = 'block';
                collabModalConnected.style.display = 'none';
            }
            collabModalOverlay.classList.add('show');
        }

        function closeCollabModal() {
            collabModalOverlay.classList.remove('show');
        }

        collabBtn.addEventListener('click', openCollabModal);
        collabCancelBtn.addEventListener('click', closeCollabModal);
        collabCloseModalBtn.addEventListener('click', closeCollabModal);

        // Close modal on overlay click
        collabModalOverlay.addEventListener('click', function(e) {
            if (e.target === collabModalOverlay) closeCollabModal();
        });

        // ---- Collab: Create Room ----

        collabCreateBtn.addEventListener('click', function() {
            const lang = isCompareMode ? langLeft.value : (currentLang ? currentLang.id : 'duan');
            const code = isCompareMode ? editorLeft.getValue() : editor.getValue();
            collabDisplayName = collabDisplayNameInput.value.trim() || generateRandomName();

            fetch('/api/collab/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ lang: lang, code: code }),
            })
            .then(r => r.json())
            .then(data => {
                if (data.roomId) {
                    connectCollab(data.roomId);
                    closeCollabModal();
                } else {
                    alert('创建房间失败');
                }
            })
            .catch(err => {
                alert('创建房间失败: ' + err.message);
            });
        });

        // ---- Collab: Join Room ----

        collabJoinBtn.addEventListener('click', function() {
            const roomId = collabRoomIdInput.value.trim();
            if (!roomId) {
                alert('请输入房间ID');
                return;
            }
            collabDisplayName = collabDisplayNameInput.value.trim() || generateRandomName();
            connectCollab(roomId);
            closeCollabModal();
        });

        // Enter key to join
        collabRoomIdInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') collabJoinBtn.click();
        });

        // ---- Collab: Leave Room ----

        collabLeaveBtn.addEventListener('click', function() {
            leaveCollabRoom();
            closeCollabModal();
        });

        // ---- Collab: Copy Room ID ----

        collabCopyRoomBtn.addEventListener('click', function() {
            if (collabRoomId) {
                try {
                    navigator.clipboard.writeText(collabRoomId).then(function() {
                        collabCopyRoomBtn.textContent = '已复制';
                        setTimeout(function() { collabCopyRoomBtn.textContent = '复制'; }, 1500);
                    });
                } catch(e) {
                    // Fallback
                    const ta = document.createElement('textarea');
                    ta.value = collabRoomId;
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                    collabCopyRoomBtn.textContent = '已复制';
                    setTimeout(function() { collabCopyRoomBtn.textContent = '复制'; }, 1500);
                }
            }
        });

        // ---- Collab: WebSocket Connection ----

        function connectCollab(roomId) {
            // Close existing connection
            if (collabWs) {
                collabWs.close();
                collabWs = null;
            }

            collabRoomId = roomId;
            collabUserId = generateUserId();

            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            collabWs = new WebSocket(protocol + '//' + location.host + '/ws/collab/' + roomId);

            collabWs.onopen = function() {
                // Send join message
                collabWs.send(JSON.stringify({
                    type: 'join',
                    roomId: roomId,
                    userId: collabUserId,
                    displayName: collabDisplayName,
                }));
            };

            collabWs.onmessage = function(event) {
                var data;
                try {
                    data = JSON.parse(event.data);
                } catch(e) { return; }
                handleCollabMessage(data);
            };

            collabWs.onclose = function() {
                updateCollabUI();
            };

            collabWs.onerror = function() {};

            // Show user list
            collabUserListEl.classList.add('active');
        }

        function leaveCollabRoom() {
            if (collabWs) {
                collabWs.close();
                collabWs = null;
            }
            collabRoomId = null;
            collabUserId = null;
            collabUsers = {};
            clearAllRemoteMarkers();
            collabUserListEl.classList.remove('active');
            updateCollabUI();
        }

        // ---- Collab: Message Handling ----

        function handleCollabMessage(data) {
            switch (data.type) {
                case 'room_state':
                    // Initial room state upon joining
                    collabUsers = {};
                    if (data.users) {
                        data.users.forEach(function(u) {
                            collabUsers[u.userId] = {
                                displayName: u.displayName || u.userId,
                                color: u.color || '#3498DB',
                                position: null,
                                selection: null,
                            };
                        });
                    }
                    // Apply initial document
                    if (data.document !== undefined) {
                        applyRemoteDocument(data.document);
                    }
                    updateCollabUI();
                    updateUserList();
                    break;

                case 'user_joined':
                    if (data.user) {
                        collabUsers[data.user.userId] = {
                            displayName: data.user.displayName || data.user.userId,
                            color: data.user.color || '#3498DB',
                            position: null,
                            selection: null,
                        };
                    }
                    updateUserList();
                    updateCollabUI();
                    break;

                case 'user_left':
                    removeRemoteCursor(data.userId);
                    removeRemoteSelection(data.userId);
                    delete collabUsers[data.userId];
                    updateUserList();
                    updateCollabUI();
                    break;

                case 'edit':
                    // Remote edit — do full document sync
                    if (data.userId !== collabUserId) {
                        scheduleFullSync();
                    }
                    break;

                case 'cursor':
                    // Remote cursor update
                    if (data.userId !== collabUserId) {
                        if (data.position) {
                            updateRemoteCursor(data.userId, data.position, data.color, data.displayName);
                        }
                        if (data.selection) {
                            updateRemoteSelection(data.userId, data.selection, data.color);
                        } else {
                            removeRemoteSelection(data.userId);
                        }
                    }
                    break;

                case 'pong':
                    // Heartbeat response, ignore
                    break;
            }
        }

        // ---- Collab: Full Document Sync ----

        function scheduleFullSync() {
            if (collabSyncTimer) clearTimeout(collabSyncTimer);
            collabSyncTimer = setTimeout(doFullSync, 150);
        }

        function doFullSync() {
            if (!collabRoomId) return;
            fetch('/api/collab/' + collabRoomId)
                .then(r => r.json())
                .then(data => {
                    if (data.document !== undefined) {
                        applyRemoteDocument(data.document);
                    }
                })
                .catch(function() {});
        }

        function applyRemoteDocument(text) {
            var cm = getActiveEditor();
            if (!cm) return;

            var currentText = cm.getValue();
            if (currentText === text) return;

            collabApplyingRemote = true;
            var cursor = cm.getCursor();
            var scrollInfo = cm.getScrollInfo();

            cm.setValue(text);

            // Restore cursor position (clamped to valid range)
            var lastLine = cm.lastLine();
            var clampedLine = Math.min(cursor.line, lastLine);
            var clampedCh = Math.min(cursor.ch, cm.getLine(clampedLine).length);
            cm.setCursor({ line: clampedLine, ch: clampedCh });

            // Restore scroll position
            cm.scrollTo(scrollInfo.left, scrollInfo.top);

            collabApplyingRemote = false;
        }

        // ---- Collab: Local Change → Send Ops ----

        function onCollabChange(cm, change) {
            if (collabApplyingRemote) return;
            if (!collabWs || collabWs.readyState !== WebSocket.OPEN) return;
            if (!collabRoomId) return;

            // Convert CodeMirror change to simple ops
            var ops = [];
            var from = change.from;
            var to = change.to;
            var insertedText = change.text.join('\n');
            var removedText = change.removed ? change.removed.join('\n') : '';

            // For delete/replace: record removal
            if (removedText.length > 0) {
                ops.push({
                    type: 'delete',
                    from: { line: from.line, ch: from.ch },
                    to: { line: to.line, ch: to.ch },
                    text: removedText,
                });
            }
            // For insert/replace: record insertion
            if (insertedText.length > 0) {
                ops.push({
                    type: 'insert',
                    from: { line: from.line, ch: from.ch },
                    text: insertedText,
                });
            }

            if (ops.length > 0) {
                collabWs.send(JSON.stringify({
                    type: 'edit',
                    roomId: collabRoomId,
                    userId: collabUserId,
                    ops: ops,
                }));
            }
        }

        // ---- Collab: Local Cursor → Send Position ----

        function onCollabCursorActivity(cm) {
            if (!collabWs || collabWs.readyState !== WebSocket.OPEN) return;
            if (!collabRoomId) return;

            // Debounce cursor updates
            if (collabCursorTimer) clearTimeout(collabCursorTimer);
            collabCursorTimer = setTimeout(function() {
                if (!collabWs || collabWs.readyState !== WebSocket.OPEN) return;
                var cursor = cm.getCursor();
                var hasSelection = cm.somethingSelected();

                collabWs.send(JSON.stringify({
                    type: 'cursor',
                    roomId: collabRoomId,
                    userId: collabUserId,
                    position: { line: cursor.line, col: cursor.ch },
                    selection: hasSelection ? {
                        start: { line: cm.getCursor('start').line, col: cm.getCursor('start').ch },
                        end: { line: cm.getCursor('end').line, col: cm.getCursor('end').ch },
                    } : null,
                }));
            }, 80);
        }

        // ---- Collab: Remote Cursor Display ----

        function updateRemoteCursor(userId, position, color, displayName) {
            // Remove existing cursor for this user
            removeRemoteCursor(userId);

            var cm = getActiveEditor();
            if (!cm || !position) return;

            var line = Math.min(position.line || 0, cm.lastLine());
            var ch = Math.min(position.col || position.ch || 0, cm.getLine(line).length);

            // Create cursor widget element
            var cursorEl = document.createElement('div');
            cursorEl.className = 'collab-remote-cursor';
            cursorEl.style.borderLeftColor = color || '#3498DB';

            // Label above cursor
            var labelEl = document.createElement('div');
            labelEl.className = 'collab-cursor-label';
            labelEl.style.background = color || '#3498DB';
            labelEl.textContent = displayName || userId;
            cursorEl.appendChild(labelEl);

            // Set bookmark at cursor position
            var bookmark = cm.setBookmark(
                { line: line, ch: ch },
                { widget: cursorEl, insertLeft: true }
            );

            collabCursors[userId] = bookmark;
        }

        function removeRemoteCursor(userId) {
            if (collabCursors[userId]) {
                try { collabCursors[userId].clear(); } catch(e) {}
                delete collabCursors[userId];
            }
        }

        function clearAllRemoteCursors() {
            Object.keys(collabCursors).forEach(function(uid) {
                removeRemoteCursor(uid);
            });
        }

        // ---- Collab: Remote Selection Display ----

        function updateRemoteSelection(userId, selection, color) {
            // Remove existing selection for this user
            removeRemoteSelection(userId);

            var cm = getActiveEditor();
            if (!cm || !selection) return;

            var start = selection.start || selection.anchor;
            var end = selection.end || selection.head;
            if (!start || !end) return;

            var startLine = Math.min(start.line || 0, cm.lastLine());
            var endLine = Math.min(end.line || 0, cm.lastLine());
            var startCh = Math.min(start.col || start.ch || 0, cm.getLine(startLine).length);
            var endCh = Math.min(end.col || end.ch || 0, cm.getLine(endLine).length);

            // Don't draw zero-length selections
            if (startLine === endLine && startCh === endCh) return;

            try {
                var marker = cm.markText(
                    { line: startLine, ch: startCh },
                    { line: endLine, ch: endCh },
                    { css: 'background-color: ' + (color || '#3498DB') + '33;' }
                );
                collabSelections[userId] = [marker];
            } catch(e) {}
        }

        function removeRemoteSelection(userId) {
            if (collabSelections[userId]) {
                collabSelections[userId].forEach(function(m) {
                    try { m.clear(); } catch(e) {}
                });
                delete collabSelections[userId];
            }
        }

        function clearAllRemoteSelections() {
            Object.keys(collabSelections).forEach(function(uid) {
                removeRemoteSelection(uid);
            });
        }

        function clearAllRemoteMarkers() {
            clearAllRemoteCursors();
            clearAllRemoteSelections();
        }

        // ---- Collab: UI Updates ----

        function updateCollabUI() {
            var isConnected = collabRoomId && collabWs && collabWs.readyState === WebSocket.OPEN;
            var userCount = Object.keys(collabUsers).length;
            var dot = collabStatusEl.querySelector('.dot');

            if (isConnected) {
                dot.classList.add('connected');
                collabStatusEl.querySelector('.dot').classList.add('connected');
                collabBtn.classList.add('active');

                // Build status text after the dot
                var existingText = collabStatusEl.querySelector('.collab-status-text');
                if (!existingText) {
                    existingText = document.createElement('span');
                    existingText.className = 'collab-status-text';
                    collabStatusEl.appendChild(existingText);
                }
                existingText.textContent = ' ' + collabRoomId.substring(0, 8) + ' · ' + userCount + '人';
            } else {
                dot.classList.remove('connected');
                collabBtn.classList.remove('active');

                var existingText = collabStatusEl.querySelector('.collab-status-text');
                if (existingText) existingText.textContent = '';

                // Hide user list if disconnected
                collabUserListEl.classList.remove('active');
            }
        }

        function updateUserList() {
            collabUserListItems.innerHTML = '';
            Object.keys(collabUsers).forEach(function(uid) {
                var user = collabUsers[uid];
                var item = document.createElement('div');
                item.className = 'collab-user-item';

                var avatar = document.createElement('div');
                avatar.className = 'collab-user-avatar';
                avatar.style.background = user.color;
                avatar.textContent = (user.displayName || uid).charAt(0);

                var nameWrap = document.createElement('div');
                nameWrap.style.cssText = 'display:flex;flex-direction:column;overflow:hidden;';

                var name = document.createElement('span');
                name.className = 'collab-user-name';
                name.textContent = user.displayName || uid;

                nameWrap.appendChild(name);

                if (uid === collabUserId) {
                    var selfLabel = document.createElement('span');
                    selfLabel.className = 'collab-user-self';
                    selfLabel.textContent = '我';
                    nameWrap.appendChild(selfLabel);
                }

                item.appendChild(avatar);
                item.appendChild(nameWrap);
                collabUserListItems.appendChild(item);
            });

            // Update room user count in modal if visible
            if (collabRoomUserCount) {
                collabRoomUserCount.textContent = Object.keys(collabUsers).length;
            }
        }

        // ---- Collab: Heartbeat ----

        setInterval(function() {
            if (collabWs && collabWs.readyState === WebSocket.OPEN) {
                collabWs.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);

        // ================================================================
        // Project Mode — 多文件项目
        // ================================================================

        const projectToggle = document.getElementById('project-toggle');
        const projectModeEl = document.getElementById('project-mode');
        const projectSidebar = document.getElementById('project-sidebar');
        const projectFileList = document.getElementById('project-file-list');
        const projectAddFileBtn = document.getElementById('project-add-file-btn');
        const projectNameDisplay = document.getElementById('project-name-display');
        const projectLangSelect = document.getElementById('project-lang-select');
        const projectRunBtn = document.getElementById('project-run-btn');
        const projectStatusEl = document.getElementById('project-status');
        const projectTabs = document.getElementById('project-tabs');
        const projectEditorContainer = document.getElementById('project-editor-container');
        const projectOutputEl = document.getElementById('project-output');
        const projectClearOutputBtn = document.getElementById('project-clear-output');
        const fileContextMenu = document.getElementById('file-context-menu');
        const projectModalOverlay = document.getElementById('project-modal-overlay');
        const projectModalTitle = document.getElementById('project-modal-title');
        const projectModalInput = document.getElementById('project-modal-input');
        const projectModalOk = document.getElementById('project-modal-ok');
        const projectModalCancel = document.getElementById('project-modal-cancel');

        let isProjectMode = false;
        let projectEditor = null;
        let currentProject = null;          // { id, name, language, mainFile, files }
        let openTabs = [];                  // [{ path, modified }]
        let activeTabPath = null;
        let projectFileContents = {};       // path → content (local cache)
        let projectModalAction = null;      // 'add' | 'rename'
        let projectModalContext = null;     // context for modal (e.g. file path)

        function initProjectEditor() {
            if (projectEditor) return;
            projectEditor = CodeMirror.fromTextArea(
                document.getElementById('project-editor'),
                {
                    mode: 'javascript',
                    theme: 'dracula',
                    lineNumbers: true,
                    lineWrapping: true,
                    indentUnit: 4,
                    tabSize: 4,
                    indentWithTabs: false,
                    autoCloseBrackets: true,
                    matchBrackets: true,
                    styleActiveLine: true,
                    extraKeys: {
                        'Ctrl-Enter': runProject,
                        'Cmd-Enter': runProject,
                    },
                }
            );
            projectEditor.setValue('// 选择一种语言，创建项目开始编写...');
            projectEditor.on('change', onProjectEditorChange);
        }

        function onProjectEditorChange(cm, change) {
            if (!currentProject || !activeTabPath) return;
            projectFileContents[activeTabPath] = cm.getValue();
            // Mark as modified
            var tab = openTabs.find(function(t) { return t.path === activeTabPath; });
            if (tab && !tab.modified) {
                tab.modified = true;
                renderProjectTabs();
            }
            // Debounced save to server
            if (projectSaveTimer) clearTimeout(projectSaveTimer);
            projectSaveTimer = setTimeout(function() {
                saveProjectFile(activeTabPath);
            }, 800);
        }

        var projectSaveTimer = null;

        function saveProjectFile(path) {
            if (!currentProject) return;
            fetch('/api/project/' + currentProject.id + '/files/' + encodeURIComponent(path), {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: projectFileContents[path] || '' }),
            }).catch(function() {});
        }

        function createProject() {
            var langId = projectLangSelect.value || (languages.length > 0 ? languages[0].id : 'duan');
            var name = '我的项目';

            fetch('/api/project/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, language: langId }),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                currentProject = data;
                projectFileContents = {};
                // Load file contents
                (data.files || {}).forEach ? null : null;
                var files = data.files || {};
                Object.keys(files).forEach(function(k) {
                    projectFileContents[k] = files[k].content || '';
                });
                projectNameDisplay.textContent = data.name;
                projectLangSelect.value = data.language;
                renderProjectFileList();
                // Open main file
                if (data.mainFile) {
                    openProjectTab(data.mainFile);
                }
                projectStatusEl.textContent = '项目已创建';
            })
            .catch(function(err) {
                projectStatusEl.textContent = '创建失败: ' + err.message;
            });
        }

        function loadProject(projectId) {
            fetch('/api/project/' + projectId)
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    currentProject = data;
                    projectFileContents = {};
                    var files = data.files || {};
                    Object.keys(files).forEach(function(k) {
                        projectFileContents[k] = files[k].content || '';
                    });
                    projectNameDisplay.textContent = data.name;
                    projectLangSelect.value = data.language;
                    renderProjectFileList();
                    // Open main file
                    if (data.mainFile) {
                        openProjectTab(data.mainFile);
                    }
                    projectStatusEl.textContent = '项目已加载';
                })
                .catch(function() {
                    projectStatusEl.textContent = '加载失败';
                });
        }

        function renderProjectFileList() {
            if (!currentProject) {
                projectFileList.innerHTML = '<div style="padding:8px 12px;color:var(--text-dim);font-size:11px;">无项目</div>';
                return;
            }

            projectFileList.innerHTML = '';
            var files = currentProject.files || {};
            var sortedPaths = Object.keys(files).sort();

            sortedPaths.forEach(function(path) {
                var item = document.createElement('div');
                item.className = 'project-file-item' +
                    (path === activeTabPath ? ' active' : '') +
                    (path === currentProject.mainFile ? ' main-file' : '');
                item.dataset.path = path;

                var icon = document.createElement('span');
                icon.className = 'project-file-icon';
                icon.textContent = path === currentProject.mainFile ? '\u25B6' : '\uD83D\uDCC4';

                var name = document.createElement('span');
                name.className = 'project-file-name';
                name.textContent = path;

                var actions = document.createElement('span');
                actions.className = 'file-actions';
                actions.innerHTML = '<button data-action="delete" title="删除">\u00D7</button>';

                item.appendChild(icon);
                item.appendChild(name);
                item.appendChild(actions);

                item.addEventListener('click', function(e) {
                    if (e.target.dataset.action === 'delete') {
                        deleteProjectFile(path);
                        return;
                    }
                    openProjectTab(path);
                });

                item.addEventListener('contextmenu', function(e) {
                    e.preventDefault();
                    showFileContextMenu(e, path);
                });

                projectFileList.appendChild(item);
            });
        }

        function openProjectTab(path) {
            // Save current tab content first
            if (activeTabPath && projectEditor) {
                projectFileContents[activeTabPath] = projectEditor.getValue();
            }

            activeTabPath = path;

            // Add tab if not already open
            var existing = openTabs.find(function(t) { return t.path === path; });
            if (!existing) {
                openTabs.push({ path: path, modified: false });
            }

            // Switch editor content
            if (projectEditor) {
                projectEditor.setValue(projectFileContents[path] || '');
                projectEditor.clearHistory();
                // Set mode based on language
                var lang = languages.find(function(l) { return l.id === (currentProject ? currentProject.language : ''); });
                if (lang) {
                    updateEditorMode(projectEditor, lang);
                }
                projectEditor.focus();
            }

            renderProjectTabs();
            renderProjectFileList();
        }

        function closeProjectTab(path) {
            if (openTabs.length <= 1) return; // Don't close last tab

            var idx = openTabs.findIndex(function(t) { return t.path === path; });
            if (idx === -1) return;

            openTabs.splice(idx, 1);

            if (activeTabPath === path) {
                // Switch to adjacent tab
                var newIdx = Math.min(idx, openTabs.length - 1);
                openProjectTab(openTabs[newIdx].path);
            }

            renderProjectTabs();
        }

        function renderProjectTabs() {
            projectTabs.innerHTML = '';
            openTabs.forEach(function(tab) {
                var tabEl = document.createElement('div');
                tabEl.className = 'project-tab' +
                    (tab.path === activeTabPath ? ' active' : '') +
                    (currentProject && tab.path === currentProject.mainFile ? ' main-tab' : '');

                var name = document.createElement('span');
                name.className = 'tab-name';
                name.textContent = tab.path;

                tabEl.appendChild(name);

                if (tab.modified) {
                    var mod = document.createElement('span');
                    mod.className = 'tab-modified';
                    mod.textContent = '\u25CF';
                    tabEl.appendChild(mod);
                }

                var close = document.createElement('span');
                close.className = 'tab-close';
                close.textContent = '\u00D7';
                close.addEventListener('click', function(e) {
                    e.stopPropagation();
                    closeProjectTab(tab.path);
                });
                tabEl.appendChild(close);

                tabEl.addEventListener('click', function() {
                    openProjectTab(tab.path);
                });

                projectTabs.appendChild(tabEl);
            });
        }

        function addProjectFile(path) {
            if (!currentProject) return;
            fetch('/api/project/' + currentProject.id + '/files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: path,
                    content: '',
                    language: currentProject.language,
                }),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    projectStatusEl.textContent = data.error;
                    return;
                }
                // Update local cache
                currentProject.files[path] = data;
                projectFileContents[path] = '';
                renderProjectFileList();
                openProjectTab(path);
                projectStatusEl.textContent = '文件已添加: ' + path;
            })
            .catch(function(err) {
                projectStatusEl.textContent = '添加失败: ' + err.message;
            });
        }

        function deleteProjectFile(path) {
            if (!currentProject) return;
            if (!confirm('确定删除文件 ' + path + '？')) return;

            fetch('/api/project/' + currentProject.id + '/files/' + encodeURIComponent(path), {
                method: 'DELETE',
            })
            .then(function(r) { return r.json(); })
            .then(function() {
                delete currentProject.files[path];
                delete projectFileContents[path];
                // Close tab if open
                openTabs = openTabs.filter(function(t) { return t.path !== path; });
                if (activeTabPath === path) {
                    if (openTabs.length > 0) {
                        openProjectTab(openTabs[0].path);
                    } else {
                        activeTabPath = null;
                        if (projectEditor) projectEditor.setValue('');
                    }
                }
                renderProjectFileList();
                renderProjectTabs();
                projectStatusEl.textContent = '文件已删除: ' + path;
            })
            .catch(function(err) {
                projectStatusEl.textContent = '删除失败: ' + err.message;
            });
        }

        function renameProjectFile(oldPath, newPath) {
            if (!currentProject) return;
            fetch('/api/project/' + currentProject.id + '/files/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ oldPath: oldPath, newPath: newPath }),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    projectStatusEl.textContent = data.error;
                    return;
                }
                // Update local cache
                var content = projectFileContents[oldPath] || '';
                delete projectFileContents[oldPath];
                delete currentProject.files[oldPath];
                currentProject.files[newPath] = { path: newPath, content: content };
                projectFileContents[newPath] = content;
                if (currentProject.mainFile === oldPath) {
                    currentProject.mainFile = newPath;
                }
                // Update tabs
                openTabs.forEach(function(t) {
                    if (t.path === oldPath) t.path = newPath;
                });
                if (activeTabPath === oldPath) activeTabPath = newPath;
                renderProjectFileList();
                renderProjectTabs();
                projectStatusEl.textContent = '文件已重命名: ' + oldPath + ' → ' + newPath;
            })
            .catch(function(err) {
                projectStatusEl.textContent = '重命名失败: ' + err.message;
            });
        }

        function setMainFile(path) {
            if (!currentProject) return;
            currentProject.mainFile = path;
            renderProjectFileList();
            renderProjectTabs();
            projectStatusEl.textContent = '入口文件已设置: ' + path;
            // Save to server by updating project — simple approach: re-save
            fetch('/api/project/' + currentProject.id, {
                method: 'GET',
            }).catch(function() {});
        }

        function showFileContextMenu(e, path) {
            fileContextMenu.style.left = e.clientX + 'px';
            fileContextMenu.style.top = e.clientY + 'px';
            fileContextMenu.classList.add('show');
            fileContextMenu._targetPath = path;
        }

        function hideFileContextMenu() {
            fileContextMenu.classList.remove('show');
        }

        function showProjectModal(title, defaultValue, action, context) {
            projectModalTitle.textContent = title;
            projectModalInput.value = defaultValue || '';
            projectModalAction = action;
            projectModalContext = context;
            projectModalOverlay.classList.add('show');
            setTimeout(function() { projectModalInput.focus(); }, 100);
        }

        function hideProjectModal() {
            projectModalOverlay.classList.remove('show');
            projectModalAction = null;
            projectModalContext = null;
        }

        function runProject() {
            if (!currentProject) {
                alert('请先创建项目');
                return;
            }
            // Save current file first
            if (activeTabPath && projectEditor) {
                projectFileContents[activeTabPath] = projectEditor.getValue();
                saveProjectFile(activeTabPath);
            }

            projectOutputEl.innerHTML = '';
            appendToOutput(projectOutputEl, 'info', '执行项目中...');
            projectStatusEl.textContent = '执行中...';

            fetch('/api/project/' + currentProject.id + '/run', {
                method: 'POST',
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                projectOutputEl.innerHTML = '';
                if (data.type === 'error') {
                    appendToOutput(projectOutputEl, 'stderr', data.message);
                    projectStatusEl.textContent = '错误';
                    return;
                }
                if (data.stdout) {
                    data.stdout.split('\n').forEach(function(line) {
                        if (line) appendToOutput(projectOutputEl, 'stdout', line);
                    });
                }
                if (data.stderr) {
                    data.stderr.split('\n').forEach(function(line) {
                        if (line) appendToOutput(projectOutputEl, 'stderr', line);
                    });
                }
                appendToOutput(projectOutputEl, 'meta', '[' + (data.durationMs || 0).toFixed(0) + 'ms]');
                projectStatusEl.textContent = data.exitCode === 0 ? '完成' : '错误';
            })
            .catch(function(err) {
                projectOutputEl.innerHTML = '';
                appendToOutput(projectOutputEl, 'stderr', '请求失败: ' + err.message);
                projectStatusEl.textContent = '失败';
            });
        }

        // ---- Project mode toggle ----

        projectToggle.addEventListener('click', function() {
            isProjectMode = !isProjectMode;
            projectToggle.classList.toggle('active', isProjectMode);

            // Hide other modes
            if (isProjectMode) {
                isCompareMode = false;
                modeToggle.classList.remove('active');
                modeToggle.textContent = '对比模式';
                singleMode.classList.add('hidden');
                compareMode.classList.remove('active');
            }

            singleMode.classList.toggle('hidden', isProjectMode);
            compareMode.classList.remove('active');
            projectModeEl.classList.toggle('active', isProjectMode);

            if (isProjectMode) {
                initProjectEditor();
                if (!currentProject) {
                    // Populate language select
                    projectLangSelect.innerHTML = '';
                    languages.forEach(function(lang) {
                        var opt = document.createElement('option');
                        opt.value = lang.id;
                        opt.textContent = lang.name + ' (' + lang.id + ')';
                        projectLangSelect.appendChild(opt);
                    });
                    createProject();
                }
                setTimeout(function() {
                    if (projectEditor) projectEditor.refresh();
                }, 50);
            } else {
                setTimeout(function() { editor.refresh(); }, 50);
            }
        });

        // ---- Project sidebar add file ----

        projectAddFileBtn.addEventListener('click', function() {
            showProjectModal('新建文件', '', 'add');
        });

        // ---- Project language change ----

        projectLangSelect.addEventListener('change', function() {
            if (currentProject) {
                currentProject.language = projectLangSelect.value;
            }
        });

        // ---- Project run ----

        projectRunBtn.addEventListener('click', runProject);

        // ---- Project clear output ----

        projectClearOutputBtn.addEventListener('click', function() {
            projectOutputEl.innerHTML = '<span class="placeholder">输出已清空</span>';
        });

        // ---- File context menu ----

        document.addEventListener('click', hideFileContextMenu);

        fileContextMenu.querySelectorAll('.file-context-menu-item').forEach(function(item) {
            item.addEventListener('click', function() {
                var action = this.dataset.action;
                var path = fileContextMenu._targetPath;
                hideFileContextMenu();

                if (action === 'rename') {
                    showProjectModal('重命名文件', path, 'rename', path);
                } else if (action === 'set-main') {
                    setMainFile(path);
                } else if (action === 'delete') {
                    deleteProjectFile(path);
                }
            });
        });

        // ---- Project modal ----

        projectModalOk.addEventListener('click', function() {
            var value = projectModalInput.value.trim();
            if (!value) return;

            if (projectModalAction === 'add') {
                addProjectFile(value);
            } else if (projectModalAction === 'rename' && projectModalContext) {
                renameProjectFile(projectModalContext, value);
            }
            hideProjectModal();
        });

        projectModalCancel.addEventListener('click', hideProjectModal);

        projectModalInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') projectModalOk.click();
            if (e.key === 'Escape') hideProjectModal();
        });

        projectModalOverlay.addEventListener('click', function(e) {
            if (e.target === projectModalOverlay) hideProjectModal();
        });

        // ---- Events ----
        langSelect.addEventListener('change', () => selectLanguage(langSelect.value));
        exampleSelect.addEventListener('change', function() {
            if (!currentLang || !exampleSelect.value) return;
            loadTemplate(currentLang.id, exampleSelect.value, function(code) {
                editor.setValue(code); editor.clearHistory();
            });
        });
        langLeft.addEventListener('change', () => selectCompareLang('left', langLeft.value));
        langRight.addEventListener('change', () => selectCompareLang('right', langRight.value));
        runBtn.addEventListener('click', runCurrentMode);

        // ---- Init ----
        initEditors();
        loadLanguages();
        connectWS();

    })();
