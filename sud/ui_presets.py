"""Пресеты в карточках вкладки Models: «Сэмплинг» и «LoRA» (общий механизм).

Отрисовка — javascript/sud-presets.js в блоке <div class="sud-sp" data-kind="...">. Связь с Python —
скрытые поле+кнопка (.sud-pr-<kind>-op / -op-btn / -state):
    {"op": "state" | "apply" | "add" | "update" | "rename" | "note" | "delete", "name": ..., ...}
apply() получает текущие значения карточки, отвечает списком пресетов (JSON) и при «apply»
выставляет значения пресета в карточку.

В webui.py:
    sud.ui_presets.container("sampling")      # в карточке, над полями
    ...
    sud.ui_presets.wire_sampling(sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness)
    sud.ui_presets.wire_loras(lora_ctrls)
"""

import json

import gradio as gr

from sud import presets as P

def container(kind):
    gr.HTML(f'<div class="sud-sp" data-kind="{kind}"></div>')


def _state(store, msg="", applied=None):
    return json.dumps({"presets": store.load(), "message": msg, "applied": applied, "path": store.path()},
                      ensure_ascii=False)


def _handler(store, values_fn, outputs_fn, n_out, check_fn=None):
    def apply(payload, *comps):
        keep = [gr.update()] * n_out
        try:
            cmd = json.loads(payload or "{}")
        except ValueError:
            return [_state(store)] + keep
        op, name = cmd.get("op", "state"), cmd.get("name", "")
        cur = values_fn(*comps)
        err, applied = "", None
        try:
            if op == "apply":
                p = store.get(name)
                if not p:
                    err = f"Пресета «{name}» нет"
                else:
                    msg = check_fn(p) if check_fn else ""
                    return [_state(store, msg, applied=name)] + [gr.update(value=v) for v in outputs_fn(p)]
            elif op == "add":
                err = store.add(name, cur, cmd.get("note", ""))
                applied = None if err else " ".join(name.split())
            elif op == "update":
                err = store.update(name, cur)
                applied = name
            elif op == "rename":
                err = store.rename(name, cmd.get("new", ""))
                applied = None if err else " ".join(cmd.get("new", "").split())
            elif op == "note":
                err = store.set_note(name, cmd.get("note", ""))
            elif op == "delete":
                err = store.delete(name)
        except Exception as ex:
            err = f"Ошибка: {ex}"
        return [_state(store, err, applied)] + keep
    return apply


def _bridge(kind, fn, comps):
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=[f"sud-pr-{kind}-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=[f"sud-pr-{kind}-state"])
        btn = gr.Button("apply", elem_classes=[f"sud-pr-{kind}-op-btn"])
    btn.click(fn, [op] + comps, [out] + comps, queue=False, show_progress=False)


def wire_sampling(sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness):
    comps = [sampler_name, scheduler_name, guidance_scale, overwrite_step, sharpness]
    _bridge("sampling", _handler(P.SAMPLING, P.sampling_values, P.sampling_outputs, 5), comps)


def wire_loras(lora_ctrls):
    n = len(lora_ctrls) // 3

    def check(p):
        import modules.config
        have = set(modules.config.lora_filenames)
        lost = [l["name"] for l in p.get("loras", []) if l["name"] not in have]
        extra = len(p.get("loras", [])) - n
        msg = []
        if lost:
            msg.append("Нет файлов: " + ", ".join(lost))
        if extra > 0:
            msg.append(f"Слотов не хватило, пропущено лор: {extra}")
        return "; ".join(msg)

    def outputs(p):
        # лоры, которых нет среди файлов, не ставим (Fooocus упал бы на генерации) — о них скажет check()
        import modules.config
        have = set(modules.config.lora_filenames)
        return P.lora_outputs({"loras": [l for l in p.get("loras", []) if l["name"] in have]}, n)

    _bridge("loras", _handler(P.LORAS, P.lora_values, outputs, len(lora_ctrls), check),
            list(lora_ctrls))
