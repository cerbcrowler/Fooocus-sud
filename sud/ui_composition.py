"""Compose with boxes — скрытое поле с раскладкой боксов (JSON) для async_worker.

Редактор рисует javascript/sud-composition.js (холст поверх области картинки, кнопка у промпта).
Поле — последний элемент ctrls в webui.py → AsyncTask.composition → modules/composition.py.
"""

import gradio as gr

from modules.composition import EMPTY_COMPOSITION


def build():
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        return gr.Textbox(value=EMPTY_COMPOSITION, show_label=False, container=False,
                          elem_classes=["sud-cmp-state"])
