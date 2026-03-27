// router

function updateNavState() {
    const activePage = STATE.page === 'run-detail' ? 'runs' : STATE.page;
    const runsEl     = document.getElementById('nav-runs');
    const docsEl     = document.getElementById('nav-docs');
    const proposalEl = document.getElementById('nav-proposal');
    if (runsEl)     runsEl.classList.toggle('active',     activePage === 'runs');
    if (docsEl)     docsEl.classList.toggle('active',     activePage === 'docs');
    if (proposalEl) proposalEl.classList.toggle('active', activePage === 'proposal');
}

function go(page, runId) {
    if (page === 'launch') {
        openLaunchPanel();
        return;
    }
    const nextRunId = runId || null;
    let nextTab = 'overview';
    if (page === 'run-detail' && STATE.page === 'run-detail' && STATE.runId === nextRunId) {
        nextTab = STATE.tab;
    }
    STATE.page = page;
    STATE.runId = nextRunId;
    STATE.tab = nextTab;
    STATE.search = '';
    const input = document.getElementById('search-input');
    if (input) input.value = '';
    const clearBtn = document.getElementById('search-clear-btn');
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
    const clearBtn = document.getElementById('search-clear-btn');
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
    const input = document.getElementById('search-input');
    if (input) input.value = '';
    handleSearch('');
}

function filterRuns(query) { handleSearch(query); }

function syncSearchInput() {
    const input = document.getElementById('search-input');
    if (input && input.value !== STATE.search) input.value = STATE.search;
    updateSearchPlaceholder();
}

function updateSearchPlaceholder() {
    const input = document.getElementById('search-input');
    if (!input) return;
    const placeholders = {
        runs: 'Search runs\u2026',
        'run-detail': 'Filter groups, detectors\u2026',
        docs: 'Search documentation\u2026',
        proposal: 'Search\u2026'
    };
    input.placeholder = placeholders[STATE.page] || 'Search\u2026';
}

function filterRunDetail(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.group-card').forEach(card => {
        if (!q) { card.style.display = ''; return; }
        const text = card.textContent.toLowerCase();
        card.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
    document.querySelectorAll('.rq-card').forEach(card => {
        if (!q) { card.style.display = ''; return; }
        const text = card.textContent.toLowerCase();
        card.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
    document.querySelectorAll('.cond-row').forEach(row => {
        if (!q) { row.style.display = ''; const detail = row.nextElementSibling; if (detail && detail.classList.contains('cond-detail-wrap')) detail.style.removeProperty('display'); return; }
        const text = row.textContent.toLowerCase();
        const match = text.indexOf(q) !== -1;
        row.style.display = match ? '' : 'none';
        const detail = row.nextElementSibling;
        if (detail && detail.classList.contains('cond-detail-wrap')) {
            if (!match) detail.style.display = 'none';
        }
    });
}

function render() {
    const el = document.getElementById('main');
    const token = ++STATE.renderToken;
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
        renderDocsPage(el);
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
