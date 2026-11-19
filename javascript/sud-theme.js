// Fooocus-sud: переключатель gruvbox light / dark.
// Gradio 3.41 включает тёмную тему классом "dark" на <body>. Выбор хранится в localStorage
// браузера (у каждого устройства свой); по умолчанию — как в системе.
(function () {
    const KEY = 'sud-theme';

    function saved() {
        try { return localStorage.getItem(KEY); } catch (e) { return null; }
    }

    function wanted() {
        const t = saved();
        if (t === 'dark' || t === 'light') return t;
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function apply() {
        const dark = wanted() === 'dark';
        if (document.body && document.body.classList.contains('dark') !== dark) {
            document.body.classList.toggle('dark', dark);
        }
        const btn = document.getElementById('sud-theme-toggle');
        if (btn) {
            btn.textContent = dark ? '☀️' : '🌙';
            btn.title = dark ? 'Светлая тема (gruvbox light)' : 'Тёмная тема (gruvbox dark)';
        }
    }

    function toggle() {
        const next = wanted() === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem(KEY, next); } catch (e) { /* без localStorage просто не запомнится */ }
        apply();
    }

    function init() {
        if (!document.getElementById('sud-theme-toggle')) {
            const btn = document.createElement('button');
            btn.id = 'sud-theme-toggle';
            btn.type = 'button';
            btn.addEventListener('click', toggle);
            document.body.appendChild(btn);
        }
        apply();
        // gradio сам ставит/снимает "dark" при загрузке и при смене темы системы — возвращаем наш выбор
        new MutationObserver(apply).observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
