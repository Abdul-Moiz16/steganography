/* Stego Explorer — Navigation, routing, search, and main render loop */

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
    STATE.search = '';
    var input = document.getElementById('search-input');
    if (input) input.value = '';
    var clearBtn = document.getElementById('search-clear-btn');
    if (clearBtn) clearBtn.style.display = 'none';
    hideDocsNav();
    render();
}

function switchTab(tab) {
    if (STATE.page !== 'run-detail') return;
    STATE.tab = tab;
    render();
}

function handleSearch(query) {
    STATE.search = query || '';
    var clearBtn = document.getElementById('search-clear-btn');
    if (clearBtn) clearBtn.style.display = STATE.search ? 'flex' : 'none';
    if (STATE.page === 'runs') {
        render();
    } else if (STATE.page === 'run-detail') {
        filterRunDetail(STATE.search);
    } else if (STATE.page === 'docs') {
        filterDocs(STATE.search);
    }
}

function clearSearch() {
    var input = document.getElementById('search-input');
    if (input) input.value = '';
    handleSearch('');
}

/* Backward compat alias */
function filterRuns(query) { handleSearch(query); }

function syncSearchInput() {
    var input = document.getElementById('search-input');
    if (input && input.value !== STATE.search) input.value = STATE.search;
    updateSearchPlaceholder();
}

function updateSearchPlaceholder() {
    var input = document.getElementById('search-input');
    if (!input) return;
    var placeholders = {
        runs: 'Search runs\u2026',
        'run-detail': 'Filter groups, detectors\u2026',
        docs: 'Search documentation\u2026',
        proposal: 'Search\u2026'
    };
    input.placeholder = placeholders[STATE.page] || 'Search\u2026';
}

/* ── Run detail filtering ── */
function filterRunDetail(query) {
    var q = query.toLowerCase().trim();
    // Filter group cards in gallery
    var groupCards = document.querySelectorAll('.group-card');
    groupCards.forEach(function (card) {
        if (!q) { card.style.display = ''; return; }
        var text = card.textContent.toLowerCase();
        card.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
    // Filter RQ cards in results
    var rqCards = document.querySelectorAll('.rq-card');
    rqCards.forEach(function (card) {
        if (!q) { card.style.display = ''; return; }
        var text = card.textContent.toLowerCase();
        card.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
    // Filter condition rows
    var condRows = document.querySelectorAll('.cond-row');
    condRows.forEach(function (row) {
        if (!q) { row.style.display = ''; var detail = row.nextElementSibling; if (detail && detail.classList.contains('cond-detail-wrap')) detail.style.removeProperty('display'); return; }
        var text = row.textContent.toLowerCase();
        var match = text.indexOf(q) !== -1;
        row.style.display = match ? '' : 'none';
        var detail = row.nextElementSibling;
        if (detail && detail.classList.contains('cond-detail-wrap')) {
            if (!match) detail.style.display = 'none';
        }
    });
}

/* ── Main render ── */
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
