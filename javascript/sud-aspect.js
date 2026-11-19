// Fooocus-sud: карточка «Разрешение» (вкладка Models).
// Источник правды — родной переключатель Fooocus (#aspect_ratios_accordion, скрыт):
//   выбор плитки = клик по его радиокнопке; изменения списка уходят в sud/ui_aspect.py,
//   который сохраняет их в настройки (Drive) и обновляет варианты переключателя без перезапуска.
(function () {
    const LS_COLLAPSED = 'sud-ar-collapsed';
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const DOT = (x, y) => `<path d="M${x} ${y}m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>`;
    const I = {
        grip: SVG(DOT(9, 5) + DOT(9, 12) + DOT(9, 19) + DOT(15, 5) + DOT(15, 12) + DOT(15, 19)),
        x: SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>'),
        edit: SVG('<path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/>'),
        check: SVG('<path d="M5 12l5 5l10 -10"/>'),
        swap: SVG('<path d="M21 17l-18 0"/><path d="M6 10l-3 -3l3 -3"/><path d="M3 7l18 0"/><path d="M18 20l3 -3l-3 -3"/>'),
        plus: SVG('<path d="M12 5l0 14"/><path d="M5 12l14 0"/>'),
    };

    let state = { list: [], sel: null, filter: 'all', editing: null, error: '' };
    let lastKey = '';
    let drag = null;

    const gcd = (a, b) => (b ? gcd(b, a % b) : a);
    const ratio = (w, h) => { const d = gcd(w, h); return `${w / d}:${h / d}`; };
    const kind = (w, h) => (w < h ? 'p' : w > h ? 'l' : 's');
    const key = (r) => `${r[0]}*${r[1]}`;

    function radios() { return [...document.querySelectorAll('#aspect_ratios_accordion input[type=radio]')]; }
    function parse(v) { const m = /(\d+)\s*[×x*]\s*(\d+)/.exec(v || ''); return m ? [+m[1], +m[2]] : null; }
    function read() {
        const rs = radios();
        const checked = rs.find((r) => r.checked);
        return { list: rs.map((r) => parse(r.value)).filter(Boolean), sel: checked ? parse(checked.value) : null };
    }

    function select(r) {
        const radio = radios().find((x) => { const p = parse(x.value); return p && p[0] === r[0] && p[1] === r[1]; });
        if (radio && !radio.checked) radio.click();
    }

    function sendList(list, selectR) {
        const ta = document.querySelector('.sud-ar-op textarea, .sud-ar-op input');
        const btn = document.querySelector('button.sud-ar-op-btn, .sud-ar-op-btn button');
        if (!ta || !btn) return;
        ta.value = JSON.stringify({ list: list.map(key), select: selectR ? key(selectR) : null, nonce: Date.now() });
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 60);
    }

    function validate(w, h, skipIndex) {
        if (!w || !h) return 'Введи ширину и высоту';
        if (w < 256 || h < 256 || w > 4096 || h > 4096) return 'Стороны — от 256 до 4096';
        if (state.list.some((r, i) => i !== skipIndex && r[0] === w && r[1] === h)) return 'Такое разрешение уже есть';
        return '';
    }

    function hintFor(w, h) {
        if (!w || !h) return '';
        const ok = w % 64 === 0 && h % 64 === 0;
        return `${ratio(w, h)} · ${(w * h / 1e6).toFixed(2)} МП · ${ok ? 'кратно 64 ✓' : 'лучше кратно 64'}`;
    }

    function tileHTML(r, i) {
        const [w, h] = r;
        const sel = state.sel && state.sel[0] === w && state.sel[1] === h;
        if (state.editing === i) {
            return `<div class="sud-ar-tile editing" data-i="${i}">
                <div class="sud-ar-edit"><input type="number" class="sud-ar-ew" value="${w}" step="64" aria-label="Ширина">
                <span>×</span><input type="number" class="sud-ar-eh" value="${h}" step="64" aria-label="Высота"></div>
                <button type="button" class="sud-ar-ok" title="Сохранить">${I.check}</button></div>`;
        }
        const s = 30 / Math.max(w, h);
        return `<div class="sud-ar-tile${sel ? ' sel' : ''}" data-i="${i}" title="Выбрать ${w}×${h}">
            <span class="sud-ar-grip" title="Перетащи, чтобы поменять порядок">${I.grip}</span>
            <button type="button" class="sud-ar-ed" title="Изменить">${I.edit}</button>
            <button type="button" class="sud-ar-del" title="Удалить">${I.x}</button>
            <div class="sud-ar-shape" style="width:${Math.round(w * s)}px;height:${Math.round(h * s)}px"></div>
            <div class="sud-ar-res">${w}×${h}</div><div class="sud-ar-rat">${ratio(w, h)}</div></div>`;
    }

    function render() {
        const body = document.querySelector('.sud-ar-body');
        if (!body) return;
        const keepW = body.querySelector('.sud-ar-w')?.value, keepH = body.querySelector('.sud-ar-h')?.value;
        const f = state.filter;
        const seg = [['all', 'Все'], ['p', 'Портрет'], ['s', 'Квадрат'], ['l', 'Пейзаж']]
            .map(([k, t]) => `<button type="button" class="sud-ar-seg-btn${f === k ? ' on' : ''}" data-f="${k}">${t}</button>`).join('');
        const tiles = state.list.map((r, i) => [r, i]).filter(([r]) => f === 'all' || kind(r[0], r[1]) === f)
            .map(([r, i]) => tileHTML(r, i)).join('');
        const w = keepW ?? 896, h = keepH ?? 1152;
        body.innerHTML = `<div class="sud-ar-seg">${seg}</div>
            <div class="sud-ar-grid">${tiles || '<div class="sud-ar-empty">Нет разрешений такого вида</div>'}</div>
            <div class="sud-ar-add"><input type="number" class="sud-ar-w" value="${w}" step="64" aria-label="Ширина">
              <span class="sud-ar-mul">×</span><input type="number" class="sud-ar-h" value="${h}" step="64" aria-label="Высота">
              <button type="button" class="sud-ibtn sud-ar-swap" title="Поменять местами">${I.swap}</button>
              <button type="button" class="sud-ibtn sud-ar-addbtn" title="Добавить">${I.plus}</button></div>
            <div class="sud-ar-hint">${hintFor(+w, +h)}</div><div class="sud-ar-err">${state.error}</div>`;
    }

    function updateHead() {
        const cur = document.querySelector('.sud-ar-current');
        if (cur) cur.textContent = state.sel ? `${state.sel[0]}×${state.sel[1]} · ${ratio(state.sel[0], state.sel[1])}` : '';
    }

    function tick() {
        const card = document.querySelector('.sud-ar-card');
        if (!card) return;
        if (!card.dataset.init) {
            card.dataset.init = '1';
            try { if (localStorage.getItem(LS_COLLAPSED) === '1') card.classList.add('sud-collapsed'); } catch (e) { /* ignore */ }
        }
        const now = read();
        const k = JSON.stringify(now);
        if (k !== lastKey && !drag && state.editing === null) {
            lastKey = k;
            state.list = now.list;
            state.sel = now.sel;
            render();
        }
        updateHead();
    }

    document.addEventListener('click', (e) => {
        const card = e.target.closest && e.target.closest('.sud-ar-card');
        if (!card) return;
        if (e.target.closest('.sud-ar-head')) {
            card.classList.toggle('sud-collapsed');
            try { localStorage.setItem(LS_COLLAPSED, card.classList.contains('sud-collapsed') ? '1' : '0'); } catch (er) { /* ignore */ }
            return;
        }
        const segBtn = e.target.closest('.sud-ar-seg-btn');
        if (segBtn) { state.filter = segBtn.dataset.f; render(); return; }

        const tile = e.target.closest('.sud-ar-tile');
        const i = tile ? +tile.dataset.i : -1;
        if (e.target.closest('.sud-ar-del')) {
            if (state.list.length <= 1) { state.error = 'Последнее разрешение удалить нельзя'; render(); return; }
            state.error = '';
            sendList(state.list.filter((_, j) => j !== i));
            return;
        }
        if (e.target.closest('.sud-ar-ed')) { state.editing = i; state.error = ''; render(); tile.querySelector?.('input')?.focus(); return; }
        if (e.target.closest('.sud-ar-ok')) {
            const w = +card.querySelector('.sud-ar-ew').value, h = +card.querySelector('.sud-ar-eh').value;
            const err = validate(w, h, i);
            if (err) { state.error = err; state.editing = null; render(); return; }
            const wasSel = state.sel && key(state.sel) === key(state.list[i]);
            const list = state.list.slice(); list[i] = [w, h];
            state.editing = null; state.error = '';
            sendList(list, wasSel ? [w, h] : null);
            return;
        }
        if (tile && !tile.classList.contains('editing') && !e.target.closest('.sud-ar-grip')) {
            select(state.list[i]);
            return;
        }
        if (e.target.closest('.sud-ar-swap')) {
            const a = card.querySelector('.sud-ar-w'), b = card.querySelector('.sud-ar-h');
            [a.value, b.value] = [b.value, a.value];
            card.querySelector('.sud-ar-hint').textContent = hintFor(+a.value, +b.value);
            return;
        }
        if (e.target.closest('.sud-ar-addbtn')) {
            const w = +card.querySelector('.sud-ar-w').value, h = +card.querySelector('.sud-ar-h').value;
            const err = validate(w, h, -1);
            state.error = err;
            if (err) { render(); return; }
            sendList(state.list.concat([[w, h]]), [w, h]);
        }
    });

    document.addEventListener('input', (e) => {
        if (!e.target.matches || !e.target.matches('.sud-ar-w, .sud-ar-h')) return;
        const card = e.target.closest('.sud-ar-card');
        card.querySelector('.sud-ar-hint').textContent =
            hintFor(+card.querySelector('.sud-ar-w').value, +card.querySelector('.sud-ar-h').value);
        card.querySelector('.sud-ar-err').textContent = '';
        state.error = '';
    });

    document.addEventListener('keydown', (e) => {
        if (!e.target.matches) return;
        if (e.key === 'Escape' && state.editing !== null && e.target.matches('.sud-ar-ew, .sud-ar-eh')) {
            state.editing = null; render(); return;
        }
        if (e.key !== 'Enter') return;
        if (e.target.matches('.sud-ar-ew, .sud-ar-eh')) e.target.closest('.sud-ar-tile').querySelector('.sud-ar-ok').click();
        if (e.target.matches('.sud-ar-w, .sud-ar-h')) e.target.closest('.sud-ar-card').querySelector('.sud-ar-addbtn').click();
    });

    // перетаскивание плиток за ⋮⋮ (pointer-события: мышь и палец)
    function clearMarks() {
        document.querySelectorAll('.sud-ar-tile.drop-before, .sud-ar-tile.drop-after, .sud-ar-tile.dragging')
            .forEach((t) => t.classList.remove('drop-before', 'drop-after', 'dragging'));
    }
    document.addEventListener('pointerdown', (e) => {
        const grip = e.target.closest && e.target.closest('.sud-ar-grip');
        if (!grip || e.button !== 0) return;
        e.preventDefault();
        const tile = grip.closest('.sud-ar-tile');
        drag = { tile, from: +tile.dataset.i, pointerId: e.pointerId };
        tile.classList.add('dragging');
        document.body.classList.add('sud-drag-active');
    });
    document.addEventListener('pointermove', (e) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        e.preventDefault();
        document.querySelectorAll('.sud-ar-tile.drop-before, .sud-ar-tile.drop-after').forEach((t) => t.classList.remove('drop-before', 'drop-after'));
        const el = document.elementFromPoint(e.clientX, e.clientY);
        const t = el && el.closest('.sud-ar-tile');
        if (t && t !== drag.tile) {
            const b = t.getBoundingClientRect();
            t.classList.add(e.clientX < b.left + b.width / 2 ? 'drop-before' : 'drop-after');
        }
    });
    function endDrag(e) {
        if (!drag || (e && e.pointerId !== drag.pointerId)) return;
        const target = document.querySelector('.sud-ar-tile.drop-before, .sud-ar-tile.drop-after');
        if (target && e.type === 'pointerup') {
            const to = +target.dataset.i;
            const list = state.list.slice();
            const [moved] = list.splice(drag.from, 1);
            let pos = list.findIndex((r) => key(r) === key(state.list[to]));
            if (target.classList.contains('drop-after')) pos += 1;
            list.splice(pos, 0, moved);
            sendList(list);
        }
        clearMarks();
        document.body.classList.remove('sud-drag-active');
        drag = null;
    }
    document.addEventListener('pointerup', endDrag);
    document.addEventListener('pointercancel', endDrag);

    setInterval(tick, 400);
})();
