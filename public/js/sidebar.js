function showSidebar(runId, activeTab) {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('main');
    const runIdEl = document.getElementById('sidebar-run-id');
    const logLink = document.getElementById('sidebar-log-link');
    sidebar.classList.remove('is-hidden');
    main.classList.add('with-sidebar');
    runIdEl.textContent = runId;
    runIdEl.classList.remove('none');
    document.getElementById('sidebar-tabs').innerHTML = SIDEBAR_TABS.map(tab => {
        const cls = `sidebar-tab${tab.id === activeTab ? ' active' : ''}`;
        return `<a class="${cls}" onclick="switchTab('${tab.id}')">${icon(tab.icon)}<span>${escapeHtml(tab.label)}</span></a>`;
    }).join('');
    if (logLink) logLink.style.display = 'none';
}

function hideSidebar() {
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('main');
    const runIdEl = document.getElementById('sidebar-run-id');
    const logLink = document.getElementById('sidebar-log-link');
    sidebar.classList.add('is-hidden');
    main.classList.remove('with-sidebar');
    runIdEl.textContent = 'No run selected';
    runIdEl.classList.add('none');
    if (logLink) logLink.style.display = 'none';
}
