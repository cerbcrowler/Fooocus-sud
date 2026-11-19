// Fooocus-sud: карточка LoRA (вкладка Models).
// - прячет пустые слоты (None), кнопка «＋ Добавить LoRA» открывает следующий
// - показывает имя лоры в 2 строки: папка мелко сверху, имя без .safetensors
// - счётчик «N из M» и кнопка «выключить все»
// Сами элементы — родные компоненты Fooocus (lora_ctrls), поэтому пресеты,
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
        if (!input) return { empty: true, on: false };
        const value = input.value;
        const empty = !value || value === 'None';
        row.classList.toggle('sud-empty', empty);
        row.classList.toggle('sud-off', !!box && !box.checked);

        const wrap = input.closest('.wrap');
        let label = row.querySelector('.sud-lora-label');
        if (!label && wrap) {
            label = document.createElement('div');
            label.className = 'sud-lora-label';
            wrap.append(label);
            input.closest('.secondary-wrap')?.classList.add('sud-has-label');
            wrap.classList.add('sud-has-label');
        }
        if (label && label.dataset.value !== value) {
            label.dataset.value = value;
            label.title = value;
            if (empty) {
                label.innerHTML = '<small>&nbsp;</small>выбери LoRA…';
            } else {
                const { folder, file } = split(value);
                label.innerHTML = '';
                const small = document.createElement('small');
                small.textContent = folder || ' ';
                label.append(small, document.createTextNode(file));
            }
        }
        return { empty, on: !!box && box.checked };
    }

    function tick() {
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
            add.textContent = hidden.length ? '＋ Добавить LoRA' : 'Все слоты заняты (число слотов — в ⚙️ Настройках)';
        }
    }

    document.addEventListener('click', (e) => {
        const add = e.target.closest('.sud-lora-add');
        if (add) {
            const card = add.closest('.sud-lora-card');
            const row = [...card.querySelectorAll('.sud-lora-row')]
                .find((r) => r.classList.contains('sud-empty') && !r.classList.contains('sud-revealed'));
            if (row) row.classList.add('sud-revealed');
            tick();
            return;
        }
        const off = e.target.closest('.sud-lora-alloff');
        if (off) {
            off.closest('.sud-lora-card').querySelectorAll('.sud-lora-row:not(.sud-empty) .sud-toggle input:checked')
                .forEach((b) => b.click());
            setTimeout(tick, 100);
        }
    });

    // клик в поле лоры: выделить текст целиком, чтобы поиск начинался с чистого листа (а не «NoneTECH/»)
    document.addEventListener('focusin', (e) => {
        const input = e.target.closest && e.target.closest('.sud-lora-name input, .sud-model-select input');
        if (input) setTimeout(() => input.select(), 0);
    });

    setInterval(tick, 400);
})();
