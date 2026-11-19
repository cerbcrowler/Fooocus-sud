// Fooocus-sud: полноэкранный менеджер моделей (кнопка 📦 внизу справа, Esc — закрыть).
// Данные и действия — sud/ui_manager.py через скрытые поля .sud-mm-op / .sud-mm-state.
(function () {
    const SVG = (p, cls = 'sud-ico') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I = {
        box: SVG('<path d="M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5"/><path d="M12 12l8 -4.5"/><path d="M12 12l0 9"/><path d="M12 12l-8 -4.5"/>'),
        x: SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>'),
        down: SVG('<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"/><path d="M7 11l5 5l5 -5"/><path d="M12 4l0 12"/>'),
        play: SVG('<path d="M7 4v16l13 -8z"/>'),
        trash: SVG('<path d="M4 7l16 0"/><path d="M10 11l0 6"/><path d="M14 11l0 6"/><path d="M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2 -2l1 -12"/><path d="M9 7v-3a1 1 0 0 1 1 -1h4a1 1 0 0 1 1 1v3"/>'),
        minus: SVG('<path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/><path d="M9 12l6 0"/>'),
        plus: SVG('<path d="M12 5l0 14"/><path d="M5 12l14 0"/>'),
        search: SVG('<path d="M10 10m-7 0a7 7 0 1 0 14 0a7 7 0 1 0 -14 0"/><path d="M21 21l-6 -6"/>'),
    };
    const ALL = '__all__', OUTSIDE = '__outside__';

    let S = null;                 // последнее состояние с сервера
    let ui = { open: false, cat: ALL, filter: 'all', q: '', adding: false, confirm: null, lastRaw: '' };
    let pollTimer = null;

    // ---------- связь с Python ----------
    function send(cmd) {
        const ta = document.querySelector('.sud-mm-op textarea, .sud-mm-op input');
        const btn = document.querySelector('button.sud-mm-op-btn, .sud-mm-op-btn button');
        if (!ta || !btn) return;
        ta.value = JSON.stringify(Object.assign({ kind: 'CHECKPOINTS' }, cmd, { nonce: Date.now() }));
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 40);
    }
    function readState() {
        const out = document.querySelector('.sud-mm-state textarea, .sud-mm-state input');
        if (!out || !out.value || out.value === ui.lastRaw) return;
        ui.lastRaw = out.value;
        try { S = JSON.parse(out.value); } catch (e) { return; }
        if (S.message) toast(S.message);
        render();
    }
    function schedulePoll() {
        clearTimeout(pollTimer);
        if (!ui.open) return;
        const busy = S && S.items.some((i) => i.status === 'downloading');
        pollTimer = setTimeout(() => { send({ op: 'state' }); schedulePoll(); }, busy ? 1200 : 6000);
    }

    // ---------- форматирование ----------
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    function gb(b) {
        if (!b) return '—';
        return b >= 1e9 ? (b / 1073741824).toFixed(1) + ' ГБ' : Math.round(b / 1048576) + ' МБ';
    }
    const catName = (c) => (c === null ? 'Вне каталога' : c === '' ? 'Без категории' : c);

    function toast(text) {
        let t = document.querySelector('.sud-mm-toast');
        if (!t) return;
        t.textContent = text;
        t.classList.add('show');
        clearTimeout(t._h);
        t._h = setTimeout(() => t.classList.remove('show'), 3200);
    }

    // ---------- каркас ----------
    function build() {
        if (document.querySelector('.sud-mm')) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.id = 'sud-mm-btn';
        btn.title = 'Менеджер моделей';
        btn.innerHTML = I.box;
        btn.addEventListener('click', open);
        document.body.appendChild(btn);

        const el = document.createElement('div');
        el.className = 'sud-mm';
        el.innerHTML = `
          <div class="sud-mm-win" role="dialog" aria-label="Менеджер моделей">
            <div class="sud-mm-top">
              ${I.box}<b class="sud-mm-title">Чекпоинты</b><span class="sud-mm-counts"></span>
              <div class="sud-mm-disk"><span class="sud-mm-disk-text"></span><div class="sud-mm-bar"><span></span></div></div>
              <button type="button" class="sud-mm-close" title="Закрыть (Esc)">${I.x}</button>
            </div>
            <div class="sud-mm-body">
              <aside class="sud-mm-side"></aside>
              <main class="sud-mm-main">
                <div class="sud-mm-tools">
                  <label class="sud-mm-search">${I.search}<input type="text" placeholder="Поиск по названию или файлу"></label>
                  <div class="sud-mm-chips"></div>
                  <button type="button" class="sud-mm-addbtn">${I.plus}<span>Добавить</span></button>
                </div>
                <div class="sud-mm-addform"></div>
                <div class="sud-mm-tablewrap"><table class="sud-mm-table"><thead><tr>
                  <th class="c-star" title="Грузить при каждом старте сессии">Старт</th><th>Модель</th>
                  <th class="c-cat">Категория</th><th class="c-size">Размер</th><th class="c-st">Статус</th><th class="c-act"></th>
                </tr></thead><tbody></tbody></table><div class="sud-mm-empty"></div></div>
                <div class="sud-mm-foot"></div>
              </main>
            </div>
            <div class="sud-mm-toast"></div>
          </div>`;
        document.body.appendChild(el);
        el.querySelector('.sud-mm-search input').addEventListener('input', (e) => { ui.q = e.target.value; renderTable(); });
    }

    function open() {
        build();
        ui.open = true;
        document.body.classList.add('sud-mm-open');
        send({ op: 'state', refresh_models: true });
        schedulePoll();
    }
    function close() {
        ui.open = false;
        ui.confirm = null;
        document.body.classList.remove('sud-mm-open');
        clearTimeout(pollTimer);
    }

    // ---------- отрисовка ----------
    function visible() {
        if (!S) return [];
        const q = ui.q.trim().toLowerCase();
        return S.items.filter((it) => {
            if (ui.cat === OUTSIDE ? it.category !== null : ui.cat !== ALL && it.category !== ui.cat) return false;
            if (ui.filter === 'local' && it.status !== 'local') return false;
            if (ui.filter === 'star' && !it.autoload) return false;
            if (q && !(it.title + ' ' + it.file).toLowerCase().includes(q)) return false;
            return true;
        });
    }

    function render() {
        if (!S || !document.querySelector('.sud-mm')) return;
        const root = document.querySelector('.sud-mm');
        const local = S.items.filter((i) => i.status === 'local').length;
        const inCat = S.items.filter((i) => i.category !== null).length;
        root.querySelector('.sud-mm-counts').textContent = `${inCat} в каталоге · ${local} в Colab`;
        if (S.disk) {
            root.querySelector('.sud-mm-disk-text').textContent = `Диск Colab ${gb(S.disk.used)} / ${gb(S.disk.total)}`;
            root.querySelector('.sud-mm-bar span').style.width = Math.round((S.disk.used / S.disk.total) * 100) + '%';
        }
        // категории
        const counts = {};
        S.items.forEach((i) => { const k = i.category === null ? OUTSIDE : i.category; counts[k] = (counts[k] || 0) + 1; });
        const cats = [[ALL, 'Все', S.items.length]].concat(S.categories.map((c) => [c, catName(c), counts[c] || 0]));
        if (counts[OUTSIDE]) cats.push([OUTSIDE, 'Вне каталога', counts[OUTSIDE]]);
        if (!cats.some(([k]) => k === ui.cat)) ui.cat = ALL;
        root.querySelector('.sud-mm-side').innerHTML = cats.map(([k, name, n]) =>
            `<button type="button" class="sud-mm-cat${k === ui.cat ? ' on' : ''}" data-cat="${esc(k)}"><span>${esc(name)}</span><small>${n}</small></button>`).join('') +
            `<button type="button" class="sud-mm-newcat">${I.plus}<span>Категория</span></button>`;
        // фильтры
        root.querySelector('.sud-mm-chips').innerHTML = [['all', 'Все'], ['local', 'В Colab'], ['star', 'Старт']]
            .map(([k, t]) => `<button type="button" class="sud-mm-chip${ui.filter === k ? ' on' : ''}" data-filter="${k}">${t}</button>`).join('');
        renderAddForm();
        renderTable();
        // итог
        const stars = S.items.filter((i) => i.autoload && i.category !== null);
        const starSize = stars.reduce((a, i) => a + (i.size || 0), 0);
        root.querySelector('.sud-mm-foot').innerHTML =
            `<span>Грузится при старте: <b>${stars.length}</b> · ${gb(starSize)}</span><span class="sud-mm-path" title="${esc(S.catalog)}">Каталог: ${esc(S.catalog.split('/').slice(-2).join('/'))}</span>`;
    }

    function statusCell(it) {
        if (it.status === 'downloading') {
            const pct = it.size ? Math.floor((it.done / it.size) * 100) : 0;
            const spd = it.speed ? ` · ${Math.round(it.speed / 1048576)} МБ/с` : '';
            return `<span class="sud-mm-st dl"><span class="sud-mm-prog" style="--p:${pct}%"></span>${pct}%${spd}</span>`;
        }
        if (it.status === 'local') return `<span class="sud-mm-st ok">${it.current ? '▶ текущая' : '✓ в Colab'}</span>`;
        if (it.status === 'error') return `<span class="sud-mm-st err" title="${esc(it.error)}">ошибка</span>`;
        return '<span class="sud-mm-st no">не загружена</span>';
    }

    function actions(it) {
        const b = (act, icon, title, cls = '') => `<button type="button" class="sud-mm-act ${cls}" data-act="${act}" title="${title}">${icon}</button>`;
        const confirming = ui.confirm && ui.confirm.key === (it.url || it.file);
        let html = '';
        if (it.status === 'local' && !it.current) html += b('select', I.play, 'Сделать текущей', 'prim');
        if (it.status === 'none' || it.status === 'error') html += b('download', I.down, 'Загрузить в Colab', 'prim');
        if (it.status === 'downloading') html += b('cancel', I.x, 'Отменить загрузку');
        if (it.status === 'local') html += confirming && ui.confirm.act === 'delete'
            ? `<button type="button" class="sud-mm-act danger wide" data-act="delete" data-sure="1">Удалить?</button>`
            : b('delete', I.trash, 'Удалить из Colab (файл в каталоге и на HF останется)');
        if (it.url) html += confirming && ui.confirm.act === 'remove'
            ? `<button type="button" class="sud-mm-act danger wide" data-act="remove" data-sure="1">Убрать?</button>`
            : b('remove', I.minus, 'Убрать из каталога');
        return html;
    }

    function renderTable() {
        if (!S) return;
        const root = document.querySelector('.sud-mm');
        const active = document.activeElement;
        if (active && active.closest && active.closest('.sud-mm-table') && active.matches('input, select')) return; // не мешать правке
        const rows = visible();
        const catOptions = (cur) => [''].concat(S.categories.filter((c) => c !== ''))
            .map((c) => `<option value="${esc(c)}"${c === cur ? ' selected' : ''}>${esc(catName(c))}</option>`).join('');
        root.querySelector('.sud-mm-table tbody').innerHTML = rows.map((it) => `
          <tr data-key="${esc(it.url || it.file)}" data-url="${esc(it.url)}" data-file="${esc(it.file)}" class="${it.current ? 'cur' : ''}">
            <td class="c-star">${it.url ? `<input type="checkbox" class="sud-mm-star"${it.autoload ? ' checked' : ''} title="Грузить при старте">` : ''}</td>
            <td class="c-name"><div class="sud-mm-name" title="Двойной клик — переименовать">${esc(it.title)}</div><div class="sud-mm-file">${esc(it.file)}</div></td>
            <td class="c-cat">${it.url ? `<select class="sud-mm-catsel">${catOptions(it.category)}</select>` : '<span class="sud-mm-tag">вне каталога</span>'}</td>
            <td class="c-size">${gb(it.size)}</td>
            <td class="c-st">${statusCell(it)}</td>
            <td class="c-act"><div class="sud-mm-acts">${actions(it)}</div></td>
          </tr>`).join('');
        root.querySelector('.sud-mm-empty').textContent = rows.length ? '' :
            (S.items.length ? 'Ничего не найдено' : 'Каталог пуст — нажми «Добавить» или впиши ссылки в links.txt');
    }

    function renderAddForm() {
        const f = document.querySelector('.sud-mm-addform');
        if (!ui.adding) { f.innerHTML = ''; f.classList.remove('on'); return; }
        if (f.classList.contains('on')) return;   // уже открыта — не трогаем введённое
        f.classList.add('on');
        const cats = [''].concat(S.categories.filter((c) => c !== ''));
        const pre = ui.cat !== ALL && ui.cat !== OUTSIDE ? ui.cat : '';
        f.innerHTML = `
          <input type="text" class="f-url" placeholder="Ссылка на файл: https://huggingface.co/автор/репо/resolve/main/модель.safetensors">
          <div class="f-row">
            <input type="text" class="f-title" placeholder="Название (необязательно)">
            <select class="f-cat">${cats.map((c) => `<option value="${esc(c)}"${c === pre ? ' selected' : ''}>${esc(catName(c))}</option>`).join('')}</select>
            <label><input type="checkbox" class="f-star"> Старт</label>
            <label><input type="checkbox" class="f-now" checked> Скачать сейчас</label>
            <button type="button" class="sud-mm-addgo">${I.plus}<span>Добавить</span></button>
          </div>`;
        f.querySelector('.f-url').focus();
    }

    // ---------- события ----------
    document.addEventListener('click', (e) => {
        if (!e.target.closest) return;
        const mm = e.target.closest('.sud-mm');
        if (!mm) return;
        if (e.target === mm || e.target.closest('.sud-mm-close')) { close(); return; }

        const cat = e.target.closest('.sud-mm-cat');
        if (cat) { ui.cat = cat.dataset.cat; render(); return; }
        const chip = e.target.closest('.sud-mm-chip');
        if (chip) { ui.filter = chip.dataset.filter; render(); return; }
        if (e.target.closest('.sud-mm-newcat')) {
            const side = document.querySelector('.sud-mm-side');
            if (!side.querySelector('.sud-mm-catinput')) {
                side.insertAdjacentHTML('beforeend', '<input type="text" class="sud-mm-catinput" placeholder="Название, Enter">');
                side.querySelector('.sud-mm-catinput').focus();
            }
            return;
        }
        if (e.target.closest('.sud-mm-addbtn')) { ui.adding = !ui.adding; renderAddForm(); return; }
        if (e.target.closest('.sud-mm-addgo')) {
            const f = document.querySelector('.sud-mm-addform');
            send({ op: 'add', url: f.querySelector('.f-url').value.trim(), title: f.querySelector('.f-title').value.trim(),
                category: f.querySelector('.f-cat').value, star: f.querySelector('.f-star').checked,
                download_now: f.querySelector('.f-now').checked });
            ui.adding = false; renderAddForm();
            return;
        }
        const act = e.target.closest('.sud-mm-act');
        if (act) {
            const tr = act.closest('tr');
            const key = tr.dataset.key, url = tr.dataset.url, file = tr.dataset.file, a = act.dataset.act;
            if ((a === 'delete' || a === 'remove') && !act.dataset.sure) {
                ui.confirm = { key, act: a };
                renderTable();
                setTimeout(() => { if (ui.confirm && ui.confirm.key === key) { ui.confirm = null; renderTable(); } }, 3500);
                return;
            }
            ui.confirm = null;
            send({ op: a, url, file });
            return;
        }
    });

    document.addEventListener('change', (e) => {
        const tr = e.target.closest && e.target.closest('.sud-mm tr');
        if (!tr) return;
        if (e.target.matches('.sud-mm-star')) send({ op: 'autoload', url: tr.dataset.url, on: e.target.checked });
        if (e.target.matches('.sud-mm-catsel')) { send({ op: 'category', url: tr.dataset.url, category: e.target.value }); e.target.blur(); }
    });

    document.addEventListener('dblclick', (e) => {
        const name = e.target.closest && e.target.closest('.sud-mm-name');
        if (!name) return;
        const tr = name.closest('tr');
        if (!tr.dataset.url) return;
        name.innerHTML = `<input type="text" class="sud-mm-rename" value="${esc(name.textContent)}">`;
        const inp = name.querySelector('input');
        inp.focus(); inp.select();
    });

    document.addEventListener('keydown', (e) => {
        if (!ui.open) return;
        const t = e.target;
        if (e.key === 'Escape') {
            if (t.matches && t.matches('.sud-mm-rename, .sud-mm-catinput')) { t.blur(); renderTable(); render(); return; }
            close();
            return;
        }
        if (e.key !== 'Enter' || !t.matches) return;
        if (t.matches('.sud-mm-rename')) {
            const tr = t.closest('tr');
            send({ op: 'title', url: tr.dataset.url, title: t.value });
            t.blur();
        } else if (t.matches('.sud-mm-catinput')) {
            const v = t.value.trim();
            if (v) { send({ op: 'add_category', category: v }); ui.cat = v; }
            t.remove();
        } else if (t.matches('.sud-mm-addform input')) {
            document.querySelector('.sud-mm-addgo').click();
        }
    });

    function init() { build(); setInterval(readState, 250); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
