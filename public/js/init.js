document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        closeLightbox();
        document.getElementById('confirm-dialog').classList.remove('open');
    }
});

window.addEventListener('beforeunload', () => {
    Object.values(STATE.jobs).forEach(job => {
        if (job.streamSource) job.streamSource.close();
    });
});

window.addEventListener('DOMContentLoaded', () => {
    const page = new URLSearchParams(window.location.search).get('page');
    if (page) go(page);
    else render();
    const syncSource = new EventSource('/api/events');
    syncSource.addEventListener('refresh', () => {
        if (STATE.page === 'runs') render();
    });
});
