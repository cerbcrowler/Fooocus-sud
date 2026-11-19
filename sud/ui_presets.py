"""Пресеты сэмплинга в карточке «Сэмплинг» (вкладка Models).

Отрисовка — javascript/sud-presets.js в блоке .sud-sp. Связь с Python — скрытые поле+кнопка:
    {"op": "state" | "apply" | "add" | "update" | "rename" | "note" | "delete", "name": ..., ...}
apply() получает текущие значения карточки (sampler, scheduler, CFG, шаги, резкость), отвечает
списком пресетов (JSON) и при «apply» выставляет значения пресета в карточку.

В webui.py:
    sud.ui_presets.container()        # над Sampler/Scheduler
    ...
    sud.ui_presets.wire(sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness)
"""

import json

import gradio as gr

from sud import presets as P


def container():
    gr.HTML('<div class="sud-sp"></div>')


def _state(msg="", applied=None):
    return json.dumps({"presets": P.load(), "message": msg, "applied": applied, "path": P.path()},
                      ensure_ascii=False)


def apply(payload, sampler, scheduler, cfg, steps, sharpness):
    keep = [gr.update()] * 5
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        return [_state()] + keep
    op, name = cmd.get("op", "state"), cmd.get("name", "")
    cur = P.values_dict(sampler, scheduler, cfg, steps, sharpness)
    err, applied = "", None
    try:
        if op == "apply":
            p = P.get(name)
            if not p:
                err = f"Пресета «{name}» нет"
            else:
                applied = name
                return [_state(applied=applied),
                        gr.update(value=p["sampler"]), gr.update(value=p["scheduler"]),
                        gr.update(value=p["cfg"]), gr.update(value=p["steps"]), gr.update(value=p["sharpness"])]
        elif op == "add":
            err = P.add(name, cur, cmd.get("note", ""))
            applied = None if err else " ".join(name.split())
        elif op == "update":
            err = P.update(name, cur)
            applied = name
        elif op == "rename":
            err = P.rename(name, cmd.get("new", ""))
            applied = None if err else " ".join(cmd.get("new", "").split())
        elif op == "note":
            err = P.set_note(name, cmd.get("note", ""))
        elif op == "delete":
            err = P.delete(name)
    except Exception as ex:
        err = f"Ошибка: {ex}"
    return [_state(err, applied)] + keep


def wire(sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness):
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-sp-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-sp-state"])
        btn = gr.Button("apply", elem_classes=["sud-sp-op-btn"])
    comps = [sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness]
    btn.click(apply, [op] + comps, [out] + comps, queue=False, show_progress=False)
