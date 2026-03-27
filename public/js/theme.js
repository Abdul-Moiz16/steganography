function toggleTheme() {
    const isLight = document.documentElement.classList.toggle('light');
    const icon = document.getElementById('theme-toggle-icon');
    if (icon) icon.textContent = isLight ? 'dark_mode' : 'light_mode';
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark'); } catch(e) {}
}

function applyStoredTheme() {
    let stored;
    try { stored = localStorage.getItem('theme'); } catch(e) {}
    // default to light; only go dark when explicitly stored
    if (stored !== 'dark') {
        document.documentElement.classList.add('light');
        const icon = document.getElementById('theme-toggle-icon');
        if (icon) icon.textContent = 'dark_mode';
    }
}
