class UploadZone extends HTMLElement {
    connectedCallback() {
        const tab   = this.getAttribute('tab');
        const label = this.getAttribute('label') || 'Drop image here or click to browse';

        this.innerHTML = `
            <div class="upload-zone" id="zone-${tab}">
                <input type="file" accept=".png,.jpg,.jpeg">
                <div class="material-symbols-outlined upload-icon">upload_file</div>
                <div class="upload-label">${label}</div>
                <div class="upload-hint">PNG or JPEG only</div>
            </div>
            <div class="file-info" id="file-info-${tab}">
                <span class="material-symbols-outlined">image</span>
                <span class="file-name" id="file-name-${tab}"></span>
                <span class="format-badge" id="format-badge-${tab}"></span>
                <span class="format-method" id="format-method-${tab}"></span>
                <button class="clear-btn" title="Remove">
                    <span class="material-symbols-outlined">close</span>
                </button>
            </div>`;

        this._zone    = this.querySelector('.upload-zone');
        this._info    = this.querySelector('.file-info');
        this._nameEl  = this.querySelector('.file-name');
        this._badgeEl = this.querySelector('.format-badge');
        this._methEl  = this.querySelector('.format-method');

        this._zone.addEventListener('dragover',  e => { e.preventDefault(); this._zone.classList.add('drag-over'); });
        this._zone.addEventListener('dragleave', () => this._zone.classList.remove('drag-over'));
        this._zone.addEventListener('drop', e => {
            e.preventDefault();
            this._zone.classList.remove('drag-over');
            if (e.dataTransfer.files[0]) this._load(e.dataTransfer.files[0]);
        });
        this.querySelector('input[type="file"]').addEventListener('change', e => {
            if (e.target.files[0]) this._load(e.target.files[0]);
        });
        this.querySelector('.clear-btn').addEventListener('click', () => this._clear());
    }

    _load(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['png', 'jpg', 'jpeg'].includes(ext)) {
            alert('Unsupported file type. Please use PNG or JPEG.');
            return;
        }
        const format = ext === 'png' ? 'png' : 'jpeg';
        const reader = new FileReader();
        reader.onload = e => {
            const b64 = e.target.result.split(',')[1];
            this._setDisplay({ b64, filename: file.name, format });
            this._emit({ b64, filename: file.name, format });
        };
        reader.readAsDataURL(file);
    }

    _clear() {
        this._setDisplay(null);
        this._emit(null);
    }

    _setDisplay(data) {
        if (data) {
            this._info.classList.add('visible');
            this._nameEl.textContent  = data.filename;
            this._badgeEl.textContent = data.format.toUpperCase();
            this._badgeEl.className   = `format-badge ${data.format}`;
            this._methEl.textContent  = data.format === 'png' ? '→ LSB method' : '→ DCT method';
        } else {
            this._info.classList.remove('visible');
            this._nameEl.textContent = '';
        }
    }

    _emit(fileData) {
        this.dispatchEvent(new CustomEvent('zone-change', {
            bubbles: true,
            detail: { tab: this.getAttribute('tab'), file: fileData },
        }));
    }
}

customElements.define('upload-zone', UploadZone);
