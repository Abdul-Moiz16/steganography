function openLaunchPanel() {
    const overlay = document.getElementById('launch-drawer-overlay');
    const drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.add('open');
    if (drawer) drawer.classList.add('open');
    renderLaunchDrawer();
}

function closeLaunchPanel() {
    const overlay = document.getElementById('launch-drawer-overlay');
    const drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.remove('open');
    if (drawer) drawer.classList.remove('open');
}

function renderLaunchDrawer() {
    const el = document.getElementById('launch-drawer-body');
    if (!el) return;
    const activeCount = getActiveJobs().length;
    const curEngine  = STATE.lastEngine  || 'stub';
    const curProfile = STATE.lastProfile || 'prototype';
    const curPayloadMode = STATE.lastPayloadMode || 'random';
    const curHardcodedPayload = STATE.lastHardcodedPayload || '';
    const maxPayloadBytes = (PROFILE_META[curProfile] || PROFILE_META.prototype).hardcoded_payload_max_bytes;

    function engineOpt(value, label, sub) {
        const checked = curEngine === value;
        return `<label class="lp-engine-opt${checked ? ' lp-engine-opt--checked' : ''}">
            <div class="lp-engine-opt-left">
                <input type="radio" class="lp-engine-radio" name="launch-engine" value="${escapeAttr(value)}"${checked ? ' checked' : ''}>
                <span class="lp-engine-name">${escapeHtml(label)}</span>
            </div>
            <span class="lp-engine-sub">${escapeHtml(sub)}</span>
        </label>`;
    }

    function payloadOpt(value, label, sub, iconName) {
        const checked = curPayloadMode === value;
        return `<label class="lp-engine-opt${checked ? ' lp-engine-opt--checked' : ''}">
            <div class="lp-engine-opt-left">
                <input type="radio" class="lp-engine-radio" name="launch-payload-mode" value="${escapeAttr(value)}"${checked ? ' checked' : ''}>
                <span class="material-symbols-outlined lp-payload-icon">${escapeHtml(iconName)}</span>
                <span class="lp-engine-name">${escapeHtml(label)}</span>
            </div>
            <span class="lp-engine-sub">${escapeHtml(sub)}</span>
        </label>`;
    }

    el.innerHTML =
        `<div class="drawer-section">
            <div class="sc-row">
                <div class="lp-field-label" style="margin-bottom:0">System Check</div>
                <button class="sc-refresh-btn" onclick="loadSystemCheck()" title="Re-check">
                    <span class="material-symbols-outlined">refresh</span>
                </button>
            </div>
            <div class="sc-panel" id="sc-panel"><div class="sc-loading"><span class="loader sc-loader"></span> Checking…</div></div>
        </div>
        <div class="drawer-divider"></div>
        <div class="drawer-section">
            <div class="lp-field-label">Research Profile</div>
            <div class="lp-dropdown" id="lp-profile-dropdown">
                <button class="lp-dropdown-trigger" type="button" onclick="toggleLpDropdown()">
                    <span class="lp-dropdown-value" id="lp-profile-label">${curProfile === 'prototype' ? 'Prototype Analysis' : 'Prototype Analysis'}</span>
                    <span class="material-symbols-outlined lp-dropdown-arrow">expand_more</span>
                </button>
                <div class="lp-dropdown-menu" id="lp-profile-menu">
                    <div class="lp-dropdown-opt lp-dropdown-opt--selected" onclick="selectLpProfile('prototype', 'Prototype Analysis', this)">
                        <span class="material-symbols-outlined lp-dropdown-check">check</span>Prototype Analysis
                    </div>
                    <div class="lp-dropdown-opt lp-dropdown-opt--disabled">
                        <span class="material-symbols-outlined lp-dropdown-check" style="opacity:0">check</span>Full Design Analysis<span class="lp-dropdown-tag">Soon</span>
                    </div>
                </div>
            </div>
            <input type="hidden" id="launch-profile" value="${escapeAttr(curProfile)}">
        </div>
        <div class="drawer-section">
            <div class="lp-field-label">ML Image Engine</div>
            <div class="lp-engine-group">
                ${engineOpt('stub',          'Fast Stub',  'Low Latency')}
                ${engineOpt('inference_api', 'Cloud API',  'High Capacity')}
                ${engineOpt('diffusers',     'Local GPU',  'Private / Secure')}
            </div>
        </div>
        <div class="drawer-section">
            <div class="lp-field-label">Payload Source</div>
            <div class="lp-engine-group">
                ${payloadOpt('random', 'Random Payload', 'Seeded Bytes', 'casino')}
                ${payloadOpt('hardcoded', 'Hardcoded Payload', 'Text Fixture', 'text_fields')}
            </div>
            <div class="lp-payload-text-wrap${curPayloadMode === 'hardcoded' ? ' open' : ''}" id="hardcoded-payload-wrap">
                <textarea id="hardcoded-payload" class="lp-payload-text" maxlength="${maxPayloadBytes}" placeholder="Payload text">${escapeHtml(curHardcodedPayload)}</textarea>
                <div class="lp-payload-meta">
                    <span id="hardcoded-payload-count">0 / ${maxPayloadBytes} bytes</span>
                    <span>UTF-8 text only</span>
                </div>
            </div>
        </div>` +
        (activeCount > 0
            ? `<div class="drawer-section"><div class="sc-running-note">
                  <span class="material-symbols-outlined">info</span>
                  ${activeCount} run${activeCount > 1 ? 's' : ''} already in progress — you can launch additional runs in parallel.
              </div></div>`
            : '') +
        `<div class="drawer-footer">
            <button class="btn-launch" id="launch-btn" onclick="launchRun()">
                <span class="material-symbols-outlined">bolt</span> START RUN
            </button>
        </div>`;

    const radios = el.querySelectorAll('input[name="launch-engine"]');
    radios.forEach(r => {
        r.addEventListener('change', function() {
            STATE.lastEngine = this.value;
            el.querySelectorAll('.lp-engine-opt').forEach(opt => {
                opt.classList.toggle('lp-engine-opt--checked', opt.querySelector('input').value === r.value);
            });
        });
    });
    const payloadRadios = el.querySelectorAll('input[name="launch-payload-mode"]');
    payloadRadios.forEach(r => {
        r.addEventListener('change', function() {
            STATE.lastPayloadMode = this.value;
            el.querySelectorAll('input[name="launch-payload-mode"]').forEach(input => {
                input.closest('.lp-engine-opt').classList.toggle('lp-engine-opt--checked', input.value === this.value);
            });
            const wrap = document.getElementById('hardcoded-payload-wrap');
            if (wrap) wrap.classList.toggle('open', this.value === 'hardcoded');
            updateHardcodedPayloadCount();
        });
    });
    const payloadText = document.getElementById('hardcoded-payload');
    if (payloadText) {
        payloadText.addEventListener('input', function() {
            STATE.lastHardcodedPayload = this.value;
            updateHardcodedPayloadCount();
        });
        updateHardcodedPayloadCount();
    }
    loadSystemCheck();
}

function hardcodedPayloadMaxBytes() {
    const profile = document.getElementById('launch-profile') ? document.getElementById('launch-profile').value : (STATE.lastProfile || 'prototype');
    return (PROFILE_META[profile] || PROFILE_META.prototype).hardcoded_payload_max_bytes;
}

function hardcodedPayloadBytes(text) {
    return new TextEncoder().encode(text || '').length;
}

function updateHardcodedPayloadCount() {
    const textEl = document.getElementById('hardcoded-payload');
    const countEl = document.getElementById('hardcoded-payload-count');
    if (!textEl || !countEl) return;
    const count = hardcodedPayloadBytes(textEl.value);
    const max = hardcodedPayloadMaxBytes();
    countEl.textContent = count + ' / ' + max + ' bytes';
    countEl.classList.toggle('lp-payload-count--bad', count > max);
}

function loadSystemCheck() {
    const panel = document.getElementById('sc-panel');
    if (!panel) return;
    panel.innerHTML = '<div class="sc-loading"><span class="loader sc-loader"></span> Checking…</div>';
    api('/api/system/check').then(data => {
        const panel = document.getElementById('sc-panel');
        if (!panel) return;
        panel.innerHTML = renderSystemCheck(data);
    }).catch(() => {
        const panel = document.getElementById('sc-panel');
        if (panel) panel.innerHTML = '<div class="sc-error">Could not reach server check endpoint.</div>';
    });
}

function renderSystemCheck(data) {
    const pyOk = data.python_ok;
    const pyBadge = pyOk
        ? `<span class="sc-badge sc-badge--ok">Python ${escapeHtml(data.python_version)}</span>`
        : `<span class="sc-badge sc-badge--err">Python ${escapeHtml(data.python_version)} (need ≥3.9)</span>`;
    const core = data.packages.filter(p => p.required);
    const optional = data.packages.filter(p => !p.required);

    function pkgRow(p) {
        const icon = p.installed ? 'check_circle' : 'cancel';
        const cls  = p.installed ? 'sc-pkg--ok' : (p.required ? 'sc-pkg--err' : 'sc-pkg--warn');
        return `<div class="sc-pkg ${cls}">
            <span class="material-symbols-outlined sc-pkg-icon">${icon}</span>
            <span class="sc-pkg-name">${escapeHtml(p.name)}</span>
            ${p.version ? `<span class="sc-pkg-ver">${escapeHtml(p.version)}</span>` : ''}
        </div>`;
    }

    return `${pyBadge}
        <div class="sc-group">
            <div class="sc-group-label">Core</div>
            ${core.map(pkgRow).join('')}
        </div>
        <div class="sc-group">
            <div class="sc-group-label">ML / Optional</div>
            ${optional.map(pkgRow).join('')}
        </div>`;
}

function toggleLpDropdown() {
    const menu = document.getElementById('lp-profile-menu');
    const dropdown = document.getElementById('lp-profile-dropdown');
    if (!menu || !dropdown) return;
    const open = dropdown.classList.toggle('lp-dropdown--open');
    if (open) {
        const close = e => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('lp-dropdown--open');
                document.removeEventListener('click', close);
            }
        };
        setTimeout(() => document.addEventListener('click', close), 0);
    }
}

function selectLpProfile(value, label, optEl) {
    const input = document.getElementById('launch-profile');
    const labelEl = document.getElementById('lp-profile-label');
    const dropdown = document.getElementById('lp-profile-dropdown');
    if (input) input.value = value;
    if (labelEl) labelEl.textContent = label;
    if (dropdown) dropdown.classList.remove('lp-dropdown--open');
    document.querySelectorAll('#lp-profile-menu .lp-dropdown-opt').forEach(opt => {
        opt.classList.toggle('lp-dropdown-opt--selected', opt === optEl);
    });
    STATE.lastProfile = value;
    updateHardcodedPayloadCount();
}

function launchRun() {
    const profile = document.getElementById('launch-profile').value;
    const engineEl = document.querySelector('input[name="launch-engine"]:checked');
    const engine = engineEl ? engineEl.value : 'stub';
    const payloadModeEl = document.querySelector('input[name="launch-payload-mode"]:checked');
    const payloadMode = payloadModeEl ? payloadModeEl.value : 'random';
    const payloadTextEl = document.getElementById('hardcoded-payload');
    const hardcodedPayload = payloadTextEl ? payloadTextEl.value : '';
    STATE.lastProfile = profile;
    STATE.lastEngine = engine;
    STATE.lastPayloadMode = payloadMode;
    STATE.lastHardcodedPayload = hardcodedPayload;

    if (payloadMode === 'hardcoded') {
        const byteCount = hardcodedPayloadBytes(hardcodedPayload);
        const maxBytes = hardcodedPayloadMaxBytes();
        if (!hardcodedPayload.trim()) {
            const panel = document.getElementById('sc-panel');
            if (panel) panel.innerHTML = '<div class="sc-error">Hardcoded payload must not be empty.</div>';
            return;
        }
        if (/[\x00-\x08\x0B\x0C\x0E-\x1F]/.test(hardcodedPayload)) {
            const panel = document.getElementById('sc-panel');
            if (panel) panel.innerHTML = '<div class="sc-error">Hardcoded payload cannot contain control characters.</div>';
            return;
        }
        if (byteCount > maxBytes) {
            const panel = document.getElementById('sc-panel');
            if (panel) panel.innerHTML = `<div class="sc-error">Hardcoded payload is ${byteCount} bytes; this profile allows ${maxBytes} bytes.</div>`;
            return;
        }
    }

    const btn = document.getElementById('launch-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="loader lp-loader"></span> Starting…'; }

    api('/api/pipeline/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            profile: profile,
            engine: engine,
            payload_mode: payloadMode,
            hardcoded_payload: payloadMode === 'hardcoded' ? hardcodedPayload : null
        })
    }).then(res => {
        if (!res.job_id) throw new Error('No job id returned by backend');
        const job = createJob(res.job_id, profile, engine, payloadMode);
        if (res.run_id) job.runId = res.run_id;
        closeLaunchPanel();
        attachStream(res.job_id);
        go('run-detail', res.run_id || res.job_id);
    }).catch(error => {
        if (btn) { btn.disabled = false; btn.innerHTML = '<span class="material-symbols-outlined">bolt</span> START RUN'; }
        const panel = document.getElementById('sc-panel');
        if (panel) panel.innerHTML = `<div class="sc-error">Launch failed: ${escapeHtml(error.message)}</div>`;
    });
}
