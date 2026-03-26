/* Stego Explorer — Search, delete confirmation, lightbox dialogs */

function clearSearch() {
    STATE.search = '';
    syncSearchInput();
    render();
}

function confirmDeleteRun(runId) {
    var overlay = document.getElementById('confirm-dialog');
    document.getElementById('dialog-title').textContent = 'Delete Run';
    document.getElementById('dialog-message').innerHTML = `Permanently delete <strong style="font-family:monospace">${escapeHtml(runId)}</strong> and all generated artifacts?`;
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
    api(`/api/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' })
        .then(function () {
            if (STATE.page === 'run-detail' && STATE.runId === runId) {
                STATE.runId = null;
            }
            render();
        })
        .catch(function (error) {
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
