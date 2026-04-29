// Renders a banner for 'prototype' and 'prototype_full' runs explaining that
// the sample size is below the proposal target. Renders nothing for
// 'full_design'.
class ProtoBanner extends HTMLElement {
    connectedCallback() {
        const profile = this.getAttribute('profile') || '';
        if (profile !== 'prototype' && profile !== 'prototype_full') { this.remove(); return; }

        const meta = (typeof PROFILE_META !== 'undefined' && PROFILE_META[profile]) || {};
        const nGroups = meta.n_groups || (profile === 'prototype' ? 20 : 100);

        let title, text;
        if (profile === 'prototype') {
            title = 'Horizontal Prototype';
            text = `These results are based on a reduced sample size ` +
                `(${nGroups} groups, LSB only) and <strong>cannot be considered statistically ` +
                `significant</strong>. This run validates the end-to-end pipeline functionality ` +
                `and LSB integration. For publishable results, run the <em>full_design</em> profile.`;
        } else {
            title = 'Prototype Full Design';
            text = `This run exercises every embedding, detector, payload level and encryption ` +
                `combination at <strong>${nGroups} groups</strong> (1/5 of the full design's 500 ` +
                `groups). Every report figure receives real data, but effect-size estimates have ` +
                `wider confidence intervals than the full <em>full_design</em> run.`;
        }

        this.innerHTML =
            `<div class="proto-banner">` +
                `<div class="proto-banner-icon">${icon('warning')}</div>` +
                `<div class="proto-banner-body">` +
                    `<div class="proto-banner-title">${title}</div>` +
                    `<div class="proto-banner-text">${text}</div>` +
                `</div>` +
            `</div>`;
    }
}

customElements.define('proto-banner', ProtoBanner);
