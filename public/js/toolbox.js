// Per-detector interpretation thresholds.
//
// Different detectors use different score conventions, so a unified percent
// bar is meaningless. We map each detector's raw score to a 3-level
// "Cover-like / Suspect / Likely stego" verdict using thresholds picked
// from the empirical distribution observed in the pipeline runs.
const DETECTOR_INTERPRETERS = {
    'Chi-Square (Spatial)': (s) => {
        // -chi_stat/df: close to 0 = balanced PoVs (stego); very negative = unbalanced (cover).
        if (s > -0.1) return { level: 'high', label: 'Likely stego' };
        if (s > -2.0) return { level: 'moderate', label: 'Suspect' };
        return { level: 'low', label: 'Cover-like' };
    },
    'Chi-Square (DCT)': (s) => {
        if (s > -0.1) return { level: 'high', label: 'Likely stego' };
        if (s > -2.0) return { level: 'moderate', label: 'Suspect' };
        return { level: 'low', label: 'Cover-like' };
    },
    'Calibration Chi-Square': (s) => {
        // Raw chi-square distance: larger = more divergent from cover-like.
        if (s > 30) return { level: 'high', label: 'Likely stego' };
        if (s > 8)  return { level: 'moderate', label: 'Suspect' };
        return { level: 'low', label: 'Cover-like' };
    },
    'RS Analysis': (s) => {
        // Toolbox returns the raw count normalised by total 2x2 groups
        // (see src/toolbox/analyze.py::_normalised_rs); roughly 0..2.
        if (s > 0.15)  return { level: 'high', label: 'Likely stego' };
        if (s > 0.05) return { level: 'moderate', label: 'Suspect' };
        return { level: 'low', label: 'Cover-like' };
    },
    'Sample Pairs': (s) => {
        if (s > 0.2)  return { level: 'high', label: 'Likely stego' };
        if (s > 0.05) return { level: 'moderate', label: 'Suspect' };
        return { level: 'low', label: 'Cover-like' };
    },
};

const _DEFAULT_INTERPRET = () => ({ level: 'moderate', label: '—' });

class ToolboxApp {
    constructor() {
        this._state = { encode: null, decode: null, analyze: null };

        document.addEventListener('zone-change', e => {
            const { tab, file } = e.detail;
            this._state[tab] = file;
            document.getElementById(`btn-${tab}`).disabled = !file;
            this._clearResult(tab);
            this._refreshMethodHint(tab, file);
        });
    }

    setTab(tab) {
        ['encode', 'decode', 'analyze'].forEach(t => {
            document.getElementById(`tab-${t}`).classList.toggle('active', t === tab);
            document.getElementById(`panel-${t}`).classList.toggle('active', t === tab);
        });
    }

    async submit(tab) {
        const extras = this._extras(tab);
        if (extras === null) return;

        this._setLoading(tab, true);
        this._clearResult(tab);

        try {
            const { b64, filename } = this._state[tab];
            const res = await fetch(`/api/toolbox/${tab}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image_b64: b64, filename, ...extras }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
            this._render(tab, data);
        } catch (err) {
            this._showError(tab, err.message);
        } finally {
            this._setLoading(tab, false);
        }
    }

    copyMessage() {
        navigator.clipboard.writeText(document.getElementById('result-decode-text').textContent);
    }

    // Private 
    _extras(tab) {
        if (tab !== 'encode') return {};
        const message = document.getElementById('encode-message').value.trim();
        if (!message) { alert('Please enter a message to hide.'); return null; }
        return { message };
    }

    _render(tab, data) {
        const card = document.getElementById(`result-${tab}`);
        card.classList.add('visible');
        card.classList.remove('error');
        ({ encode: () => this._renderEncode(data),
           decode: () => this._renderDecode(data),
           analyze: () => this._renderAnalyze(data) })[tab]();
    }

    _renderEncode(data) {
        const mime = data.format === 'png' ? 'image/png' : 'image/jpeg';
        const ext  = data.format === 'png' ? 'png' : 'jpg';
        const url  = URL.createObjectURL(this._b64ToBlob(data.image_b64, mime));

        document.getElementById('result-encode-label').textContent = 'Stego image';
        const img = document.getElementById('result-encode-img');
        img.src = url;
        img.style.display = 'block';
        const link = document.getElementById('download-link');
        link.href = url;
        link.download = `stego.${ext}`;
        document.getElementById('result-encode-actions').style.display = 'flex';
    }

    _renderDecode(data) {
        const hasMsg = Boolean(data.message);
        document.getElementById('result-decode-label').textContent =
            hasMsg ? 'Extracted message' : 'No encoded message was detected.';
        document.getElementById('result-decode-text').textContent  = data.message || '';
        document.getElementById('result-decode-copy').style.display = hasMsg ? 'flex' : 'none';
    }

    _renderAnalyze(data) {
        document.getElementById('result-analyze-label').textContent =
            `Detector scores — ${data.format.toUpperCase()}`;
        document.getElementById('scores-list').innerHTML = data.scores.map(s => {
            const interp = (DETECTOR_INTERPRETERS[s.detector] || _DEFAULT_INTERPRET)(s.score);
            return `<div class="score-row">
                <div class="score-name">${fmtDetector(s.detector)}</div>
                <div class="score-value">${s.score.toFixed(4)}</div>
                <div class="score-label ${interp.level}">${interp.label}</div>
            </div>`;
        }).join('');
    }

    _refreshMethodHint(tab, file) {
        if (tab !== 'encode') return;
        const hint = document.getElementById('encode-method-hint');
        if (!hint) return;
        if (!file) { hint.textContent = ''; hint.style.display = 'none'; return; }
        const method = file.format === 'png' ? 'spatial LSB (k=1, row-major)' : 'DCT-LSB (JSteg-style, JPEG Q=95)';
        hint.textContent = `Embedding method: ${method}`;
        hint.style.display = 'block';
    }

    _showError(tab, message) {
        const card = document.getElementById(`result-${tab}`);
        card.classList.add('visible', 'error');
        document.getElementById(`result-${tab}-label`).textContent = message;
        if (tab === 'encode') {
            document.getElementById('result-encode-img').style.display = 'none';
            document.getElementById('result-encode-actions').style.display = 'none';
        }
        if (tab === 'decode') {
            document.getElementById('result-decode-copy').style.display = 'none';
        }
    }

    _clearResult(tab) {
        document.getElementById(`result-${tab}`).classList.remove('visible', 'error');
    }

    _setLoading(tab, on) {
        document.getElementById(`btn-${tab}`).disabled = on;
        document.getElementById(`spinner-${tab}`).classList.toggle('visible', on);
    }

    _b64ToBlob(b64, mime) {
        const bytes = atob(b64);
        const arr   = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.codePointAt(i);
        return new Blob([arr], { type: mime });
    }
}

const toolbox = new ToolboxApp();
