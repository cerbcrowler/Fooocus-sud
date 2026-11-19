"""Вкладка «📦 Менеджер» для Fooocus-sud: скачать модель по ссылке и увидеть, что есть.

В webui.py две вставки:
    with gr.Tab(label='📦 Менеджер'):
        sud_manager = sud.ui_models.build()
    ...
    sud.ui_models.wire_refresh(sud_manager, refresh_files_clicked, refresh_files_output + lora_ctrls)
"""

import os

import gradio as gr

from sud import models as M

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = ["Тип", "Файл", "Размер", "Откуда"]


def _paths():
    return M.load_paths(FOOOCUS_DIR)


def _table():
    return M.list_files(_paths()) or [["—", "пока пусто", "", ""]]


def _download(url, kind, new_name, keep, progress=gr.Progress(track_tqdm=True)):
    url, new_name = (url or "").strip(), (new_name or "").strip() or None
    if not url:
        return "⚠️ Вставь ссылку на файл HuggingFace", gr.update()
    repo_id, filename = M.parse_hf_url(url)
    if not repo_id:
        return ("⚠️ Это не похоже на ссылку на файл HuggingFace. Нужна такая: "
                "`https://huggingface.co/<автор>/<репо>/resolve/main/<файл>.safetensors`"), gr.update()

    paths = _paths()
    progress(0, desc=f"Качаю {os.path.basename(filename)}...")
    path = M.download(paths, kind, url, new_name)
    if not path:
        return "❌ Не скачалось: подробности в логе Fooocus (`/content/fooocus.log`)", _table()

    msg = f"✅ Готово: **{os.path.basename(path)}** ({kind})"
    if keep:
        section = M.KINDS[kind][0]
        try:
            added = M.add_link(paths.links_file, section, url, new_name)
            msg += (f" — добавлено в `links.txt` [{section}]" if added
                    else " — в `links.txt` уже есть")
        except OSError as e:
            msg += f" — ⚠️ в `links.txt` записать не удалось: {e}"
    return msg, _table()


def build():
    """Собирает содержимое вкладки. Вызывать внутри `with gr.Tab(...)`."""
    gr.Markdown("Скачать модель по ссылке HuggingFace. "
                "С галочкой «в links.txt» она будет скачиваться сама в каждой новой сессии.")
    with gr.Group():
        url = gr.Textbox(label="Ссылка на файл (HuggingFace)", max_lines=1,
                         placeholder="https://huggingface.co/автор/репо/resolve/main/файл.safetensors")
        with gr.Row():
            kind = gr.Radio(list(M.KINDS), value="LoRA", label="Тип")
            new_name = gr.Textbox(label="Новое имя (необязательно)", max_lines=1)
        keep = gr.Checkbox(value=True, label="Добавить в links.txt (на Drive)")
        download_btn = gr.Button("⬇️ Скачать", variant="primary")
    status = gr.Markdown()

    with gr.Group():
        table = gr.Dataframe(headers=HEADERS, value=_table, interactive=False, wrap=True)
        refresh_btn = gr.Button("🔄 Обновить список", variant="secondary")

    download_event = download_btn.click(_download, [url, kind, new_name, keep], [status, table])
    refresh_btn.click(_table, [], table, queue=False, show_progress=False)
    return {"download_event": download_event, "table": table}


def wire_refresh(ui, refresh_fn, outputs):
    """После скачивания обновить выпадающие списки моделей Fooocus (как кнопка Refresh All Files)."""
    ui["download_event"].then(refresh_fn, [], outputs, queue=False, show_progress=False)
