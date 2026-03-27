async function api(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }
    return response.json();
}

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeAttr(value) {
    return String(value == null ? '' : value).replace(/'/g, '&#39;');
}

function icon(name, extraClass) {
    return `<span class="material-symbols-outlined${extraClass ? ' ' + extraClass : ''}">${escapeHtml(name)}</span>`;
}

function toArray(value) {
    return Array.isArray(value) ? value : [];
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function formatMaybeNumber(value, digits) {
    return value == null || Number.isNaN(Number(value)) ? '\u2014' : Number(value).toFixed(digits);
}

const DETECTOR_LABELS = {
    'rs':                     'RS Analysis',
    'chi_square_spatial':     'Chi-Square (Spatial)',
    'sample_pairs':           'Sample Pairs',
    'chi_square_dct':         'Chi-Square (DCT)',
    'calibration_chi_square': 'Calibration Chi-Square',
};

function fmtDetector(name) { return DETECTOR_LABELS[name] || name; }

function statusPill(label, tone) {
    return `<status-pill label="${escapeAttr(label)}" tone="${escapeAttr(tone)}"></status-pill>`;
}

function uniqueValues(list, key) {
    const seen = {};
    return list.filter(item => {
        if (seen[item[key]]) return false;
        seen[item[key]] = true;
        return true;
    }).map(item => item[key]);
}

function renderLoading() {
    return `<div class="loading-page"><div class="loader"></div></div>`;
}

function renderError(message, actionLabel, actionFn) {
    const button = actionLabel && actionFn
        ? `<div class="empty-actions"><button class="btn btn-primary" onclick="${actionFn}">${escapeHtml(actionLabel)}</button></div>`
        : '';
    return `<div class="empty-state"><h3>Something went off-track</h3><p>${escapeHtml(message)}</p>${button}</div>`;
}
