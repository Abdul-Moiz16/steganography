function toggleConditionRow(detectorKey) {
    const panel = document.getElementById(`cond-detail-${detectorKey}`);
    if (!panel) return;
    const isOpen = panel.classList.toggle('cond-open');
    const arrow = document.getElementById(`cond-arrow-${detectorKey}`);
    if (arrow) arrow.textContent = isOpen ? 'expand_less' : 'expand_more';
}

function buildConditionsTab(data) {
    const conditionRows = toArray((data.metrics || {}).condition);
    if (!conditionRows.length) {
        return `<div class="empty-state"><h3>No condition metrics</h3><p>This run has no per-condition AUC table yet.</p></div>`;
    }

    STATE._condData = conditionRows;

    const detectors   = uniqueValues(conditionRows, 'detector');
    const methods     = uniqueValues(conditionRows, 'method');
    const levels      = uniqueValues(conditionRows, 'payload_level');
    const encryptions = uniqueValues(conditionRows, 'encryption');
    const columns     = [];
    methods.forEach(method => {
        levels.forEach(level => {
            encryptions.forEach(encryption => {
                columns.push({ method, level, encryption });
            });
        });
    });

    const LEVEL_COLORS = { low: 'var(--green)', medium: 'var(--amber)', high: 'var(--error)' };
    const ENC_COLORS   = { plain: 'var(--secondary)', encrypted: 'var(--primary)' };

    function aucColor(auc) { return auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)'); }
    function fmtPct(v) { return v != null && !isNaN(Number(v)) ? (Number(v) * 100).toFixed(1) + '%' : '\u2014'; }

    const header = `<th class="cond-th-det">Detector</th>` + columns.map(col =>
        `<th style="text-align:center">
            <div style="font-size:10px;text-transform:uppercase;color:var(--secondary-dim);font-weight:700;letter-spacing:0.6px">${escapeHtml(col.method.toUpperCase())}</div>
            <div style="color:${LEVEL_COLORS[col.level] || 'var(--secondary)'};font-weight:600;font-size:11px">${escapeHtml(col.level)}</div>
            <div style="color:${ENC_COLORS[col.encryption] || 'var(--secondary-dim)'};font-size:10px">${escapeHtml(col.encryption)}</div>
        </th>`
    ).join('');

    const body = detectors.map(detector => {
        const detKey = detector.replace(/[^a-z0-9_]/gi, '_');
        const cells = columns.map(col => {
            const row = conditionRows.find(item =>
                item.detector === detector &&
                item.method === col.method &&
                item.payload_level === col.level &&
                item.encryption === col.encryption
            );
            if (!row) return `<td style="text-align:center;color:var(--secondary-dim)">\u2014</td>`;
            const auc   = Number(row.roc_auc || 0);
            const color = aucColor(auc);
            return `<td style="text-align:center">
                <div class="auc-cell" style="justify-content:center">
                    <div class="auc-glow-dot" style="background:${color};box-shadow:0 0 6px ${color}"></div>
                    <span style="font-family:monospace;font-size:12px;font-weight:600;color:${color}">${auc.toFixed(3)}</span>
                </div>
            </td>`;
        }).join('');

        const detailHeader = `<th></th>` + columns.map(col =>
            `<th style="text-align:center;font-size:9px;color:var(--secondary-dim);font-weight:600">${escapeHtml(col.method.toUpperCase())} / ${escapeHtml(col.level)} / ${escapeHtml(col.encryption)}</th>`
        ).join('');

        const metricNames = [
            { key: 'eer', label: 'EER' },
            { key: 'accuracy_at_youden_j', label: 'Accuracy' },
            { key: 'fpr_at_fixed_fnr', label: 'FPR @ 10% FNR' },
            { key: 'n_samples', label: 'Samples' }
        ];

        const detailRows = metricNames.map(m => {
            const metricCells = columns.map(col => {
                const row = conditionRows.find(item =>
                    item.detector === detector &&
                    item.method === col.method &&
                    item.payload_level === col.level &&
                    item.encryption === col.encryption
                );
                if (!row) return `<td style="text-align:center;color:var(--secondary-dim);font-size:11px">\u2014</td>`;
                const val = row[m.key];
                let display;
                if (m.key === 'n_samples') {
                    display = val != null ? String(val) : '\u2014';
                } else {
                    display = fmtPct(val);
                }
                return `<td style="text-align:center;font-family:monospace;font-size:11px;color:var(--secondary)">${escapeHtml(display)}</td>`;
            }).join('');
            return `<tr class="cond-detail-metric"><td style="font-size:10px;font-weight:600;color:var(--secondary-dim);padding-left:24px">${escapeHtml(m.label)}</td>${metricCells}</tr>`;
        }).join('');

        return `<tr class="cond-row" onclick="toggleConditionRow('${detKey}')">
            <td style="font-weight:600;cursor:pointer">
                <span class="material-symbols-outlined cond-arrow" id="cond-arrow-${detKey}">expand_more</span> ${escapeHtml(fmtDetector(detector))}
            </td>${cells}
        </tr>
        <tr class="cond-detail-wrap" id="cond-detail-${detKey}"><td colspan="${columns.length + 1}">
            <table class="cond-detail-table"><tbody>${detailRows}</tbody></table>
        </td></tr>`;
    }).join('');

    return `<div class="card">
        <div class="card-head"><span class="card-title">AUC per Condition</span><span class="card-sub">per detector &middot; method &middot; payload &middot; encryption &middot; click a row for details</span></div>
        <div style="overflow-x:auto"><table class="metrics-table"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>
    </div>`;
}
