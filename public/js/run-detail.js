/* Stego Explorer — Run detail view: header, summary strip, terminal, and overview tab */

async function renderRunDetail(el, runId, token) {
    try {
        var data = await api(`/api/runs/${encodeURIComponent(runId)}/detail`);
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
                `<div class="breadcrumb">` +
                    `<a onclick="go('runs')">Runs</a>` +
                    `<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>` +
                    `<span class="breadcrumb-active">${escapeHtml(runId)}</span>` +
                `</div>` +
                `<div class="page-header">` +
                    `<div>` +
                        `<div class="page-title">${escapeHtml(runId)}</div>` +
                        `<div class="page-subtitle">Pipeline initializing — awaiting output…</div>` +
                    `</div>` +
                    `<button class="btn btn-ghost" onclick="go('runs')">${icon('arrow_back')} Back to Runs</button>` +
                `</div>` +
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
        if (STATE.tab === 'covers') body = buildCoversTab(data, runId);
        if (STATE.tab === 'conditions') body = buildConditionsTab(data);

        el.innerHTML =
            `<div class="breadcrumb">` +
                `<a onclick="go('runs')">Runs</a>` +
                `<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>` +
                `<span class="breadcrumb-active">${escapeHtml(runId)}</span>` +
            `</div>` +
            `<div class="page-header">` +
                `<div>` +
                    `<div class="page-title">${escapeHtml(runId)}</div>` +
                    `<div class="page-subtitle">${escapeHtml(isThisRunActive && !cfg.profile ? (jobForRun ? (jobForRun.profile || 'prototype') + ' · ' + (jobForRun.engine || 'stub') + ' engine · running…' : 'Pipeline running…') : buildRunHeader(cfg, detailStats, runId))}</div>` +
                `</div>` +
                `<button class="btn btn-ghost" onclick="go('runs')">${icon('arrow_back')} Back to Runs</button>` +
            `</div>` +
            (getJobForRun(runId) ? buildTerminalSection(runId) : (isThisRunKilled ? buildKilledBanner(runId) : '')) +
            (!detailStats.detectorCount && !detailStats.coverGroups
                ? ''  /* suppress stat cards when there is no data to show */
                : buildSummaryStrip(cfg, detailStats, data)) +
            ((isThisRunActive || isThisRunKilled) && !data.has_results && !detailStats.coverGroups
                ? ''  /* suppress empty tabs while pipeline is still running or was killed early */
                : buildPrototypeBanner(cfg) + `<div id="tab-body">${body}</div>`);

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
    return `<div class="rd-terminal">` +
        `<div class="rd-terminal-hdr">` +
            `<span>${icon('terminal')} Pipeline Output</span>` +
            `<span class="badge badge-error">✗ Killed</span>` +
        `</div>` +
        `<div class="rd-error-banner">` +
            icon('cancel') +
            `<span class="rd-error-msg">This run was killed before it completed. No pipeline output is available from this viewer instance.</span>` +
        `</div>` +
    `</div>`;
}

function buildTerminalSection(runId) {
    var job = getJobForRun(runId);
    if (!job || !job.logLines.length) return '';

    var isRunning = !!job.streamSource && !job.failed && !job.killed;
    var isOpen = STATE.terminalOpen;
    var logContent = escapeHtml(job.logLines.join('\n'));

    var statusBadge = isRunning
        ? `<span class="badge badge-running">● Live</span>`
        : (job.failed || job.killed)
            ? `<span class="badge badge-error">${job.killed ? '✗ Killed' : '✗ Failed'}</span>`
            : `<span class="badge badge-done">✓ Completed</span>`;

    var killBtn = isRunning
        ? `<button class="rd-kill-btn" onclick="killRun('${escapeAttr(job.jobId)}')" title="Kill this run">` +
              `<span class="material-symbols-outlined">stop_circle</span> Kill` +
          `</button>`
        : '';

    var errorBanner = ((job.failed || job.killed) && job.error)
        ? `<div class="rd-error-banner">` +
              `<span class="material-symbols-outlined">error_outline</span>` +
              `<div><strong>Pipeline error detected</strong><div class="rd-error-msg">${escapeHtml(job.error)}</div></div>` +
          `</div>`
        : '';

    var body = isOpen
        ? `<div class="rd-terminal-body">` +
              errorBanner +
              `<div class="lp-terminal-chrome">` +
                  `<span class="lp-dot lp-dot--r"></span>` +
                  `<span class="lp-dot lp-dot--y"></span>` +
                  `<span class="lp-dot lp-dot--g"></span>` +
                  `<span class="lp-terminal-label">sh — ${escapeHtml(job.runId || job.jobId)} — pts/0</span>` +
              `</div>` +
              `<pre class="log-box lp-log-body" id="run-terminal-log">${logContent}</pre>` +
          `</div>`
        : '';

    return `<div class="rd-terminal">` +
        `<div class="rd-terminal-hdr" onclick="toggleRunTerminal()">` +
            `<div class="rd-terminal-hdr-left">` +
                `<span class="material-symbols-outlined rd-term-icon">terminal</span>` +
                `<span class="rd-terminal-title">Pipeline Output</span>` +
                statusBadge +
            `</div>` +
            `<div class="rd-terminal-hdr-right">` +
                killBtn +
                `<span class="material-symbols-outlined rd-term-chevron">${isOpen ? 'expand_less' : 'expand_more'}</span>` +
            `</div>` +
        `</div>` +
        body +
    `</div>`;
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
            ? `<div class="rd-error-banner"><span class="material-symbols-outlined">error_outline</span><div><strong>Pipeline error detected</strong><div class="rd-error-msg">${escapeHtml(job.error)}</div></div></div>`
            : '';
        var div = document.createElement('div');
        div.className = 'rd-terminal-body';
        div.innerHTML =
            errorBanner +
            `<div class="lp-terminal-chrome">` +
                `<span class="lp-dot lp-dot--r"></span><span class="lp-dot lp-dot--y"></span><span class="lp-dot lp-dot--g"></span>` +
                `<span class="lp-terminal-label">sh — ${escapeHtml(job.runId || job.jobId)} — pts/0</span>` +
            `</div>` +
            `<pre class="log-box lp-log-body" id="run-terminal-log">${escapeHtml(job.logLines.join('\n'))}</pre>`;
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

function buildSummaryStrip(cfg, detailStats, data) {
    var profile = cfg.profile || 'unknown';
    var meta = PROFILE_META[profile] || {};
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta.active_methods || []);
    var payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta.active_payload_levels || []);
    var groups = cfg.n_groups != null ? Number(cfg.n_groups) : (meta.n_groups || 0);
    var isProto = profile === 'prototype';

    // Card 1: Experimental profile
    var profileLabel = isProto ? 'Horizontal Prototype' : 'Full Factorial Design';
    var profileIcon = isProto ? 'science' : 'experiment';
    var designDesc = methods.join(' + ').toUpperCase() + ' \u00b7 ' + payloads.length + ' payload level' + (payloads.length !== 1 ? 's' : '') + ' \u00b7 ' + groups + ' groups';

    // Card 2: Coverage
    var nSources = detailStats.coverGroups ? 3 : 0;
    var nDetectors = detailStats.detectorCount || 0;
    var coverageDesc = nSources + ' sources \u00b7 ' + nDetectors + ' detectors \u00b7 ' + (methods.length * payloads.length * 2) + ' conditions';

    // Card 3: Source Effect (RQ1 — core finding)
    var sourceRows = toArray((data && data.metrics || {}).source);
    var realRows = sourceRows.filter(function (r) { return r.source === 'real' && r.roc_auc && !isNaN(Number(r.roc_auc)); });
    var mlRows = sourceRows.filter(function (r) { return r.source !== 'real' && r.roc_auc && !isNaN(Number(r.roc_auc)); });
    var realAvg = realRows.length ? realRows.reduce(function (s, r) { return s + Number(r.roc_auc); }, 0) / realRows.length : null;
    var mlAvg = mlRows.length ? mlRows.reduce(function (s, r) { return s + Number(r.roc_auc); }, 0) / mlRows.length : null;
    var hasDelta = realAvg != null && mlAvg != null;
    var delta = hasDelta ? mlAvg - realAvg : null;
    var deltaStr = hasDelta ? (delta >= 0 ? '+' : '') + delta.toFixed(3) : '\u2014';
    var deltaCls = hasDelta ? (Math.abs(delta) < 0.01 ? 'sc2-delta--neutral' : (delta > 0 ? 'sc2-delta--pos' : 'sc2-delta--neg')) : '';
    var sourceDesc = hasDelta
        ? `Real ${realAvg.toFixed(3)} vs ML ${mlAvg.toFixed(3)}`
        : 'Awaiting source metrics';

    return `<div class="summary-strip">` +
        `<div class="summary-card-v2">` +
            `<div class="sc2-icon">${icon(profileIcon)}</div>` +
            `<div class="sc2-body">` +
                `<div class="sc2-label">${escapeHtml(profileLabel)}</div>` +
                `<div class="sc2-desc">${escapeHtml(designDesc)}</div>` +
            `</div>` +
        `</div>` +
        `<div class="summary-card-v2">` +
            `<div class="sc2-icon">${icon('grid_view')}</div>` +
            `<div class="sc2-body">` +
                `<div class="sc2-label">Experimental Coverage</div>` +
                `<div class="sc2-desc">${escapeHtml(coverageDesc)}</div>` +
            `</div>` +
        `</div>` +
        `<div class="summary-card-v2 sc2-highlight">` +
            `<div class="sc2-icon">${icon('compare_arrows')}</div>` +
            `<div class="sc2-body">` +
                `<div class="sc2-label">Source Effect (RQ1)</div>` +
                `<div class="sc2-value ${deltaCls}">\u0394 ${deltaStr}</div>` +
                `<div class="sc2-desc">${escapeHtml(sourceDesc)}</div>` +
            `</div>` +
        `</div>` +
    `</div>`;
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
        return `<tr><td>${escapeHtml(pair[0])}</td><td>${escapeHtml(pair[1])}</td></tr>`;
    }).join('');

    return (
        `<div class="detail-grid">` +
            `<div class="card">` +
                `<div class="card-head"><span class="card-title">Run Configuration</span></div>` +
                `<table class="config-table">${rows}</table>` +
            `</div>` +
            `<div class="detail-note">` +
                `<h3>Operational Note</h3>` +
                `<p>` +
                    (detailStats.hasResults
                        ? 'This run already has detector output, so the fastest way to compare it is through the Results and Conditions tabs. Use the overview as the experiment contract for reproducing the same profile later.'
                        : 'This run has been created, but the explorer cannot see detector metrics yet. That usually means the pipeline has not finished, or the run only produced config scaffolding so far.') +
                `</p>` +
            `</div>` +
        `</div>` +
        `<div class="stats">` +
            `<div class="stat"><div class="stat-val">${formatNumber(groups)}</div><div class="stat-lbl">Groups</div></div>` +
            `<div class="stat"><div class="stat-val">${formatNumber(groups * 3)}</div><div class="stat-lbl">Cover Slots</div></div>` +
            `<div class="stat"><div class="stat-val">${formatNumber(conditionCount)}</div><div class="stat-lbl">Conditions</div></div>` +
            `<div class="stat"><div class="stat-val">${formatNumber(methods.length)}</div><div class="stat-lbl">Methods</div></div>` +
            `<div class="stat"><div class="stat-val">${formatNumber(payloads.length)}</div><div class="stat-lbl">Payload Levels</div></div>` +
            `<div class="stat"><div class="stat-val">${formatMaybeNumber(detailStats.bestAuc, 3)}</div><div class="stat-lbl">Best ROC-AUC</div></div>` +
        `</div>`
    );
}
