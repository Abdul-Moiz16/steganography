function openLaunchPanel() {
    const overlay = document.getElementById('launch-drawer-overlay');
    const drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.add('open');
    if (drawer) drawer.classList.add('open');
    try {
        renderLaunchDrawer();
    } catch (err) {
        console.error('renderLaunchDrawer failed:', err);
        const body = document.getElementById('launch-drawer-body');
        if (body) {
            body.innerHTML = '<div class="sc-error" style="margin:20px">Drawer render failed: '
                + (err && err.message ? err.message : String(err))
                + '</div>';
        }
    }
}

function closeLaunchPanel() {
    const overlay = document.getElementById('launch-drawer-overlay');
    const drawer = document.getElementById('launch-drawer');
    if (overlay) overlay.classList.remove('open');
    if (drawer) drawer.classList.remove('open');
}

const ADVANCED_DEFAULTS = {
    n_groups: '',
    methods: { lsb: true, dct: true },
    payload_levels: { low: true, medium: true, high: true },
    encryption: { plain: true, encrypted: true },
    detectors: {
        rs: true,
        chi_square_spatial: true,
        sample_pairs: true,
        chi_square_dct: true,
        chi_square_dct_tiled: true,
        calibration_chi_square: true,
    },
    include_bd_sens: false,
    jpeg_quality: 95,
};

// Detector labels for the launch drawer's "Advanced" checkboxes. Kept
// separate from utils.js DETECTOR_LABELS because the drawer uses richer
// labels (branch annotations + chi-square glyph) while the rest of the
// app uses ASCII-only fallbacks.
const ADV_DETECTOR_LABELS = {
    rs: 'RS Analysis (spatial)',
    chi_square_spatial: 'Chi-Square (spatial)',
    sample_pairs: 'Sample Pairs (spatial)',
    chi_square_dct: 'Chi-Square (DCT)',
    chi_square_dct_tiled: 'Tiled Chi-Square (DCT)',
    calibration_chi_square: 'Calibration Chi-Square (DCT)',
};

function getAdvancedState() {
    if (!STATE.lastAdvanced) {
        STATE.lastAdvanced = JSON.parse(JSON.stringify(ADVANCED_DEFAULTS));
    }
    return STATE.lastAdvanced;
}

// ── Live power estimate (Hanley & McNeil 1982, closed form) ──────────────────
//
// Mirrors src/analysis/power_analysis.py so the user sees the same numbers in
// the drawer that the post-run CSVs will eventually report. Updates as the
// advanced-section checkboxes / inputs change.

const _SPATIAL_DETECTORS = ['rs', 'chi_square_spatial', 'sample_pairs'];
const _DCT_DETECTORS = ['chi_square_dct', 'calibration_chi_square', 'chi_square_dct_tiled'];
const _POWER_TARGET_AUC = 0.85;
const _POWER_LEVEL = 0.80;
const _ALPHA = 0.05;

function _hanleyMcneilVar(auc, nPos, nNeg) {
    if (!(auc > 0 && auc < 1) || nPos < 1 || nNeg < 1) return NaN;
    const q1 = auc / (2 - auc);
    const q2 = 2 * auc * auc / (1 + auc);
    return (
        auc * (1 - auc)
        + (nPos - 1) * (q1 - auc * auc)
        + (nNeg - 1) * (q2 - auc * auc)
    ) / (nPos * nNeg);
}

// Abramowitz & Stegun 26.2.23 — inverse normal survival, |error| < 4.5e-4.
function _zForUpperTail(p) {
    if (p <= 0) return Infinity;
    if (p >= 0.5) return 0;
    const t = Math.sqrt(-2 * Math.log(p));
    const c0 = 2.515517, c1 = 0.802853, c2 = 0.010328;
    const d1 = 1.432788, d2 = 0.189269, d3 = 0.001308;
    return t - (c0 + c1 * t + c2 * t * t) / (1 + d1 * t + d2 * t * t + d3 * t * t * t);
}

function _familySizeRq12(methods, detectors, payloads) {
    // Strata per RQ1/RQ2 confirmatory family: spatial-detector × LSB × payload
    // PLUS dct-detector × DCT × payload.
    const spatialCount = detectors.filter(d => _SPATIAL_DETECTORS.includes(d)).length;
    const dctCount = detectors.filter(d => _DCT_DETECTORS.includes(d)).length;
    let n = 0;
    if (methods.includes('lsb')) n += spatialCount * payloads.length;
    if (methods.includes('dct')) n += dctCount * payloads.length;
    return Math.max(1, n);
}

function _familySizeRq5(methods, detectors, payloads) {
    return _familySizeRq12(methods, detectors, payloads) * 3;  // × 3 sources
}

function _detectableDelta(nGroups, familySize, mode) {
    if (!(nGroups >= 5) || familySize < 1) return null;
    const tailP = _ALPHA / (2 * familySize);
    const zAlpha = _zForUpperTail(tailP);
    const zBeta = _zForUpperTail(1 - _POWER_LEVEL);
    const vOne = _hanleyMcneilVar(_POWER_TARGET_AUC, nGroups, nGroups);
    let varDiff;
    if (mode === 'unpaired_asym') {
        // Real n=N vs pooled ML n=2N (ml_a + ml_b combined).
        const vTwo = _hanleyMcneilVar(_POWER_TARGET_AUC, 2 * nGroups, 2 * nGroups);
        varDiff = vOne + vTwo;
    } else if (mode === 'paired') {
        // Shared covers cancel V01 component; conservative approximation.
        varDiff = vOne;
    } else {
        // Default: unpaired symmetric.
        varDiff = 2 * vOne;
    }
    if (!(varDiff > 0)) return null;
    return (zAlpha + zBeta) * Math.sqrt(varDiff);
}

function computePowerEstimate(adv, profile) {
    let nGroups = (typeof adv.n_groups === 'number' && adv.n_groups >= 5)
        ? adv.n_groups
        : null;
    if (nGroups == null) {
        const profileMeta = PROFILE_META[profile] || PROFILE_META.prototype;
        nGroups = profileMeta.n_groups;
    }
    const methods = adv.methods;
    const detectors = adv.detectors;
    const payloads = adv.payload_levels;
    const enc = adv.encryption;

    const famRq12 = _familySizeRq12(methods, detectors, payloads);
    const famRq5 = _familySizeRq5(methods, detectors, payloads);
    const bothEnc = enc.includes('plain') && enc.includes('encrypted');

    return {
        nGroups: nGroups,
        nGroupsFromProfile: !(typeof adv.n_groups === 'number' && adv.n_groups >= 5),
        familyRq12: famRq12,
        familyRq5: famRq5,
        rq1Delta: _detectableDelta(nGroups, famRq12, 'unpaired_asym'),
        rq2Delta: _detectableDelta(nGroups, famRq12, 'unpaired_sym'),
        rq5Delta: bothEnc ? _detectableDelta(nGroups, famRq5, 'paired') : null,
        rq5Enabled: bothEnc,
        targetAuc: _POWER_TARGET_AUC,
        powerLevel: _POWER_LEVEL,
    };
}

function _formatDeltaCell(delta) {
    if (delta == null) return `<span class="lp-power-na">unavailable</span>`;
    const cls = delta <= 0.05 ? 'lp-power-ok' : (delta <= 0.075 ? 'lp-power-warn' : 'lp-power-low');
    return `<span class="${cls}">ΔAUC ≥ ${delta.toFixed(3)}</span>`;
}

function renderPowerEstimate(adv, profile) {
    const est = computePowerEstimate(adv, profile);
    const nSuffix = est.nGroupsFromProfile ? ` <span class="lp-muted">(profile default)</span>` : '';
    const rq5Row = est.rq5Enabled
        ? `<div class="lp-power-row"><span>RQ5 — plain vs AES (paired)</span><span>${_formatDeltaCell(est.rq5Delta)}</span></div>`
        : `<div class="lp-power-row lp-power-row--muted"><span>RQ5 — needs both encryption arms</span><span>—</span></div>`;
    return `<div class="lp-power-estimate">
        <div class="lp-power-title">
            <span class="material-symbols-outlined" style="font-size:14px;vertical-align:-2px">insights</span>
            Detectable effect at N = ${est.nGroups}${nSuffix}
        </div>
        <div class="lp-power-rows">
            <div class="lp-power-row"><span>RQ1 — real vs pooled ML</span><span>${_formatDeltaCell(est.rq1Delta)}</span></div>
            <div class="lp-power-row"><span>RQ2 — SDXL vs FLUX.1-schnell</span><span>${_formatDeltaCell(est.rq2Delta)}</span></div>
            ${rq5Row}
        </div>
        <div class="lp-power-foot">
            80% power, α=0.05, Holm over ${est.familyRq12} (RQ1/2) / ${est.familyRq5} (RQ5)
            · operating AUC ≈ ${est.targetAuc}
            · proposal threshold ΔAUC = 0.05
        </div>
    </div>`;
}

function _readAdvancedFromForm() {
    function cb(id) {
        const el = document.getElementById(id);
        return el ? el.checked : false;
    }
    const nGroupsEl = document.getElementById('adv-n-groups');
    const nGroupsRaw = nGroupsEl && nGroupsEl.value.trim() !== '' ? parseInt(nGroupsEl.value, 10) : null;
    const methods = ['lsb', 'dct'].filter(m => cb('adv-method-' + m));
    const payload_levels = ['low', 'medium', 'high'].filter(p => cb('adv-level-' + p));
    const encryption = ['plain', 'encrypted'].filter(e => cb('adv-enc-' + e));
    const detectors = Object.keys(ADV_DETECTOR_LABELS).filter(d => cb('adv-det-' + d));
    return {
        n_groups: nGroupsRaw,
        methods, payload_levels, encryption, detectors,
        include_bd_sens: cb('adv-bd-sens'),
    };
}

function updatePowerEstimate() {
    const block = document.getElementById('lp-power-estimate-block');
    if (!block) return;
    const profileEl = document.getElementById('launch-profile');
    const profile = profileEl ? profileEl.value : (STATE.lastProfile || 'prototype');
    block.innerHTML = renderPowerEstimate(_readAdvancedFromForm(), profile);
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
    const adv = getAdvancedState();

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
                    <span class="lp-dropdown-value" id="lp-profile-label">${profileLabel(curProfile)}</span>
                    <span class="material-symbols-outlined lp-dropdown-arrow">expand_more</span>
                </button>
                <div class="lp-dropdown-menu" id="lp-profile-menu">
                    <div class="lp-dropdown-opt${curProfile === 'prototype' ? ' lp-dropdown-opt--selected' : ''}" onclick="selectLpProfile('prototype', 'Prototype Analysis', this)">
                        <span class="material-symbols-outlined lp-dropdown-check">check</span>Prototype Analysis
                    </div>
                    <div class="lp-dropdown-opt${curProfile === 'prototype_full' ? ' lp-dropdown-opt--selected' : ''}" onclick="selectLpProfile('prototype_full', 'Prototype Full Design', this)">
                        <span class="material-symbols-outlined lp-dropdown-check">check</span>Prototype Full Design<span class="lp-dropdown-tag">All factors</span>
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
        `<div class="drawer-section">
            <details class="lp-advanced" ${STATE.lastAdvancedOpen ? 'open' : ''} ontoggle="STATE.lastAdvancedOpen = this.open">
                <summary class="lp-advanced-summary">
                    <span class="material-symbols-outlined">tune</span>
                    Advanced configuration
                </summary>
                <div class="lp-advanced-body">
                    <div class="lp-field-label">Groups per source</div>
                    <input type="number" id="adv-n-groups" class="lp-num-input" min="5" max="2000"
                        value="${escapeAttr(adv.n_groups)}"
                        placeholder="e.g. 500 (empty = profile default)">
                    <div class="lp-preset-row">
                        <button type="button" class="lp-preset-chip" data-n="20">20<span>prototype</span></button>
                        <button type="button" class="lp-preset-chip" data-n="100">100<span>test</span></button>
                        <button type="button" class="lp-preset-chip" data-n="500">500<span>proposal</span></button>
                        <button type="button" class="lp-preset-chip" data-n="1000">1000<span>powered</span></button>
                    </div>
                    <div class="lp-field-hint">Minimum 5; below 20 disables confirmatory tests. Click a preset or type a value.</div>
                    <div id="lp-power-estimate-block"></div>

                    <div class="lp-field-label">Embedding methods</div>
                    ${checkbox('adv-method-lsb', 'Spatial LSB (PNG)', adv.methods.lsb)}
                    ${checkbox('adv-method-dct', 'DCT-LSB (JPEG)', adv.methods.dct)}

                    <div class="lp-field-label">Payload levels</div>
                    ${checkbox('adv-level-low',    'Low (0.05 bpp)',    adv.payload_levels.low)}
                    ${checkbox('adv-level-medium', 'Medium (0.15 bpp)', adv.payload_levels.medium)}
                    ${checkbox('adv-level-high',   'High (0.30 bpp)',   adv.payload_levels.high)}

                    <div class="lp-field-label">Encryption arms</div>
                    ${checkbox('adv-enc-plain',     'Plain',         adv.encryption.plain)}
                    ${checkbox('adv-enc-encrypted', 'AES-256-CBC',   adv.encryption.encrypted)}

                    <div class="lp-field-label">Detectors</div>
                    ${Object.entries(ADV_DETECTOR_LABELS)
                        .map(([k, label]) => checkbox('adv-det-' + k, label, adv.detectors[k]))
                        .join('')}

                    <div class="lp-field-label">Extras</div>
                    ${checkbox('adv-bd-sens', 'Include BD-Sens (k=2) auxiliary', adv.include_bd_sens)}

                    <div class="lp-field-label">JPEG quality</div>
                    <input type="number" id="adv-jpeg-quality" class="lp-num-input" min="50" max="100"
                        value="${escapeAttr(adv.jpeg_quality)}">
                    <div class="lp-field-hint">Proposal-locked at 95. Other values trigger a warning.</div>

                    <button class="btn-secondary" type="button" onclick="previewLaunch()" style="margin-top:8px">
                        <span class="material-symbols-outlined">visibility</span> Preview validation
                    </button>
                    <div id="lp-preview-result" class="lp-preview-result"></div>
                </div>
            </details>
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

    // Re-render the power estimate whenever any knob that affects family
    // size or N changes. Targets the n-groups input plus every advanced
    // checkbox so the estimate updates as the user toggles methods,
    // payload levels, detectors, or encryption arms.
    const advSelectors = [
        '#adv-n-groups',
        'input[id^="adv-method-"]',
        'input[id^="adv-level-"]',
        'input[id^="adv-enc-"]',
        'input[id^="adv-det-"]',
    ];
    advSelectors.forEach(sel => {
        el.querySelectorAll(sel).forEach(input => {
            const evt = input.type === 'checkbox' ? 'change' : 'input';
            input.addEventListener(evt, updatePowerEstimate);
        });
    });
    el.querySelectorAll('.lp-preset-chip').forEach(chip => {
        chip.addEventListener('click', function() {
            const target = document.getElementById('adv-n-groups');
            if (!target) return;
            target.value = this.dataset.n;
            // Mark the active chip and clear the others.
            el.querySelectorAll('.lp-preset-chip').forEach(c => {
                c.classList.toggle('lp-preset-chip--active', c === this);
            });
            updatePowerEstimate();
        });
    });
    updatePowerEstimate();

    loadSystemCheck();
}

function profileLabel(profile) {
    if (profile === 'prototype_full') return 'Prototype Full Design';
    if (profile === 'full_design')    return 'Full Design Analysis';
    return 'Prototype Analysis';
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

function checkbox(id, label, checked) {
    return `<label class="lp-checkbox">
        <input type="checkbox" id="${id}" ${checked ? 'checked' : ''}>
        <span>${escapeHtml(label)}</span>
    </label>`;
}

function collectAdvanced() {
    function cb(id) {
        const el = document.getElementById(id);
        return el ? el.checked : false;
    }
    function pickList(map) {
        return Object.entries(map).filter(([k, v]) => cb(v)).map(([k]) => k);
    }
    const nGroupsEl = document.getElementById('adv-n-groups');
    const jpegEl = document.getElementById('adv-jpeg-quality');
    const adv = {
        methods: pickList({lsb: 'adv-method-lsb', dct: 'adv-method-dct'}),
        payload_levels: pickList({low: 'adv-level-low', medium: 'adv-level-medium', high: 'adv-level-high'}),
        encryption: pickList({plain: 'adv-enc-plain', encrypted: 'adv-enc-encrypted'}),
        detectors: pickList(Object.fromEntries(
            Object.keys(ADV_DETECTOR_LABELS).map(k => [k, 'adv-det-' + k])
        )),
        include_bd_sens: cb('adv-bd-sens'),
        n_groups: nGroupsEl && nGroupsEl.value.trim() !== '' ? parseInt(nGroupsEl.value, 10) : null,
        jpeg_quality: jpegEl && jpegEl.value.trim() !== '' ? parseInt(jpegEl.value, 10) : null,
    };
    // Persist to STATE so a re-render keeps the checkboxes in sync.
    STATE.lastAdvanced = {
        n_groups: nGroupsEl ? nGroupsEl.value : '',
        methods: {lsb: adv.methods.includes('lsb'), dct: adv.methods.includes('dct')},
        payload_levels: {
            low: adv.payload_levels.includes('low'),
            medium: adv.payload_levels.includes('medium'),
            high: adv.payload_levels.includes('high'),
        },
        encryption: {
            plain: adv.encryption.includes('plain'),
            encrypted: adv.encryption.includes('encrypted'),
        },
        detectors: Object.fromEntries(
            Object.keys(ADV_DETECTOR_LABELS).map(k => [k, adv.detectors.includes(k)])
        ),
        include_bd_sens: adv.include_bd_sens,
        jpeg_quality: jpegEl ? (jpegEl.value || 95) : 95,
    };
    return adv;
}

function buildLaunchBody(profile, engine, payloadMode, hardcodedPayload) {
    const adv = collectAdvanced();
    const body = {
        profile: profile,
        engine: engine,
        payload_mode: payloadMode,
        hardcoded_payload: payloadMode === 'hardcoded' ? hardcodedPayload : null,
        active_methods: adv.methods,
        active_payload_levels: adv.payload_levels,
        active_encryption: adv.encryption,
        active_detectors: adv.detectors,
        include_bd_sens: adv.include_bd_sens,
    };
    if (adv.n_groups !== null && !Number.isNaN(adv.n_groups)) body.n_groups = adv.n_groups;
    if (adv.jpeg_quality !== null && !Number.isNaN(adv.jpeg_quality)) body.jpeg_quality = adv.jpeg_quality;
    return body;
}

function previewLaunch() {
    const profile = document.getElementById('launch-profile').value;
    const engineEl = document.querySelector('input[name="launch-engine"]:checked');
    const engine = engineEl ? engineEl.value : 'stub';
    const payloadModeEl = document.querySelector('input[name="launch-payload-mode"]:checked');
    const payloadMode = payloadModeEl ? payloadModeEl.value : 'random';
    const payloadTextEl = document.getElementById('hardcoded-payload');
    const hardcodedPayload = payloadTextEl ? payloadTextEl.value : '';
    const body = buildLaunchBody(profile, engine, payloadMode, hardcodedPayload);
    const out = document.getElementById('lp-preview-result');
    if (out) out.innerHTML = '<span class="loader sc-loader"></span> Validating…';
    api('/api/pipeline/preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
    }).then(res => {
        if (!out) return;
        const parts = [];
        if (res.errors && res.errors.length) {
            parts.push(`<div class="sc-error"><strong>Errors:</strong><ul>${
                res.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')
            }</ul></div>`);
        } else {
            parts.push(`<div class="sc-success"><span class="material-symbols-outlined">check_circle</span> Config validates.</div>`);
        }
        if (res.warnings && res.warnings.length) {
            parts.push(`<div class="sc-warn"><strong>Warnings:</strong><ul>${
                res.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')
            }</ul></div>`);
        }
        if (res.planned_figures && res.planned_figures.length) {
            parts.push(`<div class="sc-info"><strong>Planned figures (${res.planned_figures.length}):</strong> ${
                res.planned_figures.map(f => `<code>${escapeHtml(f)}</code>`).join(' ')
            }</div>`);
        }
        out.innerHTML = parts.join('');
    }).catch(err => {
        if (out) out.innerHTML = `<div class="sc-error">Preview failed: ${escapeHtml(err.message)}</div>`;
    });
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
        body: JSON.stringify(buildLaunchBody(profile, engine, payloadMode, hardcodedPayload)),
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
