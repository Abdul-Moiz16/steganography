/* Stego Explorer — <summary-card> custom element
   Usage: <summary-card icon="science" label="Horizontal Prototype" desc="LSB · 1 payload · 20 groups"></summary-card>
          <summary-card icon="compare_arrows" label="Source Effect" value="Δ +0.042" value-class="sc2-delta--pos" desc="Real 0.814 vs ML 0.856" highlight></summary-card> */

class SummaryCard extends HTMLElement {
    connectedCallback() {
        this.classList.add('summary-card-v2');
        if (this.hasAttribute('highlight')) this.classList.add('sc2-highlight');

        var valueAttr = this.getAttribute('value');
        var valueCls  = this.getAttribute('value-class') || '';
        var valueHtml = valueAttr
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
