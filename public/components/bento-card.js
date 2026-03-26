/* Stego Explorer — <bento-card> custom element
   Usage: <bento-card label="Tracked Runs" value="12" sub="8 with metrics" value-class="primary"></bento-card> */

class BentoCard extends HTMLElement {
    connectedCallback() {
        this.classList.add('bento-card');
        var valueClass = this.getAttribute('value-class') || '';
        this.innerHTML =
            `<div class="bento-label">${escapeHtml(this.getAttribute('label') || '')}</div>` +
            `<div class="bento-value${valueClass ? ' ' + valueClass : ''}">${this.getAttribute('value') || ''}</div>` +
            `<div class="bento-sub">${escapeHtml(this.getAttribute('sub') || '')}</div>`;
    }
}

customElements.define('bento-card', BentoCard);
