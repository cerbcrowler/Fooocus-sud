// Fooocus-sud: картинки сразу в папку на ноуте (File System Access API, Chrome/Edge).
//
// Кнопка 📁 внизу справа: выбрать папку, включить/выключить автосохранение.
// Каждая новая картинка, которую Fooocus показывает в галерее (/file=…/2026-11-19_12-34-56_1234.png),
// скачивается браузером и пишется в выбранную папку с тем же именем (метаданные внутри файла сохраняются).
// Папка запоминается в IndexedDB этого браузера; после перезагрузки Chrome может попросить
// разрешение заново — тогда кнопка станет жёлтой, нажми её.
(function () {
    const IMG_RE = /\/file=[^?#]*?(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d{4}\.(?:png|jpe?g|webp))/i;
    const DB = 'sud-autosave', STORE = 'kv';
    const supported = 'showDirectoryPicker' in window;

    let dir = null;          // FileSystemDirectoryHandle
    let enabled = true;      // автосохранение вкл/выкл
    let permission = 'none'; // none | granted | prompt | denied
    const seen = new Set();  // имена, уже сохранённые (или уже бывшие в папке)
    const queue = [];
    let busy = false;
    let savedCount = 0;

    // ---------- IndexedDB (хранит handle папки и флаг вкл/выкл) ----------
    function idb() {
        return new Promise((res, rej) => {
            const r = indexedDB.open(DB, 1);
            r.onupgradeneeded = () => r.result.createObjectStore(STORE);
            r.onsuccess = () => res(r.result);
            r.onerror = () => rej(r.error);
        });
    }
    async function kvGet(k) {
        const db = await idb();
        return new Promise((res) => {
            const r = db.transaction(STORE).objectStore(STORE).get(k);
            r.onsuccess = () => res(r.result);
            r.onerror = () => res(undefined);
        });
    }
    async function kvSet(k, v) {
        const db = await idb();
        return new Promise((res) => {
            const t = db.transaction(STORE, 'readwrite');
            t.objectStore(STORE).put(v, k);
            t.oncomplete = () => res();
            t.onerror = () => res();
        });
    }

    // ---------- интерфейс ----------
    let btn, panel, toastTimer;

    function render() {
        if (!btn) return;
        let icon = '📁', cls = 'off', title;
        if (!supported) {
            cls = 'off'; title = 'Автосохранение на диск работает только в Chrome/Edge';
        } else if (!dir) {
            title = 'Выбрать папку для автосохранения картинок';
        } else if (permission !== 'granted') {
            cls = 'warn'; title = `Нажми, чтобы снова разрешить запись в «${dir.name}»`;
        } else if (enabled) {
            icon = '💾'; cls = 'on'; title = `Автосохранение в «${dir.name}» включено`;
        } else {
            title = `Автосохранение в «${dir.name}» выключено`;
        }
        btn.textContent = icon;
        btn.className = cls;
        btn.title = title;
        if (panel) {
            panel.querySelector('.sud-as-folder').textContent = dir ? dir.name : 'не выбрана';
            panel.querySelector('.sud-as-state').textContent =
                !dir ? '—' : permission !== 'granted' ? 'нужно разрешение' : enabled ? 'включено' : 'выключено';
            panel.querySelector('.sud-as-toggle').textContent = enabled ? 'Выключить' : 'Включить';
            panel.querySelector('.sud-as-toggle').disabled = !dir;
            panel.querySelector('.sud-as-count').textContent = savedCount;
        }
    }

    function toast(text) {
        let el = document.getElementById('sud-autosave-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'sud-autosave-toast';
            document.body.appendChild(el);
        }
        el.textContent = text;
        el.classList.add('show');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => el.classList.remove('show'), 2500);
    }

    async function pickFolder() {
        try {
            const h = await window.showDirectoryPicker({ id: 'sud-autosave', mode: 'readwrite', startIn: 'pictures' });
            dir = h;
            await kvSet('dir', h);
            permission = await h.queryPermission({ mode: 'readwrite' });
            if (permission !== 'granted') permission = await h.requestPermission({ mode: 'readwrite' });
            enabled = true;
            await kvSet('enabled', true);
            await markExisting();
            toast(`📁 Картинки будут сохраняться в «${h.name}»`);
        } catch (e) {
            if (e.name !== 'AbortError') toast('❌ Не удалось выбрать папку: ' + e.message);
        }
        render();
        scanAll();
    }

    async function ensurePermission() {
        if (!dir) return false;
        try {
            permission = await dir.queryPermission({ mode: 'readwrite' });
            if (permission !== 'granted') permission = await dir.requestPermission({ mode: 'readwrite' });
        } catch (e) {
            permission = 'denied';
        }
        render();
        return permission === 'granted';
    }

    async function onButton() {
        if (!supported) { toast('Нужен Chrome или Edge: в этом браузере нет доступа к папкам'); return; }
        if (!dir) { await pickFolder(); return; }
        if (permission !== 'granted') {
            if (await ensurePermission()) { toast(`💾 Снова пишу в «${dir.name}»`); scanAll(); }
            return;
        }
        panel.classList.toggle('show');
        render();
    }

    function buildUi() {
        btn = document.createElement('button');
        btn.id = 'sud-autosave-btn';
        btn.type = 'button';
        btn.addEventListener('click', onButton);
        document.body.appendChild(btn);

        panel = document.createElement('div');
        panel.id = 'sud-autosave-panel';
        panel.innerHTML = `
            <div class="sud-as-title">Автосохранение на ноут</div>
            <div>Папка: <b class="sud-as-folder"></b></div>
            <div>Статус: <span class="sud-as-state"></span></div>
            <div>Сохранено за сессию: <span class="sud-as-count">0</span></div>
            <div class="sud-as-buttons">
                <button type="button" class="sud-as-pick">Другая папка</button>
                <button type="button" class="sud-as-toggle"></button>
            </div>`;
        panel.querySelector('.sud-as-pick').addEventListener('click', () => { panel.classList.remove('show'); pickFolder(); });
        panel.querySelector('.sud-as-toggle').addEventListener('click', async () => {
            enabled = !enabled;
            await kvSet('enabled', enabled);
            toast(enabled ? '💾 Автосохранение включено' : '⏸ Автосохранение выключено');
            render();
            if (enabled) scanAll();
        });
        document.body.appendChild(panel);
        document.addEventListener('click', (e) => {
            if (!panel.contains(e.target) && e.target !== btn) panel.classList.remove('show');
        });
        render();
    }

    // ---------- сохранение ----------
    async function exists(name) {
        try { await dir.getFileHandle(name); return true; } catch (e) { return false; }
    }

    // имена, которые уже лежат в папке, не перезаписываем и не качаем повторно
    async function markExisting() {
        if (!dir || permission !== 'granted') return;
        try {
            for await (const [name] of dir.entries()) seen.add(name);
        } catch (e) { /* не страшно */ }
    }

    function consider(src) {
        if (!src) return;
        const m = IMG_RE.exec(src);
        if (!m) return;
        const name = m[1];
        if (seen.has(name)) return;
        seen.add(name);
        queue.push({ url: new URL(src, location.href).href, name });
        pump();
    }

    async function pump() {
        if (busy) return;
        busy = true;
        try {
            while (queue.length) {
                if (!dir || !enabled || permission !== 'granted') {
                    // не можем писать сейчас — забудем, чтобы сохранить при следующем включении
                    queue.splice(0).forEach((j) => seen.delete(j.name));
                    break;
                }
                const job = queue.shift();
                try {
                    if (await exists(job.name)) continue;
                    const resp = await fetch(job.url, { credentials: 'same-origin' });
                    if (!resp.ok) throw new Error('HTTP ' + resp.status);
                    const blob = await resp.blob();
                    const fh = await dir.getFileHandle(job.name, { create: true });
                    const w = await fh.createWritable();
                    await w.write(blob);
                    await w.close();
                    savedCount++;
                    toast(`💾 ${job.name}`);
                    render();
                } catch (e) {
                    seen.delete(job.name);
                    console.warn('[sud-autosave]', job.name, e);
                    if (e.name === 'NotAllowedError' || e.name === 'SecurityError') {
                        permission = 'prompt';
                        render();
                    }
                }
            }
        } finally {
            busy = false;
        }
    }

    function scanAll() {
        document.querySelectorAll('img[src*="/file="]').forEach((img) => consider(img.getAttribute('src')));
    }

    function observe() {
        new MutationObserver((muts) => {
            for (const m of muts) {
                if (m.type === 'attributes' && m.target.tagName === 'IMG') {
                    consider(m.target.getAttribute('src'));
                } else {
                    m.addedNodes.forEach((n) => {
                        if (n.nodeType !== 1) return;
                        if (n.tagName === 'IMG') consider(n.getAttribute('src'));
                        else n.querySelectorAll && n.querySelectorAll('img[src*="/file="]').forEach((i) => consider(i.getAttribute('src')));
                    });
                }
            }
        }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
    }

    async function init() {
        buildUi();
        if (!supported) return;
        try {
            dir = (await kvGet('dir')) || null;
            const en = await kvGet('enabled');
            enabled = en === undefined ? true : !!en;
            if (dir) {
                permission = await dir.queryPermission({ mode: 'readwrite' });
                await markExisting();
            }
        } catch (e) {
            console.warn('[sud-autosave] init', e);
        }
        render();
        // картинки, которые уже были на странице при загрузке, не сохраняем — только новые
        document.querySelectorAll('img[src*="/file="]').forEach((img) => {
            const m = IMG_RE.exec(img.getAttribute('src') || '');
            if (m) seen.add(m[1]);
        });
        observe();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
