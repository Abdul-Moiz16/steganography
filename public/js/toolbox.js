// ── State ──────────────────────────────────────────────────────────────────
const state = {
    encode: { b64: null, filename: null, format: null },
    decode: { b64: null, filename: null, format: null },
    analyze: { b64: null, filename: null, format: null },
};

// ── Tab switching ──────────────────────────────────────────────────────────
function setTab(tab) {
    ['encode', 'decode', 'analyze'].forEach(t => {
        document.getElementById(`tab-${t}`).classList.toggle('active', t === tab);
        document.getElementById(`panel-${t}`).classList.toggle('active', t === tab);
    });
}

// ── File handling ──────────────────────────────────────────────────────────
function onFileChange(event, tab) {
    const file = event.target.files[0];
    if (file) loadFile(file, tab);
}

function onDragOver(event, tab) {
    event.preventDefault();
    document.getElementById(`zone-${tab}`).classList.add('drag-over');
}

function onDragLeave(tab) {
    document.getElementById(`zone-${tab}`).classList.remove('drag-over');
}

function onDrop(event, tab) {
    event.preventDefault();
    document.getElementById(`zone-${tab}`).classList.remove('drag-over');
    const file = event.dataTransfer.files[0];
    if (file) loadFile(file, tab);
}

function loadFile(file, tab) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['png', 'jpg', 'jpeg'].includes(ext)) {
        alert('Unsupported file type. Please use PNG or JPEG.');
        return;
    }
    const format = ext === 'png' ? 'png' : 'jpeg';
    const reader = new FileReader();
    reader.onload = e => {
        // strip the data:...;base64, prefix
        const b64 = e.target.result.split(',')[1];
        state[tab] = { b64, filename: file.name, format };
        updateFileInfo(tab);
        clearResult(tab);
    };
    reader.readAsDataURL(file);
}

function clearFile(tab) {
    state[tab] = { b64: null, filename: null, format: null };
    updateFileInfo(tab);
    clearResult(tab);
}

function updateFileInfo(tab) {
    const { b64, filename, format } = state[tab];
    const infoEl   = document.getElementById(`file-info-${tab}`);
    const nameEl   = document.getElementById(`file-name-${tab}`);
    const badgeEl  = document.getElementById(`format-badge-${tab}`);
    const methodEl = document.getElementById(`format-method-${tab}`);
    const btnEl    = document.getElementById(`btn-${tab}`);

    if (b64) {
        infoEl.classList.add('visible');
        nameEl.textContent = filename;
        badgeEl.textContent = format.toUpperCase();
        badgeEl.className = `format-badge ${format}`;
        methodEl.textContent = format === 'png' ? '→ LSB method' : '→ DCT method';
        btnEl.disabled = false;
    } else {
        infoEl.classList.remove('visible');
        nameEl.textContent = '';
        btnEl.disabled = true;
    }
}

// ── API calls ──────────────────────────────────────────────────────────────
async function submitEncode() {
    const { b64, filename } = state.encode;
    const message = document.getElementById('encode-message').value.trim();
    if (!message) { alert('Please enter a message to hide.'); return; }

    setLoading('encode', true);
    clearResult('encode');

    try {
        const res = await fetch('/api/toolbox/encode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_b64: b64, filename, message }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
        showEncodeResult(data);
    } catch (err) {
        showError('encode', err.message);
    } finally {
        setLoading('encode', false);
    }
}

async function submitDecode() {
    const { b64, filename } = state.decode;

    setLoading('decode', true);
    clearResult('decode');

    try {
        const res = await fetch('/api/toolbox/decode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_b64: b64, filename }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
        showDecodeResult(data);
    } catch (err) {
        showError('decode', err.message);
    } finally {
        setLoading('decode', false);
    }
}

async function submitAnalyze() {
    const { b64, filename } = state.analyze;

    setLoading('analyze', true);
    clearResult('analyze');

    try {
        const res = await fetch('/api/toolbox/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_b64: b64, filename }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
        showAnalyzeResult(data);
    } catch (err) {
        showError('analyze', err.message);
    } finally {
        setLoading('analyze', false);
    }
}

// ── Result rendering ───────────────────────────────────────────────────────
function showEncodeResult(data) {
    const card    = document.getElementById('result-encode');
    const label   = document.getElementById('result-encode-label');
    const img     = document.getElementById('result-encode-img');
    const text    = document.getElementById('result-encode-text');
    const actions = document.getElementById('result-encode-actions');
    const link    = document.getElementById('download-link');

    const mime = data.format === 'png' ? 'image/png' : 'image/jpeg';
    const ext  = data.format === 'png' ? 'png' : 'jpg';
    const blob = b64ToBlob(data.image_b64, mime);
    const url  = URL.createObjectURL(blob);

    label.textContent = 'Stego image';
    img.src = url;
    img.style.display = 'block';
    text.textContent = '';
    link.href = url;
    link.download = `stego.${ext}`;
    actions.style.display = 'flex';

    card.classList.add('visible');
    card.classList.remove('error');
}

function showDecodeResult(data) {
    const card   = document.getElementById('result-decode');
    const label  = document.getElementById('result-decode-label');
    const text   = document.getElementById('result-decode-text');
    const copy   = document.getElementById('result-decode-copy');

    if (!data.message) {
        label.textContent = 'No encoded message was detected.';
        text.textContent = '';
        copy.style.display = 'none';
    } else {
        label.textContent = 'Extracted message';
        text.textContent = data.message;
        copy.style.display = 'flex';
    }
    
    card.classList.add('visible');
    card.classList.remove('error');
}

function showAnalyzeResult(data) {
    const card  = document.getElementById('result-analyze');
    const label = document.getElementById('result-analyze-label');
    const list  = document.getElementById('scores-list');

    label.textContent = `Detector scores — ${data.format.toUpperCase()}`;
    list.innerHTML = data.scores.map(s => {
        const pct = Math.min(100, Math.round(s.score * 100));
        const cls = pct >= 67 ? 'high' : pct >= 34 ? 'moderate' : 'low';
        return `
            <div class="score-row">
                <div class="score-name">${formatDetectorName(s.detector)}</div>
                <div class="score-bar-wrap">
                    <div class="score-bar ${cls}" style="width:${pct}%"></div>
                </div>
                <div class="score-label ${cls}">${pct}%</div>
            </div>`;
    }).join('');

    card.classList.add('visible');
    card.classList.remove('error');
}

function showError(tab, message) {
    const card  = document.getElementById(`result-${tab}`);
    const label = document.getElementById(`result-${tab}-label`);

    label.textContent = message;
    card.classList.add('visible', 'error');

    // hide tab-specific success elements
    if (tab === 'encode') {
        document.getElementById('result-encode-img').style.display = 'none';
        document.getElementById('result-encode-actions').style.display = 'none';
    }
    if (tab === 'decode') {
        document.getElementById('result-decode-copy').style.display = 'none';
    }
}

function clearResult(tab) {
    const card = document.getElementById(`result-${tab}`);
    card.classList.remove('visible', 'error');
}

// ── UI helpers ─────────────────────────────────────────────────────────────
function setLoading(tab, loading) {
    document.getElementById(`btn-${tab}`).disabled = loading;
    document.getElementById(`spinner-${tab}`).classList.toggle('visible', loading);
}

function copyMessage() {
    const text = document.getElementById('result-decode-text').textContent;
    navigator.clipboard.writeText(text);
}

function b64ToBlob(b64, mime) {
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    return new Blob([arr], { type: mime });
}

function formatDetectorName(key) {
    return { rs_analysis: 'RS Analysis', chi_square_spatial: 'Chi-Square (Spatial)',
                sample_pairs: 'Sample Pairs', chi_square_dct: 'Chi-Square (DCT)',
                calibration_chi_square: 'Calibration Chi-Square' }[key] || key;
}
