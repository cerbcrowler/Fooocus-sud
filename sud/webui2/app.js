// Fooocus-sud — новый интерфейс, этап 1: экран генерации поверх /sud/api (sud/api.py).
// Без сборки и библиотек. Состояние интерфейса — localStorage «sud2-ui» (переживает F5 и новые сессии Colab).
(function () {
    'use strict';
    const API = 'api/';
    const LS = 'sud2-ui', LS_HIST = 'sud2-history';
    const $ = (s, r = document) => r.querySelector(s);
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const lsGet = (k, d) => { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? d; } catch (e) { return d; } };
    const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } };
    const rawGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };   // строки классического интерфейса
    const ICON = {
        create: '<path d="M16 18a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2zm0 -12a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2zm-7 12a6 6 0 0 1 6 -6a6 6 0 0 1 -6 -6a6 6 0 0 1 -6 6a6 6 0 0 1 6 6z"/>',
        gallery: '<path d="M15 8h.01"/><path d="M3 6a3 3 0 0 1 3 -3h12a3 3 0 0 1 3 3v12a3 3 0 0 1 -3 3h-12a3 3 0 0 1 -3 -3v-12z"/><path d="M3 16l5 -5c.928 -.893 2.072 -.893 3 0l5 5"/><path d="M14 14l1 -1c.928 -.893 2.072 -.893 3 0l3 3"/>',
        classic: '<path d="M4 4h6v6h-6z"/><path d="M14 4h6v6h-6z"/><path d="M4 14h6v6h-6z"/><path d="M14 17h6"/><path d="M17 14v6"/>',
        sun: '<path d="M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"/><path d="M3 12h1m8 -9v1m8 8h1m-9 8v1m-6.4 -15.4l.7 .7m12.1 -.7l-.7 .7m0 11.4l.7 .7m-12.1 -.7l-.7 .7"/>',
        moon: '<path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454z"/>',
        chev: '<path d="M6 9l6 6l6 -6"/>',
    };
    const svg = (n) => `<svg class="i" viewBox="0 0 24 24">${ICON[n]}</svg>`;

    // ---------- состояние ----------
    let SRV = null;                                   // ответ /state
    let U = Object.assign({                           // выбор пользователя
        prompt: '', negative: '', showNeg: false, model: null, loras: null, sampler: null, scheduler: null,
        steps: -1, cfg: 1, sharpness: 2, aspect: null, image_number: 1, output_format: 'png', performance: null,
        random: true, seed: '', closed: {}, camera: { enabled: false, angle: '', height: '', shot: '', weight: 1.2 },
    }, lsGet(LS, {}));
    let history = lsGet(LS_HIST, []);                 // [{key, url, seed, prompt}]
    let current = null, running = null;
    const save = () => lsSet(LS, U);

    // ---------- API ----------
    async function api(path, body) {
        const r = await fetch(API + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
        return r.json();
    }

    // ---------- карточки справа ----------
    const card = (id, title, sub, body, fold = true) => `<div class="card${fold ? ' fold' : ''}${U.closed[id] ? ' closed' : ''}" data-card="${id}">
        <div class="ch">${title}${sub ? `<span class="sub">${sub}</span>` : ''}${fold ? `<span class="chev">${svg('chev')}</span>` : ''}</div><div class="body">${body}</div></div>`;
    const opts = (list, val, label = (x) => x) => list.map((x) => `<option value="${esc(x)}"${x === val ? ' selected' : ''}>${esc(label(x))}</option>`).join('');
    const short = (n) => String(n).split(/[\\/]/).pop().replace(/\.(safetensors|ckpt|pt|bin)$/i, '');
    const range = (key, label, min, max, step, val) => `<div class="row"><label>${label}</label><input type="range" data-u="${key}" min="${min}" max="${max}" step="${step}" value="${val}"><output>${val}</output></div>`;
    const arOf = (label) => { const m = String(label).match(/(\d+)\s*[×x*]\s*(\d+)/); return m ? [+m[1], +m[2]] : [1, 1]; };
    const gcd = (a, b) => (b ? gcd(b, a % b) : a);

    const CAM_ANGLES = [['front', 'спереди', 90], ['q_right', '¾ вправо', 45], ['right', 'профиль вправо', 0], ['bq_right', 'сзади ¾ вправо', -45],
        ['back', 'сзади', -90], ['bq_left', 'сзади ¾ влево', -135], ['left', 'профиль влево', 180], ['q_left', '¾ влево', 135]];
    const CAM_H = [['', '—'], ['top', 'С дрона'], ['high', 'Сверху'], ['above', 'Чуть сверху'], ['eye', 'На уровне глаз'], ['low', 'Снизу'], ['worm', 'С земли'], ['selfie', 'Селфи']];
    const CAM_S = [['', '—'], ['ecu', 'Глаза крупно'], ['cu', 'Лицо'], ['mcu', 'По плечи'], ['ms', 'По пояс'], ['cowboy', 'По бёдра'], ['full', 'Во весь рост'], ['long', 'Общий план'], ['establishing', 'Издалека'], ['pov', 'От первого лица']];
    const camLabel = (l, k) => (l.find((x) => x[0] === k) || [])[1];
    const camOn = () => U.camera.enabled && (U.camera.angle || U.camera.height || U.camera.shot);
    const camSummary = () => (camOn() ? [camLabel(CAM_ANGLES, U.camera.angle), camLabel(CAM_H, U.camera.height), camLabel(CAM_S, U.camera.shot)].filter((x) => x && x !== '—').join(' · ') : 'выкл');

    // ---------- пресеты: сохранить текущие / переименовать / заметка / перезаписать / удалить ----------
    const PE = { kind: null, name: null, nameVal: '', noteVal: '', del: false, busy: false, err: '' };   // name=null — новый
    const EDIT = { sampling: false, loras: false };                                                     // режим ✎: клик по пилюле = править
    const presetsOf = (kind) => (kind === 'sampling' ? SRV.sampling_presets : SRV.lora_presets);
    const curValues = (kind) => (kind === 'sampling'
        ? { sampler: U.sampler, scheduler: U.scheduler, cfg: +U.cfg, steps: +U.steps, sharpness: +U.sharpness }
        : { loras: U.loras.filter((l) => l[1] && l[1] !== 'None').map(([on, name, w]) => ({ name, weight: Math.round(+w * 100) / 100, enabled: !!on })) });
    const sumOf = (kind, v) => (kind === 'sampling'
        ? `${v.sampler} · ${v.scheduler} · ${+v.steps < 0 ? 'шаги авто' : v.steps + ' шагов'} · CFG ${(+v.cfg).toFixed(1)} · резкость ${+v.sharpness}`
        : ((v.loras || []).map((l) => `${l.enabled === false ? '⊘ ' : ''}${short(l.name)} ×${(+l.weight).toFixed(1)}`).join(', ') || 'без LoRA'));
    function peOpen(kind, name) {
        const p = name == null ? null : presetsOf(kind).find((x) => x.name === name);
        Object.assign(PE, { kind, name: p ? p.name : null, nameVal: p ? p.name : '', noteVal: p ? (p.note || '') : '', del: false, busy: false, err: '' });
        renderRight();
        const inp = document.querySelector(`.pe[data-pe-kind="${kind}"] [data-pe="name"]`);
        if (inp) { inp.focus(); inp.select(); }
    }
    const peClose = () => { PE.kind = null; renderRight(); };
    function peBox(kind) {
        if (PE.kind !== kind) return EDIT[kind] ? '<div class="hint pe-hint">✎ Нажми пресет, чтобы переименовать, перезаписать или удалить. Перетаскивать тоже можно.</div>' : '';
        const isNew = PE.name == null, p = isNew ? null : presetsOf(kind).find((x) => x.name === PE.name);
        const now = sumOf(kind, curValues(kind)), was = p ? sumOf(kind, p) : '', same = p && now === was;
        const star = kind === 'loras' && p && (rawGet('sud-pr-loras-start') || (SRV.lora_presets[0] || {}).name) === p.name;
        return `<div class="pe" data-pe-kind="${kind}">
            <div class="pe-t">${isNew ? 'Новый пресет из текущих настроек' : 'Пресет'}<button class="x" data-pe-do="close" title="Закрыть (Esc)">✕</button></div>
            <input type="text" data-pe="name" placeholder="Название" value="${esc(PE.nameVal)}" maxlength="60">
            <input type="text" data-pe="note" placeholder="Заметка — видна при наведении (необязательно)" value="${esc(PE.noteVal)}" maxlength="200">
            ${isNew ? `<div class="pe-v"><span>будет:</span> ${esc(now)}</div>`
                : (same ? `<div class="pe-v"><span>в пресете:</span> ${esc(was)} <em>= сейчас</em></div>`
                    : `<div class="pe-v"><span>в пресете:</span> ${esc(was)}</div><div class="pe-v now"><span>сейчас:</span> ${esc(now)}</div>`)}
            ${PE.err ? `<div class="pe-err">${esc(PE.err)}</div>` : ''}
            <div class="pe-b">${isNew
                ? '<button class="btn-s acc" data-pe-do="add">Сохранить</button><button class="btn-s" data-pe-do="close">Отмена</button>'
                : `<button class="btn-s acc" data-pe-do="edit" title="Сохранить название и заметку">Сохранить</button>
                   <button class="btn-s" data-pe-do="update"${same ? ' disabled' : ''} title="Записать в пресет то, что выставлено сейчас">⟳ Записать текущие</button>
                   ${kind === 'loras' ? `<button class="btn-s${star ? ' on' : ''}" data-pe-do="star" title="Ставится при первом запуске (★ — как в классическом)">★</button>` : ''}
                   <button class="btn-s danger${PE.del ? ' sure' : ''}" data-pe-do="delete" title="Удалить пресет">${PE.del ? 'Точно удалить?' : '🗑'}</button>`}</div></div>`;
    }
    async function peDo(what) {
        const kind = PE.kind;
        if (!kind || PE.busy) return;
        if (what === 'close') { peClose(); return; }
        if (what === 'star') {
            try { localStorage.setItem('sud-pr-loras-start', PE.name); } catch (e) { /* */ }
            renderRight(); return;
        }
        if (what === 'delete' && !PE.del) { PE.del = true; renderRight(); return; }
        const name = PE.nameVal.split(/\s+/).filter(Boolean).join(' ');
        if ((what === 'add' || what === 'edit') && !name) { PE.err = 'Введи название'; renderRight(); return; }
        const body = { kind, op: what, name: what === 'add' ? name : PE.name };
        if (what === 'add') Object.assign(body, { note: PE.noteVal, values: curValues(kind) });
        if (what === 'update') body.values = curValues(kind);
        if (what === 'edit') Object.assign(body, { new: name, note: PE.noteVal });
        PE.busy = true; PE.err = '';
        try {
            const r = await api('presets', body);
            SRV[kind === 'sampling' ? 'sampling_presets' : 'lora_presets'] = r.presets;
            if (kind === 'loras' && rawGet('sud-pr-loras-start') === PE.name) {   // ★ следует за переименованием/удалением
                try { if (what === 'delete') localStorage.removeItem('sud-pr-loras-start'); else if (what === 'edit') localStorage.setItem('sud-pr-loras-start', name); } catch (e) { /* */ }
            }
            PE.busy = false;
            if (what === 'delete') { peClose(); return; }
            if (what === 'add' || what === 'edit') { PE.name = name; PE.nameVal = name; }
            PE.del = false;
            flash(what === 'add' ? 'Пресет сохранён' : what === 'update' ? 'Пресет перезаписан' : 'Сохранено');
            if (what === 'add') { PE.kind = null; }
            renderRight();
        } catch (e) { PE.busy = false; PE.err = e.message; renderRight(); }
    }
    function flash(text) {
        let el = $('#flash');
        if (!el) { el = document.createElement('div'); el.id = 'flash'; document.body.appendChild(el); }
        el.textContent = '✓ ' + text; el.classList.add('show');
        clearTimeout(flash.t); flash.t = setTimeout(() => el.classList.remove('show'), 1600);
    }
    const peTools = (kind) => `<button class="pill tool" data-pe-new="${kind}" title="Сохранить текущие настройки как новый пресет">＋</button><button class="pill tool${EDIT[kind] ? ' on' : ''}" data-pe-mode="${kind}" title="Правка пресетов: переименовать, перезаписать, удалить">✎</button>`;

    function renderRight() {
        if (!SRV) return;
        const S = SRV;
        const startLora = rawGet('sud-pr-loras-start') || (S.lora_presets[0] || {}).name;
        // Модель
        let html = card('model', '<b>Модель</b>', '', `<select data-u="model">${opts(S.models, U.model, short)}</select>`, false);
        // Сэмплинг
        const sp = S.sampling_presets.map((p) => {
            const on = p.sampler === U.sampler && p.scheduler === U.scheduler && +p.steps === +U.steps && Math.abs(p.cfg - U.cfg) < 0.01 && Math.abs(p.sharpness - U.sharpness) < 0.01;
            const ed = PE.kind === 'sampling' && PE.name === p.name;
            return `<button class="pill${on ? ' on' : ''}${ed ? ' edit' : ''}" data-sp="${esc(p.name)}" title="${esc(p.note || '')}">${esc(p.name)}</button>`;
        }).join('');
        html += card('sampling', '<b>Сэмплинг</b>', `${U.sampler} · ${U.scheduler} · ${U.steps < 0 ? 'авто' : U.steps}`,
            `<div class="pills" data-kind="sampling" title="Пресеты можно перетаскивать — порядок сохранится">${sp || '<span class="hint">пресетов нет</span>'}${peTools('sampling')}</div>${peBox('sampling')}
             <div class="half"><select data-u="sampler">${opts(S.samplers, U.sampler)}</select><select data-u="scheduler">${opts(S.schedulers, U.scheduler)}</select></div>
             ${range('steps', 'Шаги', -1, 60, 1, U.steps)}${range('cfg', 'CFG', 1, 15, 0.1, U.cfg)}${range('sharpness', 'Резкость', 0, 30, 1, U.sharpness)}`);
        // LoRA
        const lp = S.lora_presets.map((p) => `<button class="pill${PE.kind === 'loras' && PE.name === p.name ? ' edit' : ''}" data-lp="${esc(p.name)}" title="${esc((p.note ? p.note + '\n' : '') + (p.loras || []).map((l) => short(l.name) + ' ×' + l.weight).join(', '))}">${esc(p.name)}${p.name === startLora ? '<span class="star">★</span>' : ''}</button>`).join('');
        const rows = U.loras.map(([on, name, w], i) => `<div class="lora" data-row="${i}"><span class="grip" title="Потяни, чтобы поменять порядок">⋮⋮</span><input type="checkbox" data-lora-on="${i}"${on ? ' checked' : ''}>
            <select data-lora-name="${i}"><option value="None">—</option>${opts(S.loras, name, (x) => x.replace(/\.safetensors$/i, ''))}</select>
            <button class="x" data-lora-del="${i}" title="Убрать">✕</button>
            <div class="w"><input type="range" data-lora-w="${i}" min="${S.lora_min}" max="${S.lora_max}" step="0.1" value="${w}"><output>${(+w).toFixed(1)}</output></div></div>`).join('');
        html += card('loras', '<b>LoRA</b>', `${U.loras.filter((l) => l[0]).length} из ${S.lora_slots}`,
            `<div class="pills" data-kind="loras">${lp}${peTools('loras')}</div>${peBox('loras')}<div class="loras">${rows}</div>${U.loras.length < S.lora_slots
                ? '<button class="add" data-act="lora-add">＋ Добавить LoRA</button>'
                : `<div class="add full" title="Больше слотов: ⚙️ Настройки классического интерфейса → «Слотов LoRA»">Все ${S.lora_slots} слота заняты · убери лишнюю ✕ или добавь слотов в ⚙️ Настройках</div>`}`);
        // Разрешение
        const ars = S.aspects.map((a) => {
            const [w, h] = arOf(a), g = gcd(w, h), k = 18 / Math.max(w, h);
            return `<button class="ar${a === U.aspect ? ' on' : ''}" data-ar="${esc(a)}" title="${w}×${h}"><span class="r" style="width:${Math.round(w * k)}px;height:${Math.round(h * k)}px"></span>${w / g}:${h / g}</button>`;
        }).join('');
        const [aw, ah] = arOf(U.aspect);
        html += card('aspect', '<b>Разрешение</b>', `${aw}×${ah}`, `<div class="ars">${ars}</div>`);
        // Камера
        const dots = CAM_ANGLES.map(([k, t, a]) => `<button class="d${U.camera.angle === k ? ' on' : ''}" data-cam-angle="${k}" title="${t}" style="left:${48 + 36 * Math.cos(a * Math.PI / 180)}px;top:${48 + 36 * Math.sin(a * Math.PI / 180)}px"></button>`).join('');
        html += card('camera', '<b>Камера</b>', camSummary(),
            `<div class="cam"><div class="dial"><div class="ring"></div><button class="who${U.camera.angle ? '' : ' on'}" data-cam-angle="" title="Ракурс не задан"></button>${dots}</div>
             <div><select data-cam="height">${CAM_H.map(([k, t]) => `<option value="${k}"${U.camera.height === k ? ' selected' : ''}>Высота: ${t}</option>`).join('')}</select>
             <select data-cam="shot" style="margin-top:6px">${CAM_S.map(([k, t]) => `<option value="${k}"${U.camera.shot === k ? ' selected' : ''}>План: ${t}</option>`).join('')}</select>
             <div class="row"><label style="width:auto">Сила</label><input type="range" data-cam="weight" min="0.5" max="2" step="0.1" value="${U.camera.weight}"><output>${(+U.camera.weight).toFixed(1)}</output></div></div></div>
             <label class="row" style="gap:6px"><input type="checkbox" data-cam="enabled"${U.camera.enabled ? ' checked' : ''}> <span class="hint">включена — слова о ракурсе добавятся в конец промпта</span></label>`);
        // Ещё
        html += card('more', '<b>Ещё</b>', `×${U.image_number} · ${U.random ? 'seed случайный' : 'seed ' + U.seed}`,
            `${range('image_number', 'Картинок', 1, S.max_images, 1, U.image_number)}
             <div class="row"><label>Seed</label><input type="checkbox" data-u="random"${U.random ? ' checked' : ''} title="Случайный"><input type="text" data-u="seed" value="${esc(U.seed)}" placeholder="случайный"${U.random ? ' disabled' : ''}></div>
             <div class="row"><label>Формат</label><select data-u="output_format">${opts(S.output_formats, U.output_format)}</select></div>
             <div class="row"><label>Performance</label><select data-u="performance">${opts(S.performances, U.performance)}</select></div>`);
        $('#right').innerHTML = html;
        updateGenButton();
        $('#chip-cam').textContent = 'Камера · ' + camSummary();
        $('#chip-cam').classList.toggle('on', !!camOn());
    }

    // ---------- автосохранение на ноут (та же папка, что у javascript/sud-autosave.js: IndexedDB «sud-autosave») ----------
    const SAVE = { dir: null, enabled: true, perm: 'none', count: 0 };
    const idb = () => new Promise((res, rej) => { const r = indexedDB.open('sud-autosave', 1); r.onupgradeneeded = () => r.result.createObjectStore('kv'); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
    const kv = async (k, v) => {
        const db = await idb();
        return new Promise((res) => {
            const t = db.transaction('kv', v === undefined ? 'readonly' : 'readwrite'), st = t.objectStore('kv');
            if (v === undefined) { const r = st.get(k); r.onsuccess = () => res(r.result); r.onerror = () => res(undefined); }
            else { st.put(v, k); t.oncomplete = () => res(); t.onerror = () => res(); }
        });
    };
    function renderSave() {
        const b = $('#st-save');
        if (!('showDirectoryPicker' in window)) { b.textContent = '💾 нет (нужен Chrome/Edge)'; b.className = 'st save bad'; return; }
        if (!SAVE.dir) { b.textContent = '💾 выбрать папку'; b.className = 'st save bad'; return; }
        if (!SAVE.enabled) { b.textContent = '💾 выкл'; b.className = 'st save'; return; }
        if (SAVE.perm !== 'granted') { b.textContent = '💾 нажми — разрешить запись'; b.className = 'st save warn'; return; }
        b.textContent = `💾 ${SAVE.dir.name}${SAVE.count ? ' · ' + SAVE.count : ''}`; b.className = 'st save ok';
    }
    async function initSave() {
        try {
            SAVE.dir = (await kv('dir')) || null;
            const en = await kv('enabled'); SAVE.enabled = en === undefined ? true : !!en;
            if (SAVE.dir) SAVE.perm = await SAVE.dir.queryPermission({ mode: 'readwrite' });
        } catch (e) { /* без папки */ }
        renderSave();
    }
    async function onSaveButton() {
        if (!('showDirectoryPicker' in window)) return;
        try {
            if (SAVE.dir && SAVE.perm !== 'granted') {
                SAVE.perm = await SAVE.dir.requestPermission({ mode: 'readwrite' });
            } else if (!SAVE.dir || confirm(`Автосохранение в «${SAVE.dir.name}».
OK — выбрать другую папку, Отмена — ${SAVE.enabled ? 'выключить' : 'включить'}`)) {
                const h = await window.showDirectoryPicker({ id: 'sud-autosave', mode: 'readwrite', startIn: 'pictures' });
                SAVE.dir = h; SAVE.perm = await h.requestPermission({ mode: 'readwrite' }); SAVE.enabled = true;
                await kv('dir', h); await kv('enabled', true);
            } else { SAVE.enabled = !SAVE.enabled; await kv('enabled', SAVE.enabled); }
        } catch (e) { /* отменил выбор */ }
        renderSave();
    }
    async function saveToLaptop(items) {
        if (!SAVE.dir || !SAVE.enabled || SAVE.perm !== 'granted') return;
        for (const it of items) {
            if (!it.name) continue;
            try {
                try { await SAVE.dir.getFileHandle(it.name); continue; } catch (e) { /* файла нет — пишем */ }
                const blob = await (await fetch(it.url)).blob();
                const fh = await SAVE.dir.getFileHandle(it.name, { create: true });
                const w = await fh.createWritable(); await w.write(blob); await w.close();
                SAVE.count++;
            } catch (e) { if (e.name === 'NotAllowedError') SAVE.perm = 'prompt'; console.warn('[autosave]', it.name, e); }
        }
        renderSave();
    }

    // ---------- генерация ----------
    function updateGenButton() {
        const n = +U.image_number || 1;
        const eta = SRV && SRV.sec_per_image ? ` · ~${Math.round(SRV.sec_per_image * n)} с` : '';
        $('#gen-sub').textContent = `×${n}${eta}`;
    }
    async function generate(extra) {
        if (running) return;
        const payload = Object.assign({
            prompt: $('#prompt').value, negative: $('#negative').value, model: U.model, loras: U.loras,
            sampler: U.sampler, scheduler: U.scheduler, steps: +U.steps, cfg: +U.cfg, sharpness: +U.sharpness,
            aspect: U.aspect, image_number: +U.image_number, output_format: U.output_format, performance: U.performance,
            seed: U.random ? null : U.seed, camera: U.camera,
        }, extra || {});
        $('#btn-gen').disabled = true;
        try {
            const r = await api('generate', payload);
            running = { id: r.id, seed: r.seed, prompt: payload.prompt, action: extra && extra.action && extra.action.type };
            if (!U.random && !(extra && extra.action)) { U.seed = String(r.seed); save(); }
            $('#btn-stop').hidden = false;
            setProgress(0, 'В очереди…');
            poll();
        } catch (e) { alert('Не получилось: ' + e.message); $('#btn-gen').disabled = false; }
    }
    async function poll() {
        if (!running) return;
        try {
            const r = await api('task/' + running.id);
            setProgress(r.percent, r.title);
            if (r.preview) showImage(r.preview, null);
            if (r.done) {
                let items = r.images.map((k, i) => ({ key: k, url: API + 'image/' + k, name: (r.names || [])[i], seed: r.seed, prompt: running.prompt, action: running.action }));
                if (running.action === 'faces') items = items.slice(-1);   // Enhance отдаёт ещё и исходник — он у нас уже есть
                saveToLaptop(items);
                history = items.concat(history).slice(0, 60);
                lsSet(LS_HIST, history);
                running = null;
                $('#btn-stop').hidden = true; $('#btn-gen').disabled = false;
                setProgress(null);
                if (items[0]) select(items[0]);
                renderStrip(); refreshState();
                return;
            }
        } catch (e) { setProgress(null, ''); }
        setTimeout(poll, 400);
    }
    function setProgress(pct, title) {
        const p = $('#progress');
        p.classList.toggle('on', pct !== null);
        if (pct !== null) { $('#progress-bar').style.width = pct + '%'; $('#progress-text').textContent = `${title || ''} ${pct}%`; }
    }
    function showImage(src, item) {
        $('#viewer').classList.add('has');
        $('#viewer-img').src = src;
        $('#dl').href = item ? item.url : src;
        $('#dl').style.display = item ? '' : 'none';
    }
    function select(item) { current = item; showImage(item.url, item); renderStrip(); }
    function applyStrip() {
        $('#strip').hidden = !!U.stripHidden;
        const c = $('#chip-strip');
        c.textContent = (U.stripHidden ? '▸ лента' : '▾ лента') + (history.length ? ` · ${history.length}` : '');
        c.classList.toggle('on', !U.stripHidden);
    }
    function renderStrip() {
        applyStrip();
        $('#strip').innerHTML = (history.length ? '<button class="strip-x" data-strip-hide title="Спрятать ленту (вернуть — чип «▸ лента» у промпта)">▾</button>' : '') + history.slice(0, 30).map((h, i) => `<img src="${h.url}" data-h="${i}" class="${current && current.key === h.key ? 'on' : ''}" title="seed ${h.seed}" loading="lazy">`).join('');
        $('#gallery').innerHTML = history.map((h, i) => `<img src="${h.url}" data-h="${i}" title="seed ${h.seed}\n${esc(h.prompt)}" loading="lazy">`).join('') || '<div class="hint">Пока пусто</div>';
    }

    // ---------- события ----------
    document.addEventListener('click', async (e) => {
        const t = e.target.closest('button, img[data-h], .ch, a');
        if (!t) return;
        if (t.matches('.ch') && t.parentElement.classList.contains('fold')) {
            const id = t.parentElement.dataset.card; U.closed[id] = !U.closed[id]; save(); t.parentElement.classList.toggle('closed'); return;
        }
        if (t.dataset.h !== undefined) { select(history[+t.dataset.h]); openLB(+t.dataset.h); return; }
        if (t.dataset.view) { switchView(t.dataset.view); return; }
        if (t.dataset.peNew) { EDIT[t.dataset.peNew] = false; peOpen(t.dataset.peNew, null); return; }
        if (t.dataset.peMode) {
            const k = t.dataset.peMode; EDIT[k] = !EDIT[k];
            if (!EDIT[k] && PE.kind === k) PE.kind = null;
            renderRight(); return;
        }
        if (t.dataset.peDo) { peDo(t.dataset.peDo); return; }
        if (t.dataset.sp && EDIT.sampling) { peOpen('sampling', t.dataset.sp); return; }
        if (t.dataset.lp && EDIT.loras) { peOpen('loras', t.dataset.lp); return; }
        if (t.dataset.sp) {
            const p = SRV.sampling_presets.find((x) => x.name === t.dataset.sp);
            Object.assign(U, { sampler: p.sampler, scheduler: p.scheduler, steps: p.steps, cfg: p.cfg, sharpness: p.sharpness });
            save(); renderRight(); return;
        }
        if (t.dataset.lp) {
            const p = SRV.lora_presets.find((x) => x.name === t.dataset.lp);
            U.loras = (p.loras || []).filter((l) => SRV.loras.includes(l.name)).slice(0, SRV.lora_slots).map((l) => [l.enabled !== false, l.name, l.weight]);
            save(); renderRight(); return;
        }
        if (t.dataset.ar) { U.aspect = t.dataset.ar; save(); renderRight(); return; }
        if (t.dataset.loraDel !== undefined) { U.loras.splice(+t.dataset.loraDel, 1); save(); renderRight(); return; }
        if (t.dataset.act === 'lora-add') { U.loras.push([true, 'None', 1]); save(); renderRight(); return; }
        if (t.dataset.camAngle !== undefined) { U.camera.angle = U.camera.angle === t.dataset.camAngle ? '' : t.dataset.camAngle; U.camera.enabled = !!(U.camera.angle || U.camera.height || U.camera.shot); save(); renderRight(); return; }
        if (t.dataset.action && current && !running) {
            const a = t.dataset.action, keepSeed = a.startsWith('upscale') || a === 'faces';
            generate({ action: { type: a, key: current.key }, prompt: current.prompt || $('#prompt').value, image_number: 1,
                       seed: keepSeed ? current.seed : null });
            return;
        }
        if (t.dataset.act === 'reuse-seed' && current) { U.random = false; U.seed = String(current.seed); save(); renderRight(); return; }
        if (t.id === 'btn-gen') { generate(); return; }
        if (t.id === 'st-save') { onSaveButton(); return; }
        if (t.id === 'btn-stop' && running) { api('task/' + running.id + '/stop', {}); return; }
        if (t.dataset.stripHide !== undefined) { U.stripHidden = true; save(); applyStrip(); return; }
        if (t.id === 'chip-strip') { U.stripHidden = !U.stripHidden; save(); applyStrip(); return; }
        if (t.id === 'chip-neg') { U.showNeg = !U.showNeg; save(); $('#neg-row').hidden = !U.showNeg; t.classList.toggle('on', U.showNeg); return; }
        if (t.id === 'chip-cam') { U.closed.camera = false; save(); renderRight(); $('[data-card="camera"]').scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
        if (t.id === 'chip-tr') {
            const ta = $('#prompt'); if (!ta.value.trim()) return;
            t.classList.add('busy');
            try { const r = await api('translate', { text: ta.value }); if (r.text) { ta.value = r.text; U.prompt = r.text; save(); } }
            catch (er) { alert('Перевод не удался: ' + er.message); }
            t.classList.remove('busy'); return;
        }
        if (t.id === 'btn-theme') {
            const now = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
            document.documentElement.dataset.theme = now; try { localStorage.setItem('sud-theme', now); } catch (er) { /* */ }
            t.innerHTML = svg(now === 'light' ? 'moon' : 'sun');
        }
    });
    document.addEventListener('input', (e) => {
        const t = e.target;
        if (t.id === 'prompt') { U.prompt = t.value; save(); return; }
        if (t.id === 'negative') { U.negative = t.value; save(); return; }
        if (t.dataset.pe) { PE[t.dataset.pe + 'Val'] = t.value; if (PE.err) { PE.err = ''; const er = t.parentElement.querySelector('.pe-err'); if (er) er.remove(); } return; }
        if (t.dataset.u && t.type === 'range') { U[t.dataset.u] = +t.value; t.nextElementSibling.textContent = t.value; save(); if (t.dataset.u === 'image_number') updateGenButton(); return; }
        if (t.dataset.loraW !== undefined) { U.loras[+t.dataset.loraW][2] = +t.value; t.nextElementSibling.textContent = (+t.value).toFixed(1); save(); return; }
        if (t.dataset.cam === 'weight') { U.camera.weight = +t.value; t.nextElementSibling.textContent = (+t.value).toFixed(1); save(); return; }
        if (t.dataset.u === 'seed') { U.seed = t.value; save(); }
    });
    document.addEventListener('change', (e) => {
        const t = e.target;
        if (t.dataset.u && (t.tagName === 'SELECT')) { U[t.dataset.u] = t.value; save(); renderRight(); return; }
        if (t.dataset.u === 'random') { U.random = t.checked; save(); renderRight(); return; }
        if (t.dataset.loraOn !== undefined) { U.loras[+t.dataset.loraOn][0] = t.checked; save(); renderRight(); return; }
        if (t.dataset.loraName !== undefined) { U.loras[+t.dataset.loraName][1] = t.value; save(); renderRight(); return; }
        if (t.dataset.cam && t.tagName === 'SELECT') { U.camera[t.dataset.cam] = t.value; U.camera.enabled = !!(U.camera.angle || U.camera.height || U.camera.shot); save(); renderRight(); return; }
        if (t.dataset.cam === 'enabled') { U.camera.enabled = t.checked; save(); renderRight(); }
        if (t.matches('input[type=range]')) renderRight();   // обновить подписи карточек
    });
    // колёсико на ползунках (как в классическом: LoRA и CFG по 0.1, резкость по 1)
    // крутит, только если курсор задержался на ползунке (~250 мс) — иначе это прокрутка панели
    let hoverEl = null, hoverSince = 0, lastWheel = 0;
    document.addEventListener('pointerover', (e) => {
        const r = e.target.closest && e.target.closest('input[type=range]');
        if (r !== hoverEl) { hoverEl = r; hoverSince = performance.now(); }
    });
    document.addEventListener('wheel', (e) => {
        const r = e.target.closest && e.target.closest('input[type=range]');
        if (!r) return;
        const now = performance.now();
        if (r !== hoverEl || (now - hoverSince < 250 && now - lastWheel > 400)) return;
        lastWheel = now;
        e.preventDefault();
        const step = parseFloat(r.step) || 1, dir = e.deltaY < 0 ? 1 : -1;
        const v = Math.min(+r.max, Math.max(+r.min, Math.round((+r.value + dir * step) / step) * step));
        r.value = String(+v.toFixed(3));
        r.dispatchEvent(new Event('input', { bubbles: true }));
    }, { passive: false });
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); generate(); }
    });
    // ---------- 🧬 эмбеддинги (данные — /sud/api/embeddings = sud/ui_embeddings.py) ----------
    const EM = { data: null, open: false, filter: 'all', q: '', folder: U.emFolder || 'all', caret: null, loading: false };
    const reEsc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const tokRe = (n) => new RegExp(`\\(?embedding:${reEsc(n)}(?![\\w.-])(?::[\\d.]+)?\\)?`, 'i');
    const emIn = (it) => tokRe(it.name).test($(it.neg ? '#negative' : '#prompt').value);
    function emToggle(it, atCaret) {
        const ta = $(it.neg ? '#negative' : '#prompt');
        if (it.neg && !U.showNeg) { U.showNeg = true; $('#neg-row').hidden = false; $('#chip-neg').classList.add('on'); }
        let v = ta.value;
        if (tokRe(it.name).test(v)) {
            v = v.replace(new RegExp(`\\s*\\(?embedding:${reEsc(it.name)}(?![\\w.-])(?::[\\d.]+)?\\)?\\s*,?`, 'i'), ' ')
                .replace(/\s{2,}/g, ' ').replace(/^\s*,\s*/, '').replace(/,\s*,/g, ',').trim().replace(/,$/, '').trim();
        } else {
            const tok = `embedding:${it.name}`;
            if (atCaret && !it.neg && EM.caret !== null && EM.caret <= v.length) {
                const a = v.slice(0, EM.caret), b = v.slice(EM.caret);
                const pre = a && !/[\s,(]$/.test(a) ? ', ' : (a && !/\s$/.test(a) ? ' ' : ''), post = b && !/^[\s,)]/.test(b) ? ', ' : '';
                v = a + pre + tok + post + b; EM.caret = (a + pre + tok).length;
            } else v = v.trim() ? `${tok}, ${v.replace(/^\s+/, '')}` : tok;
            api('embeddings', { op: 'used', name: it.name }).then((d) => { EM.data = d; }).catch(() => {});
        }
        ta.value = v; U[it.neg ? 'negative' : 'prompt'] = v; save();
        renderEm();
    }
    const emTree = () => {
        const s = new Set();
        EM.data.items.forEach((it) => { const p = (it.folder || '').split('/').filter(Boolean); p.forEach((_, i) => s.add(p.slice(0, i + 1).join('/'))); });
        return [...s].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true }));
    };
    const under = (it, f) => it.folder === f || (it.folder || '').startsWith(f + '/');
    function renderEm() {
        const box = $('#em');
        if (!EM.open) { box.hidden = true; return; }
        box.hidden = false;
        if (!EM.data) { box.innerHTML = `<div class="hint" style="padding:16px">${EM.loading ? 'Загружаю эмбеддинги… (первый раз — превью с Drive, до минуты)' : 'Не получилось загрузить список'}</div>`; return; }
        const keepSearch = document.activeElement && document.activeElement.matches('.em-search');
        const D = EM.data, ql = EM.q.trim().toLowerCase(), tree = emTree();
        if (!['all', 'rec', 'fav', '__root'].includes(EM.folder) && !tree.includes(EM.folder)) EM.folder = 'all';
        const byName = Object.fromEntries(D.items.map((i) => [i.name, i]));
        let pool = D.items, title = 'Все';
        if (!ql) {
            if (EM.folder === 'rec') { pool = D.recent.map((n) => byName[n]).filter(Boolean); title = 'Недавние'; }
            else if (EM.folder === 'fav') { pool = D.items.filter((i) => i.fav); title = '★ Избранное'; }
            else if (EM.folder === '__root') { pool = D.items.filter((i) => !i.folder); title = 'Без папки'; }
            else if (EM.folder !== 'all') { pool = D.items.filter((i) => under(i, EM.folder)); title = EM.folder; }
        }
        const list = pool.filter((it) => (EM.filter === 'all' || (EM.filter === 'pos' && !it.neg) || (EM.filter === 'neg' && it.neg)) && (!ql || it.name.toLowerCase().includes(ql)));
        const row = (k, t, n, d = 0) => `<button class="em-f${EM.folder === k ? ' on' : ''}" data-em-folder="${esc(k)}" style="padding-left:${8 + d * 12}px"><span>${esc(t)}</span><i>${n}</i></button>`;
        const side = row('all', 'Все', D.items.length) + row('rec', 'Недавние', D.recent.filter((n) => byName[n]).length) + row('fav', '★ Избранное', D.items.filter((i) => i.fav).length)
            + tree.map((f) => row(f, '📁 ' + f.split('/').pop(), D.items.filter((i) => under(i, f)).length, f.split('/').length - 1)).join('')
            + (D.items.some((i) => !i.folder) ? row('__root', 'Без папки', D.items.filter((i) => !i.folder).length) : '');
        const tiles = list.map((it) => {
            const used = emIn(it);
            return `<div class="em-t${used ? ' used' : ''}${it.sdxl === false ? ' dim' : ''}" data-em="${esc(it.name)}" title="${esc(it.name)}${it.folder ? '\n📁 ' + esc(it.folder) : ''}${used ? '\nуже в промпте — клик уберёт' : ''}">
                <div class="em-img">${it.thumb ? `<img src="${it.thumb}" alt="" loading="lazy">` : '🧬'}</div><div class="em-n">${esc(it.name)}</div>
                ${it.neg ? '<span class="em-b neg">neg</span>' : ''}${it.sdxl === false ? '<span class="em-b sd">SD1.5</span>' : ''}${used ? '<span class="em-b in">в промпте</span>' : ''}
                <button class="em-star${it.fav ? ' on' : ''}" data-em-fav="${esc(it.name)}" title="Избранное">★</button>
                <button class="em-flip" data-em-neg="${esc(it.name)}" title="${it.neg ? 'Сделать позитивным' : 'Сделать негативным'}">±</button></div>`;
        }).join('');
        const chips = [['all', 'Все'], ['pos', 'Позитивные'], ['neg', 'Негативные']].map(([k, t]) => `<button class="pill${EM.filter === k ? ' on' : ''}" data-em-filter="${k}">${t}</button>`).join('');
        box.innerHTML = `<div class="em-top"><input type="text" class="em-search" placeholder="Поиск по всем папкам" value="${esc(EM.q)}">${chips}<button class="x" data-em-close title="Закрыть (Esc)">✕</button></div>
            <div class="em-body"><div class="em-side">${side}</div><div class="em-main"><div class="em-sec">${ql ? 'Найдено' : esc(title)} · ${list.length}</div>
            <div class="em-grid">${tiles || '<div class="hint">Ничего не найдено</div>'}</div></div></div>
            <div class="hint em-hint">Клик — в начало промпта (негативные — в негатив) · Shift+клик — туда, где курсор · повторный клик убирает · ★ избранное · ± позитивный/негативный</div>`;
        if (keepSearch) { const s = box.querySelector('.em-search'); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    }
    async function emOpen(v) {
        EM.open = v === undefined ? !EM.open : v;
        $('#chip-em').classList.toggle('on', EM.open);
        renderEm();
        if (EM.open && !EM.data && !EM.loading) {
            EM.loading = true; renderEm();
            try { EM.data = await api('embeddings'); } catch (e) { EM.data = null; }
            EM.loading = false; renderEm();
        }
    }
    document.addEventListener('click', (e) => {
        if (!e.target.closest) return;
        if (e.target.closest('#chip-em')) { emOpen(); return; }
        const box = e.target.closest('#em');
        if (!box) { if (EM.open && e.isTrusted && !e.target.closest('#prompt, #negative')) emOpen(false); return; }
        const t = e.target.closest('[data-em-folder], [data-em-filter], [data-em-fav], [data-em-neg], [data-em-close], [data-em]');
        if (!t) return;
        if (t.dataset.emClose !== undefined) { emOpen(false); return; }
        if (t.dataset.emFolder !== undefined) { EM.folder = t.dataset.emFolder; U.emFolder = EM.folder; save(); renderEm(); return; }
        if (t.dataset.emFilter) { EM.filter = t.dataset.emFilter; renderEm(); return; }
        const find = (n) => EM.data.items.find((i) => i.name === n);
        if (t.dataset.emFav) { const it = find(t.dataset.emFav); it.fav = !it.fav; renderEm(); api('embeddings', { op: 'fav', name: it.name, on: it.fav }).then((d) => { EM.data = d; }).catch(() => {}); return; }
        if (t.dataset.emNeg) { const it = find(t.dataset.emNeg); it.neg = !it.neg; renderEm(); api('embeddings', { op: 'neg', name: it.name, on: it.neg }).then((d) => { EM.data = d; }).catch(() => {}); return; }
        if (t.dataset.em) emToggle(find(t.dataset.em), e.shiftKey);
    });
    document.addEventListener('input', (e) => { if (e.target.matches && e.target.matches('.em-search')) { EM.q = e.target.value; renderEm(); } });
    ['keyup', 'click', 'select'].forEach((ev) => document.addEventListener(ev, (e) => { if (e.target.id === 'prompt') EM.caret = e.target.selectionStart; }));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && EM.open && $('#lb').hidden) emOpen(false); });
    document.addEventListener('keydown', (e) => {
        if (!e.target.dataset || !e.target.dataset.pe) return;
        if (e.key === 'Enter') { e.preventDefault(); peDo(PE.name == null ? 'add' : 'edit'); }
        if (e.key === 'Escape') { e.preventDefault(); peClose(); }
    });

    // ---------- пресеты: перетаскивание пилюль (порядок сохраняется на Drive, виден и в классическом) ----------
    let suppressClick = false;
    document.addEventListener('pointerdown', (e) => {
        const pill = e.target.closest && e.target.closest('.pills[data-kind] .pill:not(.tool)');
        if (!pill || e.button !== 0) return;
        const box = pill.parentElement, kind = box.dataset.kind;
        const pills = [...box.querySelectorAll('.pill:not(.tool)')], from = pills.indexOf(pill);
        const x0 = e.clientX, y0 = e.clientY;
        let dragging = false, to = from, after = false;
        const move = (ev) => {
            if (!dragging) {
                if (Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) < 6) return;
                dragging = true; pill.classList.add('dragging'); document.body.classList.add('resizing');
            }
            let best = Infinity;
            pills.forEach((p, i) => {
                const r = p.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
                const d = Math.hypot(ev.clientX - cx, (ev.clientY - cy) * 2);
                if (d < best) { best = d; to = i; after = ev.clientX > cx; }
            });
            pills.forEach((p, i) => { p.classList.toggle('drop-l', i === to && !after); p.classList.toggle('drop-r', i === to && after); });
        };
        const up = async () => {
            document.removeEventListener('pointermove', move);
            document.body.classList.remove('resizing');
            pills.forEach((p) => p.classList.remove('dragging', 'drop-l', 'drop-r'));
            if (!dragging) return;
            suppressClick = true;
            const key = kind === 'sampling' ? 'sampling_presets' : 'lora_presets';
            const list = SRV[key].slice();
            let dst = to + (after ? 1 : 0);
            const [x] = list.splice(from, 1);
            if (dst > from) dst--;
            list.splice(dst, 0, x);
            if (kind === 'loras' && !rawGet('sud-pr-loras-start') && SRV[key][0]) {
                try { localStorage.setItem('sud-pr-loras-start', SRV[key][0].name); } catch (er) { /* */ }   // ★ не «переезжает» за первым
            }
            SRV[key] = list; renderRight();
            try { const r = await api('presets/order', { kind, names: list.map((p) => p.name) }); SRV[key] = r.presets; renderRight(); }
            catch (er) { alert('Порядок не сохранился: ' + er.message); refreshState().then(renderRight); }
        };
        document.addEventListener('pointermove', move);
        document.addEventListener('pointerup', up, { once: true });
    });
    document.addEventListener('click', (e) => { if (suppressClick) { suppressClick = false; e.stopImmediatePropagation(); e.preventDefault(); } }, true);

    // ---------- LoRA: перетаскивание строк за ⋮⋮ ----------
    document.addEventListener('pointerdown', (e) => {
        const grip = e.target.closest && e.target.closest('.lora .grip');
        if (!grip) return;
        e.preventDefault();
        const row = grip.closest('.lora'), from = +row.dataset.row, list = row.parentElement;
        let to = from;
        row.classList.add('dragging'); document.body.classList.add('resizing');
        const rows = [...list.querySelectorAll('.lora')];
        const move = (ev) => {
            to = rows.length - 1;
            for (let i = 0; i < rows.length; i++) { const r = rows[i].getBoundingClientRect(); if (ev.clientY < r.top + r.height / 2) { to = i; break; } }
            rows.forEach((r, i) => { r.classList.toggle('drop-before', i === to && to < from); r.classList.toggle('drop-after', i === to && to > from); });
        };
        const up = () => {
            document.removeEventListener('pointermove', move); document.body.classList.remove('resizing');
            if (to !== from) { const [x] = U.loras.splice(from, 1); U.loras.splice(to, 0, x); save(); }
            renderRight();
        };
        document.addEventListener('pointermove', move);
        document.addEventListener('pointerup', up, { once: true });
    });

    // ---------- ширина правой панели (перетаскивание, запоминается) ----------
    const RW_DEF = 300, RW_MIN = 240, RW_MAX = 640;
    const setRW = (w) => { U.rightW = Math.round(Math.min(RW_MAX, Math.max(RW_MIN, w))); document.querySelector('.main').style.setProperty('--right-w', U.rightW + 'px'); };
    $('#resizer').addEventListener('pointerdown', (e) => {
        e.preventDefault();
        const rz = e.currentTarget, x0 = e.clientX, w0 = U.rightW || RW_DEF;
        rz.setPointerCapture(e.pointerId); rz.classList.add('on'); document.body.classList.add('resizing');
        const move = (ev) => setRW(w0 + (x0 - ev.clientX));
        const up = () => { rz.removeEventListener('pointermove', move); rz.classList.remove('on'); document.body.classList.remove('resizing'); save(); };
        rz.addEventListener('pointermove', move);
        rz.addEventListener('pointerup', up, { once: true });
    });
    $('#resizer').addEventListener('dblclick', () => { setRW(RW_DEF); save(); });

    // ---------- просмотр на весь экран: колёсико — зум к курсору, тащить — двигать, ← → — листать ----------
    const LB = { i: -1, src: '', scale: 1, x: 0, y: 0, w: 1, h: 1 };
    const lb = $('#lb'), lbImg = $('#lb-img');
    function lbApply() {
        lbImg.style.transform = `translate(${LB.x}px, ${LB.y}px) scale(${LB.scale})`;
        $('#lb-zoom').textContent = Math.round(LB.scale * 100) + '%';
        lb.classList.toggle('pixel', LB.scale >= 3);
    }
    function lbFit() {
        const vw = innerWidth, vh = innerHeight - 50;
        LB.scale = Math.min(vw / LB.w, vh / LB.h);
        LB.x = (vw - LB.w * LB.scale) / 2; LB.y = 50 + (vh - LB.h * LB.scale) / 2;
        lbApply();
    }
    function lbZoomAt(cx, cy, scale) {
        const fit = Math.min(innerWidth / LB.w, (innerHeight - 50) / LB.h);
        scale = Math.min(16, Math.max(fit * 0.5, scale));
        LB.x = cx - (cx - LB.x) * (scale / LB.scale); LB.y = cy - (cy - LB.y) * (scale / LB.scale);
        LB.scale = scale; lbApply();
    }
    function lbShow(src, i) {
        LB.i = i; LB.src = src;
        const it = i >= 0 ? history[i] : null;
        const ACT = { upscale_tiled: '2× Tiled', upscale: '2×', upscale_15: '1.5×', vary_subtle: 'вариация', vary_strong: 'сильная вариация', faces: 'лица' };
        $('#lb-info').textContent = it ? `${i + 1} / ${history.length} · seed ${it.seed}${it.action ? ' · ' + ACT[it.action] : ''} · ${it.prompt || ''}` : 'превью';
        $('#lb-dl').href = it ? it.url : src; $('#lb-dl').style.display = it ? '' : 'none';
        lb.querySelectorAll('.lb-nav').forEach((b) => { b.hidden = i < 0 || history.length < 2; });
        lbImg.onload = () => { LB.w = lbImg.naturalWidth || 1; LB.h = lbImg.naturalHeight || 1; lbFit(); };
        lbImg.src = src;
        if (lbImg.complete && lbImg.naturalWidth) lbImg.onload();
    }
    function openLB(i) { lb.hidden = false; lbShow(i >= 0 ? history[i].url : $('#viewer-img').src, i); }
    function closeLB() { lb.hidden = true; lbImg.removeAttribute('src'); }
    function lbStep(d) { if (LB.i < 0 || !history.length) return; const i = (LB.i + d + history.length) % history.length; select(history[i]); lbShow(history[i].url, i); }
    $('#viewer-img').addEventListener('click', () => {
        const i = current ? history.findIndex((h) => h.key === current.key) : -1;
        openLB(running ? -1 : i);
    });
    lb.addEventListener('wheel', (e) => { e.preventDefault(); lbZoomAt(e.clientX, e.clientY, LB.scale * (e.deltaY < 0 ? 1.18 : 1 / 1.18)); }, { passive: false });
    lb.addEventListener('pointerdown', (e) => {
        if (e.target.closest('.lb-bar, .lb-nav')) return;
        e.preventDefault();
        const x0 = e.clientX, y0 = e.clientY, px = LB.x, py = LB.y; let moved = false;
        lb.setPointerCapture(e.pointerId); lb.classList.add('drag');
        const move = (ev) => { const dx = ev.clientX - x0, dy = ev.clientY - y0; if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; LB.x = px + dx; LB.y = py + dy; lbApply(); };
        const up = (ev) => {
            lb.removeEventListener('pointermove', move); lb.classList.remove('drag');
            if (!moved && ev.target === lb) closeLB();   // клик по пустому фону — закрыть
        };
        lb.addEventListener('pointermove', move);
        lb.addEventListener('pointerup', up, { once: true });
    });
    lb.addEventListener('dblclick', (e) => {
        if (e.target.closest('.lb-bar, .lb-nav')) return;
        const fit = Math.min(innerWidth / LB.w, (innerHeight - 50) / LB.h);
        if (Math.abs(LB.scale - fit) < 0.01) lbZoomAt(e.clientX, e.clientY, 1); else lbFit();
    });
    lb.addEventListener('click', (e) => {
        const a = e.target.closest('[data-lb]') && e.target.closest('[data-lb]').dataset.lb;
        if (a === 'close') closeLB();
        if (a === 'fit') lbFit();
        if (a === 'one') lbZoomAt(innerWidth / 2, innerHeight / 2, 1);
        if (a === 'prev') lbStep(-1);
        if (a === 'next') lbStep(1);
    });
    addEventListener('resize', () => { if (!lb.hidden) lbFit(); });
    document.addEventListener('keydown', (e) => {
        if (lb.hidden) return;
        if (e.key === 'Escape') closeLB();
        else if (e.key === 'ArrowLeft') lbStep(-1);
        else if (e.key === 'ArrowRight') lbStep(1);
        else if (e.key === '0' || e.key === 'f') lbFit();
        else if (e.key === '1') lbZoomAt(innerWidth / 2, innerHeight / 2, 1);
    });

    $('#viewer-img').addEventListener('error', () => { if (current) { history = history.filter((h) => h.key !== current.key); lsSet(LS_HIST, history); renderStrip(); } });

    function switchView(v) {
        document.querySelectorAll('.nv[data-view]').forEach((b) => b.classList.toggle('on', b.dataset.view === v));
        $('#v-create').hidden = v !== 'create'; $('#v-gallery').hidden = v !== 'gallery';
    }

    // ---------- запуск ----------
    async function refreshState() {
        try {
            SRV = await api('state');
            const st = $('#st-conn'); st.className = 'st ok'; st.lastElementChild.textContent = 'движок подключён';
            $('#st-queue').textContent = SRV.busy || SRV.queue ? `очередь: ${SRV.queue}` : '';
            return true;
        } catch (e) {
            const st = $('#st-conn'); st.className = 'st bad'; st.lastElementChild.textContent = 'движок недоступен — Colab запущен?';
            return false;
        }
    }
    async function boot() {
        document.querySelectorAll('.nv').forEach((b) => { b.innerHTML = svg(b.dataset.icon || b.dataset.view); });
        if (U.rightW) setRW(U.rightW);
        $('#btn-theme').innerHTML = svg(document.documentElement.dataset.theme === 'light' ? 'moon' : 'sun');
        $('#prompt').value = U.prompt; $('#negative').value = U.negative;
        $('#neg-row').hidden = !U.showNeg; $('#chip-neg').classList.toggle('on', U.showNeg);
        renderStrip();
        if (history[0]) select(history[0]);
        initSave();
        while (!(await refreshState())) await new Promise((r) => setTimeout(r, 4000));
        const D = SRV.defaults;
        // то, чего нет на сервере (модель удалили и т.п.), — на значения по умолчанию
        if (!SRV.models.includes(U.model)) U.model = D.model;
        if (!U.sampler || !SRV.samplers.includes(U.sampler)) U.sampler = D.sampler;
        if (!U.scheduler || !SRV.schedulers.includes(U.scheduler)) U.scheduler = D.scheduler;
        if (!SRV.aspects.includes(U.aspect)) U.aspect = D.aspect;
        if (!SRV.performances.includes(U.performance)) U.performance = D.performance;
        if (!SRV.output_formats.includes(U.output_format)) U.output_format = D.output_format;
        if (!U.loras) {   // первый запуск — пресет ★ (как в классическом) или LoRA по умолчанию
            const star = rawGet('sud-pr-loras-start'), p = SRV.lora_presets.find((x) => x.name === star) || SRV.lora_presets[0];
            U.loras = p ? p.loras.map((l) => [l.enabled !== false, l.name, l.weight]) : D.loras;
            if (U.steps === -1 && D.steps) Object.assign(U, { steps: D.steps, cfg: D.cfg, sharpness: D.sharpness });
        }
        save(); renderRight();
        setInterval(refreshState, 15000);
    }
    boot();
})();
