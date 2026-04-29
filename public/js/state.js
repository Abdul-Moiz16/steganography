// mirrors src/pipeline/profile.py
const PROFILE_META = {
    prototype:      { n_groups: 20,  active_methods: ['lsb'],        active_payload_levels: ['low'],                    n_detectors: 3, hardcoded_payload_max_bytes: 8176 },
    prototype_full: { n_groups: 100, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'],  n_detectors: 5, hardcoded_payload_max_bytes: 8176 },
    full_design:    { n_groups: 500, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'],  n_detectors: 5, hardcoded_payload_max_bytes: 8176 },
};

// Resolve the profile name from a run-id like "prototype_full_20260429_..."
// using a longest-prefix-first match so 'prototype_full' is preferred over
// 'prototype'. Returns null when no profile matches.
function profileFromRunId(runId) {
    if (!runId) return null;
    const keys = Object.keys(PROFILE_META).slice().sort((a, b) => b.length - a.length);
    return keys.find(k => runId.startsWith(k)) || null;
}

const STATE = {
    page: 'runs',
    runId: null,
    tab: 'overview',
    renderToken: 0,
    terminalOpen: true,
    lastEngine: 'stub',
    lastProfile: 'prototype',
    lastPayloadMode: 'random',
    lastHardcodedPayload: '',
    jobs: {}
};

function createJob(jobId, profile, engine, payloadMode) {
    STATE.jobs[jobId] = { jobId: jobId, runId: null, logLines: ['Starting…'], streamSource: null, streamErrors: 0, failed: false, error: null, killed: false, profile: profile || null, engine: engine || null, payloadMode: payloadMode || 'random' };
    return STATE.jobs[jobId];
}
function getJob(jobId) { return STATE.jobs[jobId]; }
function getJobForRun(runId) {
    return Object.values(STATE.jobs).find(j => j.runId === runId || j.jobId === runId);
}
function isRunActive(runId) {
    return Object.values(STATE.jobs).some(j => (j.runId === runId || j.jobId === runId) && !!j.streamSource);
}
function getActiveJobs() { return Object.values(STATE.jobs).filter(j => !!j.streamSource); }

const SOURCE_COLORS = { real: '#7bd0ff', ml_a: '#ee7d77', ml_b: '#66d9a0' };
const ENCRYPTION_COLORS = { plain: '#7bd0ff', encrypted: '#d4cdee' };
const DETECTOR_PALETTE = ['#7bd0ff', '#ee7d77', '#66d9a0', '#d4cdee', '#f0c050', '#47c4ff'];
const SIDEBAR_TABS = [
    { id: 'overview', icon: 'dashboard', label: 'Overview' },
    { id: 'results', icon: 'analytics', label: 'Results' },
    { id: 'covers', icon: 'collections', label: 'Gallery' },
    { id: 'conditions', icon: 'science', label: 'Conditions' }
];
