// Fooocus-sud: поведение карточек вкладки Models (LoRA, ползунки, кнопки в заголовках).
// - пустые слоты LoRA (None) скрыты, «＋ Добавить LoRA» открывает следующий
// - имя лоры текстом: имя крупно, ниже папка мелко (без .safetensors)
// - счётчик «N из M», кнопки заголовков: 🔄 обновить файлы, Refiner, выключить все лоры
// - заливка тонких ползунков (--p) по значению; колёсико мыши крутит любой ползунок (в конце файла)
// Сами элементы — родные компоненты Fooocus (lora_ctrls и т.д.), поэтому пресеты,
// загрузка параметров из картинок и генерация работают как раньше.
(function () {
    function split(value) {
        const parts = String(value).split(/[\\/]/);
        const file = parts.pop().replace(/\.(safetensors|ckpt|pt|bin)$/i, '');
        return { folder: parts.join(' / '), file };
    }

    function updateRow(row) {
        const input = row.querySelector('.sud-lora-name input');
        const box = row.querySelector('.sud-toggle input[type=checkbox]');
        if (!input) return { empty: true };
        const value = input.value;
        const empty = !value || value === 'None';
        row.classList.toggle('sud-empty', empty);
        row.classList.toggle('sud-off', !!box && !box.checked);

        const wrap = input.closest('.wrap-inner')?.parentElement;
        let label = row.querySelector('.sud-lora-label');
        if (!label && wrap) {
            label = document.createElement('div');
            label.className = 'sud-lora-label';
            wrap.append(label);
            input.closest('.secondary-wrap')?.classList.add('sud-has-label');
        }
        if (label && label.dataset.value !== value) {
            label.dataset.value = value;
            label.title = value;
            label.classList.toggle('sud-placeholder', empty);
            label.textContent = '';
            if (empty) {
                label.textContent = 'Выбери LoRA…';
            } else {
                const { folder, file } = split(value);
                label.append(document.createTextNode(file));
                if (folder) {
                    const small = document.createElement('small');
                    small.textContent = folder + ' /';
                    label.append(small);
                }
            }
        }
        return { empty };
    }

    function fillRange(r) {
        const min = parseFloat(r.min) || 0, max = parseFloat(r.max) || 100;
        const p = max > min ? ((parseFloat(r.value) - min) / (max - min)) * 100 : 0;
        r.style.setProperty('--p', Math.max(0, Math.min(100, p)) + '%');
    }

    // ---------- удаление и перестановка (команды выполняет sud/ui_loras.py) ----------
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const ICON_X = SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>');
    const DOT = (x, y) => `<path d="M${x} ${y}m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>`;
    const ICON_GRIP = SVG(DOT(9, 5) + DOT(9, 12) + DOT(9, 19) + DOT(15, 5) + DOT(15, 12) + DOT(15, 19));

    function sendOp(cmd) {
        const ta = document.querySelector('.sud-lora-op textarea, .sud-lora-op input');
        const btn = document.querySelector('button.sud-lora-op-btn, .sud-lora-op-btn button');
        if (!ta || !btn) return;
        cmd.nonce = Date.now();
        ta.value = JSON.stringify(cmd);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => {
            btn.click();
            document.querySelectorAll('.sud-lora-row.sud-revealed').forEach((r) => r.classList.remove('sud-revealed'));
        }, 60);
    }

    function decorateRow(row) {
        if (row.querySelector('.sud-grip')) return;
        const grip = document.createElement('div');
        grip.className = 'sud-grip';
        grip.title = 'Перетащи, чтобы поменять порядок';
        grip.innerHTML = ICON_GRIP;
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'sud-lora-del';
        del.title = 'Убрать слот';
        del.innerHTML = ICON_X;
        row.prepend(grip);
        row.append(del);
    }

    // перетаскивание за ⋮⋮ — на событиях указателя (работает и мышью, и пальцем; HTML5 DnD капризный)
    let drag = null;   // { row, card, pointerId }
    function rowsOf(card) { return [...card.querySelectorAll('.sud-lora-row')]; }
    function filledRows(card) { return rowsOf(card).filter((r) => !r.classList.contains('sud-empty')); }
    function clearDropMarks() {
        document.querySelectorAll('.sud-drop-before, .sud-drop-after, .sud-dragging')
            .forEach((r) => r.classList.remove('sud-drop-before', 'sud-drop-after', 'sud-dragging'));
    }
    function dropTarget(card, y) {
        for (const r of filledRows(card)) {
            if (r === drag.row) continue;
            const b = r.getBoundingClientRect();
            if (y >= b.top && y <= b.bottom) return { row: r, before: y < b.top + b.height / 2 };
        }
        return null;
    }

    document.addEventListener('pointerdown', (e) => {
        const grip = e.target.closest && e.target.closest('.sud-grip');
        if (!grip || e.button !== 0) return;
        const row = grip.closest('.sud-lora-row');
        if (row.classList.contains('sud-empty')) return;
        e.preventDefault();
        drag = { row, card: row.closest('.sud-lora-card'), pointerId: e.pointerId };
        row.classList.add('sud-dragging');
        document.body.classList.add('sud-drag-active');
    });
    document.addEventListener('pointermove', (e) => {
        if (!drag || e.pointerId !== drag.pointerId) return;
        e.preventDefault();
        document.querySelectorAll('.sud-drop-before, .sud-drop-after').forEach((r) => r.classList.remove('sud-drop-before', 'sud-drop-after'));
        const t = dropTarget(drag.card, e.clientY);
        if (t) t.row.classList.add(t.before ? 'sud-drop-before' : 'sud-drop-after');
    });
    function endDrag(e) {
        if (!drag || (e && e.pointerId !== drag.pointerId)) return;
        const target = document.querySelector('.sud-drop-before, .sud-drop-after');
        if (target && e && e.type === 'pointerup') {
            const all = rowsOf(drag.card);
            const list = filledRows(drag.card).filter((r) => r !== drag.row);
            const pos = list.indexOf(target) + (target.classList.contains('sud-drop-after') ? 1 : 0);
            list.splice(pos, 0, drag.row);
            const order = list.map((r) => all.indexOf(r));
            all.forEach((r, i) => { if (!order.includes(i)) order.push(i); });   // пустые — в конец
            sendOp({ op: 'move', order });
        }
        clearDropMarks();
        document.body.classList.remove('sud-drag-active');
        drag = null;
    }
    document.addEventListener('pointerup', endDrag);
    document.addEventListener('pointercancel', endDrag);

    // «＋ Добавить»: если пустые слоты затесались выше заполненных — сначала сжать (заполненные вверх)
    function revealNext(card) {
        const all = rowsOf(card);
        const lastFilled = Math.max(-1, ...all.map((r, i) => (r.classList.contains('sud-empty') ? -1 : i)));
        const gapBefore = all.some((r, i) => i < lastFilled && r.classList.contains('sud-empty'));
        if (gapBefore) {
            const filled = all.map((r, i) => i).filter((i) => !all[i].classList.contains('sud-empty'));
            const order = filled.concat(all.map((r, i) => i).filter((i) => !filled.includes(i)));
            sendOp({ op: 'move', order });
            setTimeout(() => { all[filled.length]?.classList.add('sud-revealed'); tick(); }, 500);
            return;
        }
        const row = all.find((r) => r.classList.contains('sud-empty') && !r.classList.contains('sud-revealed'));
        if (row) row.classList.add('sud-revealed');
    }

    // ---------- флаги из настроек ----------
    function applyFlags() {
        const flags = document.getElementById('sud-flags');
        if (!flags) return;
        const hideStyles = flags.dataset.hideStyles === '1';
        document.querySelectorAll('.tab-nav button').forEach((b) => {
            if (b.textContent.trim() === 'Styles') b.style.display = hideStyles ? 'none' : '';
        });
    }

    function tick() {
        applyFlags();
        document.querySelectorAll('.sud-lora-row').forEach(decorateRow);
        document.querySelectorAll('.sud-card input[type=range]').forEach(fillRange);

        const card = document.querySelector('.sud-lora-card');
        if (!card) return;
        const rows = [...card.querySelectorAll('.sud-lora-row')];
        let filled = 0;
        rows.forEach((r) => { if (!updateRow(r).empty) filled++; });

        const count = card.querySelector('.sud-lora-count');
        if (count) count.textContent = `${filled} из ${rows.length}`;

        const add = card.querySelector('.sud-lora-add');
        if (add) {
            const hidden = rows.filter((r) => r.classList.contains('sud-empty') && !r.classList.contains('sud-revealed'));
            add.disabled = hidden.length === 0;
            const text = add.querySelector('span');
            if (text) text.textContent = hidden.length ? 'Добавить LoRA' : 'Все слоты заняты (число — в ⚙️ Настройках)';
        }

    }

    document.addEventListener('click', (e) => {
        const add = e.target.closest('.sud-lora-add');
        if (add) {
            revealNext(add.closest('.sud-lora-card'));
            tick();
            return;
        }
        const del = e.target.closest('.sud-lora-del');
        if (del) {
            const row = del.closest('.sud-lora-row');
            const all = rowsOf(row.closest('.sud-lora-card'));
            if (row.classList.contains('sud-empty')) {
                row.classList.remove('sud-revealed');   // пустой открытый слот — просто спрятать
                tick();
            } else {
                sendOp({ op: 'remove', index: all.indexOf(row) });
            }
            return;
        }
        const btn = e.target.closest('[data-sud-action]');
        if (!btn) return;
        const action = btn.dataset.sudAction;
        if (action === 'refresh') {
            document.querySelector('.sud-model-card .sud-hidden-btn')?.click();
            btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin');
        } else if (action === 'lora-alloff') {
            document.querySelectorAll('.sud-lora-row:not(.sud-empty) .sud-toggle input:checked').forEach((b) => b.click());
            setTimeout(tick, 100);
        }
    });

    // ползунок тянут — заливка сразу
    document.addEventListener('input', (e) => {
        if (e.target.matches && e.target.matches('.sud-card input[type=range]')) fillRange(e.target);
    });

    // клик мышкой в поле лоры/модели: выделить текст целиком, чтобы поиск начинался с чистого листа.
    // Только по клику: при наборе gradio сам перефокусирует поле, и выделение затёрло бы ввод.
    const FIELD = '.sud-lora-name input, .sud-model-card .secondary-wrap input';
    document.addEventListener('pointerdown', (e) => {
        const input = e.target.closest && e.target.closest('.sud-lora-name, .sud-model-card .wrap')?.querySelector('input');
        if (input && input.matches(FIELD) && document.activeElement !== input) {
            setTimeout(() => input.select(), 30);
        }
    });

    setInterval(tick, 400);
})();

// ================= колёсико мыши на ползунках (все ползунки интерфейса) =================
// Fooocus-sud: ползунки крутятся колёсиком мыши при наведении.
// Шаг — шаг самого ползунка; Shift — ×10, Ctrl/Alt — точно (÷10, если шаг позволяет дробь не хуже 0.001).
// Чтобы не «ловить» ползунки при обычной прокрутке страницы: колесо срабатывает, только если курсор
// уже ~250 мс стоит над ползунком (или колесо уже крутили над ним только что).
(function () {
    const HOLD_MS = 250;
    let hoverEl = null, hoverSince = 0, lastWheel = 0, acc = 0, accEl = null;

    document.addEventListener('pointerover', (e) => {
        const r = e.target.closest && e.target.closest('input[type=range]');
        if (r !== hoverEl) { hoverEl = r; hoverSince = performance.now(); }
    });

    const decimals = (x) => { const s = String(x); return s.includes('.') ? s.split('.')[1].length : 0; };

    document.addEventListener('wheel', (e) => {
        const r = e.target.closest && e.target.closest('input[type=range]');
        if (!r || r.disabled) return;
        const now = performance.now();
        if (r !== hoverEl || (now - hoverSince < HOLD_MS && now - lastWheel > 400)) return;
        e.preventDefault();
        lastWheel = now;

        let step = parseFloat(r.step);
        if (!step || step <= 0) step = 1;
        if (e.shiftKey) step *= 10;
        else if ((e.ctrlKey || e.altKey) && step / 10 >= 0.001) step /= 10;
        const min = parseFloat(r.min || '0'), max = parseFloat(r.max || '100');
        // один щелчок колеса ≈ 100 px (в строках — ×33); тачпад шлёт мелкие порции — копим
        const px = (e.deltaY || e.deltaX) * (e.deltaMode === 1 ? 33 : e.deltaMode === 2 ? 400 : 1);
        if (r !== accEl) { accEl = r; acc = 0; }
        acc += px;
        const ticks = Math.trunc(acc / 100);
        if (!ticks) return;
        acc -= ticks * 100;
        const prec = Math.max(decimals(r.step || 1), decimals(step));
        let v = Math.round((parseFloat(r.value) - ticks * step) * 10 ** prec) / 10 ** prec;
        v = Math.min(max, Math.max(min, v));
        if (String(v) === r.value) return;
        r.value = String(v);
        r.dispatchEvent(new Event('input', { bubbles: true }));
        r.dispatchEvent(new Event('change', { bubbles: true }));
    }, { passive: false });
})();
