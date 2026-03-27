async function renderRunDetail(el, runId, token) {
    try {
        const data = await api(`/api/runs/${encodeURIComponent(runId)}/detail`);
        if (token !== STATE.renderToken) return;
        const isThisRunActive = isRunActive(runId) || !!(data && data.is_active);
        const isThisRunKilled = !isThisRunActive && !!(data && data.is_killed || (getJobForRun(runId) || {}).killed);
        const jobForRun = getJobForRun(runId);

        if (!data || !Object.keys(data).length) {
            if (!isThisRunActive) {
                hideSidebar();
                el.innerHTML = renderError('The selected run could not be found.', 'Back to Runs', 'go(\'runs\')');
                return;
            }
            // run just started -- show terminal-only initializing state
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

        const cfg = data.config || {};
        const detailStats = summarizeRunDetail(data);
        showSidebar(runId, STATE.tab);

        let body = '';
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
                ? ''
                : buildSummaryStrip(cfg, detailStats, data)) +
            ((isThisRunActive || isThisRunKilled) && !data.has_results && !detailStats.coverGroups
                ? ''
                : buildPrototypeBanner(cfg) + `<div id="tab-body">${body}</div>`);

        if (isThisRunActive && jobForRun) attachStream(jobForRun.jobId);
        if (STATE.tab === 'results' && data.has_results) {
            requestAnimationFrame(() => { drawAllCharts(data); });
        }
    } catch (error) {
        if (token !== STATE.renderToken) return;
        hideSidebar();
        el.innerHTML = renderError(error.message, 'Back to Runs', 'go(\'runs\')');
    }
}

function buildTerminalSection(runId) {
    return `<terminal-panel run-id="${escapeAttr(runId)}"></terminal-panel>`;
}

function buildKilledBanner(runId) {
    return buildTerminalSection(runId);
}

function toggleRunTerminal() {
    const panel = document.querySelector('terminal-panel');
    if (panel) panel.toggle();
}

function summarizeRunDetail(data) {
    const detectorRows = toArray((data.metrics || {}).detector);
    const covers = toArray(data.covers);
    let bestRow = null;
    let sampleTotal = 0;
    detectorRows.forEach(row => {
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
    const profileFromId = runId ? (Object.keys(PROFILE_META).find(k => runId.startsWith(k)) || null) : null;
    const profile = cfg.profile || profileFromId || 'unconfigured profile';
    const meta = PROFILE_META[profile] || null;
    const methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    const payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    const nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    const groups = nGroups != null ? nGroups + ' groups' : 'group count unavailable';
    return [
        profile, groups,
        methods.length ? methods.join(', ') : 'no methods listed',
        payloads.length ? 'payloads ' + payloads.join(', ') : 'no payload levels listed',
        detailStats.hasResults ? 'metrics ready' : 'metrics pending'
    ].join(' · ');
}

function buildSummaryStrip(cfg, detailStats, data) {
    const profile = cfg.profile || 'unknown';
    const meta = PROFILE_META[profile] || {};
    const methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta.active_methods || []);
    const payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta.active_payload_levels || []);
    const groups = cfg.n_groups != null ? Number(cfg.n_groups) : (meta.n_groups || 0);
    const isProto = profile === 'prototype';

    const profileLabel = isProto ? 'Horizontal Prototype' : 'Full Factorial Design';
    const profileIcon = isProto ? 'science' : 'experiment';
    const designDesc = methods.join(' + ').toUpperCase() + ' \u00b7 ' + payloads.length + ' payload level' + (payloads.length !== 1 ? 's' : '') + ' \u00b7 ' + groups + ' groups';

    const nSources = detailStats.coverGroups ? 3 : 0;
    const nDetectors = detailStats.detectorCount || 0;
    const coverageDesc = nSources + ' sources \u00b7 ' + nDetectors + ' detectors \u00b7 ' + (methods.length * payloads.length * 2) + ' conditions';

    // source effect (RQ1)
    const sourceRows = toArray((data && data.metrics || {}).source);
    const realRows = sourceRows.filter(r => r.source === 'real' && r.roc_auc && !isNaN(Number(r.roc_auc)));
    const mlRows = sourceRows.filter(r => r.source !== 'real' && r.roc_auc && !isNaN(Number(r.roc_auc)));
    const realAvg = realRows.length ? realRows.reduce((s, r) => s + Number(r.roc_auc), 0) / realRows.length : null;
    const mlAvg = mlRows.length ? mlRows.reduce((s, r) => s + Number(r.roc_auc), 0) / mlRows.length : null;
    const hasDelta = realAvg != null && mlAvg != null;
    const delta = hasDelta ? mlAvg - realAvg : null;
    const deltaStr = hasDelta ? (delta >= 0 ? '+' : '') + delta.toFixed(3) : '\u2014';
    const deltaCls = hasDelta ? (Math.abs(delta) < 0.01 ? 'sc2-delta--neutral' : (delta > 0 ? 'sc2-delta--pos' : 'sc2-delta--neg')) : '';
    const sourceDesc = hasDelta
        ? `Real ${realAvg.toFixed(3)} vs ML ${mlAvg.toFixed(3)}`
        : 'Awaiting source metrics';

    return `<div class="summary-strip">` +
        `<summary-card icon="${escapeAttr(profileIcon)}" label="${escapeAttr(profileLabel)}" desc="${escapeAttr(designDesc)}"></summary-card>` +
        `<summary-card icon="grid_view" label="Experimental Coverage" desc="${escapeAttr(coverageDesc)}"></summary-card>` +
        `<summary-card icon="compare_arrows" label="Source Effect (RQ1)" value="\u0394 ${deltaStr}" value-class="${deltaCls}" desc="${escapeAttr(sourceDesc)}" highlight></summary-card>` +
    `</div>`;
}

function buildOverviewTab(cfg, detailStats, runId) {
    const profileFromId = runId ? (Object.keys(PROFILE_META).find(k => runId.startsWith(k)) || null) : null;
    const profile = cfg.profile || profileFromId || null;
    const meta = PROFILE_META[profile] || null;
    const groups = cfg.n_groups != null ? Number(cfg.n_groups) : (meta ? meta.n_groups : 0);
    const methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    const payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    const conditionCount = methods.length * payloads.length * 2;
    const fillRates = Object.keys(cfg.payload_fill_rates || {}).length
        ? Object.keys(cfg.payload_fill_rates).map(key => key + '=' + cfg.payload_fill_rates[key]).join(', ')
        : '\u2014';

    const rows = [
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
    ].map(pair => `<tr><td>${escapeHtml(pair[0])}</td><td>${escapeHtml(pair[1])}</td></tr>`).join('');

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
