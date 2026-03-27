const _docsSearchState = { marks: [], current: -1 };

function filterDocs(query) {
    const q = query.toLowerCase().trim();
    clearDocsHighlights();
    hideDocsNav();

    if (!q) {
        document.querySelectorAll('.docs-section').forEach(sec => { sec.style.display = ''; });
        return;
    }

    document.querySelectorAll('.docs-section').forEach(sec => { sec.style.display = ''; });

    // walk text nodes and wrap matches with <mark>
    const marks = [];
    const walker = document.createTreeWalker(
        document.querySelector('.docs-body') || document.getElementById('main'),
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(node => {
        const parent = node.parentElement;
        if (!parent || parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE' || parent.classList.contains('docs-search-mark')) return;
        const text = node.textContent;
        const lower = text.toLowerCase();
        let idx = lower.indexOf(q);
        if (idx === -1) return;

        const frag = document.createDocumentFragment();
        let pos = 0;
        while (idx !== -1) {
            if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
            const mark = document.createElement('mark');
            mark.className = 'docs-search-mark';
            mark.textContent = text.slice(idx, idx + q.length);
            frag.appendChild(mark);
            marks.push(mark);
            pos = idx + q.length;
            idx = lower.indexOf(q, pos);
        }
        if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
        parent.replaceChild(frag, node);
    });

    _docsSearchState.marks = marks;
    _docsSearchState.current = -1;
    if (marks.length > 0) {
        showDocsNav(marks.length);
        docsSearchNext();
    }
}

function clearDocsHighlights() {
    document.querySelectorAll('.docs-search-mark').forEach(mark => {
        const parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
    });
    _docsSearchState.marks = [];
    _docsSearchState.current = -1;
}

function showDocsNav(count) {
    let nav = document.getElementById('search-nav');
    if (!nav) {
        nav = document.createElement('div');
        nav.id = 'search-nav';
        nav.className = 'search-nav';
        nav.innerHTML =
            `<span class="search-nav-count" id="search-nav-count"></span>
            <button class="search-nav-btn" onclick="docsSearchPrev()" title="Previous">
                <span class="material-symbols-outlined">keyboard_arrow_up</span>
            </button>
            <button class="search-nav-btn" onclick="docsSearchNext()" title="Next">
                <span class="material-symbols-outlined">keyboard_arrow_down</span>
            </button>`;
        const searchWrap = document.querySelector('.topbar-search');
        if (searchWrap) searchWrap.appendChild(nav);
    }
    nav.style.display = 'flex';
    document.getElementById('search-nav-count').textContent = `${count} found`;
}

function hideDocsNav() {
    const nav = document.getElementById('search-nav');
    if (nav) nav.style.display = 'none';
}

function docsSearchNext() {
    const s = _docsSearchState;
    if (!s.marks.length) return;
    if (s.current >= 0) s.marks[s.current].classList.remove('docs-search-active');
    s.current = (s.current + 1) % s.marks.length;
    s.marks[s.current].classList.add('docs-search-active');
    s.marks[s.current].scrollIntoView({ behavior: 'smooth', block: 'center' });
    const countEl = document.getElementById('search-nav-count');
    if (countEl) countEl.textContent = `${s.current + 1} / ${s.marks.length}`;
}

function docsSearchPrev() {
    const s = _docsSearchState;
    if (!s.marks.length) return;
    if (s.current >= 0) s.marks[s.current].classList.remove('docs-search-active');
    s.current = (s.current - 1 + s.marks.length) % s.marks.length;
    s.marks[s.current].classList.add('docs-search-active');
    s.marks[s.current].scrollIntoView({ behavior: 'smooth', block: 'center' });
    const countEl = document.getElementById('search-nav-count');
    if (countEl) countEl.textContent = `${s.current + 1} / ${s.marks.length}`;
}
