/* Stego Explorer — Documentation page renderer, TOC, helpers and scroll spy */

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
