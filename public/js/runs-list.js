// runs list view
async function renderRunsList(el, token) {
    try {
        const runs = await api('/api/runs');
        if (token !== STATE.renderToken) return;

        if (!runs.length) {
            el.innerHTML =
                `<div class="empty-state">
                    <h3>No runs yet</h3>
                    <p>Launch a prototype run to seed the explorer with pipeline output.</p>
                    <div class="empty-actions">
                        <button class="btn btn-primary" onclick="openLaunchPanel()">${icon('add')} New Run</button>
                    </div>
                </div>` +
                `<edu-carousel></edu-carousel>`;
            return;
        }

        const filtered = filterRunCollection(runs, STATE.search);
        const stats = summarizeRuns(runs);
        const activity = buildActivityFeed(runs);
        const tip = buildRunsTip(runs, stats);
        const rows = filtered.map(buildRunRow).join('');

        el.innerHTML =
            `<div class="breadcrumb">
                <span>Explorer</span>
                <span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>
                <span class="breadcrumb-active">Pipeline Runs</span>
            </div>
            <div class="page-header">
                <div>
                    <div class="page-title">Runs Overview</div>
                    <div class="page-subtitle">${escapeHtml(buildRunsSubtitle(filtered.length, runs.length, STATE.search))}</div>
                </div>
                <button class="btn btn-primary" onclick="openLaunchPanel()">${icon('add')} New Run</button>
            </div>
            <div class="stats-bento">
                <bento-card label="Largest Source Effect" value="${stats.largestDelta != null ? `\u0394 ${stats.largestDelta >= 0 ? '+' : ''}${stats.largestDelta.toFixed(3)}` : '\u2014'}" value-class="primary" sub="${escapeAttr(stats.largestDeltaLabel)}"></bento-card>
                <bento-card label="Tracked Runs" value="${formatNumber(runs.length)}" sub="${formatNumber(stats.completedRuns)} with metrics"></bento-card>
                <bento-card label="Processed Covers" value="${formatNumber(stats.totalImages)}" sub="${formatNumber(stats.totalGroups)} grouped specimens"></bento-card>
                <bento-card label="Detector Evaluations" value="${formatNumber(stats.totalDetectors)}" sub="${escapeAttr(stats.coverageLabel)}"></bento-card>
            </div>` +
            buildRunsTable(filtered, runs.length, rows) +
            `<div class="panels-row">
                <div class="glass-panel">
                    <div class="glass-panel-head"><div class="glass-panel-title">Recent Activity</div></div>
                    <div class="glass-panel-body"><div class="activity-feed">${activity}</div></div>
                </div>
                <div class="glass-panel">
                    <div class="glass-panel-head"><div class="glass-panel-title">Analysis Tip</div></div>
                    <div class="glass-panel-body">${tip}</div>
                </div>
            </div>
            <edu-carousel></edu-carousel>`;
    } catch (error) {
        if (token !== STATE.renderToken) return;
        el.innerHTML = renderError(error.message, 'Retry', 'render()');
    }
}

function filterRunCollection(runs, search) {
    const query = (search || '').trim().toLowerCase();
    if (!query) return runs;
    return runs.filter(run => {
        const cfg = run.config || {};
        const haystack = [
            run.id, cfg.profile,
            toArray(cfg.active_methods).join(' '),
            toArray(cfg.active_payload_levels).join(' '),
            cfg.timestamp
        ].join(' ').toLowerCase();
        return haystack.indexOf(query) !== -1;
    });
}

function summarizeRuns(runs) {
    const summary = {
        largestDelta: null,
        largestDeltaLabel: 'Awaiting source metrics',
        completedRuns: 0,
        totalImages: 0,
        totalGroups: 0,
        totalDetectors: 0,
        coverageLabel: 'No detector metrics yet'
    };
    runs.forEach(run => {
        const cfg = run.config || {};
        const groups = Number(cfg.n_groups || 0);
        summary.totalGroups += groups;
        summary.totalImages += groups * 3;
        summary.totalDetectors += Number(run.n_detectors || 0);
        if (run.has_results) summary.completedRuns += 1;
        if (run.source_delta != null) {
            const absDelta = Math.abs(Number(run.source_delta));
            if (summary.largestDelta == null || absDelta > Math.abs(summary.largestDelta)) {
                summary.largestDelta = Number(run.source_delta);
                summary.largestDeltaLabel = run.id;
            }
        }
    });
    if (summary.totalDetectors) {
        summary.coverageLabel = formatNumber(summary.totalDetectors) + ' total detector rows';
    }
    return summary;
}

function buildRunsSubtitle(filteredCount, totalCount, search) {
    if (search) {
        return `Showing ${filteredCount} of ${totalCount} runs for "${search}".`;
    }
    return `${totalCount} experiment run${totalCount === 1 ? '' : 's'} currently available in the local explorer.`;
}

function buildRunRow(run) {
    const cfg = run.config || {};
    const isActive = isRunActive(run.id) || !!run.is_active;
    const isKilled = !isActive && (run.is_killed || (getJobForRun(run.id) || {}).killed);
    const activeJob = getJobForRun(run.id);
    // parse profile from run ID as last resort (format: {profile}_{timestamp}_p{port})
    const profileFromId = Object.keys(PROFILE_META).find(k => run.id.startsWith(k)) || null;
    const profile = cfg.profile || (activeJob && activeJob.profile) || profileFromId || (isActive ? '\u2026' : 'unconfigured');
    // fallback to static profile metadata when config.json not yet written
    const meta = PROFILE_META[profile] || null;
    const methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    const levels = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    const nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    const nDetectors = run.n_detectors || (meta ? meta.n_detectors : 0);
    const runStatus = isActive
        ? statusPill('Running', 'running')
        : isKilled
            ? statusPill('Killed', 'error')
            : !run.has_results
                ? statusPill('Pending', 'pending')
                : statusPill('Ready', 'ready');
    let deltaCell;
    if (run.source_delta != null) {
        const dv = Number(run.source_delta);
        const dcls = Math.abs(dv) < 0.01 ? 'auc-mid' : (dv > 0 ? 'auc-high' : 'auc-low');
        deltaCell = `<span class="auc-badge ${dcls}">\u0394 ${dv >= 0 ? '+' : ''}${dv.toFixed(3)}</span>`;
    } else {
        deltaCell = `<div class="no-results">${icon('cloud_off')}<span>No Data</span></div>`;
    }

    const rowClass = isActive ? 'row-active' : (run.has_results ? '' : 'row-dimmed');
    return (
        `<tr${rowClass ? ` class="${rowClass}"` : ''} style="cursor:pointer" onclick="go('run-detail', '${escapeAttr(run.id)}')">
            <td>
                <div class="run-name">
                    ${isActive ? '<span class="run-live-dot"></span>' : ''}
                    <strong>${escapeHtml(run.id)}</strong>
                    <div class="run-sub-id">${escapeHtml(cfg.timestamp || 'local run artifact')}</div>
                </div>
            </td>
            <td><span class="profile-tag${isActive ? ' profile-tag--dim' : ''}">${escapeHtml(profile)}</span></td>
            <td><span class="cell-mono">${escapeHtml(nGroups != null ? nGroups : '\u2014')}</span></td>
            <td><span class="cell-dim">${escapeHtml(methods.length ? methods.join(', ') : '\u2014')}</span></td>
            <td><span class="cell-dim">${escapeHtml(levels.length ? levels.join(', ') : '\u2014')}</span></td>
            <td><div style="display:flex;align-items:center;gap:6px">${icon('security')}<span class="cell-mono">${escapeHtml(nDetectors)}</span></div></td>
            <td>${deltaCell}</td>
            <td>${runStatus}</td>
            <td>
                <button class="btn-icon" onclick="event.stopPropagation();confirmDeleteRun('${escapeAttr(run.id)}')" title="Delete run">
                    ${icon('delete')}
                </button>
            </td>
        </tr>`
    );
}

function buildRunsTable(filteredRuns, totalRuns, rows) {
    if (!filteredRuns.length) {
        return `<div class="data-table-wrap"><div class="empty-state"><h3>No runs match this search</h3><p>Try a run id, profile name, method, or payload level.</p><div class="empty-actions"><button class="btn btn-ghost" onclick="clearSearch()">Clear Search</button></div></div></div>`;
    }
    return (
        `<div class="data-table-wrap">
            <div style="overflow-x:auto">
                <table class="data-table">
                    <thead><tr>
                        <th>Run Name</th>
                        <th>Profile</th>
                        <th>Groups</th>
                        <th>Methods</th>
                        <th>Payloads</th>
                        <th>Detectors</th>
                        <th>Source \u0394</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <div class="table-footer">
                <span>Displaying ${filteredRuns.length} of ${totalRuns} runs</span>
                <div class="table-footer-actions">
                    <span class="inline-note">${icon('tips_and_updates')}<strong>Tip:</strong> click a row to inspect run detail.</span>
                </div>
            </div>
        </div>`
    );
}

function buildActivityFeed(runs) {
    return runs.slice(0, 4).map((run, index) => {
        const tone = run.source_delta == null ? (run.has_results ? 'red' : 'amber') : (index === 0 ? 'blue' : 'green');
        const text = run.source_delta == null
            ? (run.has_results ? `Run <strong>${escapeHtml(run.id)}</strong> produced partial metrics that need review.` : `Run <strong>${escapeHtml(run.id)}</strong> has been created but has not produced detector metrics yet.`)
            : `Run <strong>${escapeHtml(run.id)}</strong> completed with source effect \u0394 <strong>${escapeHtml((Number(run.source_delta) >= 0 ? '+' : '') + Number(run.source_delta).toFixed(3))}</strong>.`;
        return `<div class="activity-item">
            <div class="activity-dot ${tone}"></div>
            <div><div class="activity-text">${text}</div><div class="activity-time">${escapeHtml((run.config || {}).timestamp || 'local artifact')}</div></div>
        </div>`;
    }).join('');
}

function buildRunsTip(runs, stats) {
    const bestRun = runs.find(run => stats.bestRunLabel === run.id);
    const bestProfile = bestRun && bestRun.config && bestRun.config.profile ? bestRun.config.profile : 'prototype';
    const payloads = bestRun && bestRun.config ? toArray(bestRun.config.active_payload_levels) : [];
    return (
        `<div class="tip-icon">${icon('info')}</div>
        <div class="tip-title">Best-performing configuration</div>
        <div class="tip-text">
            Right now the strongest local run is <strong>${escapeHtml(stats.bestRunLabel)}</strong>.
            If you want the redesign to guide analysis, start by comparing new runs against the <strong>${escapeHtml(bestProfile)}</strong> profile${payloads.length ? ` across payloads ${escapeHtml(payloads.join(', '))}.` : '.'}
        </div>`
    );
}
