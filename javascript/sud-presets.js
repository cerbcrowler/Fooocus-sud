// Fooocus-sud: пресеты в карточках «Сэмплинг» и «LoRA» (один механизм на оба).
// Блок <div class="sud-sp" data-kind="sampling|loras">, данные и сохранение — sud/ui_presets.py
// (скрытые .sud-pr-<kind>-op / -state / -op-btn). Панель сворачивается кликом по заголовку «Пресет».
(function () {
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I = {
        edit: SVG('<path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4"/><path d="M13.5 6.5l4 4"/>'),
        x: SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>'),
        plus: SVG('<path d="M12 5l0 14"/><path d="M5 12l14 0"/>'),
        chev: SVG('<path d="M6 9l6 6l6 -6"/>'),
        star: SVG('<path d="M12 17.75l-6.172 3.245l1.179 -6.873l-5 -4.867l6.9 -1l3.086 -6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z"/>'),
    };
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const ls = {
        get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
    };
    const num = (el) => (el ? parseFloat(el.value) : NaN);

    // ---------- что считается «текущими значениями» каждой карточки ----------
    const KINDS = {
        sampling: {
            current() {
                const n = (sel) => num(document.querySelector(sel + ' input[type=number]'));
                return {
                    sampler: document.querySelector('#sud-sampler input')?.value,
                    scheduler: document.querySelector('#sud-scheduler input')?.value,
                    cfg: n('#sud-cfg'), steps: n('#sud-steps'), sharpness: n('#sud-sharpness'),
                };
            },
            diffs(p, c) {
                const L = { sampler: 'sampler', scheduler: 'scheduler', cfg: 'CFG', steps: 'шаги', sharpness: 'резкость' };
                const out = [];
                for (const k of Object.keys(L)) {
                    const a = p[k], b = c[k];
                    const same = typeof a === 'number' ? Math.abs(a - b) < 0.005 : a === b;
                    if (!same) out.push(`${L[k]} ${a} → ${Number.isFinite(b) || typeof b === 'string' ? b : '?'}`);
                }
                return out;
            },
            summary: (p) => `${p.sampler} · CFG ${p.cfg}`,
            empty: 'Пока нет пресетов — выставь настройки и сохрани их кнопкой «из текущих».',
        },
        loras: {
            current() {
                const loras = [];
                document.querySelectorAll('.sud-lora-row').forEach((row) => {
                    const name = row.querySelector('.sud-lora-name input')?.value;
                    if (!name || name === 'None') return;
                    loras.push({
                        name,
                        weight: num(row.querySelector('.sud-lora-weight input[type=number]')),
                        enabled: !!row.querySelector('.sud-toggle input[type=checkbox]')?.checked,
                    });
                });
                return { loras };
            },
            diffs(p, c) {
                const short = (n) => String(n).split(/[\\/]/).pop().replace(/\.(safetensors|ckpt|pt|bin)$/i, '');
                const a = p.loras || [], b = c.loras || [];
                const out = [];
                const bn = b.map((l) => l.name), an = a.map((l) => l.name);
                a.forEach((l) => { if (!bn.includes(l.name)) out.push(`убрана ${short(l.name)}`); });
                b.forEach((l) => { if (!an.includes(l.name)) out.push(`добавлена ${short(l.name)}`); });
                a.forEach((l) => {
                    const m = b.find((x) => x.name === l.name);
                    if (!m) return;
                    if (Math.abs(l.weight - m.weight) >= 0.005) out.push(`${short(l.name)} ${l.weight} → ${Number.isFinite(m.weight) ? m.weight : '?'}`);
                    if (!!l.enabled !== !!m.enabled) out.push(`${short(l.name)} ${m.enabled ? 'вкл' : 'выкл'}`);
                });
                if (!out.length && an.join('|') !== bn.filter((n) => an.includes(n)).join('|')) out.push('другой порядок');
                return out;
            },
            summary: (p) => `${(p.loras || []).length} LoRA`,
            startup: true,   // при открытии страницы применить пресет «★» (по умолчанию — первый)
            empty: 'Пока нет пресетов — собери лоры и сохрани набор кнопкой «из текущих».',
        },
    };

    // ---------- одна панель ----------
    function Panel(kind, K) {
        const LS_ACTIVE = `sud-pr-${kind}-active`, LS_OPEN = `sud-pr-${kind}-open`, LS_START = `sud-pr-${kind}-start`;
        let booted = false;
        const startName = () => {
            const n = ls.get(LS_START);
            return presets && presets.some((p) => p.name === n) ? n : (presets && presets[0] ? presets[0].name : null);
        };
        const prefix = `sud-pr-${kind}`;
        let presets = null, active = ls.get(LS_ACTIVE), lastRaw = '', lastKey = '';
        let editing = null, confirmDel = null, msg = '', msgTimer = null;
        let opened = ls.get(LS_OPEN) !== '0';
        const box = () => document.querySelector(`.sud-sp[data-kind="${kind}"]`);

        function setActive(name) { active = name; ls.set(LS_ACTIVE, name || null); }
        function flash(text) {
            msg = text; render(true);
            clearTimeout(msgTimer);
            msgTimer = setTimeout(() => { msg = ''; render(true); }, 5000);
        }
        function send(cmd) {
            const ta = document.querySelector(`.${prefix}-op textarea, .${prefix}-op input`);
            const btn = document.querySelector(`button.${prefix}-op-btn, .${prefix}-op-btn button`);
            if (!ta || !btn) return false;
            ta.value = JSON.stringify(Object.assign({}, cmd, { nonce: Date.now() }));
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            setTimeout(() => btn.click(), 40);
            return true;
        }

        function render(force) {
            const b = box();
            if (!b || presets === null) return;
            if (!force && b.contains(document.activeElement) && document.activeElement.matches('input, textarea')) return;
            const cur = K.current();
            const match = presets.find((p) => K.diffs(p, cur).length === 0);
            if (match) setActive(match.name);
            const act = presets.find((p) => p.name === active);
            if (!act && active) setActive(null);
            const mod = act && !match ? K.diffs(act, cur) : [];

            // заголовок: «Пресет · имя ●» + стрелка; в свёрнутом виде больше ничего
            const headName = act ? `<span class="sud-sp-cur">${esc(act.name)}</span>${mod.length ? '<span class="sud-sp-dot" title="Настройки изменены"></span>' : ''}`
                : `<span class="sud-sp-cur none">${presets.length ? 'не выбран' : 'нет'}</span>`;
            const head = `<div class="sud-sp-head" data-act="toggle" title="${opened ? 'Свернуть' : 'Развернуть'}">
                <span class="sud-sp-label">Пресет</span>${headName}<span class="sud-sp-chev${opened ? ' open' : ''}">${I.chev}</span></div>`;
            b.classList.toggle('collapsed', !opened);
            if (!opened) { b.innerHTML = head + (msg ? `<div class="sud-sp-msg">${esc(msg)}</div>` : ''); return; }

            const chips = presets.map((p) => {
                if (editing && editing.kind === 'rename' && editing.name === p.name) {
                    return `<input type="text" class="sud-sp-input" data-kind="rename" data-name="${esc(p.name)}" value="${esc(p.name)}">`;
                }
                const on = act && act.name === p.name;
                const del = confirmDel === p.name
                    ? `<span class="sud-sp-ic danger" data-act="delete" data-sure="1">удалить?</span>`
                    : `<span class="sud-sp-ic" data-act="delete" title="Удалить">${I.x}</span>`;
                return `<span class="sud-sp-chip${on ? ' on' : ''}${match && match.name === p.name ? ' match' : ''}" data-name="${esc(p.name)}" title="${esc((p.note ? p.note + '\n' : '') + K.summary(p))}">
                    <span class="sud-sp-name">${esc(p.name)}</span>${K.startup ? `<span class="sud-sp-ic sud-sp-star${startName() === p.name ? ' on' : ''}" data-act="start" title="${startName() === p.name ? '★ Применяется при открытии страницы' : 'Применять при открытии страницы'}">${I.star}</span>` : ''}
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
            const modified = mod.length ? `<div class="sud-sp-mod"><span class="dot"></span><span class="txt">изменено: ${esc(mod.join(', '))}</span>
                    <button type="button" class="sud-sp-btn" data-act="update">Обновить пресет</button>
                    <button type="button" class="sud-sp-btn" data-act="revert">Вернуть</button></div>` : '';
            const hint = presets.length ? '' : `<div class="sud-sp-hint">${K.empty}</div>`;
            b.innerHTML = `${head}<div class="sud-sp-chips">${chips}${add}</div>${hint}${note}${modified}` +
                (msg ? `<div class="sud-sp-msg">${esc(msg)}</div>` : '');
            const inp = b.querySelector('.sud-sp-input');
            if (inp && document.activeElement !== inp) { inp.focus(); if (inp.select) inp.select(); }
        }

        function readState() {
            const out = document.querySelector(`.${prefix}-state textarea, .${prefix}-state input`);
            if (out && out.value && out.value !== lastRaw) {
                lastRaw = out.value;
                try {
                    const st = JSON.parse(out.value);
                    presets = st.presets || [];
                    if (st.applied) setActive(st.applied);
                    if (st.message) flash(st.message); else render(true);
                    if (!booted) {
                        booted = true;
                        // Fooocus-sud: при открытии страницы — свой пресет вместо «LoRA по умолчанию» из настроек
                        const target = K.startup && presets.find((p) => p.name === startName());
                        if (target && K.diffs(target, K.current()).length) { setActive(target.name); send({ op: 'apply', name: target.name }); }
                    }
                } catch (e) { /* ignore */ }
                return;
            }
            const key = JSON.stringify(K.current());
            if (key !== lastKey) { lastKey = key; render(false); }
        }

        function onClick(e, b) {
            const actEl = e.target.closest('[data-act]');
            const chip = e.target.closest('.sud-sp-chip');
            const a = actEl && actEl.dataset.act;
            const name = chip && chip.dataset.name;
            if (a === 'toggle') { opened = !opened; ls.set(LS_OPEN, opened ? '1' : '0'); editing = null; render(true); return; }
            if (a === 'add') { editing = { kind: 'add' }; render(true); return; }
            if (a === 'start') { ls.set(LS_START, name); render(true); return; }
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
            if (chip && !chip.classList.contains('add')) { setActive(name); send({ op: 'apply', name }); }
        }

        function finishEdit(input, save) {
            const k = input.dataset.kind, name = input.dataset.name, val = input.value.trim();
            editing = null;
            if (save) {
                if (k === 'add' && val) send({ op: 'add', name: val });
                if (k === 'rename' && val && val !== name) { if (active === name) setActive(val); send({ op: 'rename', name, new: val }); }
                if (k === 'note') send({ op: 'note', name, note: val });
            }
            render(true);
        }

        const boot = setInterval(() => { if (send({ op: 'state' })) clearInterval(boot); }, 700);
        setInterval(readState, 300);
        return { onClick, finishEdit };
    }

    const panels = {};
    for (const [kind, K] of Object.entries(KINDS)) panels[kind] = Panel(kind, K);
    const panelOf = (el) => { const b = el.closest && el.closest('.sud-sp[data-kind]'); return b ? [panels[b.dataset.kind], b] : [null, null]; };

    document.addEventListener('click', (e) => {
        const [p, b] = panelOf(e.target);
        if (p) p.onClick(e, b);
    });
    // ввод не отменяется при потере фокуса (переключился в другое окно и вернулся — текст на месте); отмена — Esc
    document.addEventListener('keydown', (e) => {
        const t = e.target;
        if (!t.matches || !t.matches('.sud-sp-input')) return;
        const [p] = panelOf(t);
        if (!p) return;
        if (e.key === 'Escape') { e.preventDefault(); p.finishEdit(t, false); }
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); p.finishEdit(t, true); }
    });
})();
