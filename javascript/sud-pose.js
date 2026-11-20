// Fooocus-sud: 🦴 редактор позы (OpenPose, этап 2). Полноэкранный, открывается кнопкой «Поза» у промпта.
// Поза с фото (DWPose на сервере) или шаблон → тянешь суставы → «В Image Prompt» (скелет в слот с типом OpenPose).
// Python: sud/ui_pose.py (скрытые .sud-pose-op / -state / -op-btn). Координаты — доли 0..1 от холста (= разрешения).
(function () {
    const LS = 'sud-pose-state';
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I_POSE = SVG('<path d="M11 4a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/><path d="M7 21l3 -4"/><path d="M16 21l-2 -4l-3 -3l1 -6"/><path d="M6 12l2 -3l4 -1l3 3l3 1"/>');
    const I_UNDO = SVG('<path d="M9 14l-4 -4l4 -4"/><path d="M5 10h11a4 4 0 1 1 0 8h-1"/>');
    const I_REDO = SVG('<path d="M15 14l4 -4l-4 -4"/><path d="M19 10h-11a4 4 0 1 0 0 8h1"/>');
    const I_USER = SVG('<path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0"/><path d="M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/>');
    const I_X = SVG('<path d="M18 6l-12 12"/><path d="M6 6l12 12"/>');
    const I_EYE = SVG('<path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/><path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6"/>');
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const clone = (x) => JSON.parse(JSON.stringify(x));

    // OpenPose-18: 0 нос, 1 шея, 2-4 правая рука, 5-7 левая, 8-10 правая нога, 11-13 левая, 14-17 глаза/уши
    const LIMBS = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]];
    const COLORS = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]];
    const PARENT = { 0: 1, 2: 1, 5: 1, 8: 1, 11: 1, 3: 2, 4: 3, 6: 5, 7: 6, 9: 8, 10: 9, 12: 11, 13: 12, 14: 0, 15: 0, 16: 0, 17: 0 };
    const CHILDREN = {};
    Object.entries(PARENT).forEach(([c, p]) => { (CHILDREN[p] = CHILDREN[p] || []).push(+c); });
    const HAND_EDGES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [0, 9], [9, 10], [10, 11], [11, 12], [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]];
    const FLIP = [[2, 5], [3, 6], [4, 7], [8, 11], [9, 12], [10, 13], [14, 15], [16, 17]];
    const NAMES = ['нос', 'шея', 'правое плечо', 'правый локоть', 'правая кисть', 'левое плечо', 'левый локоть', 'левая кисть', 'правое бедро', 'правое колено', 'правая стопа', 'левое бедро', 'левое колено', 'левая стопа', 'правый глаз', 'левый глаз', 'правое ухо', 'левое ухо'];

    // шаблоны: доли от холста (человек ~80% высоты по центру)
    const TPL = {
        'Стоит': [[210, 92], [210, 130], [180, 132], [172, 190], [168, 245], [240, 132], [248, 190], [252, 245], [192, 240], [190, 320], [188, 395], [228, 240], [230, 320], [232, 395], [203, 86], [217, 86], [196, 92], [224, 92]],
        'Руки вверх': [[210, 112], [210, 150], [180, 152], [168, 100], [160, 48], [240, 152], [252, 100], [260, 48], [192, 260], [190, 335], [188, 405], [228, 260], [230, 335], [232, 405], [203, 106], [217, 106], [196, 112], [224, 112]],
        'Шаг': [[205, 92], [208, 130], [180, 134], [160, 185], [150, 235], [236, 130], [262, 180], [285, 220], [195, 240], [160, 310], [140, 385], [225, 240], [245, 318], [262, 392], [198, 86], [212, 86], [191, 92], [219, 92]],
        'Сидит': [[210, 120], [210, 158], [180, 160], [168, 215], [190, 255], [240, 160], [252, 215], [232, 255], [192, 265], [130, 275], [120, 350], [228, 265], [290, 275], [300, 350], [203, 114], [217, 114], [196, 120], [224, 120]],
    };
    const tplPerson = (name, dx = 0) => ({ body: TPL[name].map(([x, y]) => [x / 420 + dx, y / 420]), left_hand: null, right_hand: null, face: null, hidden: false });

    // ---------- состояние ----------
    let S = { people: [], sel: 0, lock: true, whole: true, hands: true, face: true, opacity: 0.4 };
    try { const v = JSON.parse(localStorage.getItem(LS) || 'null'); if (v && Array.isArray(v.people)) S = Object.assign(S, v); } catch (e) { /* ignore */ }
    let photo = null;            // {url, w, h}
    let open = false, busy = '', msg = '', drag = null, undo = [], redo = [];
    const save = () => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { /* ignore */ } };
    const snapshot = () => { undo.push(clone(S.people)); if (undo.length > 60) undo.shift(); redo = []; };

    function aspect() {
        const v = document.querySelector('.aspect_ratios input:checked')?.value || '';
        const m = v.match(/(\d+)\s*[×x*]\s*(\d+)/);
        return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : [1024, 1024];
    }

    // ---------- связь с Python ----------
    let waiting = null, lastRaw = '';
    function send(cmd) {
        const ta = document.querySelector('.sud-pose-op textarea, .sud-pose-op input');
        const btn = document.querySelector('button.sud-pose-op-btn, .sud-pose-op-btn button');
        if (!ta || !btn) return Promise.reject(new Error('мост не найден'));
        const nonce = Date.now() + Math.random();
        ta.value = JSON.stringify(Object.assign({}, cmd, { nonce }));
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => btn.click(), 40);
        return new Promise((resolve, reject) => { waiting = { nonce, resolve, reject, t: Date.now() }; });
    }
    setInterval(() => {
        const out = document.querySelector('.sud-pose-state textarea, .sud-pose-state input');
        if (!out || !out.value || out.value === lastRaw || !waiting) return;
        lastRaw = out.value;
        try {
            const r = JSON.parse(out.value);
            if (r.nonce === waiting.nonce) { const w = waiting; waiting = null; w.resolve(r); }
        } catch (e) { /* ignore */ }
    }, 200);

    const fileToDataURL = (blob) => new Promise((res) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob); });

    async function detectFrom(blob) {
        const url = URL.createObjectURL(blob);
        const img = new Image();
        await new Promise((r) => { img.onload = r; img.src = url; });
        photo = { url, w: img.naturalWidth, h: img.naturalHeight };
        busy = 'Ищу позу на фото… (первый раз ~минута: качаю DWPose)'; render();
        try {
            const r = await send({ op: 'detect', image: await fileToDataURL(blob) });
            if (r.error) { msg = r.error; }
            if (r.poses && r.poses.length) {
                snapshot();
                const [W, H] = aspect();
                // фото ложится на холст «cover» по центру — как Fooocus подгоняет картинку Image Prompt
                const k = Math.max(W / r.w, H / r.h), ox = (W - r.w * k) / 2, oy = (H - r.h * k) / 2;
                const map = (pt) => (pt ? [(pt[0] * r.w * k + ox) / W, (pt[1] * r.h * k + oy) / H] : null);
                S.people = r.poses.map((p) => ({
                    body: (p.body || []).map(map), left_hand: p.left_hand && p.left_hand.map(map),
                    right_hand: p.right_hand && p.right_hand.map(map), face: p.face && p.face.map(map), hidden: false,
                }));
                S.sel = 0; msg = `Найдено людей: ${S.people.length}`;
                save();
            }
        } catch (e) { msg = 'Не получилось: ' + e.message; }
        busy = ''; render();
    }
    async function poseFromGallery() {
        const img = [...document.querySelectorAll('.main_view img')].filter((i) => i.naturalWidth >= 256 && i.offsetParent !== null).pop()
            || [...document.querySelectorAll('.main_view img')].filter((i) => i.naturalWidth >= 256).pop();
        if (!img) { msg = 'В галерее нет картинки — сгенерируй или загрузи фото'; render(); return; }
        detectFrom(await (await fetch(img.src)).blob());
    }

    // ---------- «В Image Prompt» ----------
    function ipSlots() {
        const tab = [...document.querySelectorAll('.tabitem')].find((t) => t.querySelector('input[type=radio][value="OpenPose"]'));
        if (!tab) return [];
        return [...tab.querySelectorAll('input[type=file]')].map((fi) => {
            let col = fi;
            for (let i = 0; i < 12 && col && !col.querySelector('input[type=radio][value="OpenPose"]'); i++) col = col.parentElement;
            return { fi, col };
        }).filter((s) => s.col);
    }
    async function toImagePrompt() {
        const people = S.people.filter((p) => !p.hidden);
        if (!people.length) { msg = 'Нет ни одного человека'; render(); return; }
        const [W, H] = aspect();
        busy = 'Рисую скелет…'; render();
        try {
            const r = await send({ op: 'render', poses: people, w: W, h: H, hands: S.hands, face: S.face });
            if (r.error) throw new Error(r.error);
            const blob = await (await fetch(r.png)).blob();
            const ii = [...document.querySelectorAll('label')].find((l) => l.textContent.trim() === 'Input Image')?.querySelector('input');
            if (ii && !ii.checked) { ii.click(); await new Promise((x) => setTimeout(x, 600)); }
            [...document.querySelectorAll('.tab-nav button')].find((b) => b.textContent.trim() === 'Image Prompt')?.click();
            await new Promise((x) => setTimeout(x, 500));
            const slots = ipSlots();
            const slot = slots.find((s) => s.col.querySelector('input[value="OpenPose"]:checked'))
                || slots.find((s) => !s.col.querySelector('img')) || slots[0];
            if (!slot) throw new Error('не нашёл слоты Image Prompt');
            const clear = slot.col.querySelector('button[aria-label="Clear"], button[title="Clear"]');
            if (slot.col.querySelector('img') && clear) { clear.click(); await new Promise((x) => setTimeout(x, 500)); }
            const fi = slot.col.querySelector('input[type=file]');
            const dt = new DataTransfer();
            dt.items.add(new File([blob], 'pose.png', { type: 'image/png' }));
            fi.files = dt.files;
            fi.dispatchEvent(new Event('change', { bubbles: true }));
            await new Promise((x) => setTimeout(x, 400));
            slot.col.querySelector('input[type=radio][value="OpenPose"]')?.click();
            busy = ''; setOpen(false);
            flashToast('Скелет в Image Prompt (тип OpenPose) — жми Generate');
            return;
        } catch (e) { msg = 'Не получилось: ' + e.message; }
        busy = ''; render();
    }
    function flashToast(text) {
        const t = document.createElement('div');
        t.className = 'sud-pose-toast'; t.textContent = text;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 3500);
    }

    // ---------- правка ----------
    function subtree(j) {
        const out = [];
        (function walk(k) { (CHILDREN[k] || []).forEach((c) => { out.push(c); walk(c); }); })(j);
        return out;
    }
    function attached(p, j) {   // кисти и лицо едут за запястьем / носом
        const arr = [];
        const add = (part) => part && part.forEach((pt) => pt && arr.push(pt));
        const sub = [j, ...subtree(j)];
        if (sub.includes(4)) add(p.right_hand);
        if (sub.includes(7)) add(p.left_hand);
        if (sub.includes(0)) add(p.face);
        return arr;
    }
    function allPoints(p) {
        const arr = p.body.filter(Boolean);
        [p.left_hand, p.right_hand, p.face].forEach((part) => part && part.forEach((pt) => pt && arr.push(pt)));
        return arr;
    }
    function bbox(p) {
        const pts = p.body.filter(Boolean);
        if (!pts.length) return null;
        const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
        return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    }

    // ---------- отрисовка ----------
    function overlay() {
        let o = document.querySelector('.sud-pose');
        if (!o) { o = document.createElement('div'); o.className = 'sud-pose'; document.body.appendChild(o); }
        return o;
    }
    function svgHtml(W, H) {
        const sx = (x) => (x * W).toFixed(1), sy = (y) => (y * H).toFixed(1);
        const stroke = Math.max(4, Math.round(Math.max(W, H) / 110));
        let s = '';
        S.people.forEach((p, pi) => {
            if (p.hidden) return;
            const dim = pi !== S.sel ? ' opacity="0.55"' : '';
            s += `<g${dim}>`;
            if (pi === S.sel) {
                const b = bbox(p);
                if (b) s += `<rect x="${sx(b[0]) - 14}" y="${sy(b[1]) - 14}" width="${(b[2] - b[0]) * W + 28}" height="${(b[3] - b[1]) * H + 28}" rx="10" fill="none" stroke="#fabd2f" stroke-dasharray="8 6" stroke-width="2" opacity="0.7"/>`;
            }
            LIMBS.forEach(([a, b], k) => {
                const q1 = p.body[a - 1], q2 = p.body[b - 1];
                if (!q1 || !q2) return;
                s += `<line x1="${sx(q1[0])}" y1="${sy(q1[1])}" x2="${sx(q2[0])}" y2="${sy(q2[1])}" stroke="rgb(${COLORS[k].map((v) => (v * 0.6) | 0)})" stroke-width="${stroke * 1.6}" stroke-linecap="round" data-person="${pi}"/>`;
            });
            if (S.hands) [p.left_hand, p.right_hand].forEach((hand) => {
                if (!hand) return;
                HAND_EDGES.forEach(([a, b], i) => {
                    const q1 = hand[a], q2 = hand[b];
                    if (q1 && q2) s += `<line x1="${sx(q1[0])}" y1="${sy(q1[1])}" x2="${sx(q2[0])}" y2="${sy(q2[1])}" stroke="hsl(${(i / HAND_EDGES.length) * 360},100%,50%)" stroke-width="${Math.max(2, stroke / 2.5)}"/>`;
                });
            });
            if (S.face && p.face) p.face.forEach((q) => { if (q) s += `<circle cx="${sx(q[0])}" cy="${sy(q[1])}" r="${Math.max(2, stroke / 3)}" fill="#fff"/>`; });
            p.body.forEach((q, j) => {
                if (!q) return;
                const on = drag && drag.p === pi && drag.j === j;
                s += `<circle cx="${sx(q[0])}" cy="${sy(q[1])}" r="${stroke * (on ? 2.1 : 1.5)}" fill="rgb(${COLORS[j]})" stroke="${on ? '#fbf1c7' : '#1d2021'}" stroke-width="${on ? 3 : 1.5}" class="sud-pose-j" data-p="${pi}" data-j="${j}"><title>${NAMES[j]}</title></circle>`;
            });
            s += '</g>';
        });
        return s;
    }
    function drawCanvas() {
        const svg = document.querySelector('.sud-pose-svg');
        if (!svg) return;
        const [W, H] = aspect();
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.innerHTML = svgHtml(W, H);
    }
    function fit() {
        const wrap = document.querySelector('.sud-pose-stage'), box = document.querySelector('.sud-pose-box');
        if (!wrap || !box) return;
        const [W, H] = aspect();
        const k = Math.min((wrap.clientWidth - 24) / W, (wrap.clientHeight - 24) / H);
        box.style.width = Math.floor(W * k) + 'px';
        box.style.height = Math.floor(H * k) + 'px';
    }
    addEventListener('resize', fit);

    function render() {
        if (!open) return;
        const o = overlay();
        const [W, H] = aspect();
        const people = S.people.map((p, i) => `<div class="sud-pose-it${i === S.sel ? ' on' : ''}" data-person="${i}">${I_USER}<span>Человек ${i + 1}</span>
            <button type="button" class="sud-pose-mini" data-act="hide" data-i="${i}" title="${p.hidden ? 'Показать' : 'Скрыть'}" style="opacity:${p.hidden ? 0.4 : 1}">${I_EYE}</button>
            <button type="button" class="sud-pose-mini" data-act="del" data-i="${i}" title="Удалить">${I_X}</button></div>`).join('') || '<div class="sud-pose-hint">Пусто — возьми позу с фото или шаблон</div>';
        const tg = (k, t) => `<label class="sud-pose-tg"><input type="checkbox" data-opt="${k}"${S[k] ? ' checked' : ''}><span>${t}</span></label>`;
        o.innerHTML = `<div class="sud-pose-bar">${I_POSE}<b>Редактор позы</b><span class="sud-pose-dim">${W}×${H}</span>
                <button type="button" class="sud-pose-ic" data-act="undo" title="Отменить (Ctrl+Z)"${undo.length ? '' : ' disabled'}>${I_UNDO}</button>
                <button type="button" class="sud-pose-ic" data-act="redo" title="Повторить (Ctrl+Y)"${redo.length ? '' : ' disabled'}>${I_REDO}</button>
                <span class="sud-pose-sp"></span>
                <button type="button" class="sud-pose-pill" data-act="gallery" title="DWPose найдёт позу на картинке из галереи">Позу с картинки</button>
                <button type="button" class="sud-pose-pill" data-act="upload">Загрузить фото…</button>
                <button type="button" class="sud-pose-pill" data-act="add">＋ Человек</button>
                <button type="button" class="sud-pose-pill" data-act="close">Закрыть</button>
                <button type="button" class="sud-pose-pill acc" data-act="apply">В Image Prompt</button></div>
            <div class="sud-pose-body"><div class="sud-pose-stage"><div class="sud-pose-box">
                ${photo ? `<img class="sud-pose-photo" src="${photo.url}" style="opacity:${S.opacity}" alt="">` : ''}
                <svg class="sud-pose-svg" preserveAspectRatio="none"></svg>
                ${busy ? `<div class="sud-pose-busy">${esc(busy)}</div>` : ''}</div>
                <div class="sud-pose-tip">${msg ? esc(msg) : 'Тяни сустав · тяни линию — двигается весь человек · Delete — удалить выбранного'}</div></div>
            <div class="sud-pose-side">
                <div><div class="sud-pose-sec">Люди</div>${people}</div>
                <div><div class="sud-pose-sec">Инструменты</div>${tg('lock', 'Фиксировать длину костей')}${tg('whole', 'Двигать конечность целиком')}
                    <div class="sud-pose-chips"><button type="button" class="sud-pose-pill" data-act="flip">⇋ Отразить</button></div></div>
                <div><div class="sud-pose-sec">Шаблоны (заменят выбранного)</div><div class="sud-pose-chips">${Object.keys(TPL).map((t) => `<button type="button" class="sud-pose-pill" data-tpl="${t}">${t}</button>`).join('')}</div></div>
                <div><div class="sud-pose-sec">Слои</div>
                    ${photo ? `<div class="sud-pose-sl">Фото<input type="range" min="0" max="100" value="${Math.round(S.opacity * 100)}" data-opt="opacity"><span>${Math.round(S.opacity * 100)}%</span></div>` : '<div class="sud-pose-hint">Фото нет — только скелет</div>'}
                    ${tg('hands', 'Кисти рук')}${tg('face', 'Лицо')}</div>
                <div class="sud-pose-hint">«В Image Prompt» кладёт скелет в слот с типом OpenPose. Дальше Generate — с тем же промптом и seed картинка будет похожей, но в новой позе.</div>
            </div></div>
            <input type="file" accept="image/*" class="sud-pose-file" hidden>`;
        fit(); drawCanvas();
    }
    function setOpen(v) {
        open = v;
        overlay().classList.toggle('show', open);
        document.querySelector('.sud-pose-btn')?.classList.toggle('on', open);
        if (open) { msg = ''; render(); }
    }

    // ---------- мышь ----------
    function pt(e) {
        const r = document.querySelector('.sud-pose-svg').getBoundingClientRect();
        return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
    }
    document.addEventListener('pointerdown', (e) => {
        if (!open || !e.target.closest || !e.target.closest('.sud-pose-svg')) return;
        const [x, y] = pt(e);
        const j = e.target.closest('.sud-pose-j');
        if (j) {
            snapshot();
            drag = { p: +j.dataset.p, j: +j.dataset.j, x, y };
            S.sel = drag.p;
        } else {
            // по линии или внутри рамки — тащим человека целиком
            let pi = e.target.dataset && e.target.dataset.person !== undefined ? +e.target.dataset.person : -1;
            if (pi < 0) pi = S.people.findIndex((p) => { const b = !p.hidden && bbox(p); return b && x > b[0] - 0.03 && x < b[2] + 0.03 && y > b[1] - 0.03 && y < b[3] + 0.03; });
            if (pi < 0) return;
            snapshot();
            S.sel = pi; drag = { p: pi, j: -1, x, y };
        }
        e.preventDefault();
        render();
    });
    document.addEventListener('pointermove', (e) => {
        if (!drag) return;
        const [x, y] = pt(e);
        const p = S.people[drag.p];
        if (drag.j < 0 || drag.j === 1) {           // весь человек
            const dx = x - drag.x, dy = y - drag.y;
            allPoints(p).forEach((q) => { q[0] += dx; q[1] += dy; });
            drag.x = x; drag.y = y;
        } else {
            const q = p.body[drag.j], par = p.body[PARENT[drag.j]];
            const moving = S.whole ? [...subtree(drag.j).map((k) => p.body[k]).filter(Boolean), ...attached(p, drag.j)] : [];
            if (S.lock && par) {                     // поворот вокруг родительского сустава
                const a0 = Math.atan2(q[1] - par[1], q[0] - par[0]), a1 = Math.atan2(y - par[1], x - par[0]);
                const da = a1 - a0, cos = Math.cos(da), sin = Math.sin(da);
                [q, ...moving].forEach((m) => {
                    const dx = m[0] - par[0], dy = m[1] - par[1];
                    m[0] = par[0] + dx * cos - dy * sin; m[1] = par[1] + dx * sin + dy * cos;
                });
            } else {
                const dx = x - q[0], dy = y - q[1];
                [q, ...moving].forEach((m) => { m[0] += dx; m[1] += dy; });
            }
        }
        drawCanvas();
    });
    document.addEventListener('pointerup', () => { if (drag) { drag = null; save(); render(); } });

    // ---------- кнопки ----------
    document.addEventListener('click', (e) => {
        if (!e.target.closest) return;
        if (e.target.closest('.sud-pose-btn')) { e.preventDefault(); setOpen(!open); return; }
        const o = e.target.closest('.sud-pose');
        if (!o) return;
        const btn = e.target.closest('[data-act], [data-tpl], .sud-pose-it');
        if (!btn) return;
        const a = btn.dataset.act;
        if (btn.dataset.tpl) {
            snapshot();
            const np = tplPerson(btn.dataset.tpl);
            if (S.people[S.sel]) {   // поставить шаблон на место выбранного: по центру и росту его рамки
                const b = bbox(S.people[S.sel]), nb = bbox(np);
                if (b) {
                    const k = (b[3] - b[1]) / (nb[3] - nb[1] || 1), cx = (b[0] + b[2]) / 2, ncx = (nb[0] + nb[2]) / 2;
                    np.body = np.body.map((q) => [cx + (q[0] - ncx) * k, b[1] + (q[1] - nb[1]) * k]);
                }
                S.people[S.sel] = np;
            } else { S.people.push(np); S.sel = S.people.length - 1; }
            save(); render(); return;
        }
        if (btn.classList.contains('sud-pose-it') && !a) { S.sel = +btn.dataset.person; render(); return; }
        if (a === 'hide') { snapshot(); const p = S.people[+btn.dataset.i]; p.hidden = !p.hidden; save(); render(); return; }
        if (a === 'del') { snapshot(); S.people.splice(+btn.dataset.i, 1); S.sel = Math.max(0, Math.min(S.sel, S.people.length - 1)); save(); render(); return; }
        if (a === 'add') { snapshot(); S.people.push(tplPerson('Стоит', (S.people.length % 3 - 1) * 0.28)); S.sel = S.people.length - 1; save(); render(); return; }
        if (a === 'flip' && S.people[S.sel]) {
            snapshot();
            const p = S.people[S.sel], b = bbox(p), cx = b ? (b[0] + b[2]) / 2 : 0.5;
            allPoints(p).forEach((q) => { q[0] = 2 * cx - q[0]; });
            FLIP.forEach(([i, j]) => { [p.body[i], p.body[j]] = [p.body[j], p.body[i]]; });
            [p.left_hand, p.right_hand] = [p.right_hand, p.left_hand];
            save(); render(); return;
        }
        if (a === 'undo' && undo.length) { redo.push(clone(S.people)); S.people = undo.pop(); save(); render(); return; }
        if (a === 'redo' && redo.length) { undo.push(clone(S.people)); S.people = redo.pop(); save(); render(); return; }
        if (a === 'gallery') { poseFromGallery(); return; }
        if (a === 'upload') { o.querySelector('.sud-pose-file').click(); return; }
        if (a === 'apply') { toImagePrompt(); return; }
        if (a === 'close') setOpen(false);
    });
    document.addEventListener('change', (e) => {
        const t = e.target;
        if (!t.matches) return;
        if (t.matches('.sud-pose-file') && t.files[0]) detectFrom(t.files[0]);
        if (t.matches('.sud-pose [data-opt]') && t.type === 'checkbox') { S[t.dataset.opt] = t.checked; save(); render(); }
    });
    document.addEventListener('input', (e) => {
        const t = e.target;
        if (t.matches && t.matches('.sud-pose [data-opt="opacity"]')) {
            S.opacity = t.value / 100; t.nextElementSibling.textContent = t.value + '%';
            const ph = document.querySelector('.sud-pose-photo'); if (ph) ph.style.opacity = S.opacity;
            save();
        }
    });
    document.addEventListener('keydown', (e) => {
        if (!open || (e.target.matches && e.target.matches('input, textarea'))) return;
        if (e.key === 'Escape') setOpen(false);
        else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); document.querySelector('.sud-pose [data-act="undo"]')?.click(); }
        else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); document.querySelector('.sud-pose [data-act="redo"]')?.click(); }
        else if (e.key === 'Delete' && S.people[S.sel]) { snapshot(); S.people.splice(S.sel, 1); S.sel = Math.max(0, S.sel - 1); save(); render(); }
    });

    // ---------- кнопка у промпта ----------
    setInterval(() => {
        const box = document.querySelector('#positive_prompt textarea')?.parentElement?.querySelector(':scope > .sud-tr');
        if (!box || box.querySelector('.sud-pose-btn')) return;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'sud-pose-btn'; b.title = 'Редактор позы (OpenPose)';
        b.innerHTML = `${I_POSE}<span>Поза</span>`;
        const cmp = box.querySelector('.sud-cmp-btn');
        box.insertBefore(b, cmp ? cmp.nextSibling : box.firstChild);
    }, 500);
})();
