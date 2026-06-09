pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

class ZoomController {
  static STEPS = [0.5, 0.67, 0.75, 0.9, 1, 1.25, 1.5, 1.75, 2, 2.5, 3];

  constructor(initialIndex = 4) {
    this._index = initialIndex;
  }

  get scale()      { return ZoomController.STEPS[this._index]; }
  get label()      { return Math.round(this.scale * 100) + '%'; }
  get canZoomIn()  { return this._index < ZoomController.STEPS.length - 1; }
  get canZoomOut() { return this._index > 0; }

  zoomIn()  { if (this.canZoomIn)  this._index++; }
  zoomOut() { if (this.canZoomOut) this._index--; }

  fitTo(targetScale) {
    let best = 0;
    ZoomController.STEPS.forEach((s, i) => {
      if (Math.abs(s - targetScale) < Math.abs(ZoomController.STEPS[best] - targetScale)) best = i;
    });
    this._index = best;
  }
}

class PDFRenderer {
  constructor(scrollArea) {
    this._scrollArea = scrollArea;
    this._canvases = [];
    this._renderTasks = {};
  }

  get canvases() { return this._canvases; }

  buildPages(numPages) {
    this._scrollArea.innerHTML = '';
    this._canvases = [];
    for (let i = 0; i < numPages; i++) {
      const canvas = document.createElement('canvas');
      canvas.className = 'pdf-page';
      canvas.dataset.page = i + 1;
      this._scrollArea.appendChild(canvas);
      this._canvases.push(canvas);
    }
  }

  renderPage(pdfDoc, pageNum, scale) {
    const canvas = this._canvases[pageNum - 1];
    if (!canvas) return;
    if (this._renderTasks[pageNum]) {
      this._renderTasks[pageNum].cancel();
      delete this._renderTasks[pageNum];
    }
    pdfDoc.getPage(pageNum).then(page => {
      const viewport = page.getViewport({ scale });
      canvas.width  = viewport.width;
      canvas.height = viewport.height;
      const task = page.render({ canvasContext: canvas.getContext('2d'), viewport });
      this._renderTasks[pageNum] = task;
      task.promise.then(() => delete this._renderTasks[pageNum]).catch(() => {});
    });
  }

  renderAll(pdfDoc, scale) {
    for (let i = 1; i <= pdfDoc.numPages; i++) {
      this.renderPage(pdfDoc, i, scale);
    }
  }
}

class ToolbarController {
  constructor({ btnPrev, btnNext, btnZoomIn, btnZoomOut, btnZoomFit, pageInfo, zoomLabel, loading, scrollArea }) {
    this._btnPrev    = btnPrev;
    this._btnNext    = btnNext;
    this._btnZoomIn  = btnZoomIn;
    this._btnZoomOut = btnZoomOut;
    this._btnZoomFit = btnZoomFit;
    this._pageInfo   = pageInfo;
    this._zoomLabel  = zoomLabel;
    this._loading    = loading;
    this._scrollArea = scrollArea;
  }

  update({ pageText, canPrev, canNext, zoomLabel, canZoomIn, canZoomOut }) {
    this._pageInfo.textContent  = pageText;
    this._zoomLabel.textContent = zoomLabel;
    this._btnPrev.disabled      = !canPrev;
    this._btnNext.disabled      = !canNext;
    this._btnZoomIn.disabled    = !canZoomIn;
    this._btnZoomOut.disabled   = !canZoomOut;
  }

  hideLoading() { this._loading.remove(); }

  showError(message) {
    this._loading.style.display = 'none';
    const el = document.createElement('div');
    el.id = 'error';
    el.textContent = message;
    this._scrollArea.appendChild(el);
  }

  onPrev(fn)    { this._btnPrev.addEventListener('click', fn); }
  onNext(fn)    { this._btnNext.addEventListener('click', fn); }
  onZoomIn(fn)  { this._btnZoomIn.addEventListener('click', fn); }
  onZoomOut(fn) { this._btnZoomOut.addEventListener('click', fn); }
  onFit(fn)     { this._btnZoomFit.addEventListener('click', fn); }
}

class PDFViewer {
  constructor({ pdfUrl, scrollArea, toolbar }) {
    this._pdfUrl      = pdfUrl;
    this._scrollArea  = scrollArea;
    this._toolbar     = toolbar;
    this._pdfDoc      = null;
    this._currentPage = 1;
    this._zoom        = new ZoomController();
    this._renderer    = new PDFRenderer(scrollArea);
    this._scrollTimer = null;

    this._bindToolbar();
    this._bindScroll();
  }

  load() {
    pdfjsLib.getDocument(this._pdfUrl).promise
      .then(doc => {
        this._pdfDoc = doc;
        this._toolbar.hideLoading();
        this._renderer.buildPages(doc.numPages);
        this._updateControls();
        setTimeout(() => this._fitZoom(), 100);
      })
      .catch(err => this._toolbar.showError('Failed to load PDF: ' + err.message));
  }

  _updateControls() {
    if (!this._pdfDoc) return;
    this._toolbar.update({
      pageText:   `${this._currentPage} / ${this._pdfDoc.numPages}`,
      canPrev:    this._currentPage > 1,
      canNext:    this._currentPage < this._pdfDoc.numPages,
      zoomLabel:  this._zoom.label,
      canZoomIn:  this._zoom.canZoomIn,
      canZoomOut: this._zoom.canZoomOut,
    });
  }

  _scrollToPage(n) {
    this._currentPage = n;
    this._updateControls();
    const canvas = this._renderer.canvases[n - 1];
    if (canvas) canvas.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  _fitZoom() {
    if (!this._pdfDoc) return;
    this._pdfDoc.getPage(1).then(page => {
      const vp = page.getViewport({ scale: 1 });
      this._zoom.fitTo((this._scrollArea.clientWidth - 40) / vp.width);
      this._renderer.renderAll(this._pdfDoc, this._zoom.scale);
      this._updateControls();
    });
  }

  _bindToolbar() {
    this._toolbar.onPrev(()    => { if (this._currentPage > 1) this._scrollToPage(this._currentPage - 1); });
    this._toolbar.onNext(()    => { if (this._pdfDoc && this._currentPage < this._pdfDoc.numPages) this._scrollToPage(this._currentPage + 1); });
    this._toolbar.onZoomIn(()  => { this._zoom.zoomIn();  this._renderer.renderAll(this._pdfDoc, this._zoom.scale); this._updateControls(); });
    this._toolbar.onZoomOut(() => { this._zoom.zoomOut(); this._renderer.renderAll(this._pdfDoc, this._zoom.scale); this._updateControls(); });
    this._toolbar.onFit(()     => this._fitZoom());
  }

  _bindScroll() {
    this._scrollArea.addEventListener('scroll', () => {
      clearTimeout(this._scrollTimer);
      this._scrollTimer = setTimeout(() => {
        const mid = this._scrollArea.scrollTop + this._scrollArea.clientHeight / 2;
        let best = 1, bestDist = Infinity;
        this._renderer.canvases.forEach((c, i) => {
          const dist = Math.abs(c.offsetTop + c.offsetHeight / 2 - mid);
          if (dist < bestDist) { bestDist = dist; best = i + 1; }
        });
        if (best !== this._currentPage) { this._currentPage = best; this._updateControls(); }
      }, 80);
    });
  }
}

const scrollArea = document.getElementById('scroll-area');
const pdfUrl = scrollArea.dataset.pdfUrl || '/api/proposal-pdf';

new PDFViewer({
  pdfUrl,
  scrollArea,
  toolbar: new ToolbarController({
    btnPrev:    document.getElementById('btn-prev'),
    btnNext:    document.getElementById('btn-next'),
    btnZoomIn:  document.getElementById('btn-zoom-in'),
    btnZoomOut: document.getElementById('btn-zoom-out'),
    btnZoomFit: document.getElementById('btn-zoom-fit'),
    pageInfo:   document.getElementById('page-info'),
    zoomLabel:  document.getElementById('zoom-label'),
    loading:    document.getElementById('loading'),
    scrollArea,
  }),
}).load();
