/* ===================================================================
   Context Optimisation Agent — Dashboard Script
   =================================================================== */

// ── State ──────────────────────────────────────────────────────────────────────
let _taskId       = null;
let _pollInterval = null;
let _logInterval  = null;
let _timerInterval= null;
let _startTime    = null;

// ── Entry point ────────────────────────────────────────────────────────────────
async function startTask() {
    const task = document.getElementById('taskInput').value.trim();
    if (!task) {
        alert('Please enter a task description.');
        return;
    }

    // Reset UI
    _resetUI();

    try {
        const res  = await fetch('/run_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task }),
        });
        const data = await res.json();

        if (data.error) {
            _showError('Server error: ' + data.error);
            return;
        }

        _taskId    = data.task_id;
        _startTime = Date.now();

        _showStatus('Agents initialising...');
        _startTimer();
        _startLogPolling();
        _pollStatus();

    } catch (err) {
        _showError('Network error: ' + err.message);
    }
}

// ── Status polling ─────────────────────────────────────────────────────────────
function _pollStatus() {
    _pollInterval = setInterval(async () => {
        try {
            const res  = await fetch(`/task_status/${_taskId}`);
            const data = await res.json();

            _showStatus(data.status || 'running...');

            if (data.status === 'completed') {
                _cleanup();
                _renderResults(data.results || []);
            } else if (data.status?.includes('error')) {
                _cleanup();
                _showError('Task error: ' + (data.error || data.status));
            }
        } catch (err) {
            console.error('[poll] error:', err);
        }
    }, 2000);
}

// ── Log polling ────────────────────────────────────────────────────────────────
function _startLogPolling() {
    const logEl = document.getElementById('logOutput');
    const autoScroll = () => document.getElementById('autoScrollLog').checked;

    _logInterval = setInterval(async () => {
        try {
            const res  = await fetch('/logs');
            const text = await res.text();
            logEl.textContent = text;
            if (autoScroll()) logEl.scrollTop = logEl.scrollHeight;
        } catch (_) {}
    }, 1500);
}

function clearLogDisplay() {
    document.getElementById('logOutput').textContent = '(cleared)';
}

// ── Timer ──────────────────────────────────────────────────────────────────────
function _startTimer() {
    const el = document.getElementById('statusTimer');
    _timerInterval = setInterval(() => {
        const s = Math.floor((Date.now() - _startTime) / 1000);
        const m = Math.floor(s / 60);
        el.textContent = m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
    }, 1000);
}

// ── Render results ─────────────────────────────────────────────────────────────
function _renderResults(results) {
    document.getElementById('resultsSection').classList.remove('hidden');
    document.getElementById('statusBar').classList.add('hidden');
    document.getElementById('runBtn').disabled = false;

    const a1 = results.find(r => r.approach === 'baseline');
    const a2 = results.find(r => r.approach === 'dual');

    _renderHeroCard('1', a1);
    _renderHeroCard('2', a2);
    _renderBenchTable(a1, a2);
    _renderFileList('A1', a1);
    _renderFileList('A2', a2);
    _renderOutput('A1', a1);
    _renderOutput('A2', a2);
    _renderWinner(a1, a2);
}

function _renderHeroCard(num, res) {
    if (!res) return;
    const m      = res.metrics || {};
    const large  = m.large || {};
    const small  = m.small || {};
    const total  = (large.total || 0) + (small.total || 0);
    const calls  = (large.call_count || 0) + (small.call_count || 0);
    const wall   = res.wall_time_s ?? '?';
    const ok     = res.success;

    const prefix = num === '1' ? 'a1' : 'a2';

    _animateNumber(document.getElementById(`${prefix}TotalTokens`), total);

    if (num === '1') {
        document.getElementById('a1InTok').textContent   = `in: ${(large.input||0).toLocaleString()}`;
        document.getElementById('a1OutTok').textContent  = `out: ${(large.output||0).toLocaleString()}`;
        document.getElementById('a1Wall').textContent    = `⏱ ${wall}s`;
        document.getElementById('a1Calls').textContent   = `calls: ${calls}`;
    } else {
        document.getElementById('a2LargeTok').textContent = `large: ${(large.total||0).toLocaleString()}`;
        document.getElementById('a2SmallTok').textContent = `small: ${(small.total||0).toLocaleString()}`;
        document.getElementById('a2Wall').textContent    = `⏱ ${wall}s`;
        document.getElementById('a2Calls').textContent   = `calls: ${calls}`;
    }

    const statusEl = document.getElementById(`${prefix}Status`);
    if (res.error) {
        statusEl.textContent = '❌ Error';
        statusEl.className = 'hero-status fail';
    } else {
        statusEl.textContent = ok ? '✅ Success' : '⚠️ Incomplete';
        statusEl.className   = `hero-status ${ok ? 'success' : 'fail'}`;
    }
}

function _renderWinner(a1, a2) {
    const banner = document.getElementById('winnerBanner');
    if (!a1 || !a2 || a1.error || a2.error) return;

    const t1 = _totalTokens(a1);
    const t2 = _totalTokens(a2);
    const largeOnly1 = (a1.metrics?.large?.total || 0);
    const largeOnly2 = (a2.metrics?.large?.total || 0);

    let msg = '';
    if (t1 < t2) {
        msg = `🏆 Approach 1 (Large Only) used fewer total tokens (${t1.toLocaleString()} vs ${t2.toLocaleString()})`;
        document.getElementById('heroA1').classList.add('winner');
    } else if (t2 < t1) {
        const saved = t1 - t2;
        const pct   = ((saved / t1) * 100).toFixed(1);
        msg = `🏆 Approach 2 (Planner+Executor) saved ${pct}% tokens on the large model — ${largeOnly1.toLocaleString()} → ${largeOnly2.toLocaleString()} large-model tokens`;
        document.getElementById('heroA2').classList.add('winner');
    } else {
        msg = '🤝 Both approaches used the same number of tokens.';
    }

    banner.textContent = msg;
    banner.classList.remove('hidden');
}

function _renderBenchTable(a1, a2) {
    const body = document.getElementById('benchBody');
    body.innerHTML = '';

    if (!a1 && !a2) return;

    const m1 = a1?.metrics || {};
    const m2 = a2?.metrics || {};
    const l1 = m1.large || {}, s1 = m1.small || {};
    const l2 = m2.large || {}, s2 = m2.small || {};

    const rows = [
        ['Large model tokens',   l1.total || 0, l2.total || 0, true],
        ['Small model tokens',   s1.total || 0, s2.total || 0, true],
        ['Total tokens',         _totalTokens(a1), _totalTokens(a2), true],
        ['Large model API calls',l1.call_count || 0, l2.call_count || 0, true],
        ['Small model API calls',s1.call_count || 0, s2.call_count || 0, true],
        ['Input tokens (large)', l1.input || 0, l2.input || 0, true],
        ['Output tokens (large)',l1.output || 0, l2.output || 0, true],
        ['Avg latency / call (large)', `${l1.avg_latency_ms || 0} ms`, `${l2.avg_latency_ms || 0} ms`, false],
        ['Wall time',            `${a1?.wall_time_s ?? '?'}s`, `${a2?.wall_time_s ?? '?'}s`, false],
        ['Steps executed',       a1?.step_count ?? '?', a2?.step_count ?? '?', false],
        ['Files created',        (a1?.created_files || []).length, (a2?.created_files || []).length, false],
        ['Success',              a1?.success ? '✅ Yes' : '❌ No', a2?.success ? '✅ Yes' : '❌ No', false],
    ];

    rows.forEach(([label, v1, v2, lowerBetter]) => {
        const tr = document.createElement('tr');
        let cls1 = '', cls2 = '', delta = '—';

        if (lowerBetter && typeof v1 === 'number' && typeof v2 === 'number') {
            if (v1 < v2)  { cls1 = 'better'; cls2 = 'worse'; }
            if (v2 < v1)  { cls2 = 'better'; cls1 = 'worse'; }
            const diff = v2 - v1;
            const pct  = v1 > 0 ? ((diff / v1) * 100).toFixed(1) : '—';
            delta = diff === 0 ? '—' : (diff > 0 ? `+${diff.toLocaleString()} (+${pct}%)` : `${diff.toLocaleString()} (${pct}%)`);
        }

        const fmt = v => typeof v === 'number' ? v.toLocaleString() : v;

        tr.innerHTML = `
            <td>${label}</td>
            <td class="${cls1}">${fmt(v1)}</td>
            <td class="${cls2}">${fmt(v2)}</td>
            <td style="color: var(--text-muted); font-size: 0.82rem">${delta}</td>
        `;
        body.appendChild(tr);
    });
}

function _renderFileList(suffix, res) {
    const ul = document.getElementById(`fileList${suffix}`);
    ul.innerHTML = '';

    if (!res || res.error) {
        ul.innerHTML = '<li class="file-empty">Error occurred</li>';
        return;
    }

    const created = res.created_files || [];
    const missing = res.missing_files || [];

    if (created.length === 0 && missing.length === 0) {
        ul.innerHTML = '<li class="file-empty">No files created</li>';
        return;
    }

    created.forEach(f => {
        const li = document.createElement('li');
        li.textContent = f;
        ul.appendChild(li);
    });

    missing.forEach(f => {
        const li = document.createElement('li');
        li.className = 'file-missing';
        li.textContent = `MISSING: ${f}`;
        ul.appendChild(li);
    });
}

function _renderOutput(suffix, res) {
    const el = document.getElementById(`output${suffix}`);
    if (!res) { el.textContent = 'No data'; return; }
    if (res.error) { el.textContent = `ERROR: ${res.error}`; return; }
    el.textContent = res.output || '(no output)';
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function _totalTokens(res) {
    if (!res || !res.metrics) return 0;
    return (res.metrics.large?.total || 0) + (res.metrics.small?.total || 0);
}

function _animateNumber(el, target) {
    if (!el) return;
    const duration = 1200;
    const start    = Date.now();
    const from     = parseInt(el.textContent.replace(/,/g, '')) || 0;

    const tick = () => {
        const progress = Math.min(1, (Date.now() - start) / duration);
        const ease     = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(from + (target - from) * ease).toLocaleString();
        if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
}

function _showStatus(msg) {
    const bar = document.getElementById('statusBar');
    bar.classList.remove('hidden');
    document.getElementById('statusText').textContent = msg;
}

function _showError(msg) {
    document.getElementById('runBtn').disabled = false;
    document.getElementById('statusText').textContent = '❌ ' + msg;
    console.error(msg);
}

function _resetUI() {
    document.getElementById('runBtn').disabled = true;
    document.getElementById('resultsSection').classList.add('hidden');
    document.getElementById('statusBar').classList.remove('hidden');
    document.getElementById('statusTimer').textContent = '0s';
    document.getElementById('logOutput').textContent = 'Starting agents...';
    document.getElementById('winnerBanner').classList.add('hidden');
    document.getElementById('heroA1').classList.remove('winner');
    document.getElementById('heroA2').classList.remove('winner');
    // Reset hero values
    ['a1TotalTokens','a2TotalTokens'].forEach(id => {
        document.getElementById(id).textContent = '—';
    });

    _cleanup();
}

function _cleanup() {
    clearInterval(_pollInterval);
    clearInterval(_timerInterval);
    // Keep log polling running even after completion so user can read final logs
    _pollInterval  = null;
    _timerInterval = null;
}
