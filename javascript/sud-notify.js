// Fooocus-sud: звук, когда очередь генерации закончилась.
// Fooocus сам зовёт playNotification() после всей очереди (webui.py, цепочка generate → ... → playNotification).
// Мы подменяем её: если в ⚙️ Настройках включён звук (#sud-flags data-notify="1") — играем мягкий
// «дзынь» через WebAudio (файл не нужен). Если рядом с Fooocus лежит notification.mp3/ogg — играет он.
(function () {
    let ctx = null;
    function audio() {
        if (!ctx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (!AC) return null;
            ctx = new AC();
        }
        if (ctx.state === 'suspended') ctx.resume();
        return ctx;
    }
    // браузер разрешает звук только после действия пользователя — «будим» звук на первом клике
    ['pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, () => audio(), { once: true, capture: true }));

    function chime() {
        const a = audio();
        if (!a) return;
        const t0 = a.currentTime + 0.02;
        const master = a.createGain();
        master.gain.value = 0.22;
        master.connect(a.destination);
        // две ноты колокольчика: ми → ля, с обертоном и мягким затуханием
        [[659.25, 0], [880, 0.16]].forEach(([f, dt]) => {
            [[1, 1], [2.01, 0.25], [3.02, 0.08]].forEach(([mul, vol]) => {
                const o = a.createOscillator(), g = a.createGain();
                o.type = 'sine';
                o.frequency.value = f * mul;
                const t = t0 + dt;
                g.gain.setValueAtTime(0.0001, t);
                g.gain.exponentialRampToValueAtTime(vol, t + 0.012);
                g.gain.exponentialRampToValueAtTime(0.0001, t + 1.4);
                o.connect(g); g.connect(master);
                o.start(t); o.stop(t + 1.5);
            });
        });
    }
    window.sudChime = chime;   // для кнопки «Прослушать» в настройках

    const enabled = () => document.querySelector('#sud-flags')?.dataset.notify === '1';
    const original = window.playNotification;
    window.playNotification = function () {
        if (!enabled()) return;
        const file = (typeof gradioApp === 'function' ? gradioApp() : document).querySelector('#audio_notification audio');
        if (file) { file.play(); return; }
        chime();
    };
    window.playNotification.original = original;

    document.addEventListener('click', (e) => {
        if (e.target.closest && e.target.closest('.sud-notify-test')) { e.preventDefault(); chime(); }
    });
})();
