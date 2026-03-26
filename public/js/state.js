/* Stego Explorer — Application state, constants, and job management */

// Static profile metadata — mirrors src/pipeline/profile.py
var PROFILE_META = {
    prototype:   { n_groups: 20,  active_methods: ['lsb'],        active_payload_levels: ['low'],                    n_detectors: 3 },
    full_design: { n_groups: 500, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'],  n_detectors: 5 },
};

var STATE = {
    page: 'runs',
    runId: null,
    tab: 'overview',
    search: '',
    renderToken: 0,
    terminalOpen: true,
    lastEngine: 'stub',
    lastProfile: 'prototype',
    jobs: {}
    /* jobs[jobId] = { jobId, runId, logLines, streamSource, streamErrors, failed, error, killed } */
};

function createJob(jobId, profile, engine) {
    STATE.jobs[jobId] = { jobId: jobId, runId: null, logLines: ['Starting…'], streamSource: null, streamErrors: 0, failed: false, error: null, killed: false, profile: profile || null, engine: engine || null };
    return STATE.jobs[jobId];
}
function getJob(jobId) { return STATE.jobs[jobId]; }
function getJobForRun(runId) {
    return Object.values(STATE.jobs).find(function(j) { return j.runId === runId || j.jobId === runId; });
}
function isRunActive(runId) {
    return Object.values(STATE.jobs).some(function(j) { return (j.runId === runId || j.jobId === runId) && !!j.streamSource; });
}
function getActiveJobs() { return Object.values(STATE.jobs).filter(function(j) { return !!j.streamSource; }); }

var SOURCE_COLORS = { real: '#7bd0ff', ml_a: '#ee7d77', ml_b: '#66d9a0' };
var ENCRYPTION_COLORS = { plain: '#7bd0ff', encrypted: '#d4cdee' };
var DETECTOR_PALETTE = ['#7bd0ff', '#ee7d77', '#66d9a0', '#d4cdee', '#f0c050', '#47c4ff'];
var SIDEBAR_TABS = [
    { id: 'overview', icon: 'dashboard', label: 'Overview' },
    { id: 'results', icon: 'analytics', label: 'Results' },
    { id: 'covers', icon: 'collections', label: 'Gallery' },
    { id: 'conditions', icon: 'science', label: 'Conditions' }
];
