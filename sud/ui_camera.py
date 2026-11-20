"""Карточка «Камера» (вкладка Models). Рисует javascript/sud-camera.js, состояние — скрытое поле (JSON),
которое уходит в ctrls (после композиции) → AsyncTask.camera → sud/camera.py → добавка к промпту."""

import gradio as gr


def build():
    with gr.Group(elem_classes=["sud-card", "sud-cam-card"]):
        gr.HTML('<div class="sud-cam"></div>')
        with gr.Column(elem_classes=["sud-hidden-btn"]):
            state = gr.Textbox(value='{"enabled": false}', show_label=False, container=False,
                               elem_classes=["sud-cam-state"])
    return state
