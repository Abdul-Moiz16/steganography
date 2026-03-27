// summary-card v2
class SummaryCard extends HTMLElement {
    connectedCallback() {
        this.classList.add('summary-card-v2');
        if (this.hasAttribute('highlight')) this.classList.add('sc2-highlight');

        const valueAttr = this.getAttribute('value');
        const valueCls  = this.getAttribute('value-class') || '';
        const valueHtml = valueAttr
            ? `<div class="sc2-value ${valueCls}">${valueAttr}</div>`
            : '';

        this.innerHTML =
            `<div class="sc2-icon">${icon(this.getAttribute('icon') || 'info')}</div>` +
            `<div class="sc2-body">` +
                `<div class="sc2-label">${escapeHtml(this.getAttribute('label') || '')}</div>` +
                valueHtml +
                `<div class="sc2-desc">${escapeHtml(this.getAttribute('desc') || '')}</div>` +
            `</div>`;
    }
}

customElements.define('summary-card', SummaryCard);
