/* Stego Explorer application logic */

// Static profile metadata — mirrors src/pipeline/profile.py
var PROFILE_META = {
    prototype:   { n_groups: 20,  active_methods: ['lsb'],        active_payload_levels: ['low'],                    n_detectors: 3 },
    full_design: { n_groups: 500, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'],  n_detectors: 5 },
};

var STATE = {
    page: 'runs',
    runId: null,
    tab: 'overview',
    search: '',
    renderToken: 0,
    terminalOpen: true,
    lastEngine: 'stub',
    lastProfile: 'prototype',
    jobs: {}
    /* jobs[jobId] = { jobId, runId, logLines, streamSource, streamErrors, failed, error, killed } */
};

function createJob(jobId, profile, engine) {
    STATE.jobs[jobId] = { jobId: jobId, runId: null, logLines: ['Starting…'], streamSource: null, streamErrors: 0, failed: false, error: null, killed: false, profile: profile || null, engine: engine || null };
    return STATE.jobs[jobId];
}
function getJob(jobId) { return STATE.jobs[jobId]; }
function getJobForRun(runId) {
    return Object.values(STATE.jobs).find(function(j) { return j.runId === runId || j.jobId === runId; });
}
function isRunActive(runId) {
    return Object.values(STATE.jobs).some(function(j) { return (j.runId === runId || j.jobId === runId) && !!j.streamSource; });
}
function getActiveJobs() { return Object.values(STATE.jobs).filter(function(j) { return !!j.streamSource; }); }

var SOURCE_COLORS = { real: '#7bd0ff', ml_a: '#ee7d77', ml_b: '#66d9a0' };
var ENCRYPTION_COLORS = { plain: '#7bd0ff', encrypted: '#d4cdee' };
var DETECTOR_PALETTE = ['#7bd0ff', '#ee7d77', '#66d9a0', '#d4cdee', '#f0c050', '#47c4ff'];
var SIDEBAR_TABS = [
    { id: 'overview', icon: 'dashboard', label: 'Overview' },
    { id: 'results', icon: 'analytics', label: 'Results' },
    { id: 'covers', icon: 'collections', label: 'Gallery' },
    { id: 'conditions', icon: 'science', label: 'Conditions' }
];

async function api(url, options) {
    var response = await fetch(url, options);
    if (!response.ok) {
        var text = await response.text();
        throw new Error(text || ('Request failed: ' + response.status));
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
    return '<span class="material-symbols-outlined' + (extraClass ? ' ' + extraClass : '') + '">' + escapeHtml(name) + '</span>';
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

function statusPill(label, tone) {
    return '<span class="status-pill ' + tone + '">' + escapeHtml(label) + '</span>';
}

function uniqueValues(list, key) {
    var seen = {};
    return list.filter(function (item) {
        if (seen[item[key]]) return false;
        seen[item[key]] = true;
        return true;
    }).map(function (item) { return item[key]; });
}

function updateNavState() {
    var activePage = STATE.page === 'run-detail' ? 'runs' : STATE.page;
    var runsEl     = document.getElementById('nav-runs');
    var docsEl     = document.getElementById('nav-docs');
    var proposalEl = document.getElementById('nav-proposal');
    if (runsEl)     runsEl.classList.toggle('active',     activePage === 'runs');
    if (docsEl)     docsEl.classList.toggle('active',     activePage === 'docs');
    if (proposalEl) proposalEl.classList.toggle('active', activePage === 'proposal');
}

function go(page, runId) {
    if (page === 'launch') {
        openLaunchPanel();
        return;
    }
    var nextRunId = runId || null;
    var nextTab = 'overview';
    if (page === 'run-detail' && STATE.page === 'run-detail' && STATE.runId === nextRunId) {
        nextTab = STATE.tab;
    }

    STATE.page = page;
    STATE.runId = nextRunId;
    STATE.tab = nextTab;
    render();
}

function switchTab(tab) {
    if (STATE.page !== 'run-detail') return;
    STATE.tab = tab;
    render();
}

function filterRuns(query) {
    STATE.search = query || '';
    if (STATE.page === 'runs') render();
}

function syncSearchInput() {
    var input = document.getElementById('search-input');
    if (input && input.value !== STATE.search) input.value = STATE.search;
}

function showSidebar(runId, activeTab) {
    var sidebar = document.getElementById('sidebar');
    var main = document.getElementById('main');
    var runIdEl = document.getElementById('sidebar-run-id');
    var logLink = document.getElementById('sidebar-log-link');

    sidebar.classList.remove('is-hidden');
    main.classList.add('with-sidebar');
    runIdEl.textContent = runId;
    runIdEl.classList.remove('none');

    document.getElementById('sidebar-tabs').innerHTML = SIDEBAR_TABS.map(function (tab) {
        var cls = 'sidebar-tab' + (tab.id === activeTab ? ' active' : '');
        return '<a class="' + cls + '" onclick="switchTab(\'' + tab.id + '\')">' +
            icon(tab.icon) + '<span>' + escapeHtml(tab.label) + '</span></a>';
    }).join('');

    if (logLink) logLink.style.display = 'none';
}

function hideSidebar() {
    var sidebar = document.getElementById('sidebar');
    var main = document.getElementById('main');
    var runIdEl = document.getElementById('sidebar-run-id');
    var logLink = document.getElementById('sidebar-log-link');

    sidebar.classList.add('is-hidden');
    main.classList.remove('with-sidebar');
    runIdEl.textContent = 'No run selected';
    runIdEl.classList.add('none');
    if (logLink) logLink.style.display = 'none';
}

function renderLoading() {
    return '<div class="loading-page"><div class="loader"></div></div>';
}

function renderError(message, actionLabel, actionFn) {
    var button = actionLabel && actionFn
        ? '<div class="empty-actions"><button class="btn btn-primary" onclick="' + actionFn + '">' + escapeHtml(actionLabel) + '</button></div>'
        : '';
    return '<div class="empty-state"><h3>Something went off-track</h3><p>' + escapeHtml(message) + '</p>' + button + '</div>';
}

function render() {
    var el = document.getElementById('main');
    var token = ++STATE.renderToken;
    updateNavState();
    syncSearchInput();

    if (STATE.page === 'run-detail' && !STATE.runId) {
        STATE.page = 'runs';
    }

    if (STATE.page === 'runs') {
        hideSidebar();
        el.innerHTML = renderLoading();
        renderRunsList(el, token);
        return;
    }

    if (STATE.page === 'run-detail') {
        el.innerHTML = renderLoading();
        renderRunDetail(el, STATE.runId, token);
        return;
    }

    if (STATE.page === 'docs') {
        hideSidebar();
        el.innerHTML = renderDocsPage();
        initDocsSpy();
        return;
    }

    if (STATE.page === 'proposal') {
        hideSidebar();
        el.innerHTML = renderProposalPage();
        return;
    }

    hideSidebar();
    el.innerHTML = '';
}

// ── Documentation page ──────────────────────────────────────────────────────

var _CHILD_PARENT = {};
var DOCS_TOC = [
    { id: 'overview',   label: 'Overview' },
    { id: 'platform',   label: 'Platform Architecture' },
    { id: 'structure',  label: 'Directory Structure' },
    { id: 'pipeline',   label: 'Pipeline Stages', children: [
        { id: 'stage-covers',    label: 'Download Real Covers' },
        { id: 'stage-manifests', label: 'Generate ML Covers' },
        { id: 'stage-embedding', label: 'Merge Covers Manifest' },
        { id: 'stage-detectors', label: 'run-all (embedding + detection)' },
        { id: 'stage-metrics',   label: 'Compute & Plot Metrics' }
    ]},
    { id: 'embedding',  label: 'Embedding Methods', children: [
        { id: 'lsb-seq',    label: 'LSB Sequential' },
        { id: 'lsb-keyed',  label: 'LSB Keyed' },
        { id: 'dct-lsb',    label: 'DCT LSB (Planned)' }
    ]},
    { id: 'detectors',  label: 'Detectors', children: [
        { id: 'det-rs',          label: 'RS Analysis' },
        { id: 'det-chi-spatial', label: 'Chi-Square Spatial' },
        { id: 'det-sample',      label: 'Sample Pairs' },
        { id: 'det-chi-dct',     label: 'Chi-Square DCT' },
        { id: 'det-calib',       label: 'Calibration Chi-Square' }
    ]},
    { id: 'encryption', label: 'Encryption' },
    { id: 'refs',        label: 'References' }
];
(function() {
    DOCS_TOC.forEach(function(item) {
        (item.children || []).forEach(function(c) { _CHILD_PARENT[c.id] = item.id; });
    });
})();

/* ── HTML micro-helpers ── */
function _ds(id, html)  { return '<section class="docs-section" id="' + id + '">' + html + '</section>'; }
function _dh1(t)        { return '<h1 class="docs-h1">' + t + '</h1>'; }
function _dh2(t)        { return '<h2 class="docs-h2">' + t + '</h2>'; }
function _dh3(t)        { return '<h3 class="docs-h3">' + t + '</h3>'; }
function _dp(t)         { return '<p class="docs-p">' + t + '</p>'; }
function _dpre(t)       { return '<pre class="docs-pre"><code>' + t + '</code></pre>'; }
function _dbadge(t, c)  { return '<span class="docs-badge docs-badge--' + (c || 'default') + '">' + t + '</span>'; }
function _dref(k)       { return '<sup>[<a class="docs-ref-link" href="#ref-' + k + '">' + k + '</a>]</sup>'; }

function renderDocsPage() {
    var tocItems = DOCS_TOC.map(function(item) {
        var sub = (item.children || []).map(function(c) {
            return '<a class="docs-toc-link docs-toc-child" href="#' + c.id + '">' + escapeHtml(c.label) + '</a>';
        }).join('');
        return '<a class="docs-toc-link" href="#' + item.id + '">' + escapeHtml(item.label) + '</a>' + sub;
    }).join('');

    var toc = '<nav class="docs-toc" id="docs-toc">' +
        '<div class="docs-toc-title">Contents</div>' + tocItems +
    '</nav>';

    var main = '<article class="docs-main" id="docs-main">' +
        _docsOverview() + _docsPlatform() + _docsStructure() +
        _docsPipeline() + _docsEmbedding() + _docsDetectors() +
        _docsEncryption() + _docsRefs() +
    '</article>';

    return '<div class="docs-layout">' + toc + main + '</div>';
}

function _docsOverview() {
    return _ds('overview',
        _dh1('Stego Explorer &mdash; Documentation') +
        _dh2('Overview') +
        _dp('Stego Explorer is a self-contained pipeline browser and experiment launcher for Maastricht University Project 2.2 (Spring 2026). It lets you launch pipeline runs, monitor execution in real time via streaming logs, and explore detection results across all experimental conditions.') +
        _dp('The central question is whether the <em>source</em> of the carrier image changes how detectable steganographic embedding is. Three carrier sources are compared: real photographs (COCO/Flickr30k), ML-A (SDXL&nbsp;1.0), and ML-B (PixArt-&alpha; per proposal; FLUX.1-schnell in the prototype &mdash; see Proposal Divergences). Five research questions structure the study:') +
        '<ul class="docs-list">' +
            '<li><strong>RQ1 &mdash; Carrier Source (real vs.&nbsp;ML)</strong>: Does carrier source (real photographs vs.&nbsp;ML-generated images) affect steganographic detectability under matched embedding settings? ML-A and ML-B are pooled into one ML group for this comparison.</li>' +
            '<li><strong>RQ2 &mdash; Generator Effect Within ML</strong>: Within ML-generated carriers, does the choice of generator (ML-A vs.&nbsp;ML-B) affect detectability?</li>' +
            '<li><strong>RQ3 &mdash; Payload Interaction</strong>: Does payload size change the detectability gap between carrier sources?</li>' +
            '<li><strong>RQ4 &mdash; Embedding Branch</strong>: Do the spatial branch (LSB+PNG) and the frequency branch (DCT-LSB+JPEG) show different carrier-source effects? Each branch bundles embedding with its file format.</li>' +
            '<li><strong>RQ5 &mdash; Encryption Invariance</strong>: Does AES-256-CBC encryption of the payload affect detectability? Encrypted payloads should look like random bitstreams, so we expect no difference. A positive result here would suggest the detector is reacting to payload structure rather than to embedding distortion itself.</li>' +
        '</ul>'
    );
}

function _docsPlatform() {
    return _ds('platform',
        _dh2('Platform Architecture') +
        _dp('The viewer is a single-file Python HTTP server (<code>viewer.py</code>) built on the standard library\'s <code>http.server.BaseHTTPRequestHandler</code> and <code>socketserver.ThreadingMixIn</code>. No external web framework is required.') +
        _dh3('Backend (viewer.py)') +
        '<ul class="docs-list">' +
            '<li><strong>Static serving</strong> &mdash; Files under <code>/public/</code> are served with MIME-appropriate cache headers.</li>' +
            '<li><strong>REST API</strong> &mdash; <code>GET /api/runs</code>, <code>GET /api/runs/&lt;id&gt;/detail</code>, <code>DELETE /api/runs/&lt;id&gt;</code>, <code>POST /api/pipeline/start</code>, <code>POST /api/pipeline/kill/&lt;job&gt;</code>.</li>' +
            '<li><strong>Log streaming</strong> &mdash; <code>GET /api/pipeline/stream/&lt;job_id&gt;</code> streams subprocess stdout as Server-Sent Events.</li>' +
            '<li><strong>Cross-instance sync</strong> &mdash; <code>GET /api/events</code> broadcasts filesystem change events to all connected browsers. A background thread polls the <code>runs/</code> directory mtime every 2 seconds and emits a <code>refresh</code> event on any change.</li>' +
            '<li><strong>Multi-instance safety</strong> &mdash; Run IDs embed the server port (e.g. <code>prototype_20260312_p8765</code>). A <code>.running</code> marker file prevents deletion of active runs from any instance.</li>' +
        '</ul>' +
        _dh3('Frontend (public/)') +
        '<ul class="docs-list">' +
            '<li><strong>app.js</strong> &mdash; SPA router, API client, all page renderers, launch drawer, and educational carousel.</li>' +
            '<li><strong>charts.js</strong> &mdash; ROC curve and score distribution renderers using the Canvas 2D API.</li>' +
            '<li><strong>style.css</strong> &mdash; All styles with dark/light theming via CSS custom properties and <code>html.dark</code> / <code>html.light</code> class toggles stored in <code>localStorage</code>.</li>' +
        '</ul>'
    );
}

function _docsStructure() {
    return _ds('structure',
        _dh2('Directory Structure') +
        _dp('All experiment source code lives under <code>src/</code>. Pipeline run outputs are written to <code>runs/</code> (git-ignored). The viewer web app lives in <code>public/</code>.') +
        _dpre(
'steganography/\n' +
'├── src/\n' +
'│   ├── common/          shared contracts and utilities\n' +
'│   ├── data/            raw cover index CSVs\n' +
'│   ├── detection/       steganalysis detectors\n' +
'│   │   ├── rs_analysis.py\n' +
'│   │   ├── chi_square_spatial.py\n' +
'│   │   ├── chi_square_dct.py\n' +
'│   │   ├── calibration_chi_square.py\n' +
'│   │   ├── sample_pairs.py\n' +
'│   │   └── statistical.py      re-exports all detectors\n' +
'│   ├── embedding/       steganographic methods\n' +
'│   │   ├── lsb.py              LSB sequential + keyed\n' +
'│   │   ├── dct.py              DCT-LSB (planned)\n' +
'│   │   └── encryption.py       AES-256-CBC payload encryption\n' +
'│   ├── evaluation/      ROC / AUC computation helpers\n' +
'│   ├── metrics/         image quality metrics (PSNR, SSIM)\n' +
'│   └── pipeline/        orchestration layer\n' +
'│       ├── cli.py              argparse entry point\n' +
'│       ├── config.py           constants (image size, fill rates)\n' +
'│       ├── profile.py          run profiles (prototype / full_design)\n' +
'│       └── runner.py           PipelineRunner: all I/O and stage logic\n' +
'├── runs/                pipeline outputs (git-ignored)\n' +
'├── docs/                project documents and proposals\n' +
'├── public/              viewer web application\n' +
'└── viewer.py            self-contained HTTP server + SPA host'
        )
    );
}

function _docsPipeline() {
    return _ds('pipeline',
        _dh2('Pipeline Stages') +
        _dp('The viewer\'s <strong>Launch Run</strong> button calls <code>python run.py &lt;profile&gt;</code>. This is the single user-facing entry point. It handles cover acquisition, then delegates to the internal <code>src.pipeline.cli run-all</code> command for the embedding and detection stages. All outputs are self-contained under <code>runs/{profile}_{timestamp}/</code>.') +
        _dp('Two run profiles are defined in <code>src/pipeline/profile.py</code>. Conditions = sources(3) &times; methods &times; payload levels &times; encryptions(2).') +
        '<table class="docs-table">' +
            '<thead><tr><th>Profile</th><th>Groups</th><th>Images/run</th><th>Methods</th><th>Fill rates</th><th>Conditions</th></tr></thead>' +
            '<tbody>' +
                '<tr><td><code>prototype</code></td><td>20</td><td>60</td><td>lsb</td><td>low (0.25 bpp)</td><td>6</td></tr>' +
                '<tr><td><code>full_design</code></td><td>500</td><td>1500</td><td>lsb, dct</td><td>low / medium / high</td><td>36</td></tr>' +
            '</tbody>' +
        '</table>' +
        _dp('Cover sources per group: <strong>REAL</strong> (COCO / Flickr30k photograph), <strong>ML-A</strong> (SDXL 1.0), <strong>ML-B</strong> (FLUX.1-schnell in prototype &amp; full_design &mdash; PixArt-&alpha; per proposal, see Proposal Divergences).') +

        _ds('stage-covers', _dh3('1 &middot; Download real covers') +
            _dp('<code>run.py</code> calls <code>src.data.download_real_covers</code> to fetch COCO + Flickr30k images via the HuggingFace Datasets API. Images are written to <code>run_dir/covers/real/</code> and indexed in <code>run_dir/manifests/covers_real.csv</code>. Idempotent: skipped if the manifest already has enough rows.') +
            _dpre('# prototype: 12 COCO + 8 Flickr30k\n# full_design: 300 COCO + 200 Flickr30k')) +

        _ds('stage-manifests', _dh3('2 &middot; Generate ML covers') +
            _dp('Calls <code>src.data.generate_ml_covers</code> to produce SDXL 1.0 (ML-A) and FLUX.1-schnell (ML-B) images from the real-image captions. Engine is selectable: <code>inference_api</code> (HuggingFace Inference API, default), <code>diffusers</code> (local GPU), or <code>stub</code> (synthetic, no GPU).') +
            _dpre('python run.py prototype --ml-engine inference_api\npython run.py prototype --ml-engine stub')) +

        _ds('stage-embedding', _dh3('3 &middot; Merge covers manifest') +
            _dp('Merges <code>covers_real.csv</code>, <code>covers_ml_a.csv</code>, and <code>covers_ml_b.csv</code> into a single <code>run_dir/manifests/covers.csv</code> with standardized grayscale 512&times;512 PNG (spatial) and JPEG Q=95 (frequency) variants for each image.')) +

        _ds('stage-detectors', _dh3('4 &middot; run-all (via src.pipeline.cli)') +
            _dp('With the covers manifest ready, <code>run.py</code> invokes <code>src.pipeline.cli run-all</code> which runs four sub-stages in sequence:') +
            '<ol class="docs-list">' +
                '<li><strong>build-payload-manifest</strong> &mdash; generates pseudo-random payload bytes (seed=42) for each fill rate and encryption variant. The Cartesian product of groups &times; payload levels &times; encryptions is one row per payload artifact.</li>' +
                '<li><strong>build-stego-manifest</strong> &mdash; cross-joins covers &times; methods &times; payload levels &times; encryptions into one row per embedding job (the full experimental design table).</li>' +
                '<li><strong>run-embedding-stage</strong> &mdash; for each stego manifest row: encrypts the payload if required (AES-256-CBC), embeds it using the specified method, and writes the stego image to <code>run_dir/stego/</code>.</li>' +
                '<li><strong>run-detectors</strong> &mdash; scores every active detector against every stego and cover image. Writes <code>run_dir/predictions/predictions.csv</code>. <code>--skip-unimplemented</code> silently skips detectors that raise <code>NotImplementedError</code>.</li>' +
            '</ol>') +

        _ds('stage-metrics', _dh3('5 &middot; compute-metrics &amp; plot-metrics') +
            _dp('<strong>compute-metrics</strong> aggregates predictions into four CSV tables under <code>run_dir/metrics/</code>: per-detector (ROC-AUC, EER, accuracy at Youden\'s J), per-condition, per-source, and quality metrics. These drive the Results and Conditions tabs in the viewer.') +
            _dp('<strong>plot-metrics</strong> (optional, <code>--generate-figures</code>) generates AUC summary figures: AUC by source/detector and AUC by method/detector, written to <code>run_dir/figures/</code>.')
        )
    );
}

function _docsEmbedding() {
    return _ds('embedding',
        _dh2('Embedding Methods') +

        _ds('lsb-seq', _dh3('LSB Sequential') +
            _dbadge('IMPLEMENTED', 'ok') +
            _dp('The primary embedding method. Converts the cover image to 8-bit grayscale, flattens to row-major order, and overwrites the LSB(s) of the first <code>floor(N &times; fill_rate)</code> pixels with payload bits. Sequential order is intentional — it ensures RS analysis, chi-square, and Sample Pairs detectors observe the expected statistical pattern.') +
            _dpre(
'embed_lsb(\n' +
'    cover_image   : Image.Image,\n' +
'    payload_bytes : bytes,\n' +
'    fill_rate     : float,   # 0.25 | 0.50 | 0.75\n' +
'    *,\n' +
'    bit_depth     : int = 1  # bits per pixel replaced\n' +
') -> Image.Image'
            ) +
            _dp('Embedding for each pixel position <em>i</em>:') +
            _dpre(
'mask     = ~((1 << bit_depth) - 1) & 0xFF   # clears target bits\n' +
'stego[i] = (cover[i] & mask) | payload_bits[i]'
            )
        ) +

        _ds('lsb-keyed', _dh3('LSB Keyed') +
            _dbadge('IMPLEMENTED — OPTIONAL EXTENSION', 'warn') +
            _dp('An extension provided in <code>src/embedding/lsb.py</code> but <strong>not used by either run profile</strong>. It shuffles embedding positions using a SHA-256-derived PRNG seed, spreading distortion uniformly but breaking the sequential-order assumption of training-free detectors. The main pipeline always uses sequential LSB.') +
            _dpre(
'embed_lsb_keyed(\n' +
'    cover_image   : Image.Image,\n' +
'    payload_bytes : bytes,\n' +
'    fill_rate     : float,\n' +
'    *,\n' +
'    bit_depth     : int = 1,\n' +
'    key           : str      # passphrase used as PRNG seed\n' +
') -> Image.Image'
            ) +
            _dp('Key derivation: <code>seed = int(sha256(key.encode("utf-8")).hexdigest(), 16)</code>. A <code>random.Random(seed)</code> instance shuffles the full pixel index list; the first <code>usable_pixels</code> positions are used for embedding.')
        ) +

        _ds('dct-lsb', _dh3('DCT LSB (JSteg-style)') +
            _dbadge('PLANNED', 'warn') +
            _dp('JSteg-style LSB replacement in quantised DCT coefficients of JPEG images. DC coefficients and zero-valued AC coefficients are skipped to avoid introducing new non-zero values. Embedding traverses 8&times;8 blocks in row-major order, using the first <code>fill_rate</code> fraction of eligible AC coefficients as positions. Modified coefficients are re-entropy-coded without a second quantization pass.') +
            _dpre(
'embed_dct_lsb_jpeg(\n' +
'    cover_jpeg_bytes : bytes,\n' +
'    payload_bytes    : bytes,\n' +
'    fill_rate        : float,\n' +
'    *,\n' +
'    jpeg_quality     : int = 95\n' +
') -> bytes   # JPEG bytes'
            ) +
            _dp('References: ' + _dref('westfeld1999') + ' ' + _dref('fridrich2003'))
        )
    );
}

function _docsDetectors() {
    return _ds('detectors',
        _dh2('Steganalysis Detectors') +
        _dp('All detectors return a single float score where <strong>higher values indicate stronger evidence of embedding</strong>. Cover images produce low scores; stego images ideally produce high scores. ROC-AUC and EER are computed from the score distributions.') +

        _ds('det-rs', _dh3('RS Analysis') +
            _dbadge('IMPLEMENTED', 'ok') +
            _dp('Pixels are extracted as non-overlapping 2&times;2 blocks (flattened to 4-element vectors). Smoothness <em>f</em> of each block is the sum of absolute differences between adjacent elements. Two masks are then applied to each block:') +
            '<ul class="docs-list">' +
                '<li><strong>Positive mask</strong> &mdash; XOR positions 1 and 2 (0-indexed) with 1, flipping their LSB.</li>' +
                '<li><strong>Negative mask</strong> &mdash; at positions 1 and 2: subtract 1 if the value is even, add 1 if odd.</li>' +
            '</ul>' +
            _dp('Each block is classified by comparing its post-mask smoothness to <em>f</em>:') +
            '<ul class="docs-list">' +
                '<li><strong>Regular (R)</strong> &mdash; smoothness increases after masking</li>' +
                '<li><strong>Singular (S)</strong> &mdash; smoothness decreases after masking</li>' +
            '</ul>' +
            _dp('In an unmodified image R<sub>m</sub>&nbsp;&asymp;&nbsp;R<sub>&minus;m</sub> and S<sub>m</sub>&nbsp;&asymp;&nbsp;S<sub>&minus;m</sub>. LSB replacement disrupts this balance. Score:') +
            _dpre('score = |R_m \u2212 R_\u2212m| + |S_m \u2212 S_\u2212m|') +
            _dp('Computed independently per colour channel; the maximum channel score is returned. ' + _dref('fridrich2001'))
        ) +

        _ds('det-chi-spatial', _dh3('Chi-Square Spatial') +
            _dbadge('IMPLEMENTED', 'ok') +
            _dp('For each of the 128 value pairs (2k,&thinsp;2k+1), the expected count under full LSB replacement is the average of the two observed histogram bins. The chi-square statistic accumulates one term per valid pair (where E&nbsp;&gt;&nbsp;0) using only the even-valued bin:') +
            _dpre(
'E         = (n[2k] + n[2k+1]) / 2\n' +
'\u03c7\u00b2 += (n[2k] \u2212 E)\u00b2 / E       # one term per pair\n' +
'df        = valid pairs \u2212 1\n' +
'score     = chi2.sf(\u03c7\u00b2, df)   # survival function: high = evidence of embedding'
            ) +
            _dp('A cover image has unbalanced pairs (high &chi;&sup2;, low survival probability, low score). An LSB-embedded image has balanced pairs (low &chi;&sup2;, high survival probability, high score). ' + _dref('westfeld1999'))
        ) +

        _ds('det-sample', _dh3('Sample Pairs Analysis') +
            _dbadge('IMPLEMENTED', 'ok') +
            _dp('Analyses the trace multiset T of adjacent pixel pairs across the image in row-major order. T counts pairs (u,&thinsp;v) where one value is even and the other is odd. Sequential LSB embedding predictably shifts these counts. The embedding rate &beta; is estimated by solving a quadratic derived from the shifted multiset statistics.') +
            _dpre(
'sample_pairs_score(\n' +
'    image : Image.Image\n' +
') -> float'
            ) +
            _dp(_dref('dumitrescu2003'))
        ) +

        _ds('det-chi-dct', _dh3('Chi-Square DCT') +
            _dbadge('NOT YET IMPLEMENTED', 'err') +
            _dp('Applies the same chi-square pairs-of-values test as the spatial variant, but to quantised DCT coefficients of a JPEG image. DC coefficients are excluded; only non-zero AC values are tested. Targeted at stego images produced by DCT-LSB embedding.') +
            _dpre(
'chi_square_dct_score(\n' +
'    jpeg_bytes : bytes\n' +
') -> float'
            ) +
            _dp(_dref('westfeld1999'))
        ) +

        _ds('det-calib', _dh3('Calibration Chi-Square') +
            _dbadge('NOT YET IMPLEMENTED', 'err') +
            _dp('Improves on the DCT chi-square by constructing a calibration reference: the suspect JPEG is cropped by a non-block-aligned offset (typically 4 pixels), re-compressed at the same quality factor, and its DCT histogram is compared against the original. This subtracts the natural DCT statistics shared by both, leaving only embedding artefacts.') +
            _dpre(
'calibration_chi_square_score(\n' +
'    jpeg_bytes   : bytes,\n' +
'    *,\n' +
'    jpeg_quality : int = 95\n' +
') -> float'
            ) +
            _dp(_dref('fridrich2003'))
        )
    );
}

function _docsEncryption() {
    return _ds('encryption',
        _dh2('Encryption') +
        _dp('Before embedding, the payload can optionally be encrypted with AES-256-CBC. This is controlled by the <em>encryption</em> column of the stego manifest &mdash; each job specifies <code>plain</code> or <code>aes256cbc</code>.') +
        _dpre(
'encrypt_payload_aes_256_cbc(\n' +
'    payload : bytes,\n' +
'    key     : bytes,   # exactly 32 bytes\n' +
'    iv      : bytes    # exactly 16 bytes (CBC IV)\n' +
') -> bytes'
        ) +
        '<ul class="docs-list">' +
            '<li>AES-256 in CBC mode with PKCS#7 padding (128-bit blocks), using the <code>cryptography</code> library.</li>' +
            '<li>IV is derived deterministically: <code>SHA-256(f"{group_id}:{payload_level}".encode())[:16]</code>. This makes ciphertext fully reproducible for a fixed group and payload level without storing the IV separately.</li>' +
            '<li>The payload itself is a <strong>pseudo-random bitstream</strong> generated by the pipeline (seeded by <code>payload_seed=42</code>). The plain variant embeds this bitstream directly; the encrypted variant embeds its AES-256-CBC ciphertext.</li>' +
            '<li>Encryption is an in-memory operation; <code>PipelineRunner</code> handles all file I/O.</li>' +
            '<li>Since both the plaintext payload and the ciphertext are statistically close to uniform random bytes, the detectability difference between the two encryption conditions measures only the overhead introduced by PKCS#7 block alignment (RQ5).</li>' +
        '</ul>'
    );
}

function _docsRefs() {
    return _ds('refs',
        _dh2('References') +
        '<ol class="docs-ref-list">' +
            '<li id="ref-fridrich2001"><strong>[fridrich2001]</strong> Fridrich, J., Goljan, M., and Du, R. &ldquo;Reliable detection of LSB steganography in color and grayscale images.&rdquo; <em>IEEE Multimedia</em>, vol.&nbsp;8, no.&nbsp;4, pp.&nbsp;22&ndash;28, 2001.</li>' +
            '<li id="ref-westfeld1999"><strong>[westfeld1999]</strong> Westfeld, A. and Pfitzmann, A. &ldquo;Attacks on steganographic systems.&rdquo; Proc. <em>Information Hiding (IH)</em>, LNCS 1768, pp.&nbsp;61&ndash;76, 1999.</li>' +
            '<li id="ref-dumitrescu2003"><strong>[dumitrescu2003]</strong> Dumitrescu, S., Wu, X., and Wang, Z. &ldquo;Detection of LSB steganography via sample pair analysis.&rdquo; <em>IEEE Trans. Signal Process.</em>, vol.&nbsp;51, no.&nbsp;7, pp.&nbsp;1995&ndash;2007, 2003.</li>' +
            '<li id="ref-fridrich2003"><strong>[fridrich2003]</strong> Fridrich, J., Goljan, M., and Hogea, D. &ldquo;Steganalysis of JPEG images: breaking the F5 algorithm.&rdquo; Proc. <em>Information Hiding (IH)</em>, LNCS 2578, pp.&nbsp;310&ndash;323, 2003.</li>' +
        '</ol>'
    );
}

function initDocsSpy() {
    var links    = document.querySelectorAll('.docs-toc-link');
    var sections = document.querySelectorAll('.docs-section[id]');
    if (!sections.length) return;

    /* Smooth scroll on TOC clicks */
    links.forEach(function(a) {
        a.addEventListener('click', function(e) {
            e.preventDefault();
            var target = document.getElementById(a.getAttribute('href').slice(1));
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    /* Scroll spy */
    var obs = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (!entry.isIntersecting) return;
            links.forEach(function(l) { l.classList.remove('active'); });
            var id = entry.target.id;
            var a = document.querySelector('.docs-toc-link[href="#' + id + '"]');
            if (a) {
                a.classList.add('active');
                var parentId = _CHILD_PARENT[id];
                if (parentId) {
                    var pa = document.querySelector('.docs-toc-link[href="#' + parentId + '"]');
                    if (pa) pa.classList.add('active');
                }
            }
        });
    }, { rootMargin: '-8% 0px -78% 0px', threshold: 0 });

    sections.forEach(function(s) { obs.observe(s); });
}

var PROPOSAL_DIVERGENCES = [
    {
        title: 'Image Generation Model',
        proposed: 'PixArt-\u03b1',
        actual: 'FLUX',
        reason: 'No hosted PixelArt model was available on the HuggingFace Inference API, and running models locally was not feasible for most team members. FLUX was chosen as the nearest accessible alternative.'
    },
    {
        title: 'Vertical Prototype Coverage',
        proposed: 'LSB + DCT',
        actual: 'LSB only',
        reason: 'The proposal states the vertical prototype validates both the LSB and DCT embedding branches. In practice, only the LSB branch is validated in depth for the prototype. DCT will be included in the full design run.'
    },
    {
        title: 'Prototype Payload Level',
        proposed: 'Medium',
        actual: 'Low',
        reason: 'The prototype pipeline uses low payload capacity to establish a clean baseline with minimal distortion. Medium and high levels will be re-introduced in the full design run once the detection pipeline is validated.'
    }
];

function renderProposalPage() {
    var cards = PROPOSAL_DIVERGENCES.map(function(d) {
        return '<div class="div-card">' +
            '<div class="div-card-badge">DIVERGENCE</div>' +
            '<div class="div-card-title">' + escapeHtml(d.title) + '</div>' +
            '<div class="div-card-diff">' +
                '<span class="div-proposed">' + escapeHtml(d.proposed) + '</span>' +
                '<span class="div-arrow">→</span>' +
                '<span class="div-actual">' + escapeHtml(d.actual) + '</span>' +
            '</div>' +
            '<div class="div-card-reason">' + escapeHtml(d.reason) + '</div>' +
        '</div>';
    }).join('');

    return '<div class="proposal-page">' +
        '<div class="proposal-header">' +
            '<div class="proposal-header-left">' +
                '<div class="proposal-header-title">Project Proposal</div>' +
                '<div class="proposal-header-sub">Approved midway proposal — February 2026. The prototype implementation diverges from this plan in the following ways.</div>' +
            '</div>' +
            '<div class="div-cards">' + cards + '</div>' +
        '</div>' +
        '<iframe class="proposal-embed" src="/public/proposal.html"></iframe>' +
    '</div>';
}

// ── Educational carousel (shown on empty runs page) ──────────────────────────

var EDU_SLIDES = [
    {
        tag: 'PROJECT OVERVIEW',
        title: 'Research Questions',
        body: 'Does the source of carrier image affect steganographic detectability? We test three sources — real photographs, ML-generated images using a real photo as reference, and ML-generated images using an AI image as reference — and measure whether statistical detectors behave differently across them.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            '<rect x="8" y="14" width="68" height="34" rx="5" fill="rgba(102,217,160,0.12)" stroke="rgba(102,217,160,0.35)" stroke-width="1.2"/>' +
            '<text x="42" y="28" text-anchor="middle" font-size="8.5" fill="#66d9a0" font-family="monospace" font-weight="700">REAL</text>' +
            '<text x="42" y="41" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">photograph</text>' +
            '<rect x="8" y="58" width="68" height="34" rx="5" fill="rgba(130,120,255,0.12)" stroke="rgba(130,120,255,0.35)" stroke-width="1.2"/>' +
            '<text x="42" y="72" text-anchor="middle" font-size="8.5" fill="#8278ff" font-family="monospace" font-weight="700">ML-A</text>' +
            '<text x="42" y="85" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">real reference</text>' +
            '<rect x="8" y="102" width="68" height="34" rx="5" fill="rgba(240,192,80,0.12)" stroke="rgba(240,192,80,0.35)" stroke-width="1.2"/>' +
            '<text x="42" y="116" text-anchor="middle" font-size="8.5" fill="#f0c050" font-family="monospace" font-weight="700">ML-B</text>' +
            '<text x="42" y="129" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">AI reference</text>' +
            '<line x1="76" y1="31" x2="108" y2="66" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>' +
            '<line x1="76" y1="75" x2="108" y2="75" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>' +
            '<line x1="76" y1="119" x2="108" y2="84" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>' +
            '<rect x="108" y="54" width="52" height="42" rx="5" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" stroke-width="1.2"/>' +
            '<text x="134" y="71" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.5)">LSB</text>' +
            '<text x="134" y="83" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.5)">embed</text>' +
            '<line x1="160" y1="75" x2="185" y2="75" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>' +
            '<polygon points="185,71 193,75 185,79" fill="rgba(255,255,255,0.2)"/>' +
            '<rect x="193" y="54" width="58" height="42" rx="5" fill="rgba(99,179,255,0.1)" stroke="rgba(99,179,255,0.3)" stroke-width="1.2"/>' +
            '<text x="222" y="71" text-anchor="middle" font-size="8" fill="rgba(99,179,255,0.8)">Detect?</text>' +
            '<text x="222" y="85" text-anchor="middle" font-size="18" fill="rgba(99,179,255,0.6)">?</text>' +
        '</svg>'
    },
    {
        tag: 'EMBEDDING METHOD',
        title: 'How LSB Embedding Works',
        body: 'Least Significant Bit replacement encodes a secret bit by overwriting the final bit of a pixel. A pixel of 150 (10010110₂) with a secret bit 1 becomes 151 (10010111₂). The ±1 change is invisible to the eye, but creates statistical regularities that trained detectors can measure.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            '<text x="8" y="22" font-size="9" fill="rgba(255,255,255,0.4)" font-family="monospace">Cover pixel  150₁₀</text>' +
            // 8 bit boxes for 10010110
            ['1','0','0','1','0','1','1','0'].map(function(b,i){
                var x = 8 + i*28; var isLSB = i===7;
                return '<rect x="'+x+'" y="28" width="24" height="24" rx="3" fill="'+(isLSB?'rgba(99,179,255,0.18)':'rgba(255,255,255,0.06)')+'" stroke="'+(isLSB?'rgba(99,179,255,0.5)':'rgba(255,255,255,0.15)')+'" stroke-width="1.2"/>' +
                       '<text x="'+(x+12)+'" y="45" text-anchor="middle" font-size="11" fill="'+(isLSB?'rgba(99,179,255,0.9)':'rgba(255,255,255,0.6)')+'" font-family="monospace" font-weight="600">'+b+'</text>';
            }).join('') +
            '<text x="8" y="76" font-size="8" fill="rgba(255,255,255,0.25)" font-family="monospace">bit 7 (MSB)                bit 0 (LSB)</text>' +
            '<text x="8" y="100" font-size="9" fill="rgba(255,255,255,0.4)" font-family="monospace">Stego pixel  151₁₀</text>' +
            ['1','0','0','1','0','1','1','1'].map(function(b,i){
                var x = 8 + i*28; var isLSB = i===7;
                return '<rect x="'+x+'" y="106" width="24" height="24" rx="3" fill="'+(isLSB?'rgba(102,217,160,0.25)':'rgba(255,255,255,0.06)')+'" stroke="'+(isLSB?'rgba(102,217,160,0.7)':'rgba(255,255,255,0.15)')+'" stroke-width="1.2"/>' +
                       '<text x="'+(x+12)+'" y="123" text-anchor="middle" font-size="11" fill="'+(isLSB?'#66d9a0':'rgba(255,255,255,0.6)')+'" font-family="monospace" font-weight="600">'+b+'</text>';
            }).join('') +
            '<text x="216" y="62" font-size="18" fill="rgba(240,192,80,0.7)">↓</text>' +
            '<text x="205" y="91" font-size="8" fill="rgba(240,192,80,0.5)" font-family="monospace">secret bit</text>' +
        '</svg>'
    },
    {
        tag: 'DETECTOR · RS ANALYSIS',
        title: 'Regular-Singular (RS) Analysis',
        body: 'Pixels are partitioned into groups of 4. A flipping mask (+1/−1) is applied, and each group is classified as Regular (lower variance after flip), Singular (higher variance), or Unusable. In a clean image R ≈ R̄ and S ≈ S̄. LSB replacement predictably shifts these counts, revealing embedding.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            // pixel group
            '<text x="8" y="18" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Pixel group (4 px)</text>' +
            [148,151,149,150].map(function(v,i){
                var x = 8+i*46;
                return '<rect x="'+x+'" y="24" width="38" height="28" rx="4" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>' +
                       '<text x="'+(x+19)+'" y="43" text-anchor="middle" font-size="10" fill="rgba(255,255,255,0.7)" font-family="monospace">'+v+'</text>';
            }).join('') +
            '<text x="8" y="68" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Apply mask  [+1,−1,+1,−1]</text>' +
            [149,150,150,149].map(function(v,i){
                var x = 8+i*46;
                return '<rect x="'+x+'" y="74" width="38" height="28" rx="4" fill="rgba(130,120,255,0.1)" stroke="rgba(130,120,255,0.3)" stroke-width="1"/>' +
                       '<text x="'+(x+19)+'" y="93" text-anchor="middle" font-size="10" fill="rgba(130,120,255,0.9)" font-family="monospace">'+v+'</text>';
            }).join('') +
            '<text x="8" y="122" font-size="8" fill="rgba(255,255,255,0.3)">Variance decreased →</text>' +
            '<rect x="152" y="110" width="60" height="22" rx="4" fill="rgba(102,217,160,0.12)" stroke="rgba(102,217,160,0.35)" stroke-width="1.2"/>' +
            '<text x="182" y="125" text-anchor="middle" font-size="9.5" fill="#66d9a0" font-weight="700">REGULAR</text>' +
        '</svg>'
    },
    {
        tag: 'DETECTOR · CHI-SQUARE',
        title: 'Chi-Square Spatial Attack',
        body: 'LSB replacement pairs up pixel values that differ only in their final bit (2k ↔ 2k+1). In a natural image these pairs have different frequencies; embedding equalises them toward a 50/50 split. The chi-square statistic quantifies how far the observed pair frequencies deviate from this expected equipartition.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            '<text x="14" y="16" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Cover image pairs</text>' +
            // bars for cover (unequal pairs)
            [[14,62],[20,38],[18,28],[24,48],[16,34],[22,44],[12,18],[20,32]].map(function(pair,i){
                var x = 14+i*28; var h1=pair[0]*1.1; var h2=pair[1]*1.1; var base=130;
                return '<rect x="'+x+'" y="'+(base-h1)+'" width="10" height="'+h1+'" rx="1" fill="rgba(99,179,255,0.5)"/>' +
                       '<rect x="'+(x+12)+'" y="'+(base-h2)+'" width="10" height="'+h2+'" rx="1" fill="rgba(99,179,255,0.25)"/>';
            }).join('') +
            '<line x1="14" y1="130" x2="248" y2="130" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>' +
            '<text x="14" y="145" font-size="7.5" fill="rgba(99,179,255,0.6)" font-family="monospace">2k vs 2k+1 pairs — natural distribution</text>' +
        '</svg>'
    },
    {
        tag: 'DETECTOR · SAMPLE PAIRS',
        title: 'Sample Pairs Analysis',
        body: 'Analyses the multiset statistics of adjacent pixel pairs across the image. Sequential LSB embedding predictably shifts the count of pairs where one value is even and the other odd (the "trace" multiset). The estimated embedding rate β is derived directly from these shifted counts.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            '<text x="8" y="16" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Adjacent pixel pairs</text>' +
            // 4x3 grid of pairs
            [
                [148,151],[150,149],[147,152],[151,148],
                [149,150],[152,151],[148,149],[150,151],
                [151,152],[147,148],[150,149],[152,153]
            ].map(function(pair,i){
                var col=i%4; var row=Math.floor(i/4);
                var x=8+col*60; var y=26+row*36;
                var isOddEven = (pair[0]%2===0 && pair[1]%2===1)||(pair[0]%2===1 && pair[1]%2===0);
                return '<rect x="'+x+'" y="'+y+'" width="24" height="22" rx="3" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>' +
                       '<text x="'+(x+12)+'" y="'+(y+15)+'" text-anchor="middle" font-size="8.5" fill="rgba(255,255,255,'+(pair[0]%2===1?'0.75':'0.45')+')" font-family="monospace">'+pair[0]+'</text>' +
                       '<rect x="'+(x+28)+'" y="'+y+'" width="24" height="22" rx="3" fill="'+(isOddEven?'rgba(240,192,80,0.15)':'rgba(255,255,255,0.06)')+'" stroke="'+(isOddEven?'rgba(240,192,80,0.4)':'rgba(255,255,255,0.12)')+'" stroke-width="1"/>' +
                       '<text x="'+(x+40)+'" y="'+(y+15)+'" text-anchor="middle" font-size="8.5" fill="'+(isOddEven?'rgba(240,192,80,0.9)':'rgba(255,255,255,0.45)')+'" font-family="monospace">'+pair[1]+'</text>';
            }).join('') +
            '<text x="8" y="142" font-size="7.5" fill="rgba(240,192,80,0.6)">highlighted = odd/even pairs (trace multiset)</text>' +
        '</svg>'
    },
    {
        tag: 'EXPERIMENTAL DESIGN',
        title: 'Pipeline at a Glance',
        body: 'The prototype validates the full pipeline at small scale: 20 image groups, 1 embedding method (LSB), 1 payload level, 3 statistical detectors. The full design run scales to 500 groups, 2 methods, 3 payload levels, and 5 detectors — producing ~15,000 individual detection scores per run.',
        visual: '<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">' +
            // Row labels
            '<text x="10" y="26" font-size="8" fill="rgba(102,217,160,0.7)" font-family="monospace" font-weight="700">PROTOTYPE</text>' +
            '<text x="10" y="92" font-size="8" fill="rgba(99,179,255,0.7)" font-family="monospace" font-weight="700">FULL DESIGN</text>' +
            // Divider
            '<line x1="10" y1="60" x2="250" y2="60" stroke="rgba(255,255,255,0.07)" stroke-width="1"/>' +
            // Prototype stats: 4 cells
            [
                ['20','groups'],['1','method'],['1','payload'],['3','detectors']
            ].map(function(s,i){
                var x = 10 + i*60;
                return '<text x="'+(x+22)+'" y="47" text-anchor="middle" font-size="18" fill="rgba(102,217,160,0.9)" font-family="monospace" font-weight="700">'+s[0]+'</text>' +
                       '<text x="'+(x+22)+'" y="57" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.3)" font-family="monospace">'+s[1]+'</text>';
            }).join('') +
            // Full design stats: 4 cells
            [
                ['500','groups'],['2','methods'],['3','payloads'],['5','detectors']
            ].map(function(s,i){
                var x = 10 + i*60;
                return '<text x="'+(x+22)+'" y="115" text-anchor="middle" font-size="18" fill="rgba(99,179,255,0.9)" font-family="monospace" font-weight="700">'+s[0]+'</text>' +
                       '<text x="'+(x+22)+'" y="125" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.3)" font-family="monospace">'+s[1]+'</text>';
            }).join('') +
        '</svg>'
    }
];

var _eduTimer = null;
var _eduIdx = 0;

function buildEduCarousel() {
    var dots = EDU_SLIDES.map(function(_, i) {
        return '<button class="edu-dot' + (i === 0 ? ' active' : '') + '" onclick="eduGoTo(' + i + ')"></button>';
    }).join('');

    var slides = EDU_SLIDES.map(function(s) {
        return '<div class="edu-slide">' +
            '<div class="edu-visual">' + s.visual + '</div>' +
            '<div class="edu-text">' +
                '<div class="edu-tag">' + escapeHtml(s.tag) + '</div>' +
                '<div class="edu-title">' + escapeHtml(s.title) + '</div>' +
                '<div class="edu-body">' + escapeHtml(s.body) + '</div>' +
            '</div>' +
        '</div>';
    }).join('');

    return '<div class="edu-section">' +
        '<div class="edu-label">While you wait — project primer</div>' +
        '<div class="edu-carousel" id="edu-carousel">' +
            '<div class="edu-track" id="edu-track">' + slides + '</div>' +
            '<button class="edu-arrow edu-prev" onclick="eduPrev()" aria-label="Previous">&#8249;</button>' +
            '<button class="edu-arrow edu-next" onclick="eduNext()" aria-label="Next">&#8250;</button>' +
            '<div class="edu-dots">' + dots + '</div>' +
        '</div>' +
    '</div>';
}

function initEduCarousel() {
    _eduIdx = 0;
    clearInterval(_eduTimer);
    _eduTimer = setInterval(function() { eduNext(); }, 7000);
}

function eduGoTo(idx) {
    _eduIdx = (idx + EDU_SLIDES.length) % EDU_SLIDES.length;
    var track = document.getElementById('edu-track');
    if (track) track.style.transform = 'translateX(-' + (_eduIdx * 100) + '%)';
    document.querySelectorAll('.edu-dot').forEach(function(d, i) {
        d.classList.toggle('active', i === _eduIdx);
    });
    clearInterval(_eduTimer);
    _eduTimer = setInterval(function() { eduNext(); }, 7000);
}

function eduNext() { eduGoTo(_eduIdx + 1); }
function eduPrev() { eduGoTo(_eduIdx - 1); }

async function renderRunsList(el, token) {
    try {
        var runs = await api('/api/runs');
        if (token !== STATE.renderToken) return;

        if (!runs.length) {
            el.innerHTML =
                '<div class="empty-state">' +
                    '<h3>No runs yet</h3>' +
                    '<p>Launch a prototype run to seed the explorer with pipeline output.</p>' +
                    '<div class="empty-actions">' +
                        '<button class="btn btn-primary" onclick="openLaunchPanel()">' + icon('add') + ' New Run</button>' +
                    '</div>' +
                '</div>' +
                buildEduCarousel();
            initEduCarousel();
            return;
        }

        var filtered = filterRunCollection(runs, STATE.search);
        var stats = summarizeRuns(runs);
        var activity = buildActivityFeed(runs);
        var tip = buildRunsTip(runs, stats);
        var rows = filtered.map(buildRunRow).join('');

        el.innerHTML =
            '<div class="breadcrumb">' +
                '<span>Explorer</span>' +
                '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                '<span class="breadcrumb-active">Pipeline Runs</span>' +
            '</div>' +
            '<div class="page-header">' +
                '<div>' +
                    '<div class="page-title">Runs Overview</div>' +
                    '<div class="page-subtitle">' + escapeHtml(buildRunsSubtitle(filtered.length, runs.length, STATE.search)) + '</div>' +
                '</div>' +
                '<button class="btn btn-primary" onclick="openLaunchPanel()">' + icon('add') + ' New Run</button>' +
            '</div>' +
            '<div class="stats-bento">' +
                '<div class="bento-card"><div class="bento-label">Best Global AUC</div><div class="bento-value primary">' + formatMaybeNumber(stats.bestAuc, 3) + '</div><div class="bento-sub">' + escapeHtml(stats.bestRunLabel) + '</div></div>' +
                '<div class="bento-card"><div class="bento-label">Tracked Runs</div><div class="bento-value">' + formatNumber(runs.length) + '</div><div class="bento-sub">' + formatNumber(stats.completedRuns) + ' with metrics</div></div>' +
                '<div class="bento-card"><div class="bento-label">Processed Covers</div><div class="bento-value">' + formatNumber(stats.totalImages) + '</div><div class="bento-sub">' + formatNumber(stats.totalGroups) + ' grouped specimens</div></div>' +
                '<div class="bento-card"><div class="bento-label">Detector Evaluations</div><div class="bento-value">' + formatNumber(stats.totalDetectors) + '</div><div class="bento-sub">' + escapeHtml(stats.coverageLabel) + '</div></div>' +
            '</div>' +
            buildRunsTable(filtered, runs.length, rows) +
            '<div class="panels-row">' +
                '<div class="glass-panel">' +
                    '<div class="glass-panel-head"><div class="glass-panel-title">Recent Activity</div></div>' +
                    '<div class="glass-panel-body"><div class="activity-feed">' + activity + '</div></div>' +
                '</div>' +
                '<div class="glass-panel">' +
                    '<div class="glass-panel-head"><div class="glass-panel-title">Analysis Tip</div></div>' +
                    '<div class="glass-panel-body">' + tip + '</div>' +
                '</div>' +
            '</div>' +
            buildEduCarousel();
        initEduCarousel();
    } catch (error) {
        if (token !== STATE.renderToken) return;
        el.innerHTML = renderError(error.message, 'Retry', 'render()');
    }
}

function filterRunCollection(runs, search) {
    var query = (search || '').trim().toLowerCase();
    if (!query) return runs;
    return runs.filter(function (run) {
        var cfg = run.config || {};
        var haystack = [
            run.id,
            cfg.profile,
            toArray(cfg.active_methods).join(' '),
            toArray(cfg.active_payload_levels).join(' '),
            cfg.timestamp
        ].join(' ').toLowerCase();
        return haystack.indexOf(query) !== -1;
    });
}

function summarizeRuns(runs) {
    var summary = {
        bestAuc: null,
        bestRunLabel: 'Awaiting detector output',
        completedRuns: 0,
        totalImages: 0,
        totalGroups: 0,
        totalDetectors: 0,
        coverageLabel: 'No detector metrics yet'
    };

    runs.forEach(function (run) {
        var cfg = run.config || {};
        var groups = Number(cfg.n_groups || 0);
        summary.totalGroups += groups;
        summary.totalImages += groups * 3;
        summary.totalDetectors += Number(run.n_detectors || 0);
        if (run.has_results) summary.completedRuns += 1;
        if (run.best_auc != null && (summary.bestAuc == null || run.best_auc > summary.bestAuc)) {
            summary.bestAuc = Number(run.best_auc);
            summary.bestRunLabel = run.id;
        }
    });

    if (summary.totalDetectors) {
        summary.coverageLabel = formatNumber(summary.totalDetectors) + ' total detector rows';
    }

    return summary;
}

function buildRunsSubtitle(filteredCount, totalCount, search) {
    if (search) {
        return 'Showing ' + filteredCount + ' of ' + totalCount + ' runs for "' + search + '".';
    }
    return totalCount + ' experiment run' + (totalCount === 1 ? '' : 's') + ' currently available in the local explorer.';
}

function buildRunRow(run) {
    var cfg = run.config || {};
    // is_active / is_killed from API covers runs launched by other instances
    var isActive = isRunActive(run.id) || !!run.is_active;
    var isKilled = !isActive && (run.is_killed || (getJobForRun(run.id) || {}).killed);
    var activeJob = getJobForRun(run.id);
    // Parse profile from run ID as last resort (format: {profile}_{timestamp}_p{port})
    var profileFromId = Object.keys(PROFILE_META).find(function(k) { return run.id.startsWith(k); }) || null;
    var profile = cfg.profile || (activeJob && activeJob.profile) || profileFromId || (isActive ? '…' : 'unconfigured');
    // Use static profile metadata as fallback when config.json not yet written
    var meta = PROFILE_META[profile] || null;
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var levels = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    var nDetectors = run.n_detectors || (meta ? meta.n_detectors : 0);
    var runStatus = isActive
        ? statusPill('Running', 'running')
        : isKilled
            ? statusPill('Killed', 'error')
            : run.best_auc == null
                ? statusPill(run.has_results ? 'Metrics incomplete' : 'Pending results', run.has_results ? 'error' : 'pending')
                : statusPill('Metrics ready', 'ready');
    var aucCell;

    if (run.best_auc != null) {
        var value = Number(run.best_auc);
        var cls = value > 0.85 ? 'auc-high' : (value > 0.65 ? 'auc-mid' : 'auc-low');
        aucCell = '<span class="auc-badge ' + cls + '">' + value.toFixed(3) + '</span>';
    } else {
        aucCell = '<div class="no-results">' + icon('cloud_off') + '<span>No Results</span></div>';
    }

    var rowClass = isActive ? 'row-active' : (run.has_results ? '' : 'row-dimmed');
    return (
        '<tr' + (rowClass ? ' class="' + rowClass + '"' : '') + ' style="cursor:pointer" onclick="go(\'run-detail\', \'' + escapeAttr(run.id) + '\')">' +
            '<td>' +
                '<div class="run-name">' +
                    (isActive ? '<span class="run-live-dot"></span>' : '') +
                    '<strong>' + escapeHtml(run.id) + '</strong>' +
                    '<div class="run-sub-id">' + escapeHtml(cfg.timestamp || 'local run artifact') + '</div>' +
                '</div>' +
            '</td>' +
            '<td><span class="profile-tag' + (isActive ? ' profile-tag--dim' : '') + '">' + escapeHtml(profile) + '</span></td>' +
            '<td><span class="cell-mono">' + escapeHtml(nGroups != null ? nGroups : '\u2014') + '</span></td>' +
            '<td><span class="cell-dim">' + escapeHtml(methods.length ? methods.join(', ') : '\u2014') + '</span></td>' +
            '<td><span class="cell-dim">' + escapeHtml(levels.length ? levels.join(', ') : '\u2014') + '</span></td>' +
            '<td><div style="display:flex;align-items:center;gap:6px">' + icon('security') + '<span class="cell-mono">' + escapeHtml(nDetectors) + '</span></div></td>' +
            '<td>' + aucCell + '</td>' +
            '<td>' + runStatus + '</td>' +
            '<td>' +
                '<button class="btn-icon" onclick="event.stopPropagation();confirmDeleteRun(\'' + escapeAttr(run.id) + '\')" title="Delete run">' +
                    icon('delete') +
                '</button>' +
            '</td>' +
        '</tr>'
    );
}

function buildRunsTable(filteredRuns, totalRuns, rows) {
    if (!filteredRuns.length) {
        return '<div class="data-table-wrap"><div class="empty-state"><h3>No runs match this search</h3><p>Try a run id, profile name, method, or payload level.</p><div class="empty-actions"><button class="btn btn-ghost" onclick="clearSearch()">Clear Search</button></div></div></div>';
    }

    return (
        '<div class="data-table-wrap">' +
            '<div style="overflow-x:auto">' +
                '<table class="data-table">' +
                    '<thead><tr>' +
                        '<th>Run Name</th>' +
                        '<th>Profile</th>' +
                        '<th>Groups</th>' +
                        '<th>Methods</th>' +
                        '<th>Payloads</th>' +
                        '<th>Detectors</th>' +
                        '<th>Best AUC</th>' +
                        '<th>Status</th>' +
                        '<th>Actions</th>' +
                    '</tr></thead>' +
                    '<tbody>' + rows + '</tbody>' +
                '</table>' +
            '</div>' +
            '<div class="table-footer">' +
                '<span>Displaying ' + filteredRuns.length + ' of ' + totalRuns + ' runs</span>' +
                '<div class="table-footer-actions">' +
                    '<span class="inline-note">' + icon('tips_and_updates') + '<strong>Tip:</strong> click a row to inspect run detail.</span>' +
                '</div>' +
            '</div>' +
        '</div>'
    );
}

function buildActivityFeed(runs) {
    return runs.slice(0, 4).map(function (run, index) {
        var tone = run.best_auc == null ? (run.has_results ? 'red' : 'amber') : (index === 0 ? 'blue' : 'green');
        var text = run.best_auc == null
            ? (run.has_results ? 'Run <strong>' + escapeHtml(run.id) + '</strong> produced partial metrics that need review.' : 'Run <strong>' + escapeHtml(run.id) + '</strong> has been created but has not produced detector metrics yet.')
            : 'Run <strong>' + escapeHtml(run.id) + '</strong> completed with best ROC-AUC <strong>' + escapeHtml(Number(run.best_auc).toFixed(3)) + '</strong>.';
        return '<div class="activity-item">' +
            '<div class="activity-dot ' + tone + '"></div>' +
            '<div><div class="activity-text">' + text + '</div><div class="activity-time">' + escapeHtml((run.config || {}).timestamp || 'local artifact') + '</div></div>' +
        '</div>';
    }).join('');
}

function buildRunsTip(runs, stats) {
    var bestRun = runs.find(function (run) { return stats.bestRunLabel === run.id; });
    var bestProfile = bestRun && bestRun.config && bestRun.config.profile ? bestRun.config.profile : 'prototype';
    var payloads = bestRun && bestRun.config ? toArray(bestRun.config.active_payload_levels) : [];

    return (
        '<div class="tip-icon">' + icon('info') + '</div>' +
        '<div class="tip-title">Best-performing configuration</div>' +
        '<div class="tip-text">' +
            'Right now the strongest local run is <strong>' + escapeHtml(stats.bestRunLabel) + '</strong>. ' +
            'If you want the redesign to guide analysis, start by comparing new runs against the <strong>' + escapeHtml(bestProfile) + '</strong> profile' +
            (payloads.length ? ' across payloads ' + escapeHtml(payloads.join(', ')) + '.' : '.') +
        '</div>'
    );
}

async function renderRunDetail(el, runId, token) {
    try {
        var data = await api('/api/runs/' + encodeURIComponent(runId) + '/detail');
        if (token !== STATE.renderToken) return;
        var isThisRunActive = isRunActive(runId) || !!(data && data.is_active);
        var isThisRunKilled = !isThisRunActive && !!(data && data.is_killed || (getJobForRun(runId) || {}).killed);
        var jobForRun = getJobForRun(runId);

        if (!data || !Object.keys(data).length) {
            if (!isThisRunActive) {
                hideSidebar();
                el.innerHTML = renderError('The selected run could not be found.', 'Back to Runs', 'go(\'runs\')');
                return;
            }
            /* Run just started — show terminal-only initializing state */
            hideSidebar();
            el.innerHTML =
                '<div class="breadcrumb">' +
                    '<a onclick="go(\'runs\')">Runs</a>' +
                    '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                    '<span class="breadcrumb-active">' + escapeHtml(runId) + '</span>' +
                '</div>' +
                '<div class="page-header">' +
                    '<div>' +
                        '<div class="page-title">' + escapeHtml(runId) + '</div>' +
                        '<div class="page-subtitle">Pipeline initializing — awaiting output…</div>' +
                    '</div>' +
                    '<button class="btn btn-ghost" onclick="go(\'runs\')">' + icon('arrow_back') + ' Back to Runs</button>' +
                '</div>' +
                buildTerminalSection(runId);
            attachStream(runId);
            return;
        }

        var cfg = data.config || {};
        var detailStats = summarizeRunDetail(data);
        showSidebar(runId, STATE.tab);

        var body = '';
        if (STATE.tab === 'overview') body = buildOverviewTab(cfg, detailStats, runId);
        if (STATE.tab === 'results') body = buildResultsTab(data, detailStats);
        if (STATE.tab === 'covers') body = buildCoversTab(data.covers || []);
        if (STATE.tab === 'conditions') body = buildConditionsTab(data);

        el.innerHTML =
            '<div class="breadcrumb">' +
                '<a onclick="go(\'runs\')">Runs</a>' +
                '<span class="material-symbols-outlined breadcrumb-sep">chevron_right</span>' +
                '<span class="breadcrumb-active">' + escapeHtml(runId) + '</span>' +
            '</div>' +
            '<div class="page-header">' +
                '<div>' +
                    '<div class="page-title">' + escapeHtml(runId) + '</div>' +
                    '<div class="page-subtitle">' + escapeHtml(isThisRunActive && !cfg.profile ? (jobForRun ? (jobForRun.profile || 'prototype') + ' · ' + (jobForRun.engine || 'stub') + ' engine · running…' : 'Pipeline running…') : buildRunHeader(cfg, detailStats, runId)) + '</div>' +
                '</div>' +
                '<button class="btn btn-ghost" onclick="go(\'runs\')">' + icon('arrow_back') + ' Back to Runs</button>' +
            '</div>' +
            (getJobForRun(runId) ? buildTerminalSection(runId) : (isThisRunKilled ? buildKilledBanner(runId) : '')) +
            (!detailStats.detectorCount && !detailStats.coverGroups
                ? ''  /* suppress stat cards when there is no data to show */
                : '<div class="summary-strip">' +
                      '<div class="summary-card"><div class="summary-label">Best ROC-AUC</div><div class="summary-value primary">' + formatMaybeNumber(detailStats.bestAuc, 3) + '</div><div class="summary-sub">' + escapeHtml(detailStats.bestDetectorLabel) + '</div></div>' +
                      '<div class="summary-card"><div class="summary-label">Detector Rows</div><div class="summary-value">' + formatNumber(detailStats.detectorCount) + '</div><div class="summary-sub">' + escapeHtml(detailStats.sampleLabel) + '</div></div>' +
                      '<div class="summary-card"><div class="summary-label">Cover Groups</div><div class="summary-value">' + formatNumber(detailStats.coverGroups) + '</div><div class="summary-sub">' + escapeHtml(detailStats.coverLabel) + '</div></div>' +
                  '</div>') +
            ((isThisRunActive || isThisRunKilled) && !data.has_results && !detailStats.coverGroups
                ? ''  /* suppress empty tabs while pipeline is still running or was killed early */
                : '<div id="tab-body">' + body + '</div>');

        if (isThisRunActive && jobForRun) attachStream(jobForRun.jobId);
        if (STATE.tab === 'results' && data.has_results) {
            requestAnimationFrame(function () { drawAllCharts(data); });
        }
    } catch (error) {
        if (token !== STATE.renderToken) return;
        hideSidebar();
        el.innerHTML = renderError(error.message, 'Back to Runs', 'go(\'runs\')');
    }
}

function buildKilledBanner(runId) {
    return '<div class="rd-terminal">' +
        '<div class="rd-terminal-hdr">' +
            '<span>' + icon('terminal') + ' Pipeline Output</span>' +
            '<span class="badge badge-error">✗ Killed</span>' +
        '</div>' +
        '<div class="rd-error-banner">' +
            icon('cancel') +
            '<span class="rd-error-msg">This run was killed before it completed. No pipeline output is available from this viewer instance.</span>' +
        '</div>' +
    '</div>';
}

function buildTerminalSection(runId) {
    var job = getJobForRun(runId);
    if (!job || !job.logLines.length) return '';

    var isRunning = !!job.streamSource && !job.failed && !job.killed;
    var isOpen = STATE.terminalOpen;
    var logContent = escapeHtml(job.logLines.join('\n'));

    var statusBadge = isRunning
        ? '<span class="badge badge-running">● Live</span>'
        : (job.failed || job.killed)
            ? '<span class="badge badge-error">' + (job.killed ? '✗ Killed' : '✗ Failed') + '</span>'
            : '<span class="badge badge-done">✓ Completed</span>';

    var killBtn = isRunning
        ? '<button class="rd-kill-btn" onclick="killRun(\'' + escapeAttr(job.jobId) + '\')" title="Kill this run">' +
              '<span class="material-symbols-outlined">stop_circle</span> Kill' +
          '</button>'
        : '';

    var errorBanner = ((job.failed || job.killed) && job.error)
        ? '<div class="rd-error-banner">' +
              '<span class="material-symbols-outlined">error_outline</span>' +
              '<div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div>' +
          '</div>'
        : '';

    var body = isOpen
        ? '<div class="rd-terminal-body">' +
              errorBanner +
              '<div class="lp-terminal-chrome">' +
                  '<span class="lp-dot lp-dot--r"></span>' +
                  '<span class="lp-dot lp-dot--y"></span>' +
                  '<span class="lp-dot lp-dot--g"></span>' +
                  '<span class="lp-terminal-label">sh — ' + escapeHtml(job.runId || job.jobId) + ' — pts/0</span>' +
              '</div>' +
              '<pre class="log-box lp-log-body" id="run-terminal-log">' + logContent + '</pre>' +
          '</div>'
        : '';

    return '<div class="rd-terminal">' +
        '<div class="rd-terminal-hdr" onclick="toggleRunTerminal()">' +
            '<div class="rd-terminal-hdr-left">' +
                '<span class="material-symbols-outlined rd-term-icon">terminal</span>' +
                '<span class="rd-terminal-title">Pipeline Output</span>' +
                statusBadge +
            '</div>' +
            '<div class="rd-terminal-hdr-right">' +
                killBtn +
                '<span class="material-symbols-outlined rd-term-chevron">' + (isOpen ? 'expand_less' : 'expand_more') + '</span>' +
            '</div>' +
        '</div>' +
        body +
    '</div>';
}

function toggleRunTerminal() {
    STATE.terminalOpen = !STATE.terminalOpen;
    var section = document.querySelector('.rd-terminal');
    if (!section) return;
    var chevron = section.querySelector('.rd-term-chevron');
    var job = getJobForRun(STATE.runId);
    var existingBody = section.querySelector('.rd-terminal-body');

    if (STATE.terminalOpen && job) {
        var isRunning = !!job.streamSource && !job.failed && !job.killed;
        var errorBanner = ((job.failed || job.killed) && job.error)
            ? '<div class="rd-error-banner"><span class="material-symbols-outlined">error_outline</span><div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div></div>'
            : '';
        var div = document.createElement('div');
        div.className = 'rd-terminal-body';
        div.innerHTML =
            errorBanner +
            '<div class="lp-terminal-chrome">' +
                '<span class="lp-dot lp-dot--r"></span><span class="lp-dot lp-dot--y"></span><span class="lp-dot lp-dot--g"></span>' +
                '<span class="lp-terminal-label">sh — ' + escapeHtml((job.runId || job.jobId)) + ' — pts/0</span>' +
            '</div>' +
            '<pre class="log-box lp-log-body" id="run-terminal-log">' + escapeHtml(job.logLines.join('\n')) + '</pre>';
        section.appendChild(div);
        var box = div.querySelector('#run-terminal-log');
        if (box) box.scrollTop = box.scrollHeight;
    } else {
        if (existingBody) existingBody.remove();
    }
    if (chevron) chevron.textContent = STATE.terminalOpen ? 'expand_less' : 'expand_more';
}

function summarizeRunDetail(data) {
    var detectorRows = toArray((data.metrics || {}).detector);
    var covers = toArray(data.covers);
    var bestRow = null;
    var sampleTotal = 0;

    detectorRows.forEach(function (row) {
        sampleTotal += Number(row.n_samples || 0);
        if (row.roc_auc != null && (!bestRow || Number(row.roc_auc) > Number(bestRow.roc_auc))) {
            bestRow = row;
        }
    });

    return {
        bestAuc: bestRow ? Number(bestRow.roc_auc) : null,
        bestDetectorLabel: bestRow ? bestRow.detector : 'No detector metrics yet',
        detectorCount: detectorRows.length,
        sampleLabel: sampleTotal ? formatNumber(sampleTotal) + ' samples scored' : 'No evaluation samples',
        coverGroups: covers.length,
        coverLabel: covers.length ? 'three source slots per group' : 'manifest not generated',
        hasResults: !!data.has_results
    };
}

function buildRunHeader(cfg, detailStats, runId) {
    var profileFromId = runId ? (Object.keys(PROFILE_META).find(function(k) { return runId.startsWith(k); }) || null) : null;
    var profile = cfg.profile || profileFromId || 'unconfigured profile';
    var meta = PROFILE_META[profile] || null;
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var nGroups = cfg.n_groups != null ? cfg.n_groups : (meta ? meta.n_groups : null);
    var groups = nGroups != null ? nGroups + ' groups' : 'group count unavailable';
    return [
        profile,
        groups,
        methods.length ? methods.join(', ') : 'no methods listed',
        payloads.length ? 'payloads ' + payloads.join(', ') : 'no payload levels listed',
        detailStats.hasResults ? 'metrics ready' : 'metrics pending'
    ].join(' · ');
}

function buildOverviewTab(cfg, detailStats, runId) {
    var profileFromId = runId ? (Object.keys(PROFILE_META).find(function(k) { return runId.startsWith(k); }) || null) : null;
    var profile = cfg.profile || profileFromId || null;
    var meta = PROFILE_META[profile] || null;
    var groups = cfg.n_groups != null ? Number(cfg.n_groups) : (meta ? meta.n_groups : 0);
    var methods = cfg.active_methods ? toArray(cfg.active_methods) : (meta ? meta.active_methods : []);
    var payloads = cfg.active_payload_levels ? toArray(cfg.active_payload_levels) : (meta ? meta.active_payload_levels : []);
    var conditionCount = methods.length * payloads.length * 2;
    var fillRates = Object.keys(cfg.payload_fill_rates || {}).length
        ? Object.keys(cfg.payload_fill_rates).map(function (key) {
            return key + '=' + cfg.payload_fill_rates[key];
        }).join(', ')
        : '\u2014';

    var rows = [
        ['Profile', profile || '\u2014'],
        ['Groups', groups || '\u2014'],
        ['Methods', methods.length ? methods.join(', ') : '\u2014'],
        ['Payload levels', payloads.length ? payloads.join(', ') : '\u2014'],
        ['Fill rates', fillRates],
        ['Image size', toArray(cfg.image_size).length ? cfg.image_size.join('x') : '\u2014'],
        ['JPEG quality', cfg.jpeg_quality != null ? cfg.jpeg_quality : '\u2014'],
        ['Cover seed', cfg.cover_seed != null ? cfg.cover_seed : '\u2014'],
        ['Payload seed', cfg.payload_seed != null ? cfg.payload_seed : '\u2014'],
        ['Timestamp', cfg.timestamp || '\u2014']
    ].map(function (pair) {
        return '<tr><td>' + escapeHtml(pair[0]) + '</td><td>' + escapeHtml(pair[1]) + '</td></tr>';
    }).join('');

    return (
        '<div class="detail-grid">' +
            '<div class="card">' +
                '<div class="card-head"><span class="card-title">Run Configuration</span></div>' +
                '<table class="config-table">' + rows + '</table>' +
            '</div>' +
            '<div class="detail-note">' +
                '<h3>Operational Note</h3>' +
                '<p>' +
                    (detailStats.hasResults
                        ? 'This run already has detector output, so the fastest way to compare it is through the Results and Conditions tabs. Use the overview as the experiment contract for reproducing the same profile later.'
                        : 'This run has been created, but the explorer cannot see detector metrics yet. That usually means the pipeline has not finished, or the run only produced config scaffolding so far.') +
                '</p>' +
            '</div>' +
        '</div>' +
        '<div class="stats">' +
            '<div class="stat"><div class="stat-val">' + formatNumber(groups) + '</div><div class="stat-lbl">Groups</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(groups * 3) + '</div><div class="stat-lbl">Cover Slots</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(conditionCount) + '</div><div class="stat-lbl">Conditions</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(methods.length) + '</div><div class="stat-lbl">Methods</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatNumber(payloads.length) + '</div><div class="stat-lbl">Payload Levels</div></div>' +
            '<div class="stat"><div class="stat-val">' + formatMaybeNumber(detailStats.bestAuc, 3) + '</div><div class="stat-lbl">Best ROC-AUC</div></div>' +
        '</div>'
    );
}

function buildResultsTab(data, detailStats) {
    if (!data.has_results) {
        return '<div class="empty-state"><h3>No results yet</h3><p>Run the pipeline with detectors enabled to populate charts and score tables.</p></div>';
    }

    var detectorRows = toArray((data.metrics || {}).detector);
    var tableRows = detectorRows.map(function (row) {
        var auc = Number(row.roc_auc || 0);
        var eer = Number(row.eer || 0);
        var acc = Number(row.accuracy_at_youden_j || 0);
        var color = auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)');

        return '<tr>' +
            '<td style="font-weight:600">' + escapeHtml(row.detector) + '</td>' +
            '<td><div class="auc-inline"><div class="auc-fill" style="width:' + Math.max(4, Math.round(auc * 110)) + 'px;background:' + color + '"></div><span class="auc-num" style="color:' + color + '">' + auc.toFixed(3) + '</span></div></td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + (eer * 100).toFixed(1) + '%</td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + (acc * 100).toFixed(1) + '%</td>' +
            '<td class="cell-dim" style="font-family:monospace;font-size:12px">' + escapeHtml(row.n_samples || 0) + '</td>' +
        '</tr>';
    }).join('');

    return (
        '<div class="detail-note" style="margin-bottom:12px">' +
            '<h3>Result Snapshot</h3>' +
            '<p>The current leader is <code>' + escapeHtml(detailStats.bestDetectorLabel) + '</code> with ROC-AUC <code>' + formatMaybeNumber(detailStats.bestAuc, 3) + '</code>. Charts below compare detector strength across source families and encryption state.</p>' +
        '</div>' +
        '<div class="charts-row">' +
            '<div class="chart-box"><div class="chart-title">AUC by Detector</div><canvas id="chart-detector" height="220"></canvas></div>' +
            '<div class="chart-box"><div class="chart-title">AUC by Source</div><canvas id="chart-source" height="220"></canvas></div>' +
        '</div>' +
        '<div class="charts-full"><div class="chart-box"><div class="chart-title">AUC by Encryption</div><canvas id="chart-encryption" height="190"></canvas></div></div>' +
        '<div class="card" style="margin-top:10px">' +
            '<div class="card-head"><span class="card-title">Detector Performance</span></div>' +
            '<div style="overflow-x:auto"><table class="metrics-table"><thead><tr><th>Detector</th><th>ROC-AUC</th><th>EER</th><th>Accuracy</th><th>Samples</th></tr></thead><tbody>' + tableRows + '</tbody></table></div>' +
        '</div>'
    );
}

function drawAllCharts(data) {
    var detectorRows = toArray((data.metrics || {}).detector);
    var sourceRows = toArray((data.metrics || {}).source);
    var conditionRows = toArray((data.metrics || {}).condition);
    var detectorNames = uniqueValues(detectorRows, 'detector');

    var detectorCanvas = document.getElementById('chart-detector');
    if (detectorCanvas && detectorRows.length) {
        drawHorizontalBars(
            detectorCanvas,
            detectorRows.map(function (row) { return row.detector; }),
            detectorRows.map(function (row) { return Number(row.roc_auc || 0); }),
            detectorRows.map(function (_, index) { return DETECTOR_PALETTE[index % DETECTOR_PALETTE.length]; })
        );
    }

    var sourceCanvas = document.getElementById('chart-source');
    if (sourceCanvas && sourceRows.length) {
        drawGroupedBars(sourceCanvas, detectorNames, ['real', 'ml_a', 'ml_b'].map(function (source) {
            return {
                label: source,
                color: SOURCE_COLORS[source],
                vals: detectorNames.map(function (detector) {
                    var row = sourceRows.find(function (item) {
                        return item.detector === detector && item.source === source;
                    });
                    return row ? Number(row.roc_auc || 0) : 0;
                })
            };
        }));
    }

    var encryptionCanvas = document.getElementById('chart-encryption');
    if (encryptionCanvas && conditionRows.length) {
        drawGroupedBars(encryptionCanvas, detectorNames, ['plain', 'encrypted'].map(function (encryption) {
            return {
                label: encryption,
                color: ENCRYPTION_COLORS[encryption],
                vals: detectorNames.map(function (detector) {
                    var rows = conditionRows.filter(function (item) {
                        return item.detector === detector && item.encryption === encryption && item.roc_auc;
                    });
                    if (!rows.length) return 0;
                    return rows.reduce(function (sum, item) {
                        return sum + Number(item.roc_auc || 0);
                    }, 0) / rows.length;
                })
            };
        }));
    }
}

function buildCoversTab(covers) {
    if (!covers.length) {
        return '<div class="empty-state"><h3>No cover manifest found</h3><p>This run has not exported grouped cover previews yet.</p></div>';
    }

    var groups = covers.map(function (group) {
        var cells = ['real', 'ml_a', 'ml_b'].map(function (source) {
            var path = (group.sources || {})[source];
            var label = source.replace('_', ' ');
            if (!path) {
                return '<div class="source-cell"><div class="source-label ' + source + '">' + escapeHtml(label) + '</div><div class="image-none">\u2014</div></div>';
            }

            var url = '/api/image?path=' + encodeURIComponent(path);
            return '<div class="source-cell"><div class="source-label ' + source + '">' + escapeHtml(label) + '</div><img class="cover-thumb" src="' + escapeAttr(url) + '" loading="lazy" alt="' + escapeAttr(label) + '" onclick="openLightbox(\'' + escapeAttr(url) + '\')"></div>';
        }).join('');

        return '<div class="group-card">' +
            '<div class="group-head">' +
                '<span class="group-gid">Group ' + escapeHtml(group.group_id) + '</span>' +
                (group.caption ? '<span class="group-caption">' + escapeHtml(group.caption) + '</span>' : '') +
            '</div>' +
            '<div class="group-images">' + cells + '</div>' +
        '</div>';
    }).join('');

    return '<div class="section-header"><div><div class="section-title">Cover Images</div><div class="section-subtitle">' + covers.length + ' groups · real and generated sources</div></div></div><div class="covers-grid">' + groups + '</div>';
}

function buildConditionsTab(data) {
    var conditionRows = toArray((data.metrics || {}).condition);
    if (!conditionRows.length) {
        return '<div class="empty-state"><h3>No condition metrics</h3><p>This run has no per-condition AUC table yet.</p></div>';
    }

    var detectors = uniqueValues(conditionRows, 'detector');
    var methods = uniqueValues(conditionRows, 'method');
    var levels = uniqueValues(conditionRows, 'payload_level');
    var encryptions = uniqueValues(conditionRows, 'encryption');
    var columns = [];

    methods.forEach(function (method) {
        levels.forEach(function (level) {
            encryptions.forEach(function (encryption) {
                columns.push({ method: method, level: level, encryption: encryption });
            });
        });
    });

    var header = columns.map(function (column) {
        return '<th style="text-align:center"><div>' + escapeHtml(String(column.method).toUpperCase()) + '</div><div style="color:var(--amber);font-weight:500">' + escapeHtml(column.level) + '</div><div style="color:var(--tertiary-dim);font-weight:500">' + escapeHtml(column.encryption) + '</div></th>';
    }).join('');

    var body = detectors.map(function (detector) {
        var cells = columns.map(function (column) {
            var row = conditionRows.find(function (item) {
                return item.detector === detector &&
                    item.method === column.method &&
                    item.payload_level === column.level &&
                    item.encryption === column.encryption;
            });

            if (!row) return '<td style="text-align:center;color:var(--secondary-dim)">\u2014</td>';
            var auc = Number(row.roc_auc || 0);
            var color = auc > 0.85 ? 'var(--green)' : (auc > 0.65 ? 'var(--amber)' : 'var(--error)');
            return '<td style="text-align:center;font-weight:600;font-family:monospace;font-size:12px;color:' + color + '">' + auc.toFixed(3) + '</td>';
        }).join('');

        return '<tr><td style="font-weight:600">' + escapeHtml(detector) + '</td>' + cells + '</tr>';
    }).join('');

    return '<div class="card"><div class="card-head"><span class="card-title">AUC per Condition</span></div><div style="overflow-x:auto"><table class="metrics-table"><thead><tr><th>Detector</th>' + header + '</tr></thead><tbody>' + body + '</tbody></table></div></div>';
}

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

function attachStream(jobId) {
    var job = getJob(jobId);
    if (!job || job.streamSource) return;

    var source = new EventSource('/api/pipeline/stream/' + jobId);
    job.streamSource = source;

    source.onmessage = function (event) {
        job.streamErrors = 0;
        var line = event.data;
        job.logLines.push(line);
        appendLogForJob(jobId, line);

        /* Parse the run directory name from the pipeline header line */
        if (!job.runId) {
            var m = line.match(/Run dir\s*:\s*.*[\/\\]runs[\/\\]([^\s\/\\]+)/);
            if (m) {
                job.runId = m[1];
                /* If we're currently on the job-id placeholder page, redirect to real run */
                if (STATE.page === 'run-detail' && STATE.runId === jobId) {
                    go('run-detail', job.runId);
                }
            }
        }
    };

    source.addEventListener('done', function (event) {
        var exitCode = Number(event.data);
        job.streamSource = null;
        source.close();
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, exitCode === 0 ? '✓ Finished (exit 0)' : '✗ Pipeline exited with code ' + exitCode);

        if (exitCode !== 0) {
            job.failed = true;
            var errLine = job.logLines.slice().reverse().find(function (l) {
                return /error|failed|exception|traceback/i.test(l) && l.trim();
            });
            job.error = errLine || ('Pipeline exited with code ' + exitCode);
        }

        updateTerminalBadgeForJob(jobId, exitCode);

        /* Re-render run detail to pick up final data */
        var targetRunId = job.runId || job.jobId;
        if (STATE.page === 'run-detail' && STATE.runId === targetRunId) {
            setTimeout(function () { if (STATE.page === 'run-detail') render(); }, 2000);
        }
    });

    source.onerror = function () {
        job.streamErrors = (job.streamErrors || 0) + 1;
        if (job.streamErrors >= 5) {
            source.close();
            job.streamSource = null;
            job.failed = true;
            job.error = 'Stream connection lost after repeated failures.';
            updateTerminalBadgeForJob(jobId, -1);
        }
    };
}

function appendLogForJob(jobId, line) {
    if (STATE.page !== 'run-detail') return;
    var job = getJobForRun(STATE.runId);
    if (!job || job.jobId !== jobId) return;
    var box = document.getElementById('run-terminal-log');
    if (!box) return;
    box.textContent += (box.textContent ? '\n' : '') + line;
    box.scrollTop = box.scrollHeight;
}

function updateTerminalBadgeForJob(jobId, exitCode) {
    var job = getJob(jobId);
    if (!job) return;
    var termSection = document.querySelector('.rd-terminal');
    if (!termSection) return;
    var badge = termSection.querySelector('.badge');
    if (!badge) return;
    if (job.killed) {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Killed';
    } else if (exitCode === 0) {
        badge.className = 'badge badge-done'; badge.textContent = '✓ Completed';
    } else {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Failed';
    }
    /* Inject error banner if needed */
    if ((exitCode !== 0 || job.killed) && job.error && STATE.terminalOpen) {
        var body = termSection.querySelector('.rd-terminal-body');
        if (body && !body.querySelector('.rd-error-banner')) {
            var banner = document.createElement('div');
            banner.className = 'rd-error-banner';
            banner.innerHTML = '<span class="material-symbols-outlined">error_outline</span>' +
                '<div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div>';
            body.insertBefore(banner, body.firstChild);
        }
    }
}

function killRun(jobId) {
    var job = getJob(jobId);
    if (!job) return;
    api('/api/pipeline/kill/' + jobId, { method: 'POST' }).then(function () {
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        updateTerminalBadgeForJob(jobId, -1);
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, '✗ Run killed by user.');
        /* Refresh the current view so the "Running" pill and kill button disappear */
        render();
    }).catch(function () {
        /* job may have already finished — still mark locally */
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        render();
    });
}


function clearSearch() {
    STATE.search = '';
    syncSearchInput();
    render();
}

function confirmDeleteRun(runId) {
    var overlay = document.getElementById('confirm-dialog');
    document.getElementById('dialog-title').textContent = 'Delete Run';
    document.getElementById('dialog-message').innerHTML = 'Permanently delete <strong style="font-family:monospace">' + escapeHtml(runId) + '</strong> and all generated artifacts?';
    overlay.classList.add('open');

    document.getElementById('dialog-confirm').onclick = function () {
        overlay.classList.remove('open');
        deleteRun(runId);
    };
    document.getElementById('dialog-cancel').onclick = function () {
        overlay.classList.remove('open');
    };
    overlay.onclick = function (event) {
        if (event.target === overlay) overlay.classList.remove('open');
    };
}

function deleteRun(runId) {
    api('/api/runs/' + encodeURIComponent(runId), { method: 'DELETE' })
        .then(function () {
            if (STATE.page === 'run-detail' && STATE.runId === runId) {
                STATE.runId = null;
            }
            render();
        })
        .catch(function (error) {
            alert('Failed to delete run: ' + error.message);
        });
}

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
}

function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
}

document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
        closeLightbox();
        document.getElementById('confirm-dialog').classList.remove('open');
    }
});

window.addEventListener('beforeunload', function() {
    Object.values(STATE.jobs).forEach(function(job) {
        if (job.streamSource) job.streamSource.close();
    });
});
function toggleTheme() {
    var isLight = document.documentElement.classList.toggle('light');
    var icon = document.getElementById('theme-toggle-icon');
    if (icon) icon.textContent = isLight ? 'dark_mode' : 'light_mode';
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark'); } catch(e) {}
}

function applyStoredTheme() {
    var stored;
    try { stored = localStorage.getItem('theme'); } catch(e) {}
    if (stored === 'light') {
        document.documentElement.classList.add('light');
        var icon = document.getElementById('theme-toggle-icon');
        if (icon) icon.textContent = 'dark_mode';
    }
}

window.addEventListener('DOMContentLoaded', function () {
    applyStoredTheme();
    render();
    // Subscribe to cross-instance sync events from this viewer instance
    var syncSource = new EventSource('/api/events');
    syncSource.addEventListener('refresh', function () {
        // Re-render if on the runs overview so deletes/additions from any instance show up
        if (STATE.page === 'runs') render();
    });
});
