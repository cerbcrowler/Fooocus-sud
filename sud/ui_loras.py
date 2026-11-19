"""Удаление и перестановка слотов LoRA (вкладка Models).

Слоты — родные компоненты Fooocus (lora_ctrls: [вкл, имя, вес] × N). Поменять им значения
из JS напрямую нельзя, поэтому:
  JS (javascript/sud-loras.js) кладёт команду JSON в скрытое поле `.sud-lora-op textarea`
  и нажимает скрытую кнопку `.sud-lora-op-btn` → apply() переставляет значения и возвращает их.

Команды:
  {"op": "remove", "index": 2}          — очистить слот 2, остальные сдвинуть вверх
  {"op": "move",   "order": [1, 0, 2]}  — новый порядок слотов (перестановка индексов)
"""

import json

import gradio as gr

EMPTY = [True, "None", 1.0]


def _is_empty(slot):
    return slot[1] in (None, "", "None")


def apply(payload, *values):
    n = len(values) // 3
    slots = [list(values[i * 3:i * 3 + 3]) for i in range(n)]
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        cmd = {}

    if cmd.get("op") == "remove" and isinstance(cmd.get("index"), int) and 0 <= cmd["index"] < n:
        slots[cmd["index"]] = list(EMPTY)
        order = [i for i, s in enumerate(slots) if not _is_empty(s)] + \
                [i for i, s in enumerate(slots) if _is_empty(s)]
    elif cmd.get("op") == "move" and sorted(cmd.get("order") or []) == list(range(n)):
        order = cmd["order"]
    else:
        return [gr.update() for _ in values]

    out = []
    for i in order:
        enabled, name, weight = slots[i]
        out += [enabled, name if not _is_empty(slots[i]) else "None", weight]
    return out


def wire(lora_ctrls):
    """Создать скрытые поле+кнопку и связать с слотами. Вызывать внутри карточки LoRA."""
    op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-hidden-btn", "sud-lora-op"])
    btn = gr.Button("apply", elem_classes=["sud-hidden-btn", "sud-lora-op-btn"])
    btn.click(apply, [op] + lora_ctrls, lora_ctrls, queue=False, show_progress=False)
    return op, btn
