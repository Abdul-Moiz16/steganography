// router

function updateNavState() {
    const activePage = STATE.page === 'run-detail' ? 'runs' : STATE.page;
    const runsEl     = document.getElementById('nav-runs');
    const proposalEl = document.getElementById('nav-proposal');
    if (runsEl)     runsEl.classList.toggle('active',     activePage === 'runs');
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
    render();
}

function switchTab(tab) {
    if (STATE.page !== 'run-detail') return;
    STATE.tab = tab;
    render();
}

function render() {
    const el = document.getElementById('main');
    const token = ++STATE.renderToken;
    updateNavState();

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
    if (STATE.page === 'proposal') {
        hideSidebar();
        el.innerHTML = renderProposalPage();
        return;
    }
    hideSidebar();
    el.innerHTML = '';
}
