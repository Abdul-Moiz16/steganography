/* ═══════════════════════════════════════════════════════════════════════════
   Stego Explorer — Application logic
   SPA router, page renderers, API helpers, lightbox, pipeline launcher.
   ═══════════════════════════════════════════════════════════════════════════ */


/* ── State & constants ──────────────────────────────────────────────────── */

var STATE = {
    page: 'runs',
    runId: null,
    tab: 'overview',
    job: null,
    logLines: []
};

var SOURCE_COLORS     = { real: '#5BA3D9', ml_a: '#F06225', ml_b: '#34D399' };
var ENCRYPTION_COLORS = { plain: '#5BA3D9', encrypted: '#A78BFA' };
var DETECTOR_PALETTE  = ['#F06225', '#5BA3D9', '#34D399', '#A78BFA', '#FBBF24', '#F87171'];


/* ── API helper ─────────────────────────────────────────────────────────── */

async function api(url) {
    var response = await fetch(url);
    return response.json();
}


/* ── Router ─────────────────────────────────────────────────────────────── */

function go(page, runId) {
    STATE.page = page;
    STATE.runId = runId || null;
    STATE.tab = 'overview';
    render();

    ['runs', 'launch'].forEach(function (key) {
        var link = document.getElementById('nav-' + key);
        if (link) {
            var activePage = page === 'run-detail' ? 'runs' : page;
            link.classList.toggle('active', activePage === key);
        }
    });
}

function switchTab(tabName) {
    STATE.tab = tabName;
    render();
}


/* ── Main render ────────────────────────────────────────────────────────── */

function render() {
    var container = document.getElementById('main');

    if (STATE.page === 'runs')       { renderRunsList(container);                    return; }
    if (STATE.page === 'run-detail') { renderRunDetail(container, STATE.runId);      return; }
    if (STATE.page === 'launch')     { renderLaunchPage(container);                  return; }
}


/* ── Runs list page ─────────────────────────────────────────────────────── */

async function renderRunsList(el) {
    el.innerHTML = '<div class="loading-page"><div class="loader"></div></div>';
    var runs = await api('/api/runs');

    if (!runs.length) {
        el.innerHTML =
            '<div class="empty-state">' +
                '<h3>No runs yet</h3>' +
                '<p>Launch a prototype run to get started.</p><br>' +
                '<button class="btn btn-primary" onclick="go(\'launch\')">Launch Run</button>' +
            '</div>';
        return;
    }

    var cards = runs.map(function (r) { return buildRunCard(r); }).join('');

    el.innerHTML =
        '<div class="section-header">' +
            '<div>' +
                '<div class="section-title">Pipeline Runs</div>' +
                '<div class="section-subtitle">' +
                    runs.length + ' run' + (runs.length !== 1 ? 's' : '') +
                '</div>' +
            '</div>' +
            '<button class="btn btn-primary btn-sm" onclick="go(\'launch\')">+ New Run</button>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;gap:10px">' + cards + '</div>';
}

function buildRunCard(r) {
    var cfg     = r.config || {};
    var auc     = r.best_auc != null ? r.best_auc.toFixed(3) : null;
    var profile = cfg.profile || r.id.split('_')[0] || '?';
    var nGroups = cfg.n_groups || '?';
    var methods = (cfg.active_methods || []).join(', ') || '?';
    var levels  = (cfg.active_payload_levels || []).join(', ') || '?';

    var aucHtml = auc
        ? '<div class="run-auc">' + auc + '<small>best AUC</small></div>'
        : '<div style="color:var(--text-3);font-size:12px;font-family:var(--mono)">No results</div>';

    return (
        '<div class="run-card" onclick="go(\'run-detail\',\'' + r.id + '\')">' +
            '<div class="dot ' + (r.has_results ? 'dot-ok' : 'dot-no') + '"></div>' +
            '<div class="run-info">' +
                '<div class="run-id">' + r.id + '</div>' +
                '<div class="run-meta">' +
                    '<span>' + profile + ' &middot; ' + nGroups + ' groups</span>' +
                    '<span>methods: ' + methods + '</span>' +
                    '<span>payload: ' + levels + '</span>' +
                    (r.n_detectors ? '<span>' + r.n_detectors + ' detectors scored</span>' : '') +
                '</div>' +
            '</div>' +
            aucHtml +
            '<button class="run-delete" onclick="event.stopPropagation(); confirmDeleteRun(\'' + r.id + '\')" title="Delete run">' +
                '&times;' +
            '</button>' +
        '</div>'
    );
}


/* ── Run detail page ────────────────────────────────────────────────────── */

async function renderRunDetail(el, runId) {
    el.innerHTML = '<div class="loading-page"><div class="loader"></div></div>';
    var data = await api('/api/runs/' + runId + '/detail');

    var cfg     = data.config || {};
    var methods = (cfg.active_methods || []).join(', ') || '?';
    var levels  = (cfg.active_payload_levels || []).join(', ') || '?';

    var tabNames = ['overview', 'results', 'covers'];
    if (data.has_results) {
        tabNames.push('conditions');
    }

    var tabsHtml = '<div class="tabs">' + tabNames.map(function (t) {
        var label = t.charAt(0).toUpperCase() + t.slice(1);
        var cls   = STATE.tab === t ? 'tab active' : 'tab';
        return '<div class="' + cls + '" onclick="switchTab(\'' + t + '\')">' + label + '</div>';
    }).join('') + '</div>';

    var body = '';
    if (STATE.tab === 'overview')   body = buildOverviewTab(cfg);
    if (STATE.tab === 'results')    body = buildResultsTab(data);
    if (STATE.tab === 'covers')     body = buildCoversTab(data.covers);
    if (STATE.tab === 'conditions') body = buildConditionsTab(data);

    el.innerHTML =
        '<div class="page-header">' +
            '<div class="back-btn" onclick="go(\'runs\')">&larr; back to runs</div>' +
            '<div class="page-title">' + runId + '</div>' +
            '<div class="page-subtitle">' +
                (cfg.profile || '?') + ' &middot; ' +
                (cfg.n_groups || '?') + ' groups &middot; methods: ' +
                methods + ' &middot; levels: ' + levels +
            '</div>' +
        '</div>' +
        tabsHtml +
        '<div id="tab-body">' + body + '</div>';

    if (STATE.tab === 'results' && data.has_results) {
        requestAnimationFrame(function () { drawAllCharts(data); });
    }
}


/* ── Overview tab ───────────────────────────────────────────────────────── */

function buildOverviewTab(cfg) {
    var nGroups    = cfg.n_groups || 0;
    var methods    = cfg.active_methods || [];
    var levels     = cfg.active_payload_levels || [];
    var nConditions = 3 * methods.length * levels.length * 2;

    var fillRates = Object.entries(cfg.payload_fill_rates || {})
        .map(function (pair) { return pair[0] + '=' + pair[1]; })
        .join(', ') || '\u2014';

    var configRows = [
        ['Profile',           cfg.profile || '\u2014'],
        ['Groups per run',    nGroups],
        ['Active methods',    methods.join(', ') || '\u2014'],
        ['Payload levels',    levels.join(', ') || '\u2014'],
        ['Fill rates',        fillRates],
        ['Image size',        (cfg.image_size || []).join('\u00d7') || '\u2014'],
        ['JPEG quality',      cfg.jpeg_quality != null ? cfg.jpeg_quality : '\u2014'],
        ['Cover seed',        cfg.cover_seed != null ? cfg.cover_seed : '\u2014'],
        ['Payload seed',      cfg.payload_seed != null ? cfg.payload_seed : '\u2014'],
        ['Timestamp',         cfg.timestamp || '\u2014'],
    ];

    var tableRows = configRows.map(function (pair) {
        return '<tr><td>' + pair[0] + '</td><td>' + pair[1] + '</td></tr>';
    }).join('');

    return (
        '<div class="stats">' +
            '<div class="stat"><div class="stat-val">' + nGroups + '</div><div class="stat-lbl">Groups</div></div>' +
            '<div class="stat"><div class="stat-val">' + (nGroups * 3) + '</div><div class="stat-lbl">Cover Images</div></div>' +
            '<div class="stat"><div class="stat-val">' + nConditions + '</div><div class="stat-lbl">Conditions</div></div>' +
            '<div class="stat"><div class="stat-val">' + (nGroups * nConditions) + '</div><div class="stat-lbl">Stego Images</div></div>' +
            '<div class="stat"><div class="stat-val">' + methods.length + '</div><div class="stat-lbl">Methods</div></div>' +
            '<div class="stat"><div class="stat-val">' + (levels.length * 2) + '</div><div class="stat-lbl">Payload\u00d7Enc</div></div>' +
        '</div>' +
        '<div class="card">' +
            '<div class="card-head"><span class="card-title">Run Configuration</span></div>' +
            '<table class="config-table">' + tableRows + '</table>' +
        '</div>'
    );
}


/* ── Results tab ────────────────────────────────────────────────────────── */

function buildResultsTab(data) {
    if (!data.has_results) {
        return '<div class="empty-state"><h3>No results yet</h3>' +
               '<p>Run the pipeline with --execute-detectors to generate metrics.</p></div>';
    }

    var detMetrics = data.metrics.detector || [];

    var tableRows = detMetrics.map(function (r) {
        var auc = +(r.roc_auc || 0);
        var eer = +(r.eer || 0);
        var acc = +(r.accuracy_at_youden_j || 0);
        var color = auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--red)');

        return (
            '<tr>' +
                '<td style="font-weight:600">' + r.detector + '</td>' +
                '<td><div class="auc-inline">' +
                    '<div class="auc-fill" style="width:' + Math.round(auc * 100) + 'px;background:' + color + '"></div>' +
                    '<span class="auc-num" style="color:' + color + '">' + auc.toFixed(3) + '</span>' +
                '</div></td>' +
                '<td style="color:var(--text-3);font-family:var(--mono);font-size:12px">' + (eer * 100).toFixed(1) + '%</td>' +
                '<td style="color:var(--text-3);font-family:var(--mono);font-size:12px">' + (acc * 100).toFixed(1) + '%</td>' +
                '<td style="color:var(--text-3);font-family:var(--mono);font-size:12px">' + r.n_samples + '</td>' +
            '</tr>'
        );
    }).join('');

    return (
        '<div class="charts-row">' +
            '<div class="chart-box"><div class="chart-title">AUC by Detector</div>' +
                '<canvas id="chart-detector" height="200"></canvas></div>' +
            '<div class="chart-box"><div class="chart-title">AUC by Source</div>' +
                '<canvas id="chart-source" height="200"></canvas></div>' +
        '</div>' +
        '<div class="charts-full">' +
            '<div class="chart-box"><div class="chart-title">AUC by Encryption (averaged over conditions)</div>' +
                '<canvas id="chart-encryption" height="180"></canvas></div>' +
        '</div>' +
        '<div class="card" style="margin-top:10px">' +
            '<div class="card-head"><span class="card-title">Detector Performance Summary</span></div>' +
            '<div style="overflow-x:auto">' +
                '<table class="metrics-table"><thead><tr>' +
                    '<th>Detector</th><th>ROC-AUC</th><th>EER</th><th>Accuracy</th><th>Samples</th>' +
                '</tr></thead><tbody>' + tableRows + '</tbody></table>' +
            '</div>' +
        '</div>'
    );
}


/* ── Chart rendering ────────────────────────────────────────────────────── */

function drawAllCharts(data) {
    var detMetrics  = data.metrics.detector || [];
    var srcMetrics  = data.metrics.source || [];
    var condMetrics = data.metrics.condition || [];

    var canvasDet = document.getElementById('chart-detector');
    if (canvasDet && detMetrics.length) {
        drawHorizontalBars(
            canvasDet,
            detMetrics.map(function (r) { return r.detector; }),
            detMetrics.map(function (r) { return +(r.roc_auc || 0); }),
            detMetrics.map(function (_, i) { return DETECTOR_PALETTE[i % DETECTOR_PALETTE.length]; })
        );
    }

    var canvasSrc = document.getElementById('chart-source');
    if (canvasSrc && srcMetrics.length) {
        var detectorNames = uniqueValues(detMetrics, 'detector');

        drawGroupedBars(canvasSrc, detectorNames, ['real', 'ml_a', 'ml_b'].map(function (src) {
            return {
                label: src,
                color: SOURCE_COLORS[src],
                vals: detectorNames.map(function (dName) {
                    var row = srcMetrics.find(function (x) {
                        return x.detector === dName && x.source === src;
                    });
                    return row ? +(row.roc_auc || 0) : 0;
                })
            };
        }));
    }

    var canvasEnc = document.getElementById('chart-encryption');
    if (canvasEnc && condMetrics.length) {
        var detNames = uniqueValues(detMetrics, 'detector');

        drawGroupedBars(canvasEnc, detNames, ['plain', 'encrypted'].map(function (enc) {
            return {
                label: enc,
                color: ENCRYPTION_COLORS[enc],
                vals: detNames.map(function (dName) {
                    var rows = condMetrics.filter(function (r) {
                        return r.detector === dName && r.encryption === enc && r.roc_auc;
                    });
                    if (!rows.length) return 0;
                    return rows.reduce(function (sum, r) { return sum + (+r.roc_auc); }, 0) / rows.length;
                })
            };
        }));
    }
}

function uniqueValues(arr, key) {
    var seen = {};
    return arr.filter(function (r) {
        if (seen[r[key]]) return false;
        seen[r[key]] = true;
        return true;
    }).map(function (r) { return r[key]; });
}


/* ── Covers tab ─────────────────────────────────────────────────────────── */

function buildCoversTab(covers) {
    if (!covers || !covers.length) {
        return '<div class="empty-state"><h3>No covers found</h3></div>';
    }

    var rows = covers.map(function (group) {
        var cells = ['real', 'ml_a', 'ml_b'].map(function (src) {
            var path = group.sources[src];
            var labelClass = 'source-label ' + src;
            var labelText  = src.replace('_', ' ');

            if (!path) {
                return (
                    '<div class="source-cell">' +
                        '<div class="' + labelClass + '">' + labelText + '</div>' +
                        '<div class="image-none">\u2014</div>' +
                    '</div>'
                );
            }

            var imgUrl = '/api/image?path=' + encodeURIComponent(path);
            return (
                '<div class="source-cell">' +
                    '<div class="' + labelClass + '">' + labelText + '</div>' +
                    '<img class="cover-thumb" src="' + imgUrl + '" loading="lazy" ' +
                        'alt="' + src + '" onclick="openLightbox(\'' + imgUrl + '\')">' +
                '</div>'
            );
        }).join('');

        var captionHtml = '';
        if (group.caption) {
            var truncated = group.caption.length > 130
                ? group.caption.slice(0, 130) + '\u2026'
                : group.caption;
            captionHtml = '<span class="group-caption">' + truncated + '</span>';
        }

        return (
            '<div class="group-card">' +
                '<div class="group-head">' +
                    '<span class="group-gid">Group ' + group.group_id + '</span>' +
                    captionHtml +
                '</div>' +
                '<div class="group-images">' + cells + '</div>' +
            '</div>'
        );
    }).join('');

    return (
        '<div class="section-header">' +
            '<div>' +
                '<div class="section-title">Cover Images</div>' +
                '<div class="section-subtitle">' +
                    covers.length + ' groups &middot; 3 sources' +
                '</div>' +
            '</div>' +
        '</div>' +
        '<div class="covers-grid">' + rows + '</div>'
    );
}


/* ── Conditions tab ─────────────────────────────────────────────────────── */

function buildConditionsTab(data) {
    var condMetrics = data.metrics.condition || [];
    if (!condMetrics.length) {
        return '<div class="empty-state"><h3>No condition metrics</h3></div>';
    }

    var detectors  = uniqueValues(condMetrics, 'detector');
    var methods    = uniqueValues(condMetrics, 'method');
    var levels     = uniqueValues(condMetrics, 'payload_level');
    var encryptions = uniqueValues(condMetrics, 'encryption');

    var columns = [];
    methods.forEach(function (m) {
        levels.forEach(function (l) {
            encryptions.forEach(function (e) {
                columns.push({ method: m, level: l, encryption: e });
            });
        });
    });

    var headerCells = columns.map(function (c) {
        return (
            '<th style="text-align:center">' +
                '<div>' + c.method.toUpperCase() + '</div>' +
                '<div style="color:var(--amber);font-weight:500">' + c.level + '</div>' +
                '<div style="color:var(--purple);font-weight:500">' + c.encryption + '</div>' +
            '</th>'
        );
    }).join('');

    var bodyRows = detectors.map(function (det) {
        var cells = columns.map(function (c) {
            var row = condMetrics.find(function (x) {
                return x.detector === det &&
                       x.method === c.method &&
                       x.payload_level === c.level &&
                       x.encryption === c.encryption;
            });

            if (!row) {
                return '<td style="text-align:center;color:var(--text-3)">\u2014</td>';
            }

            var v = +(row.roc_auc || 0);
            var color = v > 0.85 ? 'var(--green)' : (v > 0.65 ? 'var(--amber)' : 'var(--red)');
            return '<td style="text-align:center;font-weight:500;font-family:var(--mono);font-size:12px;color:' + color + '">' + v.toFixed(3) + '</td>';
        }).join('');

        return '<tr><td style="font-weight:600">' + det + '</td>' + cells + '</tr>';
    }).join('');

    return (
        '<div class="card">' +
            '<div class="card-head">' +
                '<span class="card-title">AUC per Condition (detectors &times; method &times; level &times; encryption)</span>' +
            '</div>' +
            '<div style="overflow-x:auto">' +
                '<table class="metrics-table"><thead><tr>' +
                    '<th>Detector</th>' + headerCells +
                '</tr></thead><tbody>' + bodyRows + '</tbody></table>' +
            '</div>' +
        '</div>'
    );
}


/* ── Launch page ────────────────────────────────────────────────────────── */

function renderLaunchPage(el) {
    var isRunning = !!STATE.job;
    var logContent = STATE.logLines.length ? STATE.logLines.join('\n') : '';
    var showLog = isRunning || logContent;

    el.innerHTML =
        '<div class="page-header">' +
            '<div class="page-title">Launch Pipeline</div>' +
            '<div class="page-subtitle">Start a new run. Each run downloads its own fresh set of cover images.</div>' +
        '</div>' +
        '<div class="launch-form">' +
            '<div class="form-group">' +
                '<label class="form-label">Profile</label>' +
                '<select class="form-select" id="launch-profile">' +
                    '<option value="prototype">prototype \u2014 20 groups \u00b7 LSB only \u00b7 low fill rate</option>' +
                '</select>' +
            '</div>' +
            '<div class="form-group">' +
                '<label class="form-label">ML Engine</label>' +
                '<select class="form-select" id="launch-engine">' +
                    '<option value="stub">stub \u2014 deterministic synthetic images (fast, no API needed)</option>' +
                    '<option value="inference_api">inference_api \u2014 HuggingFace Inference API (requires HF_TOKEN)</option>' +
                    '<option value="diffusers">diffusers \u2014 local SDXL + FLUX (requires GPU + torch)</option>' +
                '</select>' +
            '</div>' +
            '<button class="btn btn-primary" id="launch-btn" onclick="launchRun()"' +
                (isRunning ? ' disabled' : '') + '>' +
                (isRunning
                    ? '<span class="loader" style="width:13px;height:13px;border-width:2px"></span> &nbsp;Running\u2026'
                    : '\u25b6 &nbsp;Start Run') +
            '</button>' +
        '</div>' +
        '<div class="log-wrap" id="log-wrap" style="display:' + (showLog ? 'block' : 'none') + '">' +
            '<div class="log-header">' +
                '<span class="log-title">Pipeline Output</span>' +
                '<span class="badge ' + (isRunning ? 'badge-running' : 'badge-done') + '" id="launch-badge">' +
                    (isRunning ? '\u25cf Running' : '\u2713 Done') +
                '</span>' +
            '</div>' +
            '<pre class="log-box" id="launch-log">' + logContent + '</pre>' +
        '</div>';

    if (isRunning) {
        attachStream(STATE.job);
    }
}

function launchRun() {
    var profile = document.getElementById('launch-profile').value;
    var engine  = document.getElementById('launch-engine').value;

    STATE.logLines = [];
    STATE.job = null;

    var btn = document.getElementById('launch-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="loader" style="width:13px;height:13px;border-width:2px"></span> &nbsp;Starting\u2026';

    var logWrap = document.getElementById('log-wrap');
    if (logWrap) logWrap.style.display = 'block';

    var logBox = document.getElementById('launch-log');
    if (logBox) logBox.textContent = 'Starting\u2026\n';

    fetch('/api/pipeline/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profile, engine: engine })
    })
    .then(function (r) { return r.json(); })
    .then(function (result) {
        STATE.job = result.job_id;
        attachStream(result.job_id);
    })
    .catch(function (err) {
        appendLog('Error: ' + err);
        resetLaunchButton();
    });
}

function attachStream(jobId) {
    var source = new EventSource('/api/pipeline/stream/' + jobId);

    source.onmessage = function (event) {
        STATE.logLines.push(event.data);
        appendLog(event.data);
    };

    source.addEventListener('done', function (event) {
        source.close();
        STATE.job = null;
        appendLog('\n\u2713 Finished (exit ' + event.data + ')');
        resetLaunchButton();
        setLaunchBadge(+event.data === 0 ? 'done' : 'error');
        setTimeout(function () { go('runs'); }, 2200);
    });

    source.onerror = function () {
        source.close();
        STATE.job = null;
        resetLaunchButton();
    };
}

function appendLog(line) {
    var logBox = document.getElementById('launch-log');
    if (!logBox) return;
    logBox.textContent += line + '\n';
    logBox.scrollTop = logBox.scrollHeight;
}

function resetLaunchButton() {
    var btn = document.getElementById('launch-btn');
    if (!btn) return;
    btn.disabled = false;
    btn.innerHTML = '\u25b6 &nbsp;Start Run';
}

function setLaunchBadge(type) {
    var badge = document.getElementById('launch-badge');
    if (!badge) return;
    badge.className = 'badge badge-' + type;
    badge.textContent = type === 'done' ? '\u2713 Done' : '\u2717 Error';
}


/* ── Delete runs ────────────────────────────────────────────────────────── */

function confirmDeleteRun(runId) {
    showConfirmDialog(
        'Delete Run',
        'Permanently delete <strong style="font-family:var(--mono)">' + runId + '</strong> and all its data? This cannot be undone.',
        'Delete',
        function () { deleteRun(runId); }
    );
}

function deleteRun(runId) {
    fetch('/api/runs/' + runId, { method: 'DELETE' })
        .then(function (r) { return r.json(); })
        .then(function () { go('runs'); })
        .catch(function (err) {
            alert('Failed to delete: ' + err);
        });
}

function showConfirmDialog(title, message, confirmLabel, onConfirm) {
    var existing = document.getElementById('confirm-dialog');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'confirm-dialog';
    overlay.className = 'dialog-overlay';
    overlay.innerHTML =
        '<div class="dialog-box">' +
            '<div class="dialog-title">' + title + '</div>' +
            '<div class="dialog-message">' + message + '</div>' +
            '<div class="dialog-actions">' +
                '<button class="btn btn-ghost" id="dialog-cancel">Cancel</button>' +
                '<button class="btn btn-danger" id="dialog-confirm">' + confirmLabel + '</button>' +
            '</div>' +
        '</div>';

    document.body.appendChild(overlay);

    // Force reflow then add open class for animation
    overlay.offsetHeight;
    overlay.classList.add('open');

    document.getElementById('dialog-cancel').onclick = function () { closeDialog(); };
    document.getElementById('dialog-confirm').onclick = function () { closeDialog(); onConfirm(); };

    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeDialog();
    });

    document.addEventListener('keydown', function handler(e) {
        if (e.key === 'Escape') { closeDialog(); document.removeEventListener('keydown', handler); }
    });
}

function closeDialog() {
    var el = document.getElementById('confirm-dialog');
    if (el) {
        el.classList.remove('open');
        setTimeout(function () { el.remove(); }, 150);
    }
}


/* ── Lightbox ───────────────────────────────────────────────────────────── */

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
}

function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
}

document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeLightbox();
});


/* ── Boot ────────────────────────────────────────────────────────────────── */

window.addEventListener('DOMContentLoaded', render);
