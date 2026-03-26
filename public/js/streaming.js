/* Stego Explorer — Pipeline streaming, log output, and run lifecycle */

function attachStream(jobId) {
    var job = getJob(jobId);
    if (!job || job.streamSource) return;

    var source = new EventSource('/api/pipeline/stream/' + jobId);
    job.streamSource = source;

    source.onmessage = function (event) {
        job.streamErrors = 0;
        var line = event.data;
        job.logLines.push(line);
        appendLogForJob(jobId, line);

        /* Parse the run directory name from the pipeline header line */
        if (!job.runId) {
            var m = line.match(/Run dir\s*:\s*.*[\/\\]runs[\/\\]([^\s\/\\]+)/);
            if (m) {
                job.runId = m[1];
                /* If we're currently on the job-id placeholder page, redirect to real run */
                if (STATE.page === 'run-detail' && STATE.runId === jobId) {
                    go('run-detail', job.runId);
                }
            }
        }
    };

    source.addEventListener('done', function (event) {
        var exitCode = Number(event.data);
        job.streamSource = null;
        source.close();
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, exitCode === 0 ? '✓ Finished (exit 0)' : '✗ Pipeline exited with code ' + exitCode);

        if (exitCode !== 0) {
            job.failed = true;
            var errLine = job.logLines.slice().reverse().find(function (l) {
                return /error|failed|exception|traceback/i.test(l) && l.trim();
            });
            job.error = errLine || ('Pipeline exited with code ' + exitCode);
        }

        updateTerminalBadgeForJob(jobId, exitCode);

        /* Re-render run detail to pick up final data */
        var targetRunId = job.runId || job.jobId;
        if (STATE.page === 'run-detail' && STATE.runId === targetRunId) {
            setTimeout(function () { if (STATE.page === 'run-detail') render(); }, 2000);
        }
    });

    source.onerror = function () {
        job.streamErrors = (job.streamErrors || 0) + 1;
        if (job.streamErrors >= 5) {
            source.close();
            job.streamSource = null;
            job.failed = true;
            job.error = 'Stream connection lost after repeated failures.';
            updateTerminalBadgeForJob(jobId, -1);
        }
    };
}

function appendLogForJob(jobId, line) {
    if (STATE.page !== 'run-detail') return;
    var job = getJobForRun(STATE.runId);
    if (!job || job.jobId !== jobId) return;
    var box = document.getElementById('run-terminal-log');
    if (!box) return;
    box.textContent += (box.textContent ? '\n' : '') + line;
    box.scrollTop = box.scrollHeight;
}

function updateTerminalBadgeForJob(jobId, exitCode) {
    var job = getJob(jobId);
    if (!job) return;
    var termSection = document.querySelector('.rd-terminal');
    if (!termSection) return;
    var badge = termSection.querySelector('.badge');
    if (!badge) return;
    if (job.killed) {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Killed';
    } else if (exitCode === 0) {
        badge.className = 'badge badge-done'; badge.textContent = '✓ Completed';
    } else {
        badge.className = 'badge badge-error'; badge.textContent = '✗ Failed';
    }
    /* Inject error banner if needed */
    if ((exitCode !== 0 || job.killed) && job.error && STATE.terminalOpen) {
        var body = termSection.querySelector('.rd-terminal-body');
        if (body && !body.querySelector('.rd-error-banner')) {
            var banner = document.createElement('div');
            banner.className = 'rd-error-banner';
            banner.innerHTML = '<span class="material-symbols-outlined">error_outline</span>' +
                '<div><strong>Pipeline error detected</strong><div class="rd-error-msg">' + escapeHtml(job.error) + '</div></div>';
            body.insertBefore(banner, body.firstChild);
        }
    }
}

function killRun(jobId) {
    var job = getJob(jobId);
    if (!job) return;
    api('/api/pipeline/kill/' + jobId, { method: 'POST' }).then(function () {
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        updateTerminalBadgeForJob(jobId, -1);
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, '✗ Run killed by user.');
        /* Refresh the current view so the "Running" pill and kill button disappear */
        render();
    }).catch(function () {
        /* job may have already finished — still mark locally */
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        render();
    });
}
