// gallery view
const _predictionsCache = {};

function loadPredictions(runId) {
    if (_predictionsCache[runId]) return Promise.resolve(_predictionsCache[runId]);
    return api(`/api/runs/${encodeURIComponent(runId)}/predictions`).then(rows => {
        _predictionsCache[runId] = rows;
        return rows;
    });
}

function toggleGroupMetrics(groupId, runId) {
    const panel = document.getElementById(`gm-${groupId}`);
    if (!panel) return;
    const isOpen = panel.classList.toggle('gm-open');
    const arrow = document.getElementById(`gm-arrow-${groupId}`);
    if (arrow) arrow.textContent = isOpen ? 'expand_less' : 'expand_more';
    if (!isOpen) return;
    if (panel.dataset.loaded) return;
    panel.dataset.loaded = '1';
    panel.innerHTML = `<div class="gm-loading">${icon('hourglass_empty')} Loading metrics\u2026</div>`;

    loadPredictions(runId).then(allRows => {
        const qualityRows = toArray((STATE._galData || {}).quality);
        const gRows = allRows.filter(r => String(r.group_id) === String(groupId));
        if (!gRows.length) {
            panel.innerHTML = '<div class="gm-empty">No prediction data for this group.</div>';
            return;
        }
        panel.innerHTML = buildGroupMetricsContent(groupId, gRows, qualityRows);
        requestAnimationFrame(() => { drawGroupCharts(groupId, gRows); });
    }).catch(() => {
        panel.innerHTML = '<div class="gm-empty">Failed to load predictions.</div>';
    });
}

function buildGroupMetricsContent(groupId, gRows, qualityRows) {
    const sources = ['real', 'ml_a', 'ml_b'];
    const SOURCE_NAMES = { real: 'Real', ml_a: 'ML-A (SDXL)', ml_b: 'ML-B (FLUX.1)' };
    const detectors = [];
    gRows.forEach(r => { if (detectors.indexOf(r.detector) === -1) detectors.push(r.detector); });

    const tables = sources.map(src => {
        const srcRows = gRows.filter(r => r.source === src);
        if (!srcRows.length) return '';

        const tableRows = detectors.map(det => {
            const rows = srcRows.filter(r => r.detector === det);
            const coverRows = rows.filter(r => String(r.label) === '0');
            const stegoRows = rows.filter(r => String(r.label) === '1');
            const cs = coverRows.length ? coverRows.reduce((s, r) => s + Number(r.score), 0) / coverRows.length : null;
            const ss = stegoRows.length ? stegoRows.reduce((s, r) => s + Number(r.score), 0) / stegoRows.length : null;
            const sep = (cs != null && ss != null) ? Math.abs(ss - cs) : null;
            return `<tr>
                <td class="gm-det">${escapeHtml(fmtDetector(det))}</td>
                <td class="gm-val">${cs != null ? fmtScore(cs) : '\u2014'}</td>
                <td class="gm-val gm-val--stego">${ss != null ? fmtScore(ss) : '\u2014'}</td>
                <td class="gm-val gm-val--sep">${sep != null ? fmtScore(sep) : '\u2014'}</td>
            </tr>`;
        }).join('');

        const qRows = qualityRows.filter(r => String(r.group_id) === String(groupId) && r.source === src);
        let qualityHtml = '';
        if (qRows.length) {
            const avgPsnr = qRows.reduce((s, r) => s + (r.psnr ? Number(r.psnr) : 0), 0) / qRows.length;
            const avgSsim = qRows.reduce((s, r) => s + (r.ssim ? Number(r.ssim) : 0), 0) / qRows.length;
            qualityHtml = `<div class="gm-quality">
                <span>PSNR: <strong>${avgPsnr.toFixed(1)} dB</strong></span>
                <span>SSIM: <strong>${avgSsim.toFixed(4)}</strong></span>
            </div>`;
        }

        return `<div class="gm-source-block">
            <div class="gm-source-label ${src}">${escapeHtml(SOURCE_NAMES[src] || src)}</div>
            ${qualityHtml}
            <table class="gm-table">
                <thead><tr><th>Detector</th><th>Cover</th><th>Stego</th><th>Separation</th></tr></thead>
                <tbody>${tableRows}</tbody>
            </table>
            <div class="gm-bars" id="gm-bars-${groupId}-${src}"></div>
        </div>`;
    }).join('');

    return `<div class="gm-sources-grid">${tables}</div>
        <div class="gm-chart-note">${icon('info')} Each detector is normalized to its own max score across all sources, so bar heights show relative cover\u2009/\u2009stego separation per detector.</div>`;
}

function fmtScore(v) {
    if (v == null || isNaN(v)) return '\u2014';
    const abs = Math.abs(v);
    if (abs === 0) return '0';
    if (abs >= 1000) return v.toFixed(0);
    if (abs >= 1) return v.toFixed(2);
    if (abs >= 0.0001) return v.toFixed(4);
    return v.toExponential(1);
}

function drawGroupCharts(groupId, gRows) {
    const sources = ['real', 'ml_a', 'ml_b'];
    const detectors = [];
    gRows.forEach(r => { if (detectors.indexOf(r.detector) === -1) detectors.push(r.detector); });

    function avgScore(rows) {
        if (!rows.length) return 0;
        return rows.reduce((s, r) => s + Math.abs(Number(r.score) || 0), 0) / rows.length;
    }

    // per-detector max across all sources (for normalization)
    const detMax = {};
    detectors.forEach(det => {
        const detRows = gRows.filter(r => r.detector === det);
        let mx = 0;
        sources.forEach(src => {
            const sr = detRows.filter(r => r.source === src);
            const c = avgScore(sr.filter(r => String(r.label) === '0'));
            const s = avgScore(sr.filter(r => String(r.label) === '1'));
            if (c > mx) mx = c;
            if (s > mx) mx = s;
        });
        detMax[det] = mx || 1;
    });

    sources.forEach(src => {
        const container = document.getElementById(`gm-bars-${groupId}-${src}`);
        if (!container) return;
        const srcRows = gRows.filter(r => r.source === src);
        if (!srcRows.length) return;

        const html = detectors.map(det => {
            const rows = srcRows.filter(r => r.detector === det);
            const cs = avgScore(rows.filter(r => String(r.label) === '0'));
            const ss = avgScore(rows.filter(r => String(r.label) === '1'));
            const mx = detMax[det];
            const cPct = Math.round((cs / mx) * 100);
            const sPct = Math.round((ss / mx) * 100);
            const bothZero = cs === 0 && ss === 0;

            return `<div class="gm-bar-row">
                <div class="gm-bar-label">${escapeHtml(fmtDetector(det))}</div>
                ${bothZero
                    ? '<div class="gm-bar-zero">No signal</div>'
                    : `<div class="gm-bar-tracks">
                        <div class="gm-bar-track"><div class="gm-bar-fill gm-bar--cover" style="width:${cPct}%"></div><span class="gm-bar-val">${fmtScore(cs)}</span></div>
                        <div class="gm-bar-track"><div class="gm-bar-fill gm-bar--stego" style="width:${sPct}%"></div><span class="gm-bar-val">${fmtScore(ss)}</span></div>
                    </div>`}
            </div>`;
        }).join('');

        container.innerHTML = `${html}
            <div class="gm-bar-legend"><span class="gm-bar-fill gm-bar--cover" style="width:10px;height:8px;display:inline-block;border-radius:2px"></span> Cover <span class="gm-bar-fill gm-bar--stego" style="width:10px;height:8px;display:inline-block;border-radius:2px;margin-left:8px"></span> Stego</div>`;
    });
}

function buildCoversTab(data, runId) {
    const covers = data.covers || [];
    STATE._galData = { quality: toArray((data.metrics || {}).quality) };

    if (!covers.length) {
        return '<div class="empty-state"><h3>No cover manifest found</h3><p>This run has not exported grouped cover previews yet.</p></div>';
    }

    const hasPredictions = data.has_results;

    const groups = covers.map(group => {
        const cells = ['real', 'ml_a', 'ml_b'].map(source => {
            const path = (group.sources || {})[source];
            const label = source.replace('_', ' ');
            if (!path) {
                return `<div class="source-cell">
                    <div class="source-label ${source}">${escapeHtml(label)}</div>
                    <div class="image-none">\u2014</div>
                </div>`;
            }
            const url = `/api/image?path=${encodeURIComponent(path)}`;
            return `<div class="source-cell">
                <div class="source-label ${source}">${escapeHtml(label)}</div>
                <img class="cover-thumb" src="${escapeAttr(url)}" loading="lazy" alt="${escapeAttr(label)}" onclick="openLightbox('${escapeAttr(url)}')">
            </div>`;
        }).join('');

        const metricsToggle = hasPredictions
            ? `<button class="gm-toggle" onclick="toggleGroupMetrics('${escapeAttr(group.group_id)}', '${escapeAttr(runId)}')">
                  ${icon('analytics')} <span>Metrics</span>
                  <span class="material-symbols-outlined gm-arrow" id="gm-arrow-${escapeAttr(group.group_id)}">expand_more</span>
              </button>`
            : '';

        return `<div class="group-card">
            <div class="group-head">
                <span class="group-gid">Group ${escapeHtml(group.group_id)}</span>
                ${group.caption ? `<span class="group-caption">${escapeHtml(group.caption)}</span>` : ''}
                ${metricsToggle}
            </div>
            <div class="group-images">${cells}</div>
            ${hasPredictions ? `<div class="gm-panel" id="gm-${escapeAttr(group.group_id)}"></div>` : ''}
        </div>`;
    }).join('');

    return `<div class="section-header"><div><div class="section-title">Cover Images</div><div class="section-subtitle">${covers.length} groups \u00b7 real and generated sources${hasPredictions ? ' \u00b7 click Metrics to see per-image detector scores' : ''}</div></div></div><div class="covers-grid">${groups}</div>`;
}
