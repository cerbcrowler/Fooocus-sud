// Fooocus-sud: перевод промпта RU → EN (кнопка 🌐 в углу полей промпта и негативного промпта).
// «↩» возвращает исходный русский текст. Автоперевод при Generate — настройка в ⚙️ (флаг в #sud-flags).
// Перевод делает sud/ui_translate.py (DeepL, запасной — Google) через скрытые .sud-tr-op / .sud-tr-state.
(function () {
    const FIELDS = { prompt: '#positive_prompt textarea', negative: '#negative_prompt textarea' };
    const CYR = /[А-Яа-яЁё]/;
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I_LANG = SVG('<path d="M4 5h7"/><path d="M9 3v2c0 4.418 -2.239 8 -5 8"/><path d="M5 9c0 2.144 2.952 3.908 6.7 4"/><path d="M12 20l4 -9l4 9"/><path d="M19.1 18h-6.2"/>');
    const I_UNDO = SVG('<path d="M9 14l-4 -4l4 -4"/><path d="M5 10h11a4 4 0 1 1 0 8h-1"/>');

    const originals = {};      // поле → { ru: исходный текст, en: перевод }
    let pending = null;        // { resolve, nonce }
    let lastRaw = '';
    let bypassGenerate = false;

    const ta = (name) => document.querySelector(FIELDS[name]);

    function send(fields) {
        const op = document.querySelector('.sud-tr-op textarea, .sud-tr-op input');
        const btn = document.querySelector('button.sud-tr-op-btn, .sud-tr-op-btn button');
        if (!op || !btn) return Promise.resolve(null);
        const nonce = Date.now();
        op.value = JSON.stringify({ fields, nonce });
        op.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 40);
        setBusy(fields, true);
        return new Promise((resolve) => {
            pending = { resolve, nonce, fields };
            setTimeout(() => { if (pending && pending.nonce === nonce) { finish(null); } }, 25000);
        });
    }

    function finish(st) {
        if (!pending) return;
        const p = pending;
        pending = null;
        setBusy(p.fields, false);
        if (st) {
            for (const [name, ru] of Object.entries(st.originals || {})) {
                originals[name] = { ru, en: null };
                setTimeout(() => { if (originals[name]) originals[name].en = ta(name)?.value; tick(); }, 300);
            }
            if (st.error) note(st.error, true);
            else if (st.engine) note(st.warn ? `${st.engine} · ${st.warn}` : `${st.engine} ✓`, !!st.warn);
            else note('Нечего переводить — нет русского текста', false);
        } else {
            note('Перевод не ответил — попробуй ещё раз', true);
        }
        p.resolve(st);
    }

    function readState() {
        const out = document.querySelector('.sud-tr-state textarea, .sud-tr-state input');
        if (!out || !out.value || out.value === lastRaw) return;
        lastRaw = out.value;
        try {
            const st = JSON.parse(out.value);
            if (pending && st.nonce === pending.nonce) finish(st);
        } catch (e) { /* ignore */ }
    }

    // ---------- кнопки в полях ----------
    function decorate(name) {
        const t = ta(name);
        if (!t) return null;
        const host = t.parentElement;
        let box = host.querySelector(':scope > .sud-tr');
        if (!box) {
            host.classList.add('sud-tr-host');
            box = document.createElement('div');
            box.className = 'sud-tr';
            box.dataset.field = name;
            box.innerHTML = `<span class="sud-tr-note"></span>
                <button type="button" class="sud-tr-undo" title="Вернуть русский оригинал">${I_UNDO}</button>
                <button type="button" class="sud-tr-btn" title="Перевести RU → EN">${I_LANG}<span>RU→EN</span></button>`;
            host.appendChild(box);
        }
        return box;
    }

    function tick() {
        readState();
        for (const name of Object.keys(FIELDS)) {
            const box = decorate(name);
            if (!box) continue;
            const t = ta(name);
            box.classList.toggle('has-ru', CYR.test(t.value));
            const o = originals[name];
            box.classList.toggle('can-undo', !!(o && o.en !== null && t.value === o.en));
        }
    }

    function setBusy(fields, busy) {
        fields.forEach((f) => decorate(f)?.classList.toggle('busy', busy));
    }
    let noteTimer = null;
    function note(text, warn) {
        document.querySelectorAll('.sud-tr-note').forEach((n) => { n.textContent = ''; });
        const n = decorate('prompt')?.querySelector('.sud-tr-note');
        if (!n) return;
        n.textContent = text;
        n.classList.toggle('warn', !!warn);
        clearTimeout(noteTimer);
        noteTimer = setTimeout(() => { n.textContent = ''; }, warn ? 6000 : 2500);
    }

    document.addEventListener('click', (e) => {
        const box = e.target.closest && e.target.closest('.sud-tr');
        if (!box) return;
        e.preventDefault();
        const name = box.dataset.field;
        if (e.target.closest('.sud-tr-btn')) {
            if (!CYR.test(ta(name).value)) { note('Нечего переводить — нет русского текста', false); return; }
            send([name]);
        } else if (e.target.closest('.sud-tr-undo')) {
            const o = originals[name];
            if (!o) return;
            const t = ta(name);
            t.value = o.ru;
            t.dispatchEvent(new Event('input', { bubbles: true }));
            delete originals[name];
            tick();
        }
    });

    // ---------- автоперевод при Generate ----------
    document.addEventListener('click', (e) => {
        const gen = e.target.closest && e.target.closest('#generate_button');
        if (!gen || bypassGenerate) return;
        const flags = document.getElementById('sud-flags');
        if (!flags || flags.dataset.autoTranslate !== '1') return;
        const fields = Object.keys(FIELDS).filter((n) => CYR.test(ta(n)?.value || ''));
        if (!fields.length) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        send(fields).then(() => {
            setTimeout(() => {           // дать gradio подставить перевод в поля
                bypassGenerate = true;
                document.getElementById('generate_button')?.click();
                bypassGenerate = false;
            }, 250);
        });
    }, true);

    setInterval(tick, 300);
})();
