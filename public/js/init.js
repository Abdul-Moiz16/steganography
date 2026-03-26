/* Stego Explorer — Event listeners and application bootstrap */

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
