// Fooocus-sud: панель 🧬 «Эмбеддинги» у поля промпта.
// Клик — вставить embedding:имя в начало промпта (негативные — в негативный промпт),
// Shift+клик — туда, где стоит курсор; повторный клик по подсвеченному — убрать.
// ★ — избранное, «±» — переключить «негативный». Данные — sud/ui_embeddings.py (скрытые .sud-em-*).
(function () {
    const POS = '#positive_prompt textarea', NEG = '#negative_prompt textarea';
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I_DNA = SVG('<path d="M14.828 14.828a4 4 0 1 0 -5.656 -5.656a4 4 0 0 0 5.656 5.656z"/><path d="M9.172 20.485a4 4 0 1 0 -5.657 -5.657"/><path d="M14.828 3.515a4 4 0 0 0 5.657 5.657"/>');
    const I_STAR = SVG('<path d="M12 17.75l-6.172 3.245l1.179 -6.873l-5 -4.867l6.9 -1l3.086 -6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z"/>');
    const I_SWAP = SVG('<path d="M7 3l-4 4l4 4"/><path d="M3 7h11"/><path d="M17 21l4 -4l-4 -4"/><path d="M21 17h-11"/>');
    const I_IMG = SVG('<path d="M15 8h.01"/><path d="M3 6a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v12a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3v-12z"/><path d="M3 16l5 -5c.928 -.893 2.072 -.893 3 0l5 5"/><path d="M14 14l1 -1c.928 -.893 2.072 -.893 3 0l3 3"/>');

    let S = null, lastRaw = '', open = false, filter = 'all', q = '', caret = null;
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    function send(cmd) {
        const ta = document.querySelector('.sud-em-op textarea, .sud-em-op input');
        const btn = document.querySelector('button.sud-em-op-btn, .sud-em-op-btn button');
        if (!ta || !btn) return false;
        ta.value = JSON.stringify(Object.assign({}, cmd, { nonce: Date.now() }));
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 40);
        return true;
    }
    function readState() {
        const out = document.querySelector('.sud-em-state textarea, .sud-em-state input');
        if (!out || !out.value || out.value === lastRaw) return;
        lastRaw = out.value;
        try { S = JSON.parse(out.value); } catch (e) { return; }
        if (open) render();
    }

    // ---------- работа с текстом промпта ----------
    // (?![\w.-]) — чтобы embedding:neg не находился внутри embedding:negXL
    function tokenRe(name) { return new RegExp(`\\(?embedding:${reEsc(name)}(?![\\w.-])(?::[\\d.]+)?\\)?`, 'i'); }
    function inPrompt(name, neg) { const t = document.querySelector(neg ? NEG : POS); return !!(t && tokenRe(name).test(t.value)); }
    function setValue(t, v) { t.value = v; t.dispatchEvent(new Event('input', { bubbles: true })); }

    function removeFrom(t, name) {
        let v = t.value.replace(new RegExp(`\\s*\\(?embedding:${reEsc(name)}(?![\\w.-])(?::[\\d.]+)?\\)?\\s*,?`, 'i'), ' ');
        v = v.replace(/\s{2,}/g, ' ').replace(/^\s*,\s*/, '').replace(/,\s*,/g, ',').trim().replace(/,$/, '').trim();
        setValue(t, v);
    }
    function insertInto(t, name, atCaret) {
        const tok = `embedding:${name}`;
        const v = t.value;
        if (atCaret && caret !== null && caret <= v.length) {
            const before = v.slice(0, caret), after = v.slice(caret);
            const pre = before && !/[\s,(]$/.test(before) ? ', ' : (before && !/\s$/.test(before) ? ' ' : '');
            const post = after && !/^[\s,)]/.test(after) ? ', ' : '';
            setValue(t, before + pre + tok + post + after);
            caret = (before + pre + tok).length;
        } else {
            setValue(t, v.trim() ? `${tok}, ${v.replace(/^\s+/, '')}` : tok);
        }
    }

    function toggle(item, atCaret) {
        const t = document.querySelector(item.neg ? NEG : POS);
        if (!t) return;
        if (tokenRe(item.name).test(t.value)) { removeFrom(t, item.name); }
        else { insertInto(t, item.name, atCaret && !item.neg); send({ op: 'used', name: item.name }); }
        render();
    }

    // ---------- панель ----------
    function host() { return document.querySelector(POS)?.parentElement; }
    function ensureButton() {
        const box = host()?.querySelector(':scope > .sud-tr');
        if (!box || box.querySelector('.sud-em-btn')) return;
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'sud-em-btn';
        b.title = 'Эмбеддинги (текстовые инверсии)';
        b.innerHTML = `${I_DNA}<span>Эмбеддинги</span>`;
        box.insertBefore(b, box.querySelector('.sud-tr-btn'));
    }
    function panel() {
        let p = document.querySelector('.sud-em-panel');
        if (!p) {
            p = document.createElement('div');
            p.className = 'sud-em-panel';
            document.body.appendChild(p);   // вне блоков gradio: у них overflow:hidden обрезает панель
        }
        return p;
    }
    // панель над полем промпта (поле обычно внизу экрана, а над ним — область картинки)
    function place() {
        const p = document.querySelector('.sud-em-panel');
        const box = document.querySelector('#positive_prompt');
        if (!p || !box || !open) return;
        const r = box.getBoundingClientRect();
        const width = Math.max(r.width, Math.min(760, innerWidth - 24));
        const left = Math.max(12, Math.min(r.left, innerWidth - width - 12));
        const above = r.top - 16, below = innerHeight - r.bottom - 16;
        p.style.left = left + 'px';
        p.style.width = width + 'px';
        if (above >= below) {
            p.style.top = ''; p.style.bottom = (innerHeight - r.top + 8) + 'px';
            p.style.maxHeight = Math.max(200, above - 8) + 'px';
        } else {
            p.style.bottom = ''; p.style.top = (r.bottom + 8) + 'px';
            p.style.maxHeight = Math.max(200, below - 8) + 'px';
        }
    }
    addEventListener('resize', place);
    addEventListener('scroll', place, true);

    function toggleOpen(v) {
        open = v === undefined ? !open : v;
        panel().classList.toggle('show', open);
        place();
        document.querySelector('.sud-em-btn')?.classList.toggle('on', open);
        if (open) { if (!S) panel().innerHTML = '<div class="sud-em-empty">Загружаю…</div>'; send({ op: 'state' }); render(); }
    }

    function tile(it) {
        const used = inPrompt(it.name, it.neg);
        const warn = it.sdxl === false ? '<span class="sud-em-badge sd15" title="Похоже, это эмбеддинг для SD 1.5 — с SDXL работать не будет">SD1.5</span>' : '';
        return `<div class="sud-em-tile${used ? ' used' : ''}${it.sdxl === false ? ' dim' : ''}" data-name="${esc(it.name)}" title="${esc(it.name)}${used ? ' — уже в промпте, клик уберёт' : ''}">
            <div class="sud-em-img">${it.thumb ? `<img src="${it.thumb}" alt="" loading="lazy">` : I_IMG}</div>
            <div class="sud-em-name">${esc(it.name)}</div>
            ${it.neg ? '<span class="sud-em-badge neg">neg</span>' : ''}${warn}
            ${used ? '<span class="sud-em-badge in">в промпте</span>' : ''}
            <button type="button" class="sud-em-star${it.fav ? ' on' : ''}" title="${it.fav ? 'Убрать из избранного' : 'В избранное'}">${I_STAR}</button>
            <button type="button" class="sud-em-flip" title="${it.neg ? 'Сделать позитивным' : 'Сделать негативным'}">${I_SWAP}</button>
        </div>`;
    }

    function render() {
        const p = panel();
        if (!open || !S) return;
        const keepSearch = document.activeElement && document.activeElement.matches('.sud-em-search');
        const ql = q.trim().toLowerCase();
        const list = S.items.filter((it) =>
            (filter === 'all' || (filter === 'fav' && it.fav) || (filter === 'pos' && !it.neg) || (filter === 'neg' && it.neg)) &&
            (!ql || it.name.toLowerCase().includes(ql)));
        const byName = Object.fromEntries(S.items.map((i) => [i.name, i]));
        const recent = !ql && filter === 'all' ? S.recent.map((n) => byName[n]).filter(Boolean) : [];
        const chips = [['all', 'Все'], ['fav', '★ Избранное'], ['pos', 'Позитивные'], ['neg', 'Негативные']]
            .map(([k, t]) => `<button type="button" class="sud-em-chip${filter === k ? ' on' : ''}" data-f="${k}">${t}</button>`).join('');
        p.innerHTML = `<div class="sud-em-top"><input type="text" class="sud-em-search" placeholder="Поиск эмбеддинга" value="${esc(q)}">${chips}</div>
            ${recent.length ? `<div class="sud-em-sec">Недавние</div><div class="sud-em-grid">${recent.map(tile).join('')}</div>` : ''}
            <div class="sud-em-sec">${filter === 'all' && !ql ? 'Все' : 'Найдено'} · ${list.length}</div>
            <div class="sud-em-grid">${list.map(tile).join('') || '<div class="sud-em-empty">Ничего не найдено</div>'}</div>
            <div class="sud-em-hint">Клик — в начало промпта · Shift+клик — туда, где курсор · негативные — в негативный промпт · повторный клик убирает<br>
            Папка на Drive: ${esc(S.folder)}</div>`;
        if (keepSearch) { const s = p.querySelector('.sud-em-search'); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    }

    document.addEventListener('click', (e) => {
        if (!e.target.closest) return;
        if (e.target.closest('.sud-em-btn')) { e.preventDefault(); toggleOpen(); return; }
        const p = e.target.closest('.sud-em-panel');
        if (!p) {
            // настоящий клик мимо панели (но не в поля промптов) — закрыть.
            // e.isTrusted: служебные клики скриптов (скрытые кнопки-мосты) панель не закрывают
            if (open && e.isTrusted && !e.target.closest('#positive_prompt, #negative_prompt, .sud-hidden-btn')) toggleOpen(false);
            return;
        }
        const chip = e.target.closest('.sud-em-chip');
        if (chip) { filter = chip.dataset.f; render(); return; }
        const t = e.target.closest('.sud-em-tile');
        if (!t || !S) return;
        const it = S.items.find((i) => i.name === t.dataset.name);
        if (!it) return;
        if (e.target.closest('.sud-em-star')) { it.fav = !it.fav; send({ op: 'fav', name: it.name, on: it.fav }); render(); return; }
        if (e.target.closest('.sud-em-flip')) { it.neg = !it.neg; send({ op: 'neg', name: it.name, on: it.neg }); render(); return; }
        toggle(it, e.shiftKey);
    });
    document.addEventListener('input', (e) => {
        if (e.target.matches && e.target.matches('.sud-em-search')) { q = e.target.value; render(); }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && open) toggleOpen(false); });
    // запоминаем позицию курсора в промпте (для Shift+клик)
    ['keyup', 'click', 'select'].forEach((ev) => document.addEventListener(ev, (e) => {
        if (e.target.matches && e.target.matches(POS)) caret = e.target.selectionStart;
    }));

    setInterval(() => { ensureButton(); readState(); }, 300);
})();
