/* Stego Explorer — <status-pill> custom element
   Usage: <status-pill label="Running" tone="running"></status-pill>
   Tones: running, ready, pending, error                              */

class StatusPill extends HTMLElement {
    connectedCallback() {
        this.classList.add('status-pill', this.getAttribute('tone') || '');
        this.textContent = this.getAttribute('label') || '';
    }
}

customElements.define('status-pill', StatusPill);
