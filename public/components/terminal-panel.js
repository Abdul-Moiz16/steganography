class TerminalPanel extends HTMLElement {
    connectedCallback() {
        this.refresh();
    }

    get runId() { return this.getAttribute('run-id') || ''; }

    refresh() {
        const runId = this.runId;
        const job = getJobForRun(runId);

        if (!job || !job.logLines.length) {
            const isKilled = !isRunActive(runId) && ((getJobForRun(runId) || {}).killed);
            if (isKilled) {
                this.innerHTML = this._killedBannerHtml(runId);
            } else {
                this.innerHTML = '';
            }
            return;
        }

        const isRunning = !!job.streamSource && !job.failed && !job.killed;
        const isOpen = STATE.terminalOpen;

        this.innerHTML =
            `<div class="rd-terminal">` +
                this._headerHtml(job, isRunning, isOpen) +
                (isOpen ? this._bodyHtml(job) : '') +
            `</div>`;

        const hdr = this.querySelector('.rd-terminal-hdr');
        if (hdr) hdr.addEventListener('click', () => this.toggle());

        const killBtn = this.querySelector('.rd-kill-btn');
        if (killBtn) killBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            killRun(job.jobId);
        });
    }

    toggle() {
        STATE.terminalOpen = !STATE.terminalOpen;
        const section = this.querySelector('.rd-terminal');
        if (!section) return;

        const chevron = section.querySelector('.rd-term-chevron');
        const existingBody = section.querySelector('.rd-terminal-body');
        const job = getJobForRun(this.runId);

        if (STATE.terminalOpen && job) {
            const div = document.createElement('div');
            div.className = 'rd-terminal-body';
            div.innerHTML = this._bodyInnerHtml(job);
            section.appendChild(div);
            const box = div.querySelector('#run-terminal-log');
            if (box) box.scrollTop = box.scrollHeight;
        } else {
            if (existingBody) existingBody.remove();
        }

        if (chevron) chevron.textContent = STATE.terminalOpen ? 'expand_less' : 'expand_more';
    }

    appendLog(line) {
        const box = this.querySelector('#run-terminal-log');
        if (!box) return;
        box.textContent += (box.textContent ? '\n' : '') + line;
        box.scrollTop = box.scrollHeight;
    }

    updateBadge(exitCode) {
        const job = getJobForRun(this.runId);
        if (!job) return;
        const badge = this.querySelector('.badge');
        if (!badge) return;

        if (job.killed) {
            badge.className = 'badge badge-error';
            badge.textContent = '\u2717 Killed';
        } else if (exitCode === 0) {
            badge.className = 'badge badge-done';
            badge.textContent = '\u2713 Completed';
        } else {
            badge.className = 'badge badge-error';
            badge.textContent = '\u2717 Failed';
        }

        if ((exitCode !== 0 || job.killed) && job.error && STATE.terminalOpen) {
            const body = this.querySelector('.rd-terminal-body');
            if (body && !body.querySelector('.rd-error-banner')) {
                const banner = document.createElement('div');
                banner.className = 'rd-error-banner';
                banner.innerHTML =
                    `<span class="material-symbols-outlined">error_outline</span>` +
                    `<div><strong>Pipeline error detected</strong>` +
                    `<div class="rd-error-msg">${escapeHtml(job.error)}</div></div>`;
                body.insertBefore(banner, body.firstChild);
            }
        }
    }

    _headerHtml(job, isRunning, isOpen) {
        const statusBadge = isRunning
            ? `<span class="badge badge-running">\u25cf Live</span>`
            : (job.failed || job.killed)
                ? `<span class="badge badge-error">${job.killed ? '\u2717 Killed' : '\u2717 Failed'}</span>`
                : `<span class="badge badge-done">\u2713 Completed</span>`;

        const killBtn = isRunning
            ? `<button class="rd-kill-btn" title="Kill this run">` +
                  `<span class="material-symbols-outlined">stop_circle</span> Kill` +
              `</button>`
            : '';

        return `<div class="rd-terminal-hdr">` +
            `<div class="rd-terminal-hdr-left">` +
                `<span class="material-symbols-outlined rd-term-icon">terminal</span>` +
                `<span class="rd-terminal-title">Pipeline Output</span>` +
                statusBadge +
            `</div>` +
            `<div class="rd-terminal-hdr-right">` +
                killBtn +
                `<span class="material-symbols-outlined rd-term-chevron">${isOpen ? 'expand_less' : 'expand_more'}</span>` +
            `</div>` +
        `</div>`;
    }

    _bodyHtml(job) {
        return `<div class="rd-terminal-body">${this._bodyInnerHtml(job)}</div>`;
    }

    _bodyInnerHtml(job) {
        const errorBanner = ((job.failed || job.killed) && job.error)
            ? `<div class="rd-error-banner">` +
                  `<span class="material-symbols-outlined">error_outline</span>` +
                  `<div><strong>Pipeline error detected</strong>` +
                  `<div class="rd-error-msg">${escapeHtml(job.error)}</div></div>` +
              `</div>`
            : '';

        return errorBanner +
            `<div class="lp-terminal-chrome">` +
                `<span class="lp-dot lp-dot--r"></span>` +
                `<span class="lp-dot lp-dot--y"></span>` +
                `<span class="lp-dot lp-dot--g"></span>` +
                `<span class="lp-terminal-label">sh \u2014 ${escapeHtml(job.runId || job.jobId)} \u2014 pts/0</span>` +
            `</div>` +
            `<pre class="log-box lp-log-body" id="run-terminal-log">${escapeHtml(job.logLines.join('\n'))}</pre>`;
    }

    _killedBannerHtml() {
        return `<div class="rd-terminal">` +
            `<div class="rd-terminal-hdr">` +
                `<span>${icon('terminal')} Pipeline Output</span>` +
                `<span class="badge badge-error">\u2717 Killed</span>` +
            `</div>` +
            `<div class="rd-error-banner">` +
                icon('cancel') +
                `<span class="rd-error-msg">This run was killed before it completed. No pipeline output is available from this viewer instance.</span>` +
            `</div>` +
        `</div>`;
    }
}

customElements.define('terminal-panel', TerminalPanel);
