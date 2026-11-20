// Fooocus-sud: карточка «Камера» (вкладка Models) — ракурс (циферблат вокруг человека), высота, план, сила.
// Идея — lllyasviel/Fooocus PR #1797: выбор превращается в добавку к промпту, например
// «(three-quarter view, facing left:1.2), (close-up:1.2)». Слова — в sud/camera.py, здесь только выбор.
// Состояние — JSON в скрытом поле .sud-cam-state (уходит в генерацию) + localStorage «sud-cam».
(function () {
    const LS = 'sud-cam', LS_COLL = 'sud-cam-collapsed';
    const SVG = (p) => `<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
    const I_CAM = SVG('<path d="M5 7h1a2 2 0 0 0 2 -2a1 1 0 0 1 1 -1h6a1 1 0 0 1 1 1a2 2 0 0 0 2 2h1a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-9a2 2 0 0 1 2 -2"/><path d="M9 13a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/>');
    const I_CHEV = SVG('<path d="M6 9l6 6l6 -6"/>');
    const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

    // ракурс: позиция камеры вокруг человека (вид сверху, человек смотрит вниз на экране = на зрителя)
    const ANGLES = [
        ['front', 'спереди', 90], ['q_right', '¾ вправо', 45], ['right', 'профиль вправо', 0], ['bq_right', 'сзади ¾ вправо', -45],
        ['back', 'сзади', -90], ['bq_left', 'сзади ¾ влево', -135], ['left', 'профиль влево', 180], ['q_left', '¾ влево', 135],
    ];
    const HEIGHTS = [['top', 'С дрона'], ['high', 'Сверху'], ['above', 'Чуть сверху'], ['eye', 'На уровне глаз'], ['low', 'Снизу'], ['worm', 'С земли'], ['selfie', 'Селфи']];
    const SHOTS = [['ecu', 'Глаза крупно'], ['cu', 'Лицо'], ['mcu', 'По плечи'], ['ms', 'По пояс'], ['cowboy', 'По бёдра'], ['full', 'Во весь рост'], ['long', 'Общий план'], ['establishing', 'Издалека'], ['pov', 'От первого лица']];
    // слова — те же, что в sud/camera.py (для подсказки «что добавится»)
    const WORDS = {
        front: 'front view, facing the viewer', q_left: 'three-quarter view, facing left', left: 'side view, profile, facing left',
        bq_left: 'three-quarter back view, from behind, looking left', back: 'back view, from behind',
        bq_right: 'three-quarter back view, from behind, looking right', right: 'side view, profile, facing right', q_right: 'three-quarter view, facing right',
        top: "top down view, bird's eye view", high: 'high angle', above: 'slightly above', eye: 'straight on, eye level', low: 'low angle, hero view', worm: "worm's eye view", selfie: 'selfie',
        ecu: 'extreme close-up', cu: 'close-up', mcu: 'medium close-up', ms: 'medium shot', cowboy: 'cowboy shot', full: 'full body, full shot', long: 'long shot', establishing: 'establishing shot', pov: 'point-of-view',
    };

    let S = { enabled: false, angle: '', height: '', shot: '', weight: 1.2 };
    try { Object.assign(S, JSON.parse(localStorage.getItem(LS) || '{}')); } catch (e) { /* ignore */ }
    let collapsed = false;
    try { collapsed = localStorage.getItem(LS_COLL) === '1'; } catch (e) { /* ignore */ }

    const any = () => !!(S.angle || S.height || S.shot);
    const label = (list, k) => (list.find((x) => x[0] === k) || [])[1];
    function promptText() {
        if (!S.enabled || !any()) return '';
        return [S.angle, S.height, S.shot].filter(Boolean).map((k) => `(${WORDS[k]}:${(+S.weight).toFixed(1).replace(/\.0$/, '')})`).join(', ');
    }
    function summary() {
        if (!S.enabled || !any()) return 'выкл';
        return [label(ANGLES, S.angle), label(HEIGHTS, S.height), label(SHOTS, S.shot)].filter(Boolean).join(' · ');
    }

    let lastSent = '';
    function sync() {
        try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { /* ignore */ }
        const ta = document.querySelector('.sud-cam-state textarea, .sud-cam-state input');
        const v = JSON.stringify(S);
        if (ta && ta.value !== v) { ta.value = v; ta.dispatchEvent(new Event('input', { bubbles: true })); }
        lastSent = v;
    }

    function render() {
        const box = document.querySelector('.sud-cam');
        if (!box) return;
        const card = box.closest('.sud-cam-card');
        card && card.classList.toggle('sud-collapsed', collapsed);
        const R = 46;
        const dots = ANGLES.map(([k, t, a]) => {
            const x = 60 + R * Math.cos(a * Math.PI / 180), y = 60 + R * Math.sin(a * Math.PI / 180);
            return `<button type="button" class="sud-cam-dot${S.angle === k ? ' on' : ''}" data-angle="${k}" title="${t}" style="left:${x}px;top:${y}px"></button>`;
        }).join('');
        const chips = (list, key) => list.map(([k, t]) => `<button type="button" class="sud-cam-chip${S[key] === k ? ' on' : ''}" data-${key}="${k}">${t}</button>`).join('');
        const pt = promptText();
        box.innerHTML = `<div class="sud-head sud-cam-head" data-act="collapse">${I_CAM}<span class="sud-head-title">Камера</span>
                <span class="sud-head-sub sud-cam-sum${S.enabled && any() ? ' on' : ''}">${esc(summary())}</span>
                <div class="sud-head-btns"><label class="sud-cam-tg" title="Включить/выключить камеру (выбор сохранится)"><input type="checkbox" data-act="enabled"${S.enabled ? ' checked' : ''}></label>
                <span class="sud-cam-chev">${I_CHEV}</span></div></div>
            <div class="sud-cam-body">
                <div class="sud-cam-top">
                    <div class="sud-cam-dial" title="Ракурс: где стоит камера вокруг человека (вид сверху)">
                        <div class="sud-cam-ring"></div>
                        <button type="button" class="sud-cam-who${S.angle ? '' : ' on'}" data-angle="" title="Ракурс не задан">
                            <span class="nose"></span></button>${dots}
                    </div>
                    <div class="sud-cam-side">
                        <div class="sud-cam-lbl">Ракурс: <b>${esc(label(ANGLES, S.angle) || 'любой')}</b></div>
                        <div class="sud-cam-lbl">Сила <output>${(+S.weight).toFixed(1)}</output></div>
                        <input type="range" min="0.5" max="2" step="0.1" value="${S.weight}" data-act="weight" class="sud-cam-w">
                        <button type="button" class="sud-cam-chip" data-act="reset">Сбросить всё</button>
                    </div>
                </div>
                <div class="sud-cam-lbl">Высота камеры</div><div class="sud-cam-chips">${chips(HEIGHTS, 'height')}</div>
                <div class="sud-cam-lbl">План</div><div class="sud-cam-chips">${chips(SHOTS, 'shot')}</div>
                <div class="sud-cam-prev">${pt ? `В конец промпта: <code>${esc(pt)}</code>` : 'Ничего не выбрано — промпт без изменений'}</div>
            </div>`;
    }

    document.addEventListener('click', (e) => {
        const box = e.target.closest && e.target.closest('.sud-cam');
        if (!box) return;
        const t = e.target.closest('[data-angle], [data-height], [data-shot], [data-act]');
        if (!t) return;
        if (t.dataset.act === 'collapse' && !e.target.closest('.sud-cam-tg')) {
            collapsed = !collapsed;
            try { localStorage.setItem(LS_COLL, collapsed ? '1' : '0'); } catch (er) { /* ignore */ }
            render(); return;
        }
        if (t.dataset.act === 'reset') { S = { enabled: false, angle: '', height: '', shot: '', weight: 1.2 }; sync(); render(); return; }
        for (const key of ['angle', 'height', 'shot']) {
            if (t.dataset[key] !== undefined) {
                S[key] = S[key] === t.dataset[key] ? '' : t.dataset[key];   // повторный клик снимает выбор
                S.enabled = any();
                sync(); render(); return;
            }
        }
    });
    document.addEventListener('change', (e) => {
        if (e.target.matches && e.target.matches('.sud-cam [data-act="enabled"]')) { S.enabled = e.target.checked; sync(); render(); }
    });
    document.addEventListener('input', (e) => {
        if (e.target.matches && e.target.matches('.sud-cam [data-act="weight"]')) {
            S.weight = Math.round(parseFloat(e.target.value) * 10) / 10;
            e.target.parentElement.querySelector('output').textContent = S.weight.toFixed(1);
            sync();
            const pv = document.querySelector('.sud-cam-prev'), pt = promptText();
            if (pv) pv.innerHTML = pt ? `В конец промпта: <code>${esc(pt)}</code>` : 'Ничего не выбрано — промпт без изменений';
        }
    });

    setInterval(() => {
        const box = document.querySelector('.sud-cam');
        if (box && !box.firstChild) render();
        const ta = document.querySelector('.sud-cam-state textarea, .sud-cam-state input');
        if (ta && ta.value !== lastSent) sync();
    }, 500);
})();
