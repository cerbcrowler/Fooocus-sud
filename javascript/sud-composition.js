// Fooocus-sud: Compose with boxes — редактор боксов поверх области картинки.
// Кнопка «Композиция · N» у промпта открывает холст с пропорциями выбранного разрешения.
// Пустое место: протянуть мышкой — новый бокс. Заголовок бокса — перетащить, уголок — размер,
// текст пишется прямо в боксе. Справа: вкл/выкл, список, сила выбранного бокса.
// Раскладка (доли 0..1) уходит JSON-ом в скрытое поле .sud-cmp-state → modules/composition.py,
// и запоминается в браузере (localStorage).
(function () {
    const LS = 'sud-cmp-layout';
    const MAX = 6, MIN = 0.05;
    const COLORS = ['#fabd2f', '#83a598', '#d3869b', '#b8bb26', '#fe8019', '#8ec07c'];
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I_LAYOUT = SVG('<path d="M4 4h6v8h-6z"/><path d="M4 16h6v4h-6z"/><path d="M14 12h6v8h-6z"/><path d="M14 4h6v4h-6z"/>');
    const I_X = SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>');
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    const r3 = (v) => Math.round(v * 1000) / 1000;

    let S = { version: 1, enabled: false, boxes: [] };
    let sel = -1, open = false, drag = null;
    try { const v = JSON.parse(localStorage.getItem(LS) || 'null'); if (v && Array.isArray(v.boxes)) S = v; } catch (e) { /* ignore */ }
    S.boxes.forEach((b, i) => { b.color = b.color || COLORS[i % COLORS.length]; });

    // ---------- состояние → скрытое поле ----------
    function payload() {
        return JSON.stringify({
            version: 1, enabled: !!S.enabled && S.boxes.length > 0,
            boxes: S.boxes.map((b) => ({ x: r3(b.x), y: r3(b.y), w: r3(b.w), h: r3(b.h), strength: b.strength, prompt: b.prompt || '' })),
        });
    }
    let lastSent = '';
    function sync() {
        try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { /* ignore */ }
        const ta = document.querySelector('.sud-cmp-state textarea, .sud-cmp-state input');
        const v = payload();
        if (ta && ta.value !== v) { ta.value = v; ta.dispatchEvent(new Event('input', { bubbles: true })); }
        lastSent = v;
        updateButton();
    }
    const activeCount = () => (S.enabled ? S.boxes.filter((b) => (b.prompt || '').trim()).length : 0);

    // ---------- кнопка у промпта ----------
    function ensureButton() {
        const box = document.querySelector('#positive_prompt textarea')?.parentElement?.querySelector(':scope > .sud-tr');
        if (!box || box.querySelector('.sud-cmp-btn')) return;
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'sud-cmp-btn';
        b.title = 'Композиция: свой промпт в каждом боксе';
        box.insertBefore(b, box.firstChild);
        updateButton();
    }
    function updateButton() {
        const b = document.querySelector('.sud-cmp-btn');
        if (!b) return;
        const n = activeCount();
        b.innerHTML = `${I_LAYOUT}<span>Композиция${n ? ' · ' + n : ''}</span>`;
        b.classList.toggle('on', open);
        b.classList.toggle('active', n > 0);
    }

    // ---------- холст ----------
    function aspect() {
        const v = document.querySelector('.aspect_ratios input:checked')?.value || '';
        const m = v.match(/(\d+)\s*[×x*]\s*(\d+)/);
        return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : [1024, 1024];
    }
    function host() {
        return [...document.querySelectorAll('.main_view')].find((e) => e.offsetParent !== null && e.getBoundingClientRect().height > 50);
    }
    function overlay() {
        let o = document.querySelector('.sud-cmp');
        if (!o) {
            o = document.createElement('div');
            o.className = 'sud-cmp';
            document.body.appendChild(o);   // вне gradio-блоков (overflow), позицию ставит place()
        }
        return o;
    }
    function place() {
        const o = document.querySelector('.sud-cmp');
        const h = host();
        if (!o || !open || !h) return;
        const r = h.getBoundingClientRect();
        Object.assign(o.style, { left: r.left + 'px', top: Math.max(0, r.top) + 'px', width: r.width + 'px', height: Math.max(260, r.bottom - Math.max(0, r.top)) + 'px' });
        fitStage();
    }
    function fitStage() {
        const wrap = document.querySelector('.sud-cmp-stage');
        const c = document.querySelector('.sud-cmp-canvas');
        if (!wrap || !c) return;
        const [w, h] = aspect();
        const W = wrap.clientWidth - 16, H = wrap.clientHeight - 16;
        const k = Math.min(W / w, H / h);
        c.style.width = Math.floor(w * k) + 'px';
        c.style.height = Math.floor(h * k) + 'px';
    }
    addEventListener('resize', place);
    addEventListener('scroll', place, true);

    function setOpen(v) {
        open = v;
        overlay().classList.toggle('show', open);
        if (open) render();
        place();
        updateButton();
    }

    function boxHtml(b, i) {
        return `<div class="sud-cmp-box${i === sel ? ' sel' : ''}" data-i="${i}" style="left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%;--c:${b.color}">
            <div class="sud-cmp-bhead" data-drag="move"><span>${i + 1} · ×${b.strength.toFixed(1)}</span><button type="button" class="sud-cmp-del" title="Удалить бокс">${I_X}</button></div>
            <textarea class="sud-cmp-text" placeholder="кто/что здесь… (можно по-русски)">${esc(b.prompt)}</textarea>
            <div class="sud-cmp-grip" data-drag="resize"></div></div>`;
    }
    function render() {
        if (!open) return;
        const o = overlay();
        const keep = document.activeElement && document.activeElement.matches('.sud-cmp-text') ? document.activeElement.closest('.sud-cmp-box').dataset.i : null;
        const caret = keep !== null ? document.activeElement.selectionStart : 0;
        const [w, h] = aspect();
        const b = S.boxes[sel];
        o.innerHTML = `<div class="sud-cmp-bar">${I_LAYOUT}<b>Композиция</b><span class="sud-cmp-dim">${w}×${h}</span><span class="sud-cmp-sp"></span>
                <button type="button" class="sud-cmp-pill acc" data-act="add"${S.boxes.length >= MAX ? ' disabled' : ''}>＋ Бокс</button>
                <button type="button" class="sud-cmp-pill" data-act="clear"${S.boxes.length ? '' : ' disabled'}>Очистить</button>
                <button type="button" class="sud-cmp-pill" data-act="close">Показать картинку</button></div>
            <div class="sud-cmp-body"><div class="sud-cmp-stage"><div class="sud-cmp-canvas">${S.boxes.map(boxHtml).join('')}
                ${S.boxes.length ? '' : '<div class="sud-cmp-empty">Протяни мышкой по холсту — появится бокс.<br>Общий промпт = сцена, свет, стиль. Боксы = кто где.</div>'}</div></div>
            <div class="sud-cmp-side">
                <label class="sud-cmp-tg"><input type="checkbox" data-act="enabled"${S.enabled ? ' checked' : ''}><span>Включена</span></label>
                <div class="sud-cmp-list">${S.boxes.map((x, i) => `<div class="sud-cmp-it${i === sel ? ' on' : ''}" data-i="${i}"><span class="sw" style="background:${x.color}"></span><span class="t">${esc(x.prompt || '(пусто)')}</span><i>${x.strength.toFixed(1)}</i></div>`).join('') || '<div class="sud-cmp-hint">Боксов нет</div>'}</div>
                ${b ? `<div class="sud-cmp-str">Сила бокса ${sel + 1}<input type="range" min="0.1" max="3" step="0.1" value="${b.strength}" data-act="strength"><output>${b.strength.toFixed(1)}</output></div>` : ''}
                <div class="sud-cmp-hint">До ${MAX} боксов. Сила 1.0 — норма, больше — бокс «давит» сильнее. Работает для обычной генерации и Image Prompt (не для Vary/Upscale/Inpaint).</div>
            </div></div>`;
        fitStage();
        if (keep !== null) {
            const t = o.querySelector(`.sud-cmp-box[data-i="${keep}"] .sud-cmp-text`);
            if (t) { t.focus(); t.setSelectionRange(caret, caret); }
        }
    }

    function addBox(x, y, w, h) {
        if (S.boxes.length >= MAX) return -1;
        const used = new Set(S.boxes.map((b) => b.color));
        const color = COLORS.find((c) => !used.has(c)) || COLORS[S.boxes.length % COLORS.length];
        S.boxes.push({ x, y, w, h, strength: 1.0, prompt: '', color });
        S.enabled = true;
        sel = S.boxes.length - 1;
        sync(); render();
        setTimeout(() => document.querySelector(`.sud-cmp-box[data-i="${sel}"] .sud-cmp-text`)?.focus(), 30);
        return sel;
    }

    // ---------- мышь: рисование, перенос, размер ----------
    function rel(e) {
        const c = document.querySelector('.sud-cmp-canvas').getBoundingClientRect();
        return [clamp((e.clientX - c.left) / c.width, 0, 1), clamp((e.clientY - c.top) / c.height, 0, 1)];
    }
    document.addEventListener('pointerdown', (e) => {
        if (!open || !e.target.closest) return;
        const canvas = e.target.closest('.sud-cmp-canvas');
        if (!canvas || e.target.closest('.sud-cmp-text, .sud-cmp-del')) return;
        const boxEl = e.target.closest('.sud-cmp-box');
        const [px, py] = rel(e);
        if (boxEl) {
            const i = +boxEl.dataset.i, b = S.boxes[i], mode = e.target.closest('[data-drag]')?.dataset.drag;
            if (sel !== i) { sel = i; render(); }
            if (!mode) return;
            drag = { mode, i, px, py, b0: { ...b } };
        } else {
            drag = { mode: 'draw', px, py, i: -1 };
        }
        e.preventDefault();
    });
    document.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const [px, py] = rel(e);
        const dx = px - drag.px, dy = py - drag.py;
        if (drag.mode === 'draw') {
            if (drag.i < 0) {
                if (Math.abs(dx) < 0.02 && Math.abs(dy) < 0.02) return;
                drag.i = addBox(drag.px, drag.py, MIN, MIN);
                if (drag.i < 0) { drag = null; return; }
            }
            const b = S.boxes[drag.i];
            b.x = Math.min(drag.px, px); b.y = Math.min(drag.py, py);
            b.w = Math.max(MIN, Math.abs(dx)); b.h = Math.max(MIN, Math.abs(dy));
            b.w = Math.min(b.w, 1 - b.x); b.h = Math.min(b.h, 1 - b.y);
        } else {
            const b = S.boxes[drag.i], o = drag.b0;
            if (drag.mode === 'move') {
                b.x = clamp(o.x + dx, 0, 1 - o.w); b.y = clamp(o.y + dy, 0, 1 - o.h);
            } else {
                b.w = clamp(o.w + dx, MIN, 1 - o.x); b.h = clamp(o.h + dy, MIN, 1 - o.y);
            }
        }
        const el = document.querySelector(`.sud-cmp-box[data-i="${drag.i}"]`), b = S.boxes[drag.i];
        if (el) Object.assign(el.style, { left: b.x * 100 + '%', top: b.y * 100 + '%', width: b.w * 100 + '%', height: b.h * 100 + '%' });
    });
    document.addEventListener('pointerup', () => {
        if (!drag) return;
        const wasDraw = drag.mode === 'draw' && drag.i >= 0;
        drag = null;
        sync();
        if (wasDraw) setTimeout(() => document.querySelector(`.sud-cmp-box[data-i="${sel}"] .sud-cmp-text`)?.focus(), 30);
    });

    // ---------- клики и ввод ----------
    document.addEventListener('click', (e) => {
        if (!e.target.closest) return;
        if (e.target.closest('.sud-cmp-btn')) { e.preventDefault(); setOpen(!open); return; }
        // нажали Generate — прячем холст, чтобы видеть превью
        if (open && e.target.closest('#generate_button')) { setOpen(false); return; }
        const o = e.target.closest('.sud-cmp');
        if (!o) return;
        const del = e.target.closest('.sud-cmp-del');
        if (del) {
            const i = +del.closest('.sud-cmp-box').dataset.i;
            S.boxes.splice(i, 1);
            sel = Math.min(sel, S.boxes.length - 1);
            sync(); render(); return;
        }
        const it = e.target.closest('.sud-cmp-it');
        if (it) { sel = +it.dataset.i; render(); return; }
        const a = e.target.closest('[data-act]')?.dataset.act;
        if (a === 'add') { const n = S.boxes.length; addBox(0.1 + (n % 3) * 0.28, 0.15 + Math.floor(n / 3) * 0.4, 0.3, 0.35); }
        if (a === 'clear') { S.boxes = []; sel = -1; sync(); render(); }
        if (a === 'close') setOpen(false);
    });
    document.addEventListener('input', (e) => {
        const t = e.target;
        if (!t.matches) return;
        if (t.matches('.sud-cmp-text')) {
            const i = +t.closest('.sud-cmp-box').dataset.i;
            S.boxes[i].prompt = t.value.slice(0, 2000);
            sync();
            const row = document.querySelector(`.sud-cmp-it[data-i="${i}"] .t`);
            if (row) row.textContent = S.boxes[i].prompt || '(пусто)';
        } else if (t.matches('.sud-cmp [data-act="strength"]') && S.boxes[sel]) {
            S.boxes[sel].strength = Math.round(parseFloat(t.value) * 10) / 10;
            t.nextElementSibling.textContent = S.boxes[sel].strength.toFixed(1);
            const head = document.querySelector(`.sud-cmp-box[data-i="${sel}"] .sud-cmp-bhead span`);
            if (head) head.textContent = `${sel + 1} · ×${S.boxes[sel].strength.toFixed(1)}`;
            sync();
        } else if (t.matches('.sud-cmp [data-act="enabled"]')) {
            S.enabled = t.checked; sync();
        }
    });
    document.addEventListener('keydown', (e) => {
        if (!open) return;
        if (e.key === 'Escape' && !e.target.matches?.('.sud-cmp-text')) { setOpen(false); return; }
        if (e.key === 'Escape') { e.target.blur(); return; }
        if ((e.key === 'Delete') && sel >= 0 && !e.target.matches?.('input, textarea')) {
            S.boxes.splice(sel, 1); sel = Math.min(sel, S.boxes.length - 1); sync(); render();
        }
    });

    // поле в gradio появляется не сразу; разрешение могли сменить — пропорции холста
    let lastAspect = '';
    setInterval(() => {
        ensureButton();
        const ta = document.querySelector('.sud-cmp-state textarea, .sud-cmp-state input');
        if (ta && ta.value !== lastSent) sync();
        const a = aspect().join('x');
        if (a !== lastAspect) { lastAspect = a; if (open) render(); }
        if (open) place();
    }, 400);
})();
