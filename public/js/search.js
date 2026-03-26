/* Stego Explorer — Documentation search, highlight and navigation */

var _docsSearchState = { marks: [], current: -1 };

function filterDocs(query) {
    var q = query.toLowerCase().trim();

    // Clear previous highlights
    clearDocsHighlights();
    hideDocsNav();

    if (!q) {
        document.querySelectorAll('.docs-section').forEach(function (sec) { sec.style.display = ''; });
        return;
    }

    // Show all sections but highlight matching text
    document.querySelectorAll('.docs-section').forEach(function (sec) { sec.style.display = ''; });

    // Walk text nodes and wrap matches with <mark>
    var marks = [];
    var walker = document.createTreeWalker(
        document.querySelector('.docs-body') || document.getElementById('main'),
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(function (node) {
        var parent = node.parentElement;
        if (!parent || parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE' || parent.classList.contains('docs-search-mark')) return;
        var text = node.textContent;
        var lower = text.toLowerCase();
        var idx = lower.indexOf(q);
        if (idx === -1) return;

        var frag = document.createDocumentFragment();
        var pos = 0;
        while (idx !== -1) {
            if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
            var mark = document.createElement('mark');
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
    document.querySelectorAll('.docs-search-mark').forEach(function (mark) {
        var parent = mark.parentNode;
        parent.replaceChild(document.createTextNode(mark.textContent), mark);
        parent.normalize();
    });
    _docsSearchState.marks = [];
    _docsSearchState.current = -1;
}

function showDocsNav(count) {
    var nav = document.getElementById('search-nav');
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
        var searchWrap = document.querySelector('.topbar-search');
        if (searchWrap) searchWrap.appendChild(nav);
    }
    nav.style.display = 'flex';
    document.getElementById('search-nav-count').textContent = `${count} found`;
}

function hideDocsNav() {
    var nav = document.getElementById('search-nav');
    if (nav) nav.style.display = 'none';
}

function docsSearchNext() {
    var s = _docsSearchState;
    if (!s.marks.length) return;
    if (s.current >= 0) s.marks[s.current].classList.remove('docs-search-active');
    s.current = (s.current + 1) % s.marks.length;
    s.marks[s.current].classList.add('docs-search-active');
    s.marks[s.current].scrollIntoView({ behavior: 'smooth', block: 'center' });
    var countEl = document.getElementById('search-nav-count');
    if (countEl) countEl.textContent = `${s.current + 1} / ${s.marks.length}`;
}

function docsSearchPrev() {
    var s = _docsSearchState;
    if (!s.marks.length) return;
    if (s.current >= 0) s.marks[s.current].classList.remove('docs-search-active');
    s.current = (s.current - 1 + s.marks.length) % s.marks.length;
    s.marks[s.current].classList.add('docs-search-active');
    s.marks[s.current].scrollIntoView({ behavior: 'smooth', block: 'center' });
    var countEl = document.getElementById('search-nav-count');
    if (countEl) countEl.textContent = `${s.current + 1} / ${s.marks.length}`;
}
