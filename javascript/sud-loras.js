// Fooocus-sud: поведение карточек вкладки Models (LoRA, ползунки, кнопки в заголовках).
// - пустые слоты LoRA (None) скрыты, «＋ Добавить LoRA» открывает следующий
// - имя лоры текстом: имя крупно, ниже папка мелко (без .safetensors)
// - счётчик «N из M», кнопки заголовков: 🔄 обновить файлы, Refiner, выключить все лоры
// - заливка тонких ползунков (--p) по значению
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

    function tick() {
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

        const refinerBtn = document.querySelector('.sud-model-card [data-sud-action=refiner]');
        const refinerOpen = document.querySelector('.sud-refiner > .label-wrap.open');
        if (refinerBtn) refinerBtn.classList.toggle('active', !!refinerOpen);
    }

    document.addEventListener('click', (e) => {
        const add = e.target.closest('.sud-lora-add');
        if (add) {
            const row = [...add.closest('.sud-lora-card').querySelectorAll('.sud-lora-row')]
                .find((r) => r.classList.contains('sud-empty') && !r.classList.contains('sud-revealed'));
            if (row) row.classList.add('sud-revealed');
            tick();
            return;
        }
        const btn = e.target.closest('[data-sud-action]');
        if (!btn) return;
        const action = btn.dataset.sudAction;
        if (action === 'refresh') {
            document.querySelector('.sud-model-card .sud-hidden-btn')?.click();
            btn.classList.remove('spin'); void btn.offsetWidth; btn.classList.add('spin');
        } else if (action === 'refiner') {
            document.querySelector('.sud-refiner > .label-wrap')?.click();
            setTimeout(tick, 50);
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
