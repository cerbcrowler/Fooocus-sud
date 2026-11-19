// Fooocus-sud: пресеты сэмплинга в карточке «Сэмплинг».
// Данные и сохранение — sud/ui_presets.py (скрытые .sud-sp-op / .sud-sp-state / .sud-sp-op-btn).
// Текущие значения читаются из полей #sud-sampler, #sud-scheduler, #sud-cfg, #sud-steps, #sud-sharpness.
(function () {
    const LS_ACTIVE = 'sud-sp-active';
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I = {
        edit: SVG('<path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/>'),
        x: SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>'),
        plus: SVG('<path d="M12 5l0 14"/><path d="M5 12l14 0"/>'),
    };
    const LABELS = { sampler: 'sampler', scheduler: 'scheduler', cfg: 'CFG', steps: 'шаги', sharpness: 'резкость' };

    let presets = null;
    let active = null;
    let lastRaw = '', lastKey = '';
    let editing = null;      // { kind: 'add' | 'rename' | 'note', name }
    let confirmDel = null;
    let msg = '', msgTimer = null;
    try { active = localStorage.getItem(LS_ACTIVE); } catch (e) { /* ignore */ }

    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const num = (sel) => { const el = document.querySelector(sel + ' input[type=number]'); return el ? parseFloat(el.value) : NaN; };
    function current() {
        return {
            sampler: document.querySelector('#sud-sampler input')?.value,
            scheduler: document.querySelector('#sud-scheduler input')?.value,
            cfg: num('#sud-cfg'), steps: num('#sud-steps'), sharpness: num('#sud-sharpness'),
        };
    }
    function diffs(p, c) {
        const out = [];
        for (const k of Object.keys(LABELS)) {
            const a = p[k], b = c[k];
            const same = typeof a === 'number' ? Math.abs(a - b) < 0.005 : a === b;
            if (!same) out.push(`${LABELS[k]} ${a} → ${Number.isFinite(b) || typeof b === 'string' ? b : '?'}`);
        }
        return out;
    }
    function setActive(name) {
        active = name;
        try { name ? localStorage.setItem(LS_ACTIVE, name) : localStorage.removeItem(LS_ACTIVE); } catch (e) { /* ignore */ }
    }
    function flash(text) {
        msg = text; render(true);
        clearTimeout(msgTimer);
        msgTimer = setTimeout(() => { msg = ''; render(true); }, 3500);
    }

    function send(cmd) {
        const ta = document.querySelector('.sud-sp-op textarea, .sud-sp-op input');
        const btn = document.querySelector('button.sud-sp-op-btn, .sud-sp-op-btn button');
        if (!ta || !btn) return false;
        ta.value = JSON.stringify(Object.assign({}, cmd, { nonce: Date.now() }));
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 40);
        return true;
    }

    function render(force) {
        const box = document.querySelector('.sud-sp');
        if (!box || presets === null) return;
        if (!force && box.contains(document.activeElement) && document.activeElement.matches('input, textarea')) return;
        const cur = current();
        const match = presets.find((p) => diffs(p, cur).length === 0);
        if (match) setActive(match.name);
        const act = presets.find((p) => p.name === active);
        if (!act && active) setActive(null);

        const chips = presets.map((p) => {
            if (editing && editing.kind === 'rename' && editing.name === p.name) {
                return `<input type="text" class="sud-sp-input" data-kind="rename" data-name="${esc(p.name)}" value="${esc(p.name)}">`;
            }
            const on = act && act.name === p.name;
            const del = confirmDel === p.name
                ? `<span class="sud-sp-ic danger" data-act="delete" data-sure="1">удалить?</span>`
                : `<span class="sud-sp-ic" data-act="delete" title="Удалить">${I.x}</span>`;
            return `<span class="sud-sp-chip${on ? ' on' : ''}${match && match.name === p.name ? ' match' : ''}" data-name="${esc(p.name)}" title="${esc(p.note || p.name)}">
                <span class="sud-sp-name">${esc(p.name)}</span>
                <span class="sud-sp-ic" data-act="rename" title="Переименовать">${I.edit}</span>${del}</span>`;
        }).join('');
        const add = editing && editing.kind === 'add'
            ? `<input type="text" class="sud-sp-input" data-kind="add" placeholder="Название, Enter">`
            : `<span class="sud-sp-chip add" data-act="add" title="Сохранить текущие настройки как пресет">${I.plus}<span>из текущих</span></span>`;

        let note = '';
        if (act) {
            note = editing && editing.kind === 'note'
                ? `<textarea class="sud-sp-input sud-sp-noteedit" data-kind="note" data-name="${esc(act.name)}" rows="2" placeholder="Впечатления, для чего хорош… Enter — сохранить">${esc(act.note || '')}</textarea>`
                : `<div class="sud-sp-note${act.note ? '' : ' empty'}" data-act="note">${act.note ? esc(act.note) : '＋ заметка к пресету'}</div>`;
        }
        let modified = '';
        if (act && !match) {
            const d = diffs(act, cur);
            modified = `<div class="sud-sp-mod"><span class="dot"></span><span class="txt">изменено: ${esc(d.join(', '))}</span>
                <button type="button" class="sud-sp-btn" data-act="update">Обновить пресет</button>
                <button type="button" class="sud-sp-btn" data-act="revert">Вернуть</button></div>`;
        }
        const hint = presets.length ? '' : '<div class="sud-sp-hint">Пока нет пресетов — выставь настройки и сохрани их кнопкой «из текущих».</div>';
        box.innerHTML = `<div class="sud-sp-label">Пресет</div><div class="sud-sp-chips">${chips}${add}</div>${hint}${note}${modified}` +
            (msg ? `<div class="sud-sp-msg">${esc(msg)}</div>` : '');
        const inp = box.querySelector('.sud-sp-input');
        if (inp && document.activeElement !== inp) { inp.focus(); if (inp.select) inp.select(); }
    }

    function readState() {
        const out = document.querySelector('.sud-sp-state textarea, .sud-sp-state input');
        if (out && out.value && out.value !== lastRaw) {
            lastRaw = out.value;
            try {
                const st = JSON.parse(out.value);
                presets = st.presets || [];
                if (st.applied) setActive(st.applied);
                if (st.message) flash(st.message); else render(true);
            } catch (e) { /* ignore */ }
            return;
        }
        // значения в карточке поменялись — пересчитать подсветку и «изменено»
        const key = JSON.stringify(current());
        if (key !== lastKey) { lastKey = key; render(false); }
    }

    document.addEventListener('click', (e) => {
        const box = e.target.closest && e.target.closest('.sud-sp');
        if (!box) return;
        const actEl = e.target.closest('[data-act]');
        const chip = e.target.closest('.sud-sp-chip');
        const a = actEl && actEl.dataset.act;
        const name = chip && chip.dataset.name;
        if (a === 'add') { editing = { kind: 'add' }; render(true); return; }
        if (a === 'rename') { editing = { kind: 'rename', name }; render(true); return; }
        if (a === 'delete') {
            if (!actEl.dataset.sure) {
                confirmDel = name; render(true);
                setTimeout(() => { if (confirmDel === name) { confirmDel = null; render(true); } }, 3000);
                return;
            }
            confirmDel = null;
            if (active === name) setActive(null);
            send({ op: 'delete', name });
            return;
        }
        if (a === 'note') { editing = { kind: 'note' }; render(true); return; }
        if (a === 'update') { send({ op: 'update', name: active }); return; }
        if (a === 'revert') { send({ op: 'apply', name: active }); return; }
        if (chip && !chip.classList.contains('add')) {
            setActive(name);
            send({ op: 'apply', name });
        }
    });

    function finishEdit(input, save) {
        const kind = input.dataset.kind, name = input.dataset.name, val = input.value.trim();
        editing = null;
        if (save) {
            if (kind === 'add' && val) send({ op: 'add', name: val });
            if (kind === 'rename' && val && val !== name) { if (active === name) setActive(val); send({ op: 'rename', name, new: val }); }
            if (kind === 'note') send({ op: 'note', name, note: val });
        }
        render(true);
    }
    document.addEventListener('keydown', (e) => {
        const t = e.target;
        if (!t.matches || !t.matches('.sud-sp-input')) return;
        if (e.key === 'Escape') { e.preventDefault(); finishEdit(t, false); }
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); finishEdit(t, true); }
    });
    // ввод не отменяется при потере фокуса (переключился в другое окно и вернулся — текст на месте); отмена — Esc

    // первый запрос списка, когда элементы gradio на месте
    const boot = setInterval(() => { if (send({ op: 'state' })) clearInterval(boot); }, 700);
    setInterval(readState, 300);
})();
