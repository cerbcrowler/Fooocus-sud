"""Перевод промпта RU → EN в интерфейсе: кнопки 🌐 в полях промпта и негативного промпта.

Кнопки рисует javascript/sud-translate.js. Связь — скрытые поле+кнопка:
    {"fields": ["prompt", "negative"]}  → переводит указанные поля (только если в них есть кириллица)
Ответ: JSON-статус (движок, предупреждение, исходные тексты для «↩ оригинал») + новые значения полей.
Движок — настройка sud_translate_engine («deepl» = DeepL с запасным Google, «google»).
"""

import json

import gradio as gr

from sud import settings as S
from sud import translate as T


def apply(payload, prompt, negative):
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        cmd = {}
    fields = cmd.get("fields") or ["prompt"]
    engine = S.effective().get("sud_translate_engine", "deepl")
    status = {"engine": "", "warn": "", "originals": {}, "error": "", "nonce": cmd.get("nonce")}
    out = {"prompt": gr.update(), "negative": gr.update()}
    for name, text in (("prompt", prompt), ("negative", negative)):
        if name not in fields or not T.has_cyrillic(text):
            continue
        try:
            tr, used, warn = T.translate_prompt(text, engine)
        except Exception as e:
            status["error"] = f"Не удалось перевести: {e}"
            continue
        status["originals"][name] = text
        status["engine"] = used or status["engine"]
        status["warn"] = warn or status["warn"]
        out[name] = gr.update(value=tr)
    return json.dumps(status, ensure_ascii=False), out["prompt"], out["negative"]


def wire(prompt, negative_prompt):
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-tr-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-tr-state"])
        btn = gr.Button("apply", elem_classes=["sud-tr-op-btn"])
    btn.click(apply, [op, prompt, negative_prompt], [out, prompt, negative_prompt], queue=False, show_progress=False)
