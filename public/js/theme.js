/* Stego Explorer — Theme toggling and persistence */

function toggleTheme() {
    var isLight = document.documentElement.classList.toggle('light');
    var icon = document.getElementById('theme-toggle-icon');
    if (icon) icon.textContent = isLight ? 'dark_mode' : 'light_mode';
    try { localStorage.setItem('theme', isLight ? 'light' : 'dark'); } catch(e) {}
}

function applyStoredTheme() {
    var stored;
    try { stored = localStorage.getItem('theme'); } catch(e) {}
    // Default to light; only go dark when explicitly stored as 'dark'
    if (stored !== 'dark') {
        document.documentElement.classList.add('light');
        var icon = document.getElementById('theme-toggle-icon');
        if (icon) icon.textContent = 'dark_mode';
    }
}
