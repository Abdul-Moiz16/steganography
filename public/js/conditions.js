/* Stego Explorer — Conditions tab: per-condition AUC table with drill-down details */

function toggleConditionRow(detectorKey) {
    var panel = document.getElementById('cond-detail-' + detectorKey);
    if (!panel) return;
    var isOpen = panel.classList.toggle('cond-open');
    var arrow = document.getElementById('cond-arrow-' + detectorKey);
    if (arrow) arrow.textContent = isOpen ? 'expand_less' : 'expand_more';
}

function buildConditionsTab(data) {
    var conditionRows = toArray((data.metrics || {}).condition);
    if (!conditionRows.length) {
        return '<div class="empty-state"><h3>No condition metrics</h3><p>This run has no per-condition AUC table yet.</p></div>';
    }

    // Store for drill-down
    STATE._condData = conditionRows;

    var detectors  = uniqueValues(conditionRows, 'detector');
    var methods    = uniqueValues(conditionRows, 'method');
    var levels     = uniqueValues(conditionRows, 'payload_level');
    var encryptions = uniqueValues(conditionRows, 'encryption');
    var columns    = [];
    methods.forEach(function (method) {
        levels.forEach(function (level) {
            encryptions.forEach(function (encryption) {
                columns.push({ method: method, level: level, encryption: encryption });
            });
        });
    });

    var LEVEL_COLORS = { low: 'var(--green)', medium: 'var(--amber)', high: 'var(--error)' };
    var ENC_COLORS   = { plain: 'var(--secondary)', encrypted: 'var(--primary)' };

    function aucColor(auc) { return auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)'); }
    function fmtPct(v) { return v != null && !isNaN(Number(v)) ? (Number(v) * 100).toFixed(1) + '%' : '\u2014'; }

    var header = '<th class="cond-th-det">Detector</th>' + columns.map(function (col) {
        return '<th style="text-align:center">' +
            '<div style="font-size:10px;text-transform:uppercase;color:var(--secondary-dim);font-weight:700;letter-spacing:0.6px">' + escapeHtml(col.method.toUpperCase()) + '</div>' +
            '<div style="color:' + (LEVEL_COLORS[col.level] || 'var(--secondary)') + ';font-weight:600;font-size:11px">' + escapeHtml(col.level) + '</div>' +
            '<div style="color:' + (ENC_COLORS[col.encryption] || 'var(--secondary-dim)') + ';font-size:10px">' + escapeHtml(col.encryption) + '</div>' +
        '</th>';
    }).join('');

    var body = detectors.map(function (detector) {
        var detKey = detector.replace(/[^a-z0-9_]/gi, '_');
        var cells = columns.map(function (col) {
            var row = conditionRows.find(function (item) {
                return item.detector === detector &&
                    item.method === col.method &&
                    item.payload_level === col.level &&
                    item.encryption === col.encryption;
            });
            if (!row) return '<td style="text-align:center;color:var(--secondary-dim)">\u2014</td>';
            var auc   = Number(row.roc_auc || 0);
            var color = aucColor(auc);
            return '<td style="text-align:center">' +
                '<div class="auc-cell" style="justify-content:center">' +
                    '<div class="auc-glow-dot" style="background:' + color + ';box-shadow:0 0 6px ' + color + '"></div>' +
                    '<span style="font-family:monospace;font-size:12px;font-weight:600;color:' + color + '">' + auc.toFixed(3) + '</span>' +
                '</div>' +
            '</td>';
        }).join('');

        // Build expanded detail rows for this detector
        var detailHeader = '<th></th>' + columns.map(function (col) {
            return '<th style="text-align:center;font-size:9px;color:var(--secondary-dim);font-weight:600">' +
                escapeHtml(col.method.toUpperCase()) + ' / ' + escapeHtml(col.level) + ' / ' + escapeHtml(col.encryption) + '</th>';
        }).join('');

        var metricNames = [
            { key: 'eer', label: 'EER' },
            { key: 'accuracy_at_youden_j', label: 'Accuracy' },
            { key: 'fpr_at_fixed_fnr', label: 'FPR @ 10% FNR' },
            { key: 'n_samples', label: 'Samples' }
        ];

        var detailRows = metricNames.map(function (m) {
            var metricCells = columns.map(function (col) {
                var row = conditionRows.find(function (item) {
                    return item.detector === detector &&
                        item.method === col.method &&
                        item.payload_level === col.level &&
                        item.encryption === col.encryption;
                });
                if (!row) return '<td style="text-align:center;color:var(--secondary-dim);font-size:11px">\u2014</td>';
                var val = row[m.key];
                var display;
                if (m.key === 'n_samples') {
                    display = val != null ? String(val) : '\u2014';
                } else {
                    display = fmtPct(val);
                }
                return '<td style="text-align:center;font-family:monospace;font-size:11px;color:var(--secondary)">' + escapeHtml(display) + '</td>';
            }).join('');
            return '<tr class="cond-detail-metric"><td style="font-size:10px;font-weight:600;color:var(--secondary-dim);padding-left:24px">' + escapeHtml(m.label) + '</td>' + metricCells + '</tr>';
        }).join('');

        return '<tr class="cond-row" onclick="toggleConditionRow(\'' + detKey + '\')">' +
            '<td style="font-weight:600;cursor:pointer">' +
                '<span class="material-symbols-outlined cond-arrow" id="cond-arrow-' + detKey + '">expand_more</span> ' +
                escapeHtml(fmtDetector(detector)) +
            '</td>' + cells +
        '</tr>' +
        '<tr class="cond-detail-wrap" id="cond-detail-' + detKey + '"><td colspan="' + (columns.length + 1) + '">' +
            '<table class="cond-detail-table"><tbody>' + detailRows + '</tbody></table>' +
        '</td></tr>';
    }).join('');

    return '<div class="card">' +
        '<div class="card-head"><span class="card-title">AUC per Condition</span><span class="card-sub">per detector &middot; method &middot; payload &middot; encryption &middot; click a row for details</span></div>' +
        '<div style="overflow-x:auto"><table class="metrics-table"><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div>' +
    '</div>';
}
