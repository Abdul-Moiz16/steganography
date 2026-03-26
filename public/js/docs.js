/* Stego Explorer — Documentation page: TOC generation, content loading, and scroll spy */

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
    { id: 'refs',       label: 'References' }
];

/* Build child → parent index for scroll spy */
(function() {
    DOCS_TOC.forEach(function(item) {
        (item.children || []).forEach(function(c) { _CHILD_PARENT[c.id] = item.id; });
    });
})();

/* ── Cache for fetched docs HTML ──────────────────────────────────────────── */
var _docsContentCache = null;

/* ── Build TOC sidebar from DOCS_TOC array ────────────────────────────────── */
function buildDocsToc() {
    var items = DOCS_TOC.map(function(item) {
        var sub = (item.children || []).map(function(c) {
            return `<a class="docs-toc-link docs-toc-child" href="#${c.id}">${escapeHtml(c.label)}</a>`;
        }).join('');
        return `<a class="docs-toc-link" href="#${item.id}">${escapeHtml(item.label)}</a>${sub}`;
    }).join('');

    return `<nav class="docs-toc" id="docs-toc">` +
        `<div class="docs-toc-title">Contents</div>${items}` +
    `</nav>`;
}

/* ── Render docs page (async — fetches HTML content on first load) ────────── */
async function renderDocsPage(el) {
    el.innerHTML =
        `<div class="docs-layout">` +
            buildDocsToc() +
            `<article class="docs-main" id="docs-main">${renderLoading()}</article>` +
        `</div>`;

    if (!_docsContentCache) {
        try {
            var response = await fetch('/public/docs-content.html');
            _docsContentCache = await response.text();
        } catch (e) {
            document.getElementById('docs-main').innerHTML =
                renderError('Failed to load documentation content.');
            return;
        }
    }

    var main = document.getElementById('docs-main');
    if (main) main.innerHTML = _docsContentCache;
    initDocsSpy();
}

/* ── Scroll spy + smooth TOC navigation ───────────────────────────────────── */
function initDocsSpy() {
    var links    = document.querySelectorAll('.docs-toc-link');
    var sections = document.querySelectorAll('.docs-section[id]');
    if (!sections.length) return;

    links.forEach(function(a) {
        a.addEventListener('click', function(e) {
            e.preventDefault();
            var target = document.getElementById(a.getAttribute('href').slice(1));
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    });

    var obs = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (!entry.isIntersecting) return;
            links.forEach(function(l) { l.classList.remove('active'); });
            var id = entry.target.id;
            var a = document.querySelector(`.docs-toc-link[href="#${id}"]`);
            if (a) {
                a.classList.add('active');
                var parentId = _CHILD_PARENT[id];
                if (parentId) {
                    var pa = document.querySelector(`.docs-toc-link[href="#${parentId}"]`);
                    if (pa) pa.classList.add('active');
                }
            }
        });
    }, { rootMargin: '-8% 0px -78% 0px', threshold: 0 });

    sections.forEach(function(s) { obs.observe(s); });
}
