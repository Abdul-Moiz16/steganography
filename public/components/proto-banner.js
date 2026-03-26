/* Stego Explorer — <proto-banner> custom element
   Usage: <proto-banner profile="prototype"></proto-banner>
   Renders nothing if profile !== 'prototype'.                         */

class ProtoBanner extends HTMLElement {
    connectedCallback() {
        var profile = this.getAttribute('profile') || '';
        if (profile !== 'prototype') { this.remove(); return; }

        var nGroups = (typeof PROFILE_META !== 'undefined' && PROFILE_META.prototype)
            ? PROFILE_META.prototype.n_groups
            : 20;

        this.innerHTML =
            `<div class="proto-banner">` +
                `<div class="proto-banner-icon">${icon('warning')}</div>` +
                `<div class="proto-banner-body">` +
                    `<div class="proto-banner-title">Horizontal Prototype</div>` +
                    `<div class="proto-banner-text">These results are based on a reduced sample size ` +
                        `(${nGroups} groups, LSB only) and <strong>cannot be considered statistically ` +
                        `significant</strong>. This run validates the end-to-end pipeline functionality ` +
                        `and LSB integration. For publishable results, run the <em>full_design</em> profile.</div>` +
                `</div>` +
            `</div>`;
    }
}

customElements.define('proto-banner', ProtoBanner);
