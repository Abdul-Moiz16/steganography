// pipeline streaming + run lifecycle

function attachStream(jobId) {
    const job = getJob(jobId);
    if (!job || job.streamSource) return;

    const source = new EventSource(`/api/pipeline/stream/${jobId}`);
    job.streamSource = source;

    source.onmessage = (event) => {
        job.streamErrors = 0;
        const line = event.data;
        job.logLines.push(line);
        appendLogForJob(jobId, line);

        // grab the run directory name from the pipeline header line
        if (!job.runId) {
            const m = line.match(/Run dir\s*:\s*.*[\/\\]runs[\/\\]([^\s\/\\]+)/);
            if (m) {
                job.runId = m[1];
                if (STATE.page === 'run-detail' && STATE.runId === jobId) {
                    go('run-detail', job.runId);
                }
            }
        }
    };

    source.addEventListener('done', (event) => {
        const exitCode = Number(event.data);
        job.streamSource = null;
        source.close();
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, exitCode === 0 ? '\u2713 Finished (exit 0)' : `\u2717 Pipeline exited with code ${exitCode}`);

        if (exitCode !== 0) {
            job.failed = true;
            const errLine = job.logLines.slice().reverse().find(l => /error|failed|exception|traceback/i.test(l) && l.trim());
            job.error = errLine || `Pipeline exited with code ${exitCode}`;
        }

        updateTerminalBadgeForJob(jobId, exitCode);

        const targetRunId = job.runId || job.jobId;
        if (STATE.page === 'run-detail' && STATE.runId === targetRunId) {
            setTimeout(() => { if (STATE.page === 'run-detail') render(); }, 2000);
        }
    });

    source.onerror = () => {
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
    const job = getJobForRun(STATE.runId);
    if (!job || job.jobId !== jobId) return;
    const panel = document.querySelector('terminal-panel');
    if (panel) panel.appendLog(line);
}

function updateTerminalBadgeForJob(jobId, exitCode) {
    const panel = document.querySelector('terminal-panel');
    if (panel) panel.updateBadge(exitCode);
}

function killRun(jobId) {
    const job = getJob(jobId);
    if (!job) return;
    api(`/api/pipeline/kill/${jobId}`, { method: 'POST' }).then(() => {
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        updateTerminalBadgeForJob(jobId, -1);
        appendLogForJob(jobId, '');
        appendLogForJob(jobId, '\u2717 Run killed by user.');
        render();
    }).catch(() => {
        // job may have already finished
        if (job.streamSource) { job.streamSource.close(); job.streamSource = null; }
        job.killed = true;
        job.failed = true;
        job.error = 'Run was manually killed.';
        render();
    });
}
