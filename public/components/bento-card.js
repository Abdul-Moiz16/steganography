// <bento-card> component
class BentoCard extends HTMLElement {
    connectedCallback() {
        this.classList.add('bento-card');
        const valueClass = this.getAttribute('value-class') || '';
        this.innerHTML =
            `<div class="bento-label">${escapeHtml(this.getAttribute('label') || '')}</div>` +
            `<div class="bento-value${valueClass ? ' ' + valueClass : ''}">${this.getAttribute('value') || ''}</div>` +
            `<div class="bento-sub">${escapeHtml(this.getAttribute('sub') || '')}</div>`;
    }
}

customElements.define('bento-card', BentoCard);
