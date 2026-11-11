(() => {
    const allowed = new Set(['system', 'light', 'dark']);
    let theme = 'system';
    try { const saved = localStorage.getItem('modus-theme'); if (allowed.has(saved)) theme = saved; } catch {}
    document.documentElement.dataset.theme = theme;
    // Apply accessibility preferences before painting the page.
    for (const [key, cls] of [['contrast', 'high-contrast'], ['font-size', 'large-text']]) {
        try { document.documentElement.classList.toggle(cls, localStorage.getItem(key) === 'true'); } catch {}
    }
    document.addEventListener('DOMContentLoaded', () => {
        for (const control of document.querySelectorAll('[data-theme-control]')) {
            control.value = theme;
            control.closest('label').hidden = false;
            control.addEventListener('change', () => {
                if (!allowed.has(control.value)) return;
                theme = control.value;
                document.documentElement.dataset.theme = theme;
                try { localStorage.setItem('modus-theme', theme); } catch {}
            });
        }
    });
})();
