function clearSearch() {
    STATE.search = '';
    syncSearchInput();
    render();
}

function confirmDeleteRun(runId) {
    const overlay = document.getElementById('confirm-dialog');
    document.getElementById('dialog-title').textContent = 'Delete Run';
    document.getElementById('dialog-message').innerHTML = `Permanently delete <strong style="font-family:monospace">${escapeHtml(runId)}</strong> and all generated artifacts?`;
    overlay.classList.add('open');

    document.getElementById('dialog-confirm').onclick = () => {
        overlay.classList.remove('open');
        deleteRun(runId);
    };
    document.getElementById('dialog-cancel').onclick = () => {
        overlay.classList.remove('open');
    };
    overlay.onclick = (event) => {
        if (event.target === overlay) overlay.classList.remove('open');
    };
}

function deleteRun(runId) {
    api(`/api/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' })
        .then(() => {
            if (STATE.page === 'run-detail' && STATE.runId === runId) {
                STATE.runId = null;
            }
            render();
        })
        .catch(error => {
            alert(`Failed to delete run: ${error.message}`);
        });
}

function openLightbox(src) {
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
}

function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
}
