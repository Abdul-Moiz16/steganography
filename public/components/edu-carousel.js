/* Stego Explorer — <edu-carousel> custom element
   Usage: <edu-carousel></edu-carousel>
   Fully self-contained: slides data, auto-advance timer, navigation.
   Call .destroy() or let disconnectedCallback clean up the timer.     */

class EduCarousel extends HTMLElement {
    constructor() {
        super();
        this._idx = 0;
        this._timer = null;
    }

    connectedCallback() {
        this._render();
        this._startTimer();
    }

    disconnectedCallback() {
        this._stopTimer();
    }

    /* ── Navigation ─────────────────────────────────────────────── */

    goTo(idx) {
        this._idx = (idx + EduCarousel.SLIDES.length) % EduCarousel.SLIDES.length;
        var track = this.querySelector('.edu-track');
        if (track) track.style.transform = `translateX(-${this._idx * 100}%)`;
        this.querySelectorAll('.edu-dot').forEach((dot, i) => {
            dot.classList.toggle('active', i === this._idx);
        });
        this._restartTimer();
    }

    next() { this.goTo(this._idx + 1); }
    prev() { this.goTo(this._idx - 1); }
    destroy() { this._stopTimer(); }

    /* ── Internal ───────────────────────────────────────────────── */

    _startTimer() {
        this._stopTimer();
        this._timer = setInterval(() => this.next(), 7000);
    }

    _restartTimer() { this._startTimer(); }

    _stopTimer() {
        if (this._timer) { clearInterval(this._timer); this._timer = null; }
    }

    _render() {
        var slides = EduCarousel.SLIDES.map(s =>
            `<div class="edu-slide">` +
                `<div class="edu-visual">${s.visual}</div>` +
                `<div class="edu-text">` +
                    `<div class="edu-tag">${escapeHtml(s.tag)}</div>` +
                    `<div class="edu-title">${escapeHtml(s.title)}</div>` +
                    `<div class="edu-body">${escapeHtml(s.body)}</div>` +
                `</div>` +
            `</div>`
        ).join('');

        var dots = EduCarousel.SLIDES.map((_, i) =>
            `<button class="edu-dot${i === 0 ? ' active' : ''}" data-idx="${i}"></button>`
        ).join('');

        this.innerHTML =
            `<div class="edu-section">` +
                `<div class="edu-label">While you wait \u2014 project primer</div>` +
                `<div class="edu-carousel">` +
                    `<div class="edu-track">${slides}</div>` +
                    `<button class="edu-arrow edu-prev" aria-label="Previous">&#8249;</button>` +
                    `<button class="edu-arrow edu-next" aria-label="Next">&#8250;</button>` +
                    `<div class="edu-dots">${dots}</div>` +
                `</div>` +
            `</div>`;

        /* Attach event listeners via delegation */
        this.addEventListener('click', e => {
            var target = e.target.closest('.edu-prev, .edu-next, .edu-dot');
            if (!target) return;
            if (target.classList.contains('edu-prev')) this.prev();
            else if (target.classList.contains('edu-next')) this.next();
            else if (target.classList.contains('edu-dot')) this.goTo(Number(target.dataset.idx));
        });
    }
}

/* ── Slide data ─────────────────────────────────────────────────────── */

EduCarousel.SLIDES = [
    {
        tag: 'PROJECT OVERVIEW',
        title: 'Research Questions',
        body: 'Does the source of carrier image affect steganographic detectability? We test three sources \u2014 real photographs, ML-generated images using a real photo as reference, and ML-generated images using an AI image as reference \u2014 and measure whether statistical detectors behave differently across them.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">
            <rect x="8" y="14" width="68" height="34" rx="5" fill="rgba(102,217,160,0.12)" stroke="rgba(102,217,160,0.35)" stroke-width="1.2"/>
            <text x="42" y="28" text-anchor="middle" font-size="8.5" fill="#66d9a0" font-family="monospace" font-weight="700">REAL</text>
            <text x="42" y="41" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">photograph</text>
            <rect x="8" y="58" width="68" height="34" rx="5" fill="rgba(130,120,255,0.12)" stroke="rgba(130,120,255,0.35)" stroke-width="1.2"/>
            <text x="42" y="72" text-anchor="middle" font-size="8.5" fill="#8278ff" font-family="monospace" font-weight="700">ML-A</text>
            <text x="42" y="85" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">real reference</text>
            <rect x="8" y="102" width="68" height="34" rx="5" fill="rgba(240,192,80,0.12)" stroke="rgba(240,192,80,0.35)" stroke-width="1.2"/>
            <text x="42" y="116" text-anchor="middle" font-size="8.5" fill="#f0c050" font-family="monospace" font-weight="700">ML-B</text>
            <text x="42" y="129" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.45)">AI reference</text>
            <line x1="76" y1="31" x2="108" y2="66" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>
            <line x1="76" y1="75" x2="108" y2="75" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>
            <line x1="76" y1="119" x2="108" y2="84" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3,2"/>
            <rect x="108" y="54" width="52" height="42" rx="5" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" stroke-width="1.2"/>
            <text x="134" y="71" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.5)">LSB</text>
            <text x="134" y="83" text-anchor="middle" font-size="8" fill="rgba(255,255,255,0.5)">embed</text>
            <line x1="160" y1="75" x2="185" y2="75" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
            <polygon points="185,71 193,75 185,79" fill="rgba(255,255,255,0.2)"/>
            <rect x="193" y="54" width="58" height="42" rx="5" fill="rgba(99,179,255,0.1)" stroke="rgba(99,179,255,0.3)" stroke-width="1.2"/>
            <text x="222" y="71" text-anchor="middle" font-size="8" fill="rgba(99,179,255,0.8)">Detect?</text>
            <text x="222" y="85" text-anchor="middle" font-size="18" fill="rgba(99,179,255,0.6)">?</text>
        </svg>`
    },
    {
        tag: 'EMBEDDING METHOD',
        title: 'How LSB Embedding Works',
        body: 'Least Significant Bit replacement encodes a secret bit by overwriting the final bit of a pixel. A pixel of 150 (10010110\u2082) with a secret bit 1 becomes 151 (10010111\u2082). The \u00b11 change is invisible to the eye, but creates statistical regularities that trained detectors can measure.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">
            <text x="8" y="22" font-size="9" fill="rgba(255,255,255,0.4)" font-family="monospace">Cover pixel  150\u2081\u2080</text>` +
            ['1','0','0','1','0','1','1','0'].map(function(b,i){
                var x = 8 + i*28; var isLSB = i===7;
                return `<rect x="${x}" y="28" width="24" height="24" rx="3" fill="${isLSB?'rgba(99,179,255,0.18)':'rgba(255,255,255,0.06)'}" stroke="${isLSB?'rgba(99,179,255,0.5)':'rgba(255,255,255,0.15)'}" stroke-width="1.2"/>
                       <text x="${x+12}" y="45" text-anchor="middle" font-size="11" fill="${isLSB?'rgba(99,179,255,0.9)':'rgba(255,255,255,0.6)'}" font-family="monospace" font-weight="600">${b}</text>`;
            }).join('') +
            `<text x="8" y="76" font-size="8" fill="rgba(255,255,255,0.25)" font-family="monospace">bit 7 (MSB)                bit 0 (LSB)</text>
            <text x="8" y="100" font-size="9" fill="rgba(255,255,255,0.4)" font-family="monospace">Stego pixel  151\u2081\u2080</text>` +
            ['1','0','0','1','0','1','1','1'].map(function(b,i){
                var x = 8 + i*28; var isLSB = i===7;
                return `<rect x="${x}" y="106" width="24" height="24" rx="3" fill="${isLSB?'rgba(102,217,160,0.25)':'rgba(255,255,255,0.06)'}" stroke="${isLSB?'rgba(102,217,160,0.7)':'rgba(255,255,255,0.15)'}" stroke-width="1.2"/>
                       <text x="${x+12}" y="123" text-anchor="middle" font-size="11" fill="${isLSB?'#66d9a0':'rgba(255,255,255,0.6)'}" font-family="monospace" font-weight="600">${b}</text>`;
            }).join('') +
            `<text x="216" y="62" font-size="18" fill="rgba(240,192,80,0.7)">\u2193</text>
            <text x="205" y="91" font-size="8" fill="rgba(240,192,80,0.5)" font-family="monospace">secret bit</text>
        </svg>`
    },
    {
        tag: 'DETECTOR \u00b7 RS ANALYSIS',
        title: 'Regular-Singular (RS) Analysis',
        body: 'Pixels are partitioned into groups of 4. A flipping mask (+1/\u22121) is applied, and each group is classified as Regular (lower variance after flip), Singular (higher variance), or Unusable. In a clean image R \u2248 R\u0304 and S \u2248 S\u0304. LSB replacement predictably shifts these counts, revealing embedding.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">` +
            `<text x="8" y="18" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Pixel group (4 px)</text>` +
            [148,151,149,150].map(function(v,i){
                var x = 8+i*46;
                return `<rect x="${x}" y="24" width="38" height="28" rx="4" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
                       <text x="${x+19}" y="43" text-anchor="middle" font-size="10" fill="rgba(255,255,255,0.7)" font-family="monospace">${v}</text>`;
            }).join('') +
            `<text x="8" y="68" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Apply mask  [+1,\u22121,+1,\u22121]</text>` +
            [149,150,150,149].map(function(v,i){
                var x = 8+i*46;
                return `<rect x="${x}" y="74" width="38" height="28" rx="4" fill="rgba(130,120,255,0.1)" stroke="rgba(130,120,255,0.3)" stroke-width="1"/>
                       <text x="${x+19}" y="93" text-anchor="middle" font-size="10" fill="rgba(130,120,255,0.9)" font-family="monospace">${v}</text>`;
            }).join('') +
            `<text x="8" y="122" font-size="8" fill="rgba(255,255,255,0.3)">Variance decreased \u2192</text>
            <rect x="152" y="110" width="60" height="22" rx="4" fill="rgba(102,217,160,0.12)" stroke="rgba(102,217,160,0.35)" stroke-width="1.2"/>
            <text x="182" y="125" text-anchor="middle" font-size="9.5" fill="#66d9a0" font-weight="700">REGULAR</text>
        </svg>`
    },
    {
        tag: 'DETECTOR \u00b7 CHI-SQUARE',
        title: 'Chi-Square Spatial Attack',
        body: 'LSB replacement pairs up pixel values that differ only in their final bit (2k \u2194 2k+1). In a natural image these pairs have different frequencies; embedding equalises them toward a 50/50 split. The chi-square statistic quantifies how far the observed pair frequencies deviate from this expected equipartition.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">
            <text x="14" y="16" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Cover image pairs</text>` +
            [[14,62],[20,38],[18,28],[24,48],[16,34],[22,44],[12,18],[20,32]].map(function(pair,i){
                var x = 14+i*28; var h1=pair[0]*1.1; var h2=pair[1]*1.1; var base=130;
                return `<rect x="${x}" y="${base-h1}" width="10" height="${h1}" rx="1" fill="rgba(99,179,255,0.5)"/>
                       <rect x="${x+12}" y="${base-h2}" width="10" height="${h2}" rx="1" fill="rgba(99,179,255,0.25)"/>`;
            }).join('') +
            `<line x1="14" y1="130" x2="248" y2="130" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
            <text x="14" y="145" font-size="7.5" fill="rgba(99,179,255,0.6)" font-family="monospace">2k vs 2k+1 pairs \u2014 natural distribution</text>
        </svg>`
    },
    {
        tag: 'DETECTOR \u00b7 SAMPLE PAIRS',
        title: 'Sample Pairs Analysis',
        body: 'Analyses the multiset statistics of adjacent pixel pairs across the image. Sequential LSB embedding predictably shifts the count of pairs where one value is even and the other odd (the \u201ctrace\u201d multiset). The estimated embedding rate \u03b2 is derived directly from these shifted counts.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">
            <text x="8" y="16" font-size="8.5" fill="rgba(255,255,255,0.35)" font-family="monospace">Adjacent pixel pairs</text>` +
            [
                [148,151],[150,149],[147,152],[151,148],
                [149,150],[152,151],[148,149],[150,151],
                [151,152],[147,148],[150,149],[152,153]
            ].map(function(pair,i){
                var col=i%4; var row=Math.floor(i/4);
                var x=8+col*60; var y=26+row*36;
                var isOddEven = (pair[0]%2===0 && pair[1]%2===1)||(pair[0]%2===1 && pair[1]%2===0);
                return `<rect x="${x}" y="${y}" width="24" height="22" rx="3" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)" stroke-width="1"/>
                       <text x="${x+12}" y="${y+15}" text-anchor="middle" font-size="8.5" fill="rgba(255,255,255,${pair[0]%2===1?'0.75':'0.45'})" font-family="monospace">${pair[0]}</text>
                       <rect x="${x+28}" y="${y}" width="24" height="22" rx="3" fill="${isOddEven?'rgba(240,192,80,0.15)':'rgba(255,255,255,0.06)'}" stroke="${isOddEven?'rgba(240,192,80,0.4)':'rgba(255,255,255,0.12)'}" stroke-width="1"/>
                       <text x="${x+40}" y="${y+15}" text-anchor="middle" font-size="8.5" fill="${isOddEven?'rgba(240,192,80,0.9)':'rgba(255,255,255,0.45)'}" font-family="monospace">${pair[1]}</text>`;
            }).join('') +
            `<text x="8" y="142" font-size="7.5" fill="rgba(240,192,80,0.6)">highlighted = odd/even pairs (trace multiset)</text>
        </svg>`
    },
    {
        tag: 'EXPERIMENTAL DESIGN',
        title: 'Pipeline at a Glance',
        body: 'The prototype validates the full pipeline at small scale: 20 image groups, 1 embedding method (LSB), 1 payload level, 3 statistical detectors. The full design run scales to 500 groups, 2 methods, 3 payload levels, and 5 detectors \u2014 producing ~15,000 individual detection scores per run.',
        visual: `<svg viewBox="0 0 260 150" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%">` +
            `<text x="10" y="26" font-size="8" fill="rgba(102,217,160,0.7)" font-family="monospace" font-weight="700">PROTOTYPE</text>
            <text x="10" y="92" font-size="8" fill="rgba(99,179,255,0.7)" font-family="monospace" font-weight="700">FULL DESIGN</text>` +
            `<line x1="10" y1="60" x2="250" y2="60" stroke="rgba(255,255,255,0.07)" stroke-width="1"/>` +
            [
                ['20','groups'],['1','method'],['1','payload'],['3','detectors']
            ].map(function(s,i){
                var x = 10 + i*60;
                return `<text x="${x+22}" y="47" text-anchor="middle" font-size="18" fill="rgba(102,217,160,0.9)" font-family="monospace" font-weight="700">${s[0]}</text>
                       <text x="${x+22}" y="57" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.3)" font-family="monospace">${s[1]}</text>`;
            }).join('') +
            [
                ['500','groups'],['2','methods'],['3','payloads'],['5','detectors']
            ].map(function(s,i){
                var x = 10 + i*60;
                return `<text x="${x+22}" y="115" text-anchor="middle" font-size="18" fill="rgba(99,179,255,0.9)" font-family="monospace" font-weight="700">${s[0]}</text>
                       <text x="${x+22}" y="125" text-anchor="middle" font-size="7.5" fill="rgba(255,255,255,0.3)" font-family="monospace">${s[1]}</text>`;
            }).join('') +
        `</svg>`
    }
];

customElements.define('edu-carousel', EduCarousel);
