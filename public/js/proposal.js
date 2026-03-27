// proposal divergences
const PROPOSAL_DIVERGENCES = [
    {
        title: 'Image Generation Model',
        proposed: 'PixArt-\u03b1',
        actual: 'FLUX',
        reason: 'No hosted PixelArt model was available on the HuggingFace Inference API, and running models locally was not feasible for most team members. FLUX was chosen as the nearest accessible alternative.'
    },
    {
        title: 'Vertical Prototype Coverage',
        proposed: 'LSB + DCT',
        actual: 'LSB only',
        reason: 'The proposal states the vertical prototype validates both the LSB and DCT embedding branches. In practice, only the LSB branch is validated in depth for the prototype. DCT will be included in the full design run.'
    },
    {
        title: 'Prototype Payload Level',
        proposed: 'Medium',
        actual: 'Low',
        reason: 'The prototype pipeline uses low payload capacity to establish a clean baseline with minimal distortion. Medium and high levels will be re-introduced in the full design run once the detection pipeline is validated.'
    }
];

function renderProposalPage() {
    const cards = PROPOSAL_DIVERGENCES.map(d =>
        `<div class="div-card">
            <div class="div-card-badge">DIVERGENCE</div>
            <div class="div-card-title">${escapeHtml(d.title)}</div>
            <div class="div-card-diff">
                <span class="div-proposed">${escapeHtml(d.proposed)}</span>
                <span class="div-arrow">\u2192</span>
                <span class="div-actual">${escapeHtml(d.actual)}</span>
            </div>
            <div class="div-card-reason">${escapeHtml(d.reason)}</div>
        </div>`
    ).join('');

    return `<div class="proposal-page">
        <div class="proposal-header">
            <div class="proposal-header-left">
                <div class="proposal-header-title">Project Proposal</div>
                <div class="proposal-header-sub">Approved midway proposal \u2014 February 2026. The prototype implementation diverges from this plan in the following ways.</div>
            </div>
            <div class="div-cards">${cards}</div>
        </div>
        <iframe class="proposal-embed" src="/public/proposal.html"></iframe>
    </div>`;
}
