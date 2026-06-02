// proposal divergences
const PROPOSAL_DIVERGENCES = [
	{
		title: "Generator model",
		proposed: "PixArt-\u03b1",
		actual: "FLUX",
		reason:
			"No hosted PixArt model on the HF Inference API, and local inference wasn't feasible for the team. Switched to FLUX as the closest available alternative.",
	},
	{
		title: "Prototype scope",
		proposed: "LSB + DCT",
		actual: "LSB only",
		reason:
			"Prototype only validates LSB in depth. DCT is deferred to the full design run.",
	},
	{
		title: "Payload level",
		proposed: "Medium",
		actual: "Low",
		reason:
			"Low payload gives us a clean baseline with minimal distortion. Medium and high come back in the full design run.",
	},
];

function renderProposalPage() {
	const cards = PROPOSAL_DIVERGENCES.map(
		(d) =>
			`<div class="div-card">
            <div class="div-card-badge">CHANGED</div>
            <div class="div-card-title">${escapeHtml(d.title)}</div>
            <div class="div-card-diff">
                <span class="div-proposed">${escapeHtml(d.proposed)}</span>
                <span class="div-arrow">\u2192</span>
                <span class="div-actual">${escapeHtml(d.actual)}</span>
            </div>
            <div class="div-card-reason">${escapeHtml(d.reason)}</div>
        </div>`,
	).join("");

	return `<div class="proposal-page">
        <div class="proposal-left">
            <div class="proposal-header">
                <div class="proposal-header-title">Project Proposal</div>
                <div class="proposal-header-sub">Project Proposal, February 2026. During implementation, some things changed from the proposal:</div>
            </div>
            <div class="div-cards">${cards}</div>
        </div>
        <div class="proposal-right">
            <iframe class="proposal-embed" src="/public/proposal.html" title="Project proposal PDF viewer"></iframe>
        </div>
    </div>`;
}
