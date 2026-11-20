"""Полноэкранный менеджер моделей (пока чекпоинты; механизм общий — лоры подключим тем же кодом).

Интерфейс рисует javascript/sud-manager.js. Связь с Python — как в других карточках:
JS кладёт команду JSON в скрытое поле `.sud-mm-op` и жмёт скрытую кнопку, apply() отвечает
полным состоянием (JSON в скрытом поле `.sud-mm-state`) и при нужде обновляет выбор модели.

Команды: state · download · cancel · delete · autoload · category · title · add · remove ·
add_category · select
"""

import json
import os
import shutil

import gradio as gr

from sud import models as M
from sud.catalog import Catalog
from sud.downloads import cached_size, fetch_sizes_bg, jobs

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KINDS = {
    "CHECKPOINTS": {"title": "Чекпоинты", "folder": "checkpoints", "exts": (".safetensors", ".ckpt")},
    "LORAS": {"title": "LoRA", "folder": "loras", "exts": (".safetensors",)},
}


def _on_drive(path):
    """Файл (или ссылка на него) физически лежит на Google Drive — удалять из менеджера нельзя."""
    try:
        return os.path.realpath(path).startswith("/content/drive/")
    except OSError:
        return False


def _paths():
    return M.load_paths(FOOOCUS_DIR)


def _folder(kind):
    return getattr(_paths(), KINDS[kind]["folder"])


def _catalog():
    return Catalog(_paths().links_file)


def _local_files(kind):
    folder = _folder(kind)
    out = {}
    if os.path.isdir(folder):
        for root, _, files in os.walk(folder):
            for f in files:
                if f.endswith(KINDS[kind]["exts"]):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, folder).replace("\\", "/")
                    try:
                        out[rel] = os.path.getsize(full)
                    except OSError:
                        out[rel] = None
    return out


def state(kind="CHECKPOINTS", current=None, message=""):
    cat = _catalog()
    entries = cat.entries(kind)
    local = _local_files(kind)
    drive = {rel for rel in local if _on_drive(os.path.join(_folder(kind), rel))}
    items, in_catalog = [], set()
    for e in entries:
        fname = e.filename
        in_catalog.add(fname)
        job = jobs.status(e.url)
        if job and job["state"] == "running":
            status = "downloading"
        elif fname in local:
            status = "local"
        elif job and job["state"] == "error":
            status = "error"
        else:
            status = "none"
        size = local.get(fname) or (job or {}).get("total") or cached_size(e.url)
        items.append({
            "url": e.url, "file": fname, "title": e.display, "category": e.category, "note": e.note,
            "autoload": e.autoload, "star": e.star, "status": status, "size": size,
            "done": (job or {}).get("done", 0), "speed": (job or {}).get("speed", 0),
            "error": (job or {}).get("error", ""), "current": fname == current, "drive": fname in drive,
        })
    for fname, size in sorted(local.items()):
        if fname not in in_catalog:
            items.append({"url": "", "file": fname, "title": os.path.splitext(os.path.basename(fname))[0],
                          "category": None, "autoload": False, "star": False, "status": "local", "size": size,
                          "done": 0, "speed": 0, "error": "", "current": fname == current, "drive": fname in drive})
    fetch_sizes_bg([e.url for e in entries if not cached_size(e.url)])
    try:
        du = shutil.disk_usage(_folder(kind) if os.path.isdir(_folder(kind)) else FOOOCUS_DIR)
        disk = {"used": du.used, "total": du.total}
    except OSError:
        disk = None
    return {
        "kind": kind, "kinds": {k: v["title"] for k, v in KINDS.items()},
        "items": items, "categories": cat.categories(kind), "disk": disk,
        "current": current, "catalog": _paths().links_file, "message": message,
    }


def _model_dropdown(select=None):
    import modules.config as C
    C.update_files()
    upd = {"choices": C.model_filenames}
    if select:
        upd["value"] = select
    return gr.update(**upd)


def apply(payload, current_model):
    """Классический интерфейс (скрытые поле + кнопка)."""
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        cmd = {}
    st, fx = run(cmd, current_model)
    dropdown = gr.update()
    if fx["select"]:
        dropdown = _model_dropdown(select=fx["select"])
    elif fx["refresh"]:
        dropdown = _model_dropdown()
    return json.dumps(st, ensure_ascii=False), dropdown


def run(cmd, current_model=None):
    """Команда менеджера → (состояние, {"refresh": обновить список моделей Fooocus, "select": имя файла}).
    Без Gradio — общая для классического интерфейса и нового (/sud/api/models)."""
    op, kind = cmd.get("op", "state"), cmd.get("kind", "CHECKPOINTS")
    if kind not in KINDS:
        kind = "CHECKPOINTS"
    url = cmd.get("url", "")
    cat = _catalog()
    msg, current = "", current_model
    fx = {"refresh": False, "select": None}

    try:
        if op == "download":
            e = cat.find(url)
            if e:
                jobs.start(url, _folder(kind), e.filename)
                msg = f"⬇️ Загружаю {e.display}"
        elif op == "cancel":
            jobs.cancel(url)
            msg = "Загрузка отменена"
        elif op == "delete":
            fname = cmd.get("file", "")
            full = os.path.normpath(os.path.join(_folder(kind), fname))
            if fname and _on_drive(full):
                msg = "⚠️ Этот файл лежит на Google Drive — удаляй его там, а не из Colab"
            elif fname and full.startswith(os.path.normpath(_folder(kind))) and os.path.lexists(full):
                os.remove(full)
                jobs.forget(url)
                msg = f"🗑 Удалено из Colab: {os.path.basename(fname)}"
                fx["refresh"] = True
        elif op == "autoload":
            cat.set_autoload(url, bool(cmd.get("on")))
        elif op == "category":
            cat.set_category(url, cmd.get("category", ""))
        elif op == "title":
            cat.set_title(url, cmd.get("title", ""))
        elif op == "note":
            cat.set_note(url, cmd.get("note", ""))
        elif op == "reorder":
            cat.reorder(kind, [str(u) for u in cmd.get("urls") or []])
        elif op == "move":   # перетащили на другую категорию (и, может, в нужное место)
            cat.set_category(url, cmd.get("category", ""))
            if cmd.get("urls"):
                _catalog().reorder(kind, [str(u) for u in cmd["urls"]])
            msg = f"Перенесено в «{cmd.get('category') or 'Без категории'}»"
        elif op == "remove":
            cat.remove(url)
            msg = "Убрано из каталога (файл в Colab, если был, остался)"
        elif op == "add_category":
            if cmd.get("category", "").strip():
                cat.add_category(kind, cmd["category"])
        elif op == "add":
            if not url.startswith("http"):
                msg = "⚠️ Нужна ссылка на файл (https://huggingface.co/…/resolve/main/…)"
            elif not cat.add(kind, url, name=cmd.get("name", ""), title=cmd.get("title", ""),
                             category=cmd.get("category", ""), star=bool(cmd.get("star"))):
                msg = "⚠️ Такая ссылка уже есть в каталоге"
            else:
                msg = "✅ Добавлено в каталог"
                if cmd.get("download_now"):
                    e = cat.find(url)
                    jobs.start(url, _folder(kind), e.filename)
                    msg += ", загрузка пошла"
        elif op == "select":
            fname = cmd.get("file", "")
            if fname in _local_files(kind):
                fx["select"] = fname
                current = fname
                msg = f"▶ Текущая модель: {os.path.splitext(os.path.basename(fname))[0]}"
        elif op == "state" and cmd.get("refresh_models"):
            fx["refresh"] = True
    except Exception as ex:  # чтобы ошибка не роняла панель
        msg = f"❌ {ex}"

    return state(kind, current, msg), fx


def build(base_model):
    """Скрытые элементы связи. Саму панель рисует JS поверх интерфейса."""
    with gr.Column(elem_classes=["sud-hidden-btn", "sud-mm-bridge"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-mm-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-mm-state"])
        btn = gr.Button("apply", elem_classes=["sud-mm-op-btn"])
    btn.click(apply, [op, base_model], [out, base_model], queue=False, show_progress=False)
