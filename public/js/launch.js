/* Stego Explorer — Launch panel: pipeline configuration, system check, and run initiation */

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
