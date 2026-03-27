class StatusPill extends HTMLElement {
    connectedCallback() {
        this.classList.add('status-pill', this.getAttribute('tone') || '');
        this.textContent = this.getAttribute('label') || '';
    }
}

customElements.define('status-pill', StatusPill);
