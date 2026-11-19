"""Общие кусочки для карточек интерфейса Fooocus-sud: контурные иконки и заголовки.

Иконки — Tabler Icons (outline, MIT), вставлены как inline SVG, без внешних загрузок.
Заголовок карточки — чистый HTML; кнопки в нём (data-sud-action) обрабатывает
javascript/sud-loras.js (например, нажимает спрятанную родную кнопку gradio).
"""

_PATHS = {
    "box": '<path d="M12 3l8 4.5l0 9l-8 4.5l-8 -4.5l0 -9l8 -4.5"/><path d="M12 12l8 -4.5"/>'
           '<path d="M12 12l0 9"/><path d="M12 12l-8 -4.5"/>',
    "stack": '<path d="M12 4l-8 4l8 4l8 -4l-8 -4"/><path d="M4 12l8 4l8 -4"/><path d="M4 16l8 4l8 -4"/>',
    "sliders": '<path d="M14 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/><path d="M4 6l8 0"/><path d="M16 6l4 0"/>'
               '<path d="M8 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/><path d="M4 12l2 0"/><path d="M10 12l10 0"/>'
               '<path d="M17 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/><path d="M4 18l11 0"/><path d="M19 18l1 0"/>',
    "refresh": '<path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"/>',
    "adjustments": '<path d="M4 10a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/><path d="M6 4v4"/><path d="M6 12v8"/>'
                   '<path d="M10 16a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/><path d="M12 4v10"/><path d="M12 18v2"/>'
                   '<path d="M16 7a2 2 0 1 0 4 0a2 2 0 0 0 -4 0"/><path d="M18 4v1"/><path d="M18 9v11"/>',
    "power": '<path d="M7 6a7.75 7.75 0 1 0 10 0"/><path d="M12 4l0 8"/>',
    "plus": '<path d="M12 5l0 14"/><path d="M5 12l14 0"/>',
}


def icon(name):
    return ('<svg class="sud-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_PATHS[name]}</svg>')


def head(title, ico, buttons=(), sub_class=None):
    """HTML заголовка карточки. buttons: [(action, icon, подсказка)]."""
    sub = f'<span class="sud-head-sub {sub_class}"></span>' if sub_class else ''
    btns = ''.join(f'<button type="button" class="sud-ibtn" data-sud-action="{a}" title="{t}">{icon(i)}</button>'
                   for a, i, t in buttons)
    return (f'<div class="sud-head">{icon(ico)}<span class="sud-head-title">{title}</span>{sub}'
            f'<div class="sud-head-btns">{btns}</div></div>')


def add_button(text):
    return f'<button type="button" class="sud-lora-add">{icon("plus")}<span>{text}</span></button>'
