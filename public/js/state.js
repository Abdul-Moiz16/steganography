// mirrors src/pipeline/profile.py
const PROFILE_META = {
    prototype:      { n_groups: 20,  active_methods: ['lsb'],        active_payload_levels: ['low'],                   n_detectors: 3, hardcoded_payload_max_bytes: 8176 },
    prototype_full: { n_groups: 100, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'], n_detectors: 5, hardcoded_payload_max_bytes: 8176 },
    full_design:    { n_groups: 500, active_methods: ['lsb', 'dct'], active_payload_levels: ['low', 'medium', 'high'], n_detectors: 5, hardcoded_payload_max_bytes: 8176 },
};

// Resolve the profile name from a run-id like "prototype_full_20260429_..."
// using a longest-prefix-first match so 'prototype_full' is preferred over
// 'prototype'. Returns null when no profile matches.
function profileFromRunId(runId) {
    if (!runId) return null;
    const keys = Object.keys(PROFILE_META).slice().sort((a, b) => b.length - a.length);
    return keys.find(k => runId.startsWith(k)) || null;
}


// ── AppState ──────────────────────────────────────────────────────────────────
//
// Encapsulates all mutable application state. Typed getters/setters replace
// direct property access so state changes have a single, controlled owner.
// Job management methods replace the free functions that previously mutated
// STATE.jobs directly from multiple files.
//
// The singleton is exposed as `STATE` so existing code requires no changes.

class AppState {
    constructor() {
        // Navigation
        this._page        = 'runs';
        this._runId       = null;
        this._tab         = 'overview';
        this._renderToken = 0;

        // UI toggles
        this._terminalOpen    = true;
        this._lastAdvancedOpen = false;

        // Launch drawer last-used values
        this._lastEngine           = 'stub';
        this._lastProfile          = 'prototype';
        this._lastPayloadMode      = 'random';
        this._lastHardcodedPayload = '';
        this._lastAdvanced         = null;

        // Proposal page subtab
        this._proposalTab = 'proposal';

        // Active pipeline jobs, keyed by jobId
        this._jobs = {};
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    get page()        { return this._page; }
    set page(v)       { this._page = v; }

    get runId()       { return this._runId; }
    set runId(v)      { this._runId = v; }

    get tab()         { return this._tab; }
    set tab(v)        { this._tab = v; }

    get renderToken() { return this._renderToken; }
    set renderToken(v){ this._renderToken = v; }

    // ── UI toggles ────────────────────────────────────────────────────────────

    get proposalTab()      { return this._proposalTab; }
    set proposalTab(v)     { this._proposalTab = v; }

    get terminalOpen()     { return this._terminalOpen; }
    set terminalOpen(v)    { this._terminalOpen = v; }

    get lastAdvancedOpen() { return this._lastAdvancedOpen; }
    set lastAdvancedOpen(v){ this._lastAdvancedOpen = v; }

    // ── Launch drawer ─────────────────────────────────────────────────────────

    get lastEngine()            { return this._lastEngine; }
    set lastEngine(v)           { this._lastEngine = v; }

    get lastProfile()           { return this._lastProfile; }
    set lastProfile(v)          { this._lastProfile = v; }

    get lastPayloadMode()       { return this._lastPayloadMode; }
    set lastPayloadMode(v)      { this._lastPayloadMode = v; }

    get lastHardcodedPayload()  { return this._lastHardcodedPayload; }
    set lastHardcodedPayload(v) { this._lastHardcodedPayload = v; }

    get lastAdvanced()          { return this._lastAdvanced; }
    set lastAdvanced(v)         { this._lastAdvanced = v; }

    // ── Job management ────────────────────────────────────────────────────────

    // jobs is exposed as a plain object for the few places that iterate it
    // directly (e.g. init.js beforeunload). Internal mutations go through
    // the methods below.
    get jobs() { return this._jobs; }

    createJob(jobId, profile, engine, payloadMode) {
        this._jobs[jobId] = {
            jobId,
            runId:        null,
            logLines:     ['Starting…'],
            streamSource: null,
            streamErrors: 0,
            failed:       false,
            error:        null,
            killed:       false,
            profile:      profile     || null,
            engine:       engine      || null,
            payloadMode:  payloadMode || 'random',
        };
        return this._jobs[jobId];
    }

    getJob(jobId) {
        return this._jobs[jobId];
    }

    getJobForRun(runId) {
        return Object.values(this._jobs).find(j => j.runId === runId || j.jobId === runId);
    }

    isRunActive(runId) {
        return Object.values(this._jobs).some(j => (j.runId === runId || j.jobId === runId) && !!j.streamSource);
    }

    getActiveJobs() {
        return Object.values(this._jobs).filter(j => !!j.streamSource);
    }
}

// Singleton — all other files continue using STATE.page, STATE.jobs, etc.
const STATE = new AppState();

// ── Global shims for job helpers ──────────────────────────────────────────────
//
// These free functions are called throughout the codebase. They now delegate
// to STATE so callers require no changes.

function createJob(jobId, profile, engine, payloadMode) { return STATE.createJob(jobId, profile, engine, payloadMode); }
function getJob(jobId)                                   { return STATE.getJob(jobId); }
function getJobForRun(runId)                             { return STATE.getJobForRun(runId); }
function isRunActive(runId)                              { return STATE.isRunActive(runId); }
function getActiveJobs()                                 { return STATE.getActiveJobs(); }


// ── UI constants (not state — live here for co-location) ─────────────────────

const SOURCE_COLORS     = { real: '#7bd0ff', ml_a: '#ee7d77', ml_b: '#66d9a0' };
const ENCRYPTION_COLORS = { plain: '#7bd0ff', encrypted: '#d4cdee' };
const DETECTOR_PALETTE  = ['#7bd0ff', '#ee7d77', '#66d9a0', '#d4cdee', '#f0c050', '#47c4ff'];
const SIDEBAR_TABS      = [
    { id: 'overview',   icon: 'dashboard',   label: 'Overview' },
    { id: 'results',    icon: 'analytics',   label: 'Results' },
    { id: 'covers',     icon: 'collections', label: 'Gallery' },
    { id: 'conditions', icon: 'science',     label: 'Conditions' },
];
