"""Карточка «Разрешение» (вкладка Models): плитки разрешений, выбор, правка, перестановка.

Родной переключатель Fooocus (aspect_ratios_selection, Radio на вкладке Settings) остаётся
«двигателем» и скрыт: выбор плитки = клик по его радиокнопке (это делает javascript/sud-aspect.js),
поэтому генерация, пресеты и загрузка параметров из картинок работают как раньше.

Изменение списка (добавить / удалить / переставить / поправить) JS присылает целиком:
    {"list": ["832*1216", "1024*1024", ...], "select": "896*1152"}
apply() проверяет, сохраняет в settings.json (Drive) и сразу обновляет варианты переключателя —
без перезапуска Fooocus.
"""

import json
import re

import gradio as gr

from sud import settings as S
from sud import ui_cards

MIN_SIDE, MAX_SIDE = 256, 4096


def _clean(items):
    out = []
    for item in items or []:
        m = re.fullmatch(r"\s*(\d+)\s*[*x×]\s*(\d+)\s*", str(item))
        if not m:
            continue
        w, h = int(m.group(1)), int(m.group(2))
        if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= h <= MAX_SIDE):
            continue
        r = f"{w}*{h}"
        if r not in out:
            out.append(r)
    return out


def _value_of(label):
    m = re.match(r"\s*(\d+)\s*[*x×]\s*(\d+)", label or "")
    return f"{m.group(1)}*{m.group(2)}" if m else None


def apply(payload, current_label):
    import modules.config as C

    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        return gr.update()
    ratios = _clean(cmd.get("list"))
    if not ratios:
        return gr.update()

    # сохранить (дописать в settings.json, не трогая остальные настройки)
    user = S.load_user()
    user["available_aspect_ratios"] = ratios
    default = user.get("default_aspect_ratio") or S.effective().get("default_aspect_ratio")
    if default not in ratios:
        user["default_aspect_ratio"] = ratios[0]
    S.save_user(user)
    S.apply()

    # обновить Fooocus «на лету»
    C.available_aspect_ratios = ratios
    C.available_aspect_ratios_labels = [C.add_ratio(r) for r in ratios]

    want = _clean([cmd.get("select")])
    cur = _value_of(current_label)
    pick = want[0] if want and want[0] in ratios else cur if cur in ratios else ratios[0]
    return gr.update(choices=C.available_aspect_ratios_labels, value=C.add_ratio(pick))


def build(aspect_ratios_selection):
    """Карточка. Вызывать внутри вкладки Models (переключатель уже создан на вкладке Settings)."""
    with gr.Group(elem_classes=["sud-card", "sud-ar-card"]):
        gr.HTML(ui_cards.head("Разрешение", "aspect", [], sub_class="sud-ar-current")
                .replace('<div class="sud-head">', '<div class="sud-head sud-ar-head" title="Свернуть / развернуть">', 1)
                .replace('<div class="sud-head-btns"></div>',
                         f'<div class="sud-head-btns"><span class="sud-ar-chev">{ui_cards.icon("chevron")}</span></div>', 1))
        gr.HTML('<div class="sud-ar-body"></div>')
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-hidden-btn", "sud-ar-op"])
        btn = gr.Button("apply", elem_classes=["sud-hidden-btn", "sud-ar-op-btn"])
    btn.click(apply, [op, aspect_ratios_selection], aspect_ratios_selection, queue=False, show_progress=False)
