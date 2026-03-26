/* Stego Explorer application logic */

// Static profile metadata — mirrors src/pipeline/profile.py
var PROFILE_META = {
    prototype:   { n_groups: 20,  active_methods: ['lsb'],        active_payload_levels: ['low'],                    n_detectors: 3 },
    full_design: { n_groups: 500, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'],  n_detectors: 5 },
};

var STATE = {
    page: 'runs',
    runId: null,
    tab: 'overview',
    search: '',
    renderToken: 0,
    terminalOpen: true,
    lastEngine: 'stub',
    lastProfile: 'prototype',
    jobs: {}
    /* jobs[jobId] = { jobId, runId, logLines, streamSource, streamErrors, failed, error, killed } */
};

function createJob(jobId, profile, engine) {
    STATE.jobs[jobId] = { jobId: jobId, runId: null, logLines: ['Starting…'], streamSource: null, streamErrors: 0, failed: false, error: null, killed: false, profile: profile || null, engine: engine || null };
    return STATE.jobs[jobId];
}
function getJob(jobId) { return STATE.jobs[jobId]; }
function getJobForRun(runId) {
    return Object.values(STATE.jobs).find(function(j) { return j.runId === runId || j.jobId === runId; });
}
function isRunActive(runId) {
    return Object.values(STATE.jobs).some(function(j) { return (j.runId === runId || j.jobId === runId) && !!j.streamSource; });
}
function getActiveJobs() { return Object.values(STATE.jobs).filter(function(j) { return !!j.streamSource; }); }

var SOURCE_COLORS = { real: '#7bd0ff', ml_a: '#ee7d77', ml_b: '#66d9a0' };
var ENCRYPTION_COLORS = { plain: '#7bd0ff', encrypted: '#d4cdee' };
var DETECTOR_PALETTE = ['#7bd0ff', '#ee7d77', '#66d9a0', '#d4cdee', '#f0c050', '#47c4ff'];
var SIDEBAR_TABS = [
    { id: 'overview', icon: 'dashboard', label: 'Overview' },
    { id: 'results', icon: 'analytics', label: 'Results' },
    { id: 'covers', icon: 'collections', label: 'Gallery' },
    { id: 'conditions', icon: 'science', label: 'Conditions' }
];

async function api(url, options) {
    var response = await fetch(url, options);
    if (!response.ok) {
        var text = await response.text();
        throw new Error(text || ('Request failed: ' + response.status));
    }
    return response.json();
}

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
    return String(value == null ? '' : value).replace(/'/g, '&#39;');
}

function icon(name, extraClass) {
    return '<span class="material-symbols-outlined' + (extraClass ? ' ' + extraClass : '') + '">' + escapeHtml(name) + '</span>';
}

function toArray(value) {
    return Array.isArray(value) ? value : [];
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function formatMaybeNumber(value, digits) {
    return value == null || Number.isNaN(Number(value)) ? '\u2014' : Number(value).toFixed(digits);
}

function statusPill(label, tone) {
    return '<span class="status-pill ' + tone + '">' + escapeHtml(label) + '</span>';
}

function uniqueValues(list, key) {
    var seen = {};
    return list.filter(function (item) {
        if (seen[item[key]]) return false;
        seen[item[key]] = true;
        return true;
    }).map(function (item) { return item[key]; });
}

function updateNavState() {
    var activePage = STATE.page === 'run-detail' ? 'runs' : STATE.page;
    var el = document.getElementById('nav-runs');
    if (el) el.classList.toggle('active', activePage === 'runs');
}

function go(page, runId) {
    if (page === 'launch') {
        openLaunchPanel();
        return;
    }
    var nextRunId = runId || null;
    var nextTab = 'overview';
    if (page === 'run-detail' && STATE.page === 'run-detail' && STATE.runId === nextRunId) {
        nextTab = STATE.tab;
    }

    STATE.page = page;
    STATE.runId = nextRunId;
    STATE.tab = nextTab;
    render();
}

function switchTab(tab) {
    if (STATE.page !== 'run-detail') return;
    STATE.tab = tab;
    render();
}

function filterRuns(query) {
    STATE.search = query || '';
    if (STATE.page === 'runs') render();
}

function syncSearchInput() {
    var input = document.getElementById('search-input');
    if (input && input.value !== STATE.search) input.value = STATE.search;
}

function showSidebar(runId, activeTab) {
    var sidebar = document.getElementById('sidebar');
    var main = document.getElementById('main');
    var runIdEl = document.getElementById('sidebar-run-id');
    var logLink = document.getElementById('sidebar-log-link');

    sidebar.classList.remove('is-hidden');
    main.classList.add('with-sidebar');
    runIdEl.textContent = runId;
    runIdEl.classList.remove('none');

    document.getElementById('sidebar-tabs').innerHTML = SIDEBAR_TABS.map(function (tab) {
        var cls = 'sidebar-tab' + (tab.id === activeTab ? ' active' : '');
        return '<a class="' + cls + '" onclick="switchTab(\'' + tab.id + '\')">' +
            icon(tab.icon) + '<span>' + escapeHtml(tab.label) + '</span></a>';
    }).join('');

    if (logLink) logLink.style.display = 'none';
}

function hideSidebar() {
    var sidebar = document.getElementById('sidebar');
    var main = document.getElementById('main');
    var runIdEl = document.getElementById('sidebar-run-id');
    var logLink = document.getElementById('sidebar-log-link');

    sidebar.classList.add('is-hidden');
    main.classList.remove('with-sidebar');
    runIdEl.textContent = 'No run selected';
    runIdEl.classList.add('none');
    if (logLink) logLink.style.display = 'none';
}

function renderLoading() {
    return '<div class="loading-page"><div class="loader"></div></div>';
}

function renderError(message, actionLabel, actionFn) {
    var button = actionLabel && actionFn
        ? '<div class="empty-actions"><button class="btn btn-primary" onclick="' + actionFn + '">' + escapeHtml(actionLabel) + '</button></div>'
        : '';
    return '<div class="empty-state"><h3>Something went off-track</h3><p>' + escapeHtml(message) + '</p>' + button + '</div>';
}

function render() {
    var el = document.getElementById('main');
    var token = ++STATE.renderToken;
    updateNavState();
    syncSearchInput();

    if (STATE.page === 'run-detail' && !STATE.runId) {
        STATE.page = 'runs';
    }

    if (STATE.page === 'runs') {
        hideSidebar();
        el.innerHTML = renderLoading();
        renderRunsList(el, token);
        return;
    }

    if (STATE.page === 'run-detail') {
        el.innerHTML = renderLoading();
        renderRunDetail(el, STATE.runId, token);
        return;
    }

    hideSidebar();
    el.innerHTML = '';
}

async function renderRunsList(el, token) {
    try {
        var runs = await api('/api/runs');
        if (token !== STATE.renderToken) return;

        if (!runs.length) {
            el.innerHTML =
                '<div class="empty-state">' +
                    '<h3>No runs yet</h3>' +
                    '<p>Launch a prototype run to seed the explorer with pipeline output.</p>' +
                    '<div class="empty-actions">' +
                        '<button class="btn btn-primary" onclick="openLaunchPanel()">' + icon('add') + ' New Run</button>' +
                    '</div>' +
                '</div>';
            return;
        }

        var filtered = filterRunCollection(runs, STATE.search);
        var stats = summarizeRuns(runs);
        var activity = buildActivityFeed(runs);
        var tip = buildRunsTip(runs, stats);
        var rows = filtered.map(buildRunRow).join('');

        el.innerHTML =
            '<div class="breadcrumb">' +
                '<span>Explorer</span>' +
                '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                '<span class="breadcrumb-active">Pipeline Runs</span>' +
            '</div>' +
            '<div class="page-header">' +
                '<div>' +
                    '<div class="page-title">Runs Overview</div>' +
                    '<div class="page-subtitle">' + escapeHtml(buildRunsSubtitle(filtered.length, runs.length, STATE.search)) + '</div>' +
                '</div>' +
                '<button class="btn btn-primary" onclick="openLaunchPanel()">' + icon('add') + ' New Run</button>' +
            '</div>' +
            '<div class="stats-bento">' +
                '<div class="bento-card"><div class="bento-label">Best Global AUC</div><div class="bento-value primary">' + formatMaybeNumber(stats.bestAuc, 3) + '</div><div class="bento-sub">' + escapeHtml(stats.bestRunLabel) + '</div></div>' +
                '<div class="bento-card"><div class="bento-label">Tracked Runs</div><div class="bento-value">' + formatNumber(runs.length) + '</div><div class="bento-sub">' + formatNumber(stats.completedRuns) + ' with metrics</div></div>' +
                '<div class="bento-card"><div class="bento-label">Processed Covers</div><div class="bento-value">' + formatNumber(stats.totalImages) + '</div><div class="bento-sub">' + formatNumber(stats.totalGroups) + ' grouped specimens</div></div>' +
                '<div class="bento-card"><div class="bento-label">Detector Evaluations</div><div class="bento-value">' + formatNumber(stats.totalDetectors) + '</div><div class="bento-sub">' + escapeHtml(stats.coverageLabel) + '</div></div>' +
            '</div>' +
            buildRunsTable(filtered, runs.length, rows) +
            '<div class="panels-row">' +
                '<div class="glass-panel">' +
                    '<div class="glass-panel-head"><div class="glass-panel-title">Recent Activity</div></div>' +
                    '<div class="glass-panel-body"><div class="activity-feed">' + activity + '</div></div>' +
                '</div>' +
                '<div class="glass-panel">' +
                    '<div class="glass-panel-head"><div class="glass-panel-title">Analysis Tip</div></div>' +
                    '<div class="glass-panel-body">' + tip + '</div>' +
                '</div>' +
            '</div>';
    } catch (error) {
        if (token !== STATE.renderToken) return;
        el.innerHTML = renderError(error.message, 'Retry', 'render()');
    }
}

function filterRunCollection(runs, search) {
    var query = (search || '').trim().toLowerCase();
    if (!query) return runs;
    return runs.filter(function (run) {
        var cfg = run.config || {};
        var haystack = [
            run.id,
            cfg.profile,
            toArray(cfg.active_methods).join(' '),
            toArray(cfg.active_payload_levels).join(' '),
            cfg.timestamp
        ].join(' ').toLowerCase();
        return haystack.indexOf(query) !== -1;
    });
}

function summarizeRuns(runs) {
    var summary = {
        bestAuc: null,
        bestRunLabel: 'Awaiting detector output',
        completedRuns: 0,
        totalImages: 0,
        totalGroups: 0,
        totalDetectors: 0,
        coverageLabel: 'No detector metrics yet'
    };

    runs.forEach(function (run) {
        var cfg = run.config || {};
        var groups = Number(cfg.n_groups || 0);
        summary.totalGroups += groups;
        summary.totalImages += groups * 3;
        summary.totalDetectors += Number(run.n_detectors || 0);
        if (run.has_results) summary.completedRuns += 1;
        if (run.best_auc != null && (summary.bestAuc == null || run.best_auc > summary.bestAuc)) {
            summary.bestAuc = Number(run.best_auc);
            summary.bestRunLabel = run.id;
        }
    });

    if (summary.totalDetectors) {
        summary.coverageLabel = formatNumber(summary.totalDetectors) + ' total detector rows';
    }

    return summary;
}

function buildRunsSubtitle(filteredCount, totalCount, search) {
    if (search) {
        return 'Showing ' + filteredCount + ' of ' + totalCount + ' runs for "' + search + '".';
    }
    return totalCount + ' experiment run' + (totalCount === 1 ? '' : 's') + ' currently available in the local explorer.';
}

function buildRunRow(run) {
    var cfg = run.config || {};
    // is_active / is_killed from API covers runs launched by other instances
    var isActive = isRunActive(run.id) || !!run.is_active;
    var isKilled = !isActive && (run.is_killed || (getJobForRun(run.id) || {}).killed);
    var activeJob = getJobForRun(run.id);
    // Parse profile from run ID as last resort (format: {profile}_{timestamp}_p{port})
    var profileFromId = Object.keys(PROFILE_META).find(function(k) { return run.id.startsWith(k); }) || null;
    var profile = cfg.profile || (activeJob && activeJob.profile) || profileFromId || (isActive ? '…' : 'unconfigured');
    // Use static profile metadata as fallback when config.json not yet written
    var meta = PROFILE_META[profile] || null;
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var levels = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    var nDetectors = run.n_detectors || (meta ? meta.n_detectors : 0);
    var runStatus = isActive
        ? statusPill('Running', 'running')
        : isKilled
            ? statusPill('Killed', 'error')
            : run.best_auc == null
                ? statusPill(run.has_results ? 'Metrics incomplete' : 'Pending results', run.has_results ? 'error' : 'pending')
                : statusPill('Metrics ready', 'ready');
    var aucCell;

    if (run.best_auc != null) {
        var value = Number(run.best_auc);
        var cls = value > 0.85 ? 'auc-high' : (value > 0.65 ? 'auc-mid' : 'auc-low');
        aucCell = '<span class="auc-badge ' + cls + '">' + value.toFixed(3) + '</span>';
    } else {
        aucCell = '<div class="no-results">' + icon('cloud_off') + '<span>No Results</span></div>';
    }

    var rowClass = isActive ? 'row-active' : (run.has_results ? '' : 'row-dimmed');
    return (
        '<tr' + (rowClass ? ' class="' + rowClass + '"' : '') + ' style="cursor:pointer" onclick="go(\'run-detail\', \'' + escapeAttr(run.id) + '\')">' +
            '<td>' +
                '<div class="run-name">' +
                    (isActive ? '<span class="run-live-dot"></span>' : '') +
                    '<strong>' + escapeHtml(run.id) + '</strong>' +
                    '<div class="run-sub-id">' + escapeHtml(cfg.timestamp || 'local run artifact') + '</div>' +
                '</div>' +
            '</td>' +
            '<td><span class="profile-tag' + (isActive ? ' profile-tag--dim' : '') + '">' + escapeHtml(profile) + '</span></td>' +
            '<td><span class="cell-mono">' + escapeHtml(nGroups != null ? nGroups : '\u2014') + '</span></td>' +
            '<td><span class="cell-dim">' + escapeHtml(methods.length ? methods.join(', ') : '\u2014') + '</span></td>' +
            '<td><span class="cell-dim">' + escapeHtml(levels.length ? levels.join(', ') : '\u2014') + '</span></td>' +
            '<td><div style="display:flex;align-items:center;gap:6px">' + icon('security') + '<span class="cell-mono">' + escapeHtml(nDetectors) + '</span></div></td>' +
            '<td>' + aucCell + '</td>' +
            '<td>' + runStatus + '</td>' +
            '<td>' +
                '<button class="btn-icon" onclick="event.stopPropagation();confirmDeleteRun(\'' + escapeAttr(run.id) + '\')" title="Delete run">' +
                    icon('delete') +
                '</button>' +
            '</td>' +
        '</tr>'
    );
}

function buildRunsTable(filteredRuns, totalRuns, rows) {
    if (!filteredRuns.length) {
        return '<div class="data-table-wrap"><div class="empty-state"><h3>No runs match this search</h3><p>Try a run id, profile name, method, or payload level.</p><div class="empty-actions"><button class="btn btn-ghost" onclick="clearSearch()">Clear Search</button></div></div></div>';
    }

    return (
        '<div class="data-table-wrap">' +
            '<div style="overflow-x:auto">' +
                '<table class="data-table">' +
                    '<thead><tr>' +
                        '<th>Run Name</th>' +
                        '<th>Profile</th>' +
                        '<th>Groups</th>' +
                        '<th>Methods</th>' +
                        '<th>Payloads</th>' +
                        '<th>Detectors</th>' +
                        '<th>Best AUC</th>' +
                        '<th>Status</th>' +
                        '<th>Actions</th>' +
                    '</tr></thead>' +
                    '<tbody>' + rows + '</tbody>' +
                '</table>' +
            '</div>' +
            '<div class="table-footer">' +
                '<span>Displaying ' + filteredRuns.length + ' of ' + totalRuns + ' runs</span>' +
                '<div class="table-footer-actions">' +
                    '<span class="inline-note">' + icon('tips_and_updates') + '<strong>Tip:</strong> click a row to inspect run detail.</span>' +
                '</div>' +
            '</div>' +
        '</div>'
    );
}

function buildActivityFeed(runs) {
    return runs.slice(0, 4).map(function (run, index) {
        var tone = run.best_auc == null ? (run.has_results ? 'red' : 'amber') : (index === 0 ? 'blue' : 'green');
        var text = run.best_auc == null
            ? (run.has_results ? 'Run <strong>' + escapeHtml(run.id) + '</strong> produced partial metrics that need review.' : 'Run <strong>' + escapeHtml(run.id) + '</strong> has been created but has not produced detector metrics yet.')
            : 'Run <strong>' + escapeHtml(run.id) + '</strong> completed with best ROC-AUC <strong>' + escapeHtml(Number(run.best_auc).toFixed(3)) + '</strong>.';
        return '<div class="activity-item">' +
            '<div class="activity-dot ' + tone + '"></div>' +
            '<div><div class="activity-text">' + text + '</div><div class="activity-time">' + escapeHtml((run.config || {}).timestamp || 'local artifact') + '</div></div>' +
        '</div>';
    }).join('');
}

function buildRunsTip(runs, stats) {
    var bestRun = runs.find(function (run) { return stats.bestRunLabel === run.id; });
    var bestProfile = bestRun && bestRun.config && bestRun.config.profile ? bestRun.config.profile : 'prototype';
    var payloads = bestRun && bestRun.config ? toArray(bestRun.config.active_payload_levels) : [];

    return (
        '<div class="tip-icon">' + icon('info') + '</div>' +
        '<div class="tip-title">Best-performing configuration</div>' +
        '<div class="tip-text">' +
            'Right now the strongest local run is <strong>' + escapeHtml(stats.bestRunLabel) + '</strong>. ' +
            'If you want the redesign to guide analysis, start by comparing new runs against the <strong>' + escapeHtml(bestProfile) + '</strong> profile' +
            (payloads.length ? ' across payloads ' + escapeHtml(payloads.join(', ')) + '.' : '.') +
        '</div>'
    );
}

async function renderRunDetail(el, runId, token) {
    try {
        var data = await api('/api/runs/' + encodeURIComponent(runId) + '/detail');
        if (token !== STATE.renderToken) return;
        var isThisRunActive = isRunActive(runId) || !!(data && data.is_active);
        var isThisRunKilled = !isThisRunActive && !!(data && data.is_killed || (getJobForRun(runId) || {}).killed);
        var jobForRun = getJobForRun(runId);

        if (!data || !Object.keys(data).length) {
            if (!isThisRunActive) {
                hideSidebar();
                el.innerHTML = renderError('The selected run could not be found.', 'Back to Runs', 'go(\'runs\')');
                return;
            }
            /* Run just started — show terminal-only initializing state */
            hideSidebar();
            el.innerHTML =
                '<div class="breadcrumb">' +
                    '<a onclick="go(\'runs\')">Runs</a>' +
                    '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                    '<span class="breadcrumb-active">' + escapeHtml(runId) + '</span>' +
                '</div>' +
                '<div class="page-header">' +
                    '<div>' +
                        '<div class="page-title">' + escapeHtml(runId) + '</div>' +
                        '<div class="page-subtitle">Pipeline initializing — awaiting output…</div>' +
                    '</div>' +
                    '<button class="btn btn-ghost" onclick="go(\'runs\')">' + icon('arrow_back') + ' Back to Runs</button>' +
                '</div>' +
                buildTerminalSection(runId);
            attachStream(runId);
            return;
        }

        var cfg = data.config || {};
        var detailStats = summarizeRunDetail(data);
        showSidebar(runId, STATE.tab);

        var body = '';
        if (STATE.tab === 'overview') body = buildOverviewTab(cfg, detailStats, runId);
        if (STATE.tab === 'results') body = buildResultsTab(data, detailStats);
        if (STATE.tab === 'covers') body = buildCoversTab(data.covers || []);
        if (STATE.tab === 'conditions') body = buildConditionsTab(data);

        el.innerHTML =
            '<div class="breadcrumb">' +
                '<a onclick="go(\'runs\')">Runs</a>' +
                '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                '<span class="breadcrumb-active">' + escapeHtml(runId) + '</span>' +
            '</div>' +
            '<div class="page-header">' +
                '<div>' +
                    '<div class="page-title">' + escapeHtml(runId) + '</div>' +
                    '<div class="page-subtitle">' + escapeHtml(isThisRunActive && !cfg.profile ? (jobForRun ? (jobForRun.profile || 'prototype') + ' · ' + (jobForRun.engine || 'stub') + ' engine · running…' : 'Pipeline running…') : buildRunHeader(cfg, detailStats, runId)) + '</div>' +
                '</div>' +
                '<button class="btn btn-ghost" onclick="go(\'runs\')">' + icon('arrow_back') + ' Back to Runs</button>' +
            '</div>' +
            (getJobForRun(runId) ? buildTerminalSection(runId) : (isThisRunKilled ? buildKilledBanner(runId) : '')) +
            (!detailStats.detectorCount && !detailStats.coverGroups
                ? ''  /* suppress stat cards when there is no data to show */
                : '<div class="summary-strip">' +
                      '<div class="summary-card"><div class="summary-label">Best ROC-AUC</div><div class="summary-value primary">' + formatMaybeNumber(detailStats.bestAuc, 3) + '</div><div class="summary-sub">' + escapeHtml(detailStats.bestDetectorLabel) + '</div></div>' +
                      '<div class="summary-card"><div class="summary-label">Detector Rows</div><div class="summary-value">' + formatNumber(detailStats.detectorCount) + '</div><div class="summary-sub">' + escapeHtml(detailStats.sampleLabel) + '</div></div>' +
                      '<div class="summary-card"><div class="summary-label">Cover Groups</div><div class="summary-value">' + formatNumber(detailStats.coverGroups) + '</div><div class="summary-sub">' + escapeHtml(detailStats.coverLabel) + '</div></div>' +
                  '</div>') +
            ((isThisRunActive || isThisRunKilled) && !data.has_results && !detailStats.coverGroups
                ? ''  /* suppress empty tabs while pipeline is still running or was killed early */
                : '<div id="tab-body">' + body + '</div>');

        if (isThisRunActive && jobForRun) attachStream(jobForRun.jobId);
        if (STATE.tab === 'results' && data.has_results) {
            requestAnimationFrame(function () { drawAllCharts(data); });
        }
    } catch (error) {
        if (token !== STATE.renderToken) return;
        hideSidebar();
        el.innerHTML = renderError(error.message, 'Back to Runs', 'go(\'runs\')');
    }
}

function buildKilledBanner(runId) {
    return '<div class="rd-terminal">' +
        '<div class="rd-terminal-hdr">' +
            '<span>' + icon('terminal') + ' Pipeline Output</span>' +
            '<span class="badge badge-error">✗ Killed</span>' +
        '</div>' +
        '<div class="rd-error-banner">' +
            icon('cancel') +
            '<span class="rd-error-msg">This run was killed before it completed. No pipeline output is available from this viewer instance.</span>' +
        '</div>' +
    '</div>';
}

function buildTerminalSection(runId) {
    var job = getJobForRun(runId);
    if (!job || !job.logLines.length) return '';

    var isRunning = !!job.streamSource && !job.failed && !job.killed;
    var isOpen = STATE.terminalOpen;
    var logContent = escapeHtml(job.logLines.join('\n'));

    var statusBadge = isRunning
        ? '<span class="badge badge-running">● Live</span>'
        : (job.failed || job.killed)
            ? '<span class="badge badge-error">' + (job.killed ? '✗ Killed' : '✗ Failed') + '</span>'
            : '<span class="badge badge-done">✓ Completed</span>';

    var killBtn = isRunning
        ? '<button class="rd-kill-btn" onclick="killRun(\'' + escapeAttr(job.jobId) + '\')" title="Kill this run">' +
              '<span class="material-symbols-outlined">stop_circle</span> Kill' +
          '</button>'
        : '';

    var errorBanner = ((job.failed || job.killed) && job.error)
        ? '<div class="rd-error-banner">' +
              '<span class="material-symbols-outlined">error_outline</span>' +
              '<div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div>' +
          '</div>'
        : '';

    var body = isOpen
        ? '<div class="rd-terminal-body">' +
              errorBanner +
              '<div class="lp-terminal-chrome">' +
                  '<span class="lp-dot lp-dot--r"></span>' +
                  '<span class="lp-dot lp-dot--y"></span>' +
                  '<span class="lp-dot lp-dot--g"></span>' +
                  '<span class="lp-terminal-label">sh — ' + escapeHtml(job.runId || job.jobId) + ' — pts/0</span>' +
              '</div>' +
              '<pre class="log-box lp-log-body" id="run-terminal-log">' + logContent + '</pre>' +
          '</div>'
        : '';

    return '<div class="rd-terminal">' +
        '<div class="rd-terminal-hdr" onclick="toggleRunTerminal()">' +
            '<div class="rd-terminal-hdr-left">' +
                '<span class="material-symbols-outlined rd-term-icon">terminal</span>' +
                '<span class="rd-terminal-title">Pipeline Output</span>' +
                statusBadge +
            '</div>' +
            '<div class="rd-terminal-hdr-right">' +
                killBtn +
                '<span class="material-symbols-outlined rd-term-chevron">' + (isOpen ? 'expand_less' : 'expand_more') + '</span>' +
            '</div>' +
        '</div>' +
        body +
    '</div>';
}

function toggleRunTerminal() {
    STATE.terminalOpen = !STATE.terminalOpen;
    var section = document.querySelector('.rd-terminal');
    if (!section) return;
    var chevron = section.querySelector('.rd-term-chevron');
    var job = getJobForRun(STATE.runId);
    var existingBody = section.querySelector('.rd-terminal-body');

    if (STATE.terminalOpen && job) {
        var isRunning = !!job.streamSource && !job.failed && !job.killed;
        var errorBanner = ((job.failed || job.killed) && job.error)
            ? '<div class="rd-error-banner"><span class="material-symbols-outlined">error_outline</span><div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div></div>'
            : '';
        var div = document.createElement('div');
        div.className = 'rd-terminal-body';
        div.innerHTML =
            errorBanner +
            '<div class="lp-terminal-chrome">' +
                '<span class="lp-dot lp-dot--r"></span><span class="lp-dot lp-dot--y"></span><span class="lp-dot lp-dot--g"></span>' +
                '<span class="lp-terminal-label">sh — ' + escapeHtml((job.runId || job.jobId)) + ' — pts/0</span>' +
            '</div>' +
            '<pre class="log-box lp-log-body" id="run-terminal-log">' + escapeHtml(job.logLines.join('\n')) + '</pre>';
        section.appendChild(div);
        var box = div.querySelector('#run-terminal-log');
        if (box) box.scrollTop = box.scrollHeight;
    } else {
        if (existingBody) existingBody.remove();
    }
    if (chevron) chevron.textContent = STATE.terminalOpen ? 'expand_less' : 'expand_more';
}

function summarizeRunDetail(data) {
    var detectorRows = toArray((data.metrics || {}).detector);
    var covers = toArray(data.covers);
    var bestRow = null;
    var sampleTotal = 0;

    detectorRows.forEach(function (row) {
        sampleTotal += Number(row.n_samples || 0);
        if (row.roc_auc != null && (!bestRow || Number(row.roc_auc) > Number(bestRow.roc_auc))) {
            bestRow = row;
        }
    });

    return {
        bestAuc: bestRow ? Number(bestRow.roc_auc) : null,
        bestDetectorLabel: bestRow ? bestRow.detector : 'No detector metrics yet',
        detectorCount: detectorRows.length,
        sampleLabel: sampleTotal ? formatNumber(sampleTotal) + ' samples scored' : 'No evaluation samples',
        coverGroups: covers.length,
        coverLabel: covers.length ? 'three source slots per group' : 'manifest not generated',
        hasResults: !!data.has_results
    };
}

function buildRunHeader(cfg, detailStats, runId) {
    var profileFromId = runId ? (Object.keys(PROFILE_META).find(function(k) { return runId.startsWith(k); }) || null) : null;
    var profile = cfg.profile || profileFromId || 'unconfigured profile';
    var meta = PROFILE_META[profile] || null;
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    var groups = nGroups != null ? nGroups + ' groups' : 'group count unavailable';
    return [
        profile,
        groups,
        methods.length ? methods.join(', ') : 'no methods listed',
        payloads.length ? 'payloads ' + payloads.join(', ') : 'no payload levels listed',
        detailStats.hasResults ? 'metrics ready' : 'metrics pending'
    ].join(' · ');
}

function buildOverviewTab(cfg, detailStats, runId) {
    var profileFromId = runId ? (Object.keys(PROFILE_META).find(function(k) { return runId.startsWith(k); }) || null) : null;
    var profile = cfg.profile || profileFromId || null;
    var meta = PROFILE_META[profile] || null;
    var groups = cfg.n_groups != null ? Number(cfg.n_groups) : (meta ? meta.n_groups : 0);
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var conditionCount = methods.length * payloads.length * 2;
    var fillRates = Object.keys(cfg.payload_fill_rates || {}).length
        ? Object.keys(cfg.payload_fill_rates).map(function (key) {
            return key + '=' + cfg.payload_fill_rates[key];
        }).join(', ')
        : '\u2014';

    var rows = [
        ['Profile', profile || '\u2014'],
        ['Groups', groups || '\u2014'],
        ['Methods', methods.length ? methods.join(', ') : '\u2014'],
        ['Payload levels', payloads.length ? payloads.join(', ') : '\u2014'],
        ['Fill rates', fillRates],
        ['Image size', toArray(cfg.image_size).length ? cfg.image_size.join('x') : '\u2014'],
        ['JPEG quality', cfg.jpeg_quality != null ? cfg.jpeg_quality : '\u2014'],
        ['Cover seed', cfg.cover_seed != null ? cfg.cover_seed : '\u2014'],
        ['Payload seed', cfg.payload_seed != null ? cfg.payload_seed : '\u2014'],
        ['Timestamp', cfg.timestamp || '\u2014']
    ].map(function (pair) {
        return '<tr><td>' + escapeHtml(pair[0]) + '</td><td>' + escapeHtml(pair[1]) + '</td></tr>';
    }).join('');

    return (
        '<div class="detail-grid">' +
            '<div class="card">' +
                '<div class="card-head"><span class="card-title">Run Configuration</span></div>' +
                '<table class="config-table">' + rows + '</table>' +
            '</div>' +
            '<div class="detail-note">' +
                '<h3>Operational Note</h3>' +
                '<p>' +
                    (detailStats.hasResults
                        ? 'This run already has detector output, so the fastest way to compare it is through the Results and Conditions tabs. Use the overview as the experiment contract for reproducing the same profile later.'
                        : 'This run has been created, but the explorer cannot see detector metrics yet. That usually means the pipeline has not finished, or the run only produced config scaffolding so far.') +
                '</p>' +
            '</div>' +
        '</div>' +
        '<div class="stats">' +
            '<div class="stat"><div class="stat-val">' + formatNumber(groups) + '</div><div class="stat-lbl">Groups</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(groups * 3) + '</div><div class="stat-lbl">Cover Slots</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(conditionCount) + '</div><div class="stat-lbl">Conditions</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(methods.length) + '</div><div class="stat-lbl">Methods</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(payloads.length) + '</div><div class="stat-lbl">Payload Levels</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatMaybeNumber(detailStats.bestAuc, 3) + '</div><div class="stat-lbl">Best ROC-AUC</div></div>' +
        '</div>'
    );
}

function buildResultsTab(data, detailStats) {
    if (!data.has_results) {
        return '<div class="empty-state"><h3>No results yet</h3><p>Run the pipeline with detectors enabled to populate charts and score tables.</p></div>';
    }

    var detectorRows = toArray((data.metrics || {}).detector);
    var tableRows = detectorRows.map(function (row) {
        var auc = Number(row.roc_auc || 0);
        var eer = Number(row.eer || 0);
        var acc = Number(row.accuracy_at_youden_j || 0);
        var color = auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)');

        return '<tr>' +
            '<td style="font-weight:600">' + escapeHtml(row.detector) + '</td>' +
            '<td><div class="auc-inline"><div class="auc-fill" style="width:' + Math.max(4, Math.round(auc * 110)) + 'px;background:' + color + '"></div><span class="auc-num" style="color:' + color + '">' + auc.toFixed(3) + '</span></div></td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + (eer * 100).toFixed(1) + '%</td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + (acc * 100).toFixed(1) + '%</td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + escapeHtml(row.n_samples || 0) + '</td>' +
        '</tr>';
    }).join('');

    return (
        '<div class="detail-note" style="margin-bottom:12px">' +
            '<h3>Result Snapshot</h3>' +
            '<p>The current leader is <code>' + escapeHtml(detailStats.bestDetectorLabel) + '</code> with ROC-AUC <code>' + formatMaybeNumber(detailStats.bestAuc, 3) + '</code>. Charts below compare detector strength across source families and encryption state.</p>' +
        '</div>' +
        '<div class="charts-row">' +
            '<div class="chart-box"><div class="chart-title">AUC by Detector</div><canvas id="chart-detector" height="220"></canvas></div>' +
            '<div class="chart-box"><div class="chart-title">AUC by Source</div><canvas id="chart-source" height="220"></canvas></div>' +
        '</div>' +
        '<div class="charts-full"><div class="chart-box"><div class="chart-title">AUC by Encryption</div><canvas id="chart-encryption" height="190"></canvas></div></div>' +
        '<div class="card" style="margin-top:10px">' +
            '<div class="card-head"><span class="card-title">Detector Performance</span></div>' +
            '<div style="overflow-x:auto"><table class="metrics-table"><thead><tr><th>Detector</th><th>ROC-AUC</th><th>EER</th><th>Accuracy</th><th>Samples</th></tr></thead><tbody>' + tableRows + '</tbody></table></div>' +
        '</div>'
    );
}

function drawAllCharts(data) {
    var detectorRows = toArray((data.metrics || {}).detector);
    var sourceRows = toArray((data.metrics || {}).source);
    var conditionRows = toArray((data.metrics || {}).condition);
    var detectorNames = uniqueValues(detectorRows, 'detector');

    var detectorCanvas = document.getElementById('chart-detector');
    if (detectorCanvas && detectorRows.length) {
        drawHorizontalBars(
            detectorCanvas,
            detectorRows.map(function (row) { return row.detector; }),
            detectorRows.map(function (row) { return Number(row.roc_auc || 0); }),
            detectorRows.map(function (_, index) { return DETECTOR_PALETTE[index % DETECTOR_PALETTE.length]; })
        );
    }

    var sourceCanvas = document.getElementById('chart-source');
    if (sourceCanvas && sourceRows.length) {
        drawGroupedBars(sourceCanvas, detectorNames, ['real', 'ml_a', 'ml_b'].map(function (source) {
            return {
                label: source,
                color: SOURCE_COLORS[source],
                vals: detectorNames.map(function (detector) {
                    var row = sourceRows.find(function (item) {
                        return item.detector === detector && item.source === source;
                    });
                    return row ? Number(row.roc_auc || 0) : 0;
                })
            };
        }));
    }

    var encryptionCanvas = document.getElementById('chart-encryption');
    if (encryptionCanvas && conditionRows.length) {
        drawGroupedBars(encryptionCanvas, detectorNames, ['plain', 'encrypted'].map(function (encryption) {
            return {
                label: encryption,
                color: ENCRYPTION_COLORS[encryption],
                vals: detectorNames.map(function (detector) {
                    var rows = conditionRows.filter(function (item) {
                        return item.detector === detector && item.encryption === encryption && item.roc_auc;
                    });
                    if (!rows.length) return 0;
                    return rows.reduce(function (sum, item) {
                        return sum + Number(item.roc_auc || 0);
                    }, 0) / rows.length;
                })
            };
        }));
    }
}

function buildCoversTab(covers) {
    if (!covers.length) {
        return '<div class="empty-state"><h3>No cover manifest found</h3><p>This run has not exported grouped cover previews yet.</p></div>';
    }

    var groups = covers.map(function (group) {
        var cells = ['real', 'ml_a', 'ml_b'].map(function (source) {
            var path = (group.sources || {})[source];
            var label = source.replace('_', ' ');
            if (!path) {
                return '<div class="source-cell"><div class="source-label ' + source + '">' + escapeHtml(label) + '</div><div class="image-none">\u2014</div></div>';
            }

            var url = '/api/image?path=' + encodeURIComponent(path);
            return '<div class="source-cell"><div class="source-label ' + source + '">' + escapeHtml(label) + '</div><img class="cover-thumb" src="' + escapeAttr(url) + '" loading="lazy" alt="' + escapeAttr(label) + '" onclick="openLightbox(\'' + escapeAttr(url) + '\')"></div>';
        }).join('');

        return '<div class="group-card">' +
            '<div class="group-head">' +
                '<span class="group-gid">Group ' + escapeHtml(group.group_id) + '</span>' +
                (group.caption ? '<span class="group-caption">' + escapeHtml(group.caption) + '</span>' : '') +
            '</div>' +
            '<div class="group-images">' + cells + '</div>' +
        '</div>';
    }).join('');

    return '<div class="section-header"><div><div class="section-title">Cover Images</div><div class="section-subtitle">' + covers.length + ' groups · real and generated sources</div></div></div><div class="covers-grid">' + groups + '</div>';
}

function buildConditionsTab(data) {
    var conditionRows = toArray((data.metrics || {}).condition);
    if (!conditionRows.length) {
        return '<div class="empty-state"><h3>No condition metrics</h3><p>This run has no per-condition AUC table yet.</p></div>';
    }

    var detectors = uniqueValues(conditionRows, 'detector');
    var methods = uniqueValues(conditionRows, 'method');
    var levels = uniqueValues(conditionRows, 'payload_level');
    var encryptions = uniqueValues(conditionRows, 'encryption');
    var columns = [];

    methods.forEach(function (method) {
        levels.forEach(function (level) {
            encryptions.forEach(function (encryption) {
                columns.push({ method: method, level: level, encryption: encryption });
            });
        });
    });

    var header = columns.map(function (column) {
        return '<th style="text-align:center"><div>' + escapeHtml(String(column.method).toUpperCase()) + '</div><div style="color:var(--amber);font-weight:500">' + escapeHtml(column.level) + '</div><div style="color:var(--tertiary-dim);font-weight:500">' + escapeHtml(column.encryption) + '</div></th>';
    }).join('');

    var body = detectors.map(function (detector) {
        var cells = columns.map(function (column) {
            var row = conditionRows.find(function (item) {
                return item.detector === detector &&
                    item.method === column.method &&
                    item.payload_level === column.level &&
                    item.encryption === column.encryption;
            });

            if (!row) return '<td style="text-align:center;color:var(--secondary-dim)">\u2014</td>';
            var auc = Number(row.roc_auc || 0);
            var color = auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)');
            return '<td style="text-align:center;font-weight:600;font-family:monospace;font-size:12px;color:' + color + '">' + auc.toFixed(3) + '</td>';
        }).join('');

        return '<tr><td style="font-weight:600">' + escapeHtml(detector) + '</td>' + cells + '</tr>';
    }).join('');

    return '<div class="card"><div class="card-head"><span class="card-title">AUC per Condition</span></div><div style="overflow-x:auto"><table class="metrics-table"><thead><tr><th>Detector</th>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div></div>';
}

function openLaunchPanel() {
    var overlay = document.getElementById('launch-drawer-overlay');
    var drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.add('open');
    if (drawer) drawer.classList.add('open');
    renderLaunchDrawer();
}

function closeLaunchPanel() {
    var overlay = document.getElementById('launch-drawer-overlay');
    var drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.remove('open');
    if (drawer) drawer.classList.remove('open');
}

function renderLaunchDrawer() {
    var el = document.getElementById('launch-drawer-body');
    if (!el) return;
    var activeCount = getActiveJobs().length;
    var curEngine  = STATE.lastEngine  || 'stub';
    var curProfile = STATE.lastProfile || 'prototype';

    function engineOpt(value, label, sub) {
        var checked = curEngine === value;
        return '<label class="lp-engine-opt' + (checked ? ' lp-engine-opt--checked' : '') + '">' +
            '<div class="lp-engine-opt-left">' +
                '<input type="radio" class="lp-engine-radio" name="launch-engine" value="' + escapeAttr(value) + '"' + (checked ? ' checked' : '') + '>' +
                '<span class="lp-engine-name">' + escapeHtml(label) + '</span>' +
            '</div>' +
            '<span class="lp-engine-sub">' + escapeHtml(sub) + '</span>' +
        '</label>';
    }

    el.innerHTML =
        /* System check */
        '<div class="drawer-section">' +
            '<div class="sc-row">' +
                '<div class="lp-field-label" style="margin-bottom:0">System Check</div>' +
                '<button class="sc-refresh-btn" onclick="loadSystemCheck()" title="Re-check">' +
                    '<span class="material-symbols-outlined">refresh</span>' +
                '</button>' +
            '</div>' +
            '<div class="sc-panel" id="sc-panel"><div class="sc-loading"><span class="loader sc-loader"></span> Checking…</div></div>' +
        '</div>' +
        '<div class="drawer-divider"></div>' +
        '<div class="drawer-section">' +
            '<div class="lp-field-label">Research Profile</div>' +
            '<div class="lp-dropdown" id="lp-profile-dropdown">' +
                '<button class="lp-dropdown-trigger" type="button" onclick="toggleLpDropdown()">' +
                    '<span class="lp-dropdown-value" id="lp-profile-label">' + (curProfile === 'prototype' ? 'Prototype Analysis' : 'Prototype Analysis') + '</span>' +
                    '<span class="material-symbols-outlined lp-dropdown-arrow">expand_more</span>' +
                '</button>' +
                '<div class="lp-dropdown-menu" id="lp-profile-menu">' +
                    '<div class="lp-dropdown-opt lp-dropdown-opt--selected" onclick="selectLpProfile(\'prototype\', \'Prototype Analysis\', this)">' +
                        '<span class="material-symbols-outlined lp-dropdown-check">check</span>Prototype Analysis' +
                    '</div>' +
                    '<div class="lp-dropdown-opt lp-dropdown-opt--disabled">' +
                        '<span class="material-symbols-outlined lp-dropdown-check" style="opacity:0">check</span>Full Design Analysis<span class="lp-dropdown-tag">Soon</span>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<input type="hidden" id="launch-profile" value="' + escapeAttr(curProfile) + '">' +
        '</div>' +
        '<div class="drawer-section">' +
            '<div class="lp-field-label">ML Image Engine</div>' +
            '<div class="lp-engine-group">' +
                engineOpt('stub',          'Fast Stub',  'Low Latency') +
                engineOpt('inference_api', 'Cloud API',  'High Capacity') +
                engineOpt('diffusers',     'Local GPU',  'Private / Secure') +
            '</div>' +
        '</div>' +
        (activeCount > 0
            ? '<div class="drawer-section"><div class="sc-running-note">' +
                  '<span class="material-symbols-outlined">info</span>' +
                  activeCount + ' run' + (activeCount > 1 ? 's' : '') + ' already in progress — you can launch additional runs in parallel.' +
              '</div></div>'
            : '') +
        '<div class="drawer-footer">' +
            '<button class="btn-launch" id="launch-btn" onclick="launchRun()">' +
                '<span class="material-symbols-outlined">bolt</span> START RUN' +
            '</button>' +
        '</div>';

    /* wire up radio → state */
    var radios = el.querySelectorAll('input[name="launch-engine"]');
    radios.forEach(function(r) {
        r.addEventListener('change', function() {
            STATE.lastEngine = this.value;
            el.querySelectorAll('.lp-engine-opt').forEach(function(opt) {
                opt.classList.toggle('lp-engine-opt--checked', opt.querySelector('input').value === r.value);
            });
        });
    });

    loadSystemCheck();
}

function loadSystemCheck() {
    var panel = document.getElementById('sc-panel');
    if (!panel) return;
    panel.innerHTML = '<div class="sc-loading"><span class="loader sc-loader"></span> Checking…</div>';
    api('/api/system/check').then(function(data) {
        var panel = document.getElementById('sc-panel');
        if (!panel) return;
        panel.innerHTML = renderSystemCheck(data);
    }).catch(function() {
        var panel = document.getElementById('sc-panel');
        if (panel) panel.innerHTML = '<div class="sc-error">Could not reach server check endpoint.</div>';
    });
}

function renderSystemCheck(data) {
    var pyOk = data.python_ok;
    var pyBadge = pyOk
        ? '<span class="sc-badge sc-badge--ok">Python ' + escapeHtml(data.python_version) + '</span>'
        : '<span class="sc-badge sc-badge--err">Python ' + escapeHtml(data.python_version) + ' (need ≥3.9)</span>';

    var core = data.packages.filter(function(p) { return p.required; });
    var optional = data.packages.filter(function(p) { return !p.required; });

    function pkgRow(p) {
        var icon = p.installed ? 'check_circle' : 'cancel';
        var cls  = p.installed ? 'sc-pkg--ok' : (p.required ? 'sc-pkg--err' : 'sc-pkg--warn');
        return '<div class="sc-pkg ' + cls + '">' +
            '<span class="material-symbols-outlined sc-pkg-icon">' + icon + '</span>' +
            '<span class="sc-pkg-name">' + escapeHtml(p.name) + '</span>' +
            (p.version ? '<span class="sc-pkg-ver">' + escapeHtml(p.version) + '</span>' : '') +
        '</div>';
    }

    return pyBadge +
        '<div class="sc-group">' +
            '<div class="sc-group-label">Core</div>' +
            core.map(pkgRow).join('') +
        '</div>' +
        '<div class="sc-group">' +
            '<div class="sc-group-label">ML / Optional</div>' +
            optional.map(pkgRow).join('') +
        '</div>';
}

function toggleLpDropdown() {
    var menu = document.getElementById('lp-profile-menu');
    var dropdown = document.getElementById('lp-profile-dropdown');
    if (!menu || !dropdown) return;
    var open = dropdown.classList.toggle('lp-dropdown--open');
    if (open) {
        var close = function(e) {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('lp-dropdown--open');
                document.removeEventListener('click', close);
            }
        };
        setTimeout(function() { document.addEventListener('click', close); }, 0);
    }
}

function selectLpProfile(value, label, optEl) {
    var input = document.getElementById('launch-profile');
    var labelEl = document.getElementById('lp-profile-label');
    var dropdown = document.getElementById('lp-profile-dropdown');
    if (input) input.value = value;
    if (labelEl) labelEl.textContent = label;
    if (dropdown) dropdown.classList.remove('lp-dropdown--open');
    /* update check marks */
    document.querySelectorAll('#lp-profile-menu .lp-dropdown-opt').forEach(function(opt) {
        opt.classList.toggle('lp-dropdown-opt--selected', opt === optEl);
    });
    STATE.lastProfile = value;
}

function renderLaunchPage(el) {
    var isRunning = !!STATE.job;
    var showLog = isRunning || STATE.logLines.length > 0;
    var logContent = escapeHtml(STATE.logLines.join('\n'));

    var curEngine  = STATE.lastEngine  || 'stub';
    var curProfile = STATE.lastProfile || 'prototype';

    var ENGINE_LABELS = { stub: 'Fast Stub', inference_api: 'Cloud API', diffusers: 'Local GPU' };

    function engineRadio(value, label, sub) {
        var checked = curEngine === value;
        return '<label class="lp-engine-opt' + (checked ? ' lp-engine-opt--checked' : '') + '">' +
            '<div class="lp-engine-opt-left">' +
                '<input type="radio" class="lp-engine-radio" name="launch-engine" value="' + escapeAttr(value) + '"' + (checked ? ' checked' : '') + '>' +
                '<span class="lp-engine-name">' + escapeHtml(label) + '</span>' +
            '</div>' +
            '<span class="lp-engine-sub">' + escapeHtml(sub) + '</span>' +
        '</label>';
    }

    el.innerHTML =
        /* ── Header ── */
        '<div class="lp-header">' +
            '<div>' +
                '<h1 class="lp-title">Initialize Pipeline</h1>' +
                '<p class="lp-subtitle">Configure engine parameters and start a fresh forensic analysis run.</p>' +
            '</div>' +
            '<span class="lp-status-badge">' +
                '<span class="lp-status-dot' + (isRunning ? ' lp-status-dot--pulse' : '') + '"></span>' +
                (isRunning ? 'Run in progress' : 'Ready for deployment') +
            '</span>' +
        '</div>' +

        /* ── Config grid ── */
        '<div class="lp-config-grid">' +

            /* Left: form */
            '<div class="lp-config-left glass-panel">' +
                '<div class="lp-form-grid">' +

                    /* Profile */
                    '<div class="lp-field">' +
                        '<label class="lp-field-label">Research Profile</label>' +
                        '<div class="lp-dropdown" id="lp-profile-dropdown">' +
                            '<button class="lp-dropdown-trigger" type="button" onclick="toggleLpDropdown()">' +
                                '<span class="lp-dropdown-value" id="lp-profile-label">Prototype Analysis</span>' +
                                '<span class="material-symbols-outlined lp-dropdown-arrow">expand_more</span>' +
                            '</button>' +
                            '<div class="lp-dropdown-menu" id="lp-profile-menu">' +
                                '<div class="lp-dropdown-opt lp-dropdown-opt--selected" onclick="selectLpProfile(\'prototype\', \'Prototype Analysis\', this)">' +
                                    '<span class="material-symbols-outlined lp-dropdown-check">check</span>' +
                                    'Prototype Analysis' +
                                '</div>' +
                                '<div class="lp-dropdown-opt lp-dropdown-opt--disabled">' +
                                    '<span class="material-symbols-outlined lp-dropdown-check" style="opacity:0">check</span>' +
                                    'Full Design Analysis' +
                                    '<span class="lp-dropdown-tag">Soon</span>' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                        '<input type="hidden" id="launch-profile" value="' + escapeAttr(curProfile) + '">' +
                        '<p class="lp-field-hint">Determines algorithmic sensitivity and output resolution.</p>' +
                    '</div>' +

                    /* Engine */
                    '<div class="lp-field">' +
                        '<label class="lp-field-label">ML Image Engine</label>' +
                        '<div class="lp-engine-group">' +
                            engineRadio('stub',          'Fast Stub',  'Low Latency') +
                            engineRadio('inference_api', 'Cloud API',  'High Capacity') +
                            engineRadio('diffusers',     'Local GPU',  'Private / Secure') +
                        '</div>' +
                    '</div>' +

                '</div>' +
            '</div>' +

            /* Right: launch card */
            '<div class="lp-launch-card glass-panel">' +
                '<div>' +
                    '<h4 class="lp-launch-title">Finalize Launch</h4>' +
                    '<p class="lp-launch-desc">Execution will stream pipeline output directly into the log viewer below.</p>' +
                '</div>' +
                '<button class="btn-launch" id="launch-btn" onclick="launchRun()"' + (isRunning ? ' disabled' : '') + '>' +
                    (isRunning
                        ? '<span class="loader lp-loader"></span> Running...'
                        : '<span class="material-symbols-outlined">bolt</span> START RUN') +
                '</button>' +
            '</div>' +

        '</div>' +

        /* ── Terminal viewer ── */
        '<section class="lp-terminal-section">' +
            '<div class="lp-terminal-hdr">' +
                '<div class="lp-terminal-hdr-left">' +
                    '<span class="material-symbols-outlined lp-terminal-icon">terminal</span>' +
                    '<span class="lp-terminal-title">SYSTEM LOG VIEWER</span>' +
                '</div>' +
                '<div class="lp-terminal-hdr-right">' +
                    '<span class="lp-run-indicator' + (isRunning ? ' lp-run-indicator--on' : '') + '">' +
                        '<span class="lp-run-dot' + (isRunning ? ' lp-run-dot--pulse' : '') + '"></span>' +
                        (isRunning ? 'Running' : 'Idle') +
                    '</span>' +
                    '<span class="lp-divider"></span>' +
                    '<span class="badge ' + (isRunning ? 'badge-running' : (STATE.logLines.length ? 'badge-done' : '')) + '" id="launch-badge">' +
                        (isRunning ? '● Running' : (STATE.logLines.length ? '✓ Done' : '— Standby')) +
                    '</span>' +
                '</div>' +
            '</div>' +
            '<div class="lp-terminal-wrap">' +
                '<div class="lp-terminal-chrome">' +
                    '<span class="lp-dot lp-dot--r"></span>' +
                    '<span class="lp-dot lp-dot--y"></span>' +
                    '<span class="lp-dot lp-dot--g"></span>' +
                    '<span class="lp-terminal-label">sh — steganography-pipeline — pts/0</span>' +
                '</div>' +
                '<pre class="log-box lp-log-body" id="launch-log">' + logContent + '</pre>' +
            '</div>' +
        '</section>' +

        /* ── Stats row ── */
        '<div class="lp-stats-row">' +
            '<div class="lp-stat-card">' +
                '<p class="lp-stat-label">Queue Status</p>' +
                '<div class="lp-stat-bottom">' +
                    '<span class="lp-stat-val">' + (isRunning ? '1 Job' : '0 Jobs') + '</span>' +
                    '<span class="lp-stat-note' + (isRunning ? ' lp-stat-note--on' : '') + '">' + (isRunning ? 'Active' : 'Standby') + '</span>' +
                '</div>' +
            '</div>' +
            '<div class="lp-stat-card">' +
                '<p class="lp-stat-label">Engine</p>' +
                '<div class="lp-stat-bottom">' +
                    '<span class="lp-stat-val" id="lp-engine-stat">' + escapeHtml(ENGINE_LABELS[curEngine] || curEngine) + '</span>' +
                    '<span class="lp-stat-note">Selected</span>' +
                '</div>' +
            '</div>' +
            '<div class="lp-stat-card">' +
                '<p class="lp-stat-label">Profile</p>' +
                '<div class="lp-stat-bottom">' +
                    '<span class="lp-stat-val">Default</span>' +
                    '<span class="lp-stat-note">Forensic</span>' +
                '</div>' +
            '</div>' +
        '</div>';

    if (isRunning) attachStream(STATE.job);

    /* Live-update engine stat when radio changes */
    var radios = el.querySelectorAll('input[name="launch-engine"]');
    radios.forEach(function(r) {
        r.addEventListener('change', function() {
            var stat = document.getElementById('lp-engine-stat');
            if (stat) stat.textContent = ENGINE_LABELS[this.value] || this.value;
            STATE.lastEngine = this.value;
            /* update checked styling */
            el.querySelectorAll('.lp-engine-opt').forEach(function(opt) {
                opt.classList.toggle('lp-engine-opt--checked', opt.querySelector('input').value === r.value);
            });
        });
    });
}

function launchRun() {
    var profile = document.getElementById('launch-profile').value;
    var engineEl = document.querySelector('input[name="launch-engine"]:checked');
    var engine = engineEl ? engineEl.value : 'stub';
    STATE.lastProfile = profile;
    STATE.lastEngine = engine;

    var btn = document.getElementById('launch-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="loader lp-loader"></span> Starting…'; }

    api('/api/pipeline/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profile, engine: engine })
    }).then(function (res) {
        if (!res.job_id) throw new Error('No job id returned by backend');
        var job = createJob(res.job_id, profile, engine);
        // Backend pre-assigns the run_id — use it immediately for direct navigation
        if (res.run_id) job.runId = res.run_id;
        closeLaunchPanel();
        attachStream(res.job_id);
        go('run-detail', res.run_id || res.job_id);
    }).catch(function (error) {
        if (btn) { btn.disabled = false; btn.innerHTML = '<span class="material-symbols-outlined">bolt</span> START RUN'; }
        var panel = document.getElementById('sc-panel');
        if (panel) panel.innerHTML = '<div class="sc-error">Launch failed: ' + escapeHtml(error.message) + '</div>';
    });
}

function attachStream(jobId) {
    var job = getJob(jobId);
    if (!job || job.streamSource) return;

    var source = new EventSource('/api/pipeline/stream/' + jobId);
    job.streamSource = source;

    source.onmessage = function (event) {
        job.streamErrors = 0;
        var line = event.data;
        job.logLines.push(line);
        appendLogForJob(jobId, line);

        /* Parse the run directory name from the pipeline header line */
        if (!job.runId) {
            var m = line.match(/Run dir\s*:\s*.*[\/\\]runs[\/\\]([^\s\/\\]+)/);
            if (m) {
                job.runId = m[1];
                /* If we're currently on the job-id placeholder page, redirect to real run */
                if (STATE.page === 'run-detail' && STATE.runId === jobId) {
                    go('run-detail', job.runId);
                }
            }
        }
    };

    source.addEventListener('done', function (event) {
        var exitCode = Number(event.data);
        job.streamSource = null;
        source.close();
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, exitCode === 0 ? '✓ Finished (exit 0)' : '✗ Pipeline exited with code ' + exitCode);

        if (exitCode !== 0) {
            job.failed = true;
            var errLine = job.logLines.slice().reverse().find(function (l) {
                return /error|failed|exception|traceback/i.test(l) && l.trim();
            });
            job.error = errLine || ('Pipeline exited with code ' + exitCode);
        }

        updateTerminalBadgeForJob(jobId, exitCode);

        /* Re-render run detail to pick up final data */
        var targetRunId = job.runId || job.jobId;
        if (STATE.page === 'run-detail' && STATE.runId === targetRunId) {
            setTimeout(function () { if (STATE.page === 'run-detail') render(); }, 2000);
        }
    });

    source.onerror = function () {
        job.streamErrors = (job.streamErrors || 0) + 1;
        if (job.streamErrors >= 5) {
            source.close();
            job.streamSource = null;
            job.failed = true;
            job.error = 'Stream connection lost after repeated failures.';
            updateTerminalBadgeForJob(jobId, -1);
        }
    };
}

function appendLogForJob(jobId, line) {
    if (STATE.page !== 'run-detail') return;
    var job = getJobForRun(STATE.runId);
    if (!job || job.jobId !== jobId) return;
    var box = document.getElementById('run-terminal-log');
    if (!box) return;
    box.textContent += (box.textContent ? '\n' : '') + line;
    box.scrollTop = box.scrollHeight;
}

function updateTerminalBadgeForJob(jobId, exitCode) {
    var job = getJob(jobId);
    if (!job) return;
    var termSection = document.querySelector('.rd-terminal');
    if (!termSection) return;
    var badge = termSection.querySelector('.badge');
    if (!badge) return;
    if (job.killed) {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Killed';
    } else if (exitCode === 0) {
        badge.className = 'badge badge-done'; badge.textContent = '✓ Completed';
    } else {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Failed';
    }
    /* Inject error banner if needed */
    if ((exitCode !== 0 || job.killed) && job.error && STATE.terminalOpen) {
        var body = termSection.querySelector('.rd-terminal-body');
        if (body && !body.querySelector('.rd-error-banner')) {
            var banner = document.createElement('div');
            banner.className = 'rd-error-banner';
            banner.innerHTML = '<span class="material-symbols-outlined">error_outline</span>' +
                '<div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div>';
            body.insertBefore(banner, body.firstChild);
        }
    }
}

function killRun(jobId) {
    var job = getJob(jobId);
    if (!job) return;
    api('/api/pipeline/kill/' + jobId, { method: 'POST' }).then(function () {
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        updateTerminalBadgeForJob(jobId, -1);
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, '✗ Run killed by user.');
        /* Refresh the current view so the "Running" pill and kill button disappear */
        render();
    }).catch(function () {
        /* job may have already finished — still mark locally */
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        render();
    });
}


function clearSearch() {
    STATE.search = '';
    syncSearchInput();
    render();
}

function confirmDeleteRun(runId) {
    var overlay = document.getElementById('confirm-dialog');
    document.getElementById('dialog-title').textContent = 'Delete Run';
    document.getElementById('dialog-message').innerHTML = 'Permanently delete <strong style="font-family:monospace">' + escapeHtml(runId) + '</strong> and all generated artifacts?';
    overlay.classList.add('open');

    document.getElementById('dialog-confirm').onclick = function () {
        overlay.classList.remove('open');
        deleteRun(runId);
    };
    document.getElementById('dialog-cancel').onclick = function () {
        overlay.classList.remove('open');
    };
    overlay.onclick = function (event) {
        if (event.target === overlay) overlay.classList.remove('open');
    };
}

function deleteRun(runId) {
    api('/api/runs/' + encodeURIComponent(runId), { method: 'DELETE' })
        .then(function () {
            if (STATE.page === 'run-detail' && STATE.runId === runId) {
                STATE.runId = null;
            }
            render();
        })
        .catch(function (error) {
            alert('Failed to delete run: ' + error.message);
        });
}

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
}

function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
}

document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
        closeLightbox();
        document.getElementById('confirm-dialog').classList.remove('open');
    }
});

window.addEventListener('beforeunload', function() {
    Object.values(STATE.jobs).forEach(function(job) {
        if (job.streamSource) job.streamSource.close();
    });
});
function toggleTheme() {
    var isLight = document.documentElement.classList.toggle('light');
    var icon = document.getElementById('theme-toggle-icon');
    if (icon) icon.textContent = isLight ? 'dark_mode' : 'light_mode';
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark'); } catch(e) {}
}

function applyStoredTheme() {
    var stored;
    try { stored = localStorage.getItem('theme'); } catch(e) {}
    if (stored === 'light') {
        document.documentElement.classList.add('light');
        var icon = document.getElementById('theme-toggle-icon');
        if (icon) icon.textContent = 'dark_mode';
    }
}

window.addEventListener('DOMContentLoaded', function () {
    applyStoredTheme();
    render();
    // Subscribe to cross-instance sync events from this viewer instance
    var syncSource = new EventSource('/api/events');
    syncSource.addEventListener('refresh', function () {
        // Re-render if on the runs overview so deletes/additions from any instance show up
        if (STATE.page === 'runs') render();
    });
});
