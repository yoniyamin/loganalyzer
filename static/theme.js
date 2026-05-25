/**
 * UI theme toggle — dark default, persisted to localStorage + backend DB.
 */
(function () {
    const STORAGE_KEY = 'logAnalyzer_uiTheme';
    const SETTINGS_KEY = 'ui_theme';
    const root = document.documentElement;

    function getSavedTheme() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved === 'light' ? 'light' : 'dark';
        } catch {
            return 'dark';
        }
    }

    function syncWelcomeImages(theme) {
        var isLight = theme === 'light';
        document.querySelectorAll('.welcome-image-dark').forEach(function (el) {
            el.style.display = isLight ? 'none' : 'block';
        });
        document.querySelectorAll('.welcome-image-light').forEach(function (el) {
            el.style.display = isLight ? 'block' : 'none';
        });
    }

    function applyTheme(theme) {
        const resolved = theme === 'light' ? 'light' : 'dark';
        if (resolved === 'light') {
            root.setAttribute('data-theme', 'light');
        } else {
            root.removeAttribute('data-theme');
        }
        root.dataset.uiTheme = resolved;
        syncWelcomeImages(resolved);
    }

    function saveThemeLocal(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch {
            /* ignore quota / private mode */
        }
    }

    function saveThemeToBackend(theme) {
        return fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: SETTINGS_KEY, value: { theme } }),
        }).catch(function () {
            /* offline or server unavailable */
        });
    }

    function loadThemeFromBackend() {
        return fetch('/api/settings/' + SETTINGS_KEY)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var theme = data && data.value && data.value.theme;
                return theme === 'light' || theme === 'dark' ? theme : null;
            })
            .catch(function () { return null; });
    }

    function persistTheme(theme) {
        saveThemeLocal(theme);
        return saveThemeToBackend(theme);
    }

    function toggleTheme() {
        var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        applyTheme(next);
        persistTheme(next);
    }

    function initThemeToggle() {
        var btn = document.getElementById('themeToggleBtn');
        if (!btn || btn.dataset.bound === '1') return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', toggleTheme);
    }

    function getInitialTheme() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved === 'light' || saved === 'dark') return saved;
        } catch {
            /* ignore */
        }
        // Anti-flash inline script may have set data-theme from server DB
        if (root.getAttribute('data-theme') === 'light') return 'light';
        return 'dark';
    }

    function bootstrap() {
        applyTheme(getInitialTheme());
        initThemeToggle();

        loadThemeFromBackend().then(function (backendTheme) {
            if (!backendTheme) return;
            var current = root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
            if (backendTheme !== current) {
                applyTheme(backendTheme);
                saveThemeLocal(backendTheme);
            } else if (!localStorage.getItem(STORAGE_KEY)) {
                saveThemeLocal(backendTheme);
            }
        });
    }

    bootstrap();

    window.logAnalyzerTheme = {
        applyTheme: applyTheme,
        toggleTheme: toggleTheme,
        getSavedTheme: getSavedTheme,
        persistTheme: persistTheme,
    };
})();
