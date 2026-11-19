"""Панель 🧬 «Эмбеддинги» у поля промпта: превью, поиск, ⭐ избранное, недавние, негативные.

Список — файлы в models/embeddings (туда ссылками подключены папки с Drive, см. sud/paths.py).
Превью — картинка с тем же именем рядом с эмбеддингом (.jpeg/.jpg/.png/.webp, в т.ч. «имя.preview.png»),
уменьшается до миниатюры и отдаётся как data-URI. Избранное, недавние и ручные пометки «негативный» —
в FOOOCUS-SUD/settings/embeddings.json.

SDXL или нет: у SDXL-эмбеддингов в .safetensors есть ключи clip_g/clip_l (читаем только заголовок файла).
"""

import base64
import io
import json
import os
import re
import struct

import gradio as gr

from sud import paths

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMB_DIR = os.path.join(FOOOCUS_DIR, "models", "embeddings")
EXTS = (".safetensors", ".pt", ".bin")
PREVIEW_EXTS = (".preview.png", ".preview.jpeg", ".preview.jpg", ".jpeg", ".jpg", ".png", ".webp")
NEG_RE = re.compile(r"neg|unaesthetic|bad[_-]?|worst|lowres|ugly|easynegative|deformed", re.I)
RECENT_MAX = 10
# кэш превью и SDXL-проверки: чтение с Drive медленное (~1 с на файл), поэтому храним в памяти
# и в файле рядом с Fooocus (переживает перезапуски Fooocus в пределах сессии Colab)
CACHE_FILE = os.path.join(FOOOCUS_DIR, "sud_embeddings_cache.json")
try:
    with open(CACHE_FILE, encoding="utf-8") as _f:
        _disk = json.load(_f)
except Exception:
    _disk = {}
_thumbs = {tuple(k.split("|", 1)): v for k, v in _disk.get("thumbs", {}).items()}
_kinds = {tuple(k.split("|", 1)): v for k, v in _disk.get("kinds", {}).items()}
_dirty = False


def _key(path):
    return (path, str(os.path.getmtime(path)))


def _flush_cache():
    global _dirty
    if not _dirty:
        return
    try:
        data = {"thumbs": {"|".join(k): v for k, v in _thumbs.items()},
                "kinds": {"|".join(k): v for k, v in _kinds.items()}}
        with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        _dirty = False
    except OSError:
        pass


def _store_path():
    return paths.settings_file("embeddings.json") if paths.drive_mounted() else os.path.join(FOOOCUS_DIR, "sud_embeddings.json")


def _load_store():
    try:
        with open(_store_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data.setdefault("favorites", [])
    data.setdefault("recent", [])
    data.setdefault("negative", {})
    return data


def _save_store(data):
    p = _store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(p + ".tmp", p)


def _is_sdxl(path):
    """True — SDXL, False — SD1.5, None — не понять (.pt/.bin или битый файл)."""
    global _dirty
    try:
        key = _key(path)
    except OSError:
        return None
    if key in _kinds:
        return _kinds[key]
    result = None
    if path.endswith(".safetensors"):
        try:
            with open(path, "rb") as f:
                n = struct.unpack("<Q", f.read(8))[0]
                header = json.loads(f.read(min(n, 1_000_000)))
            keys = set(header) - {"__metadata__"}
            result = bool({"clip_g", "clip_l"} & keys) if keys else None
        except Exception:
            result = None
    _kinds[key] = result
    _dirty = True
    return result


def _preview(path):
    real = os.path.realpath(path)
    stem = os.path.splitext(real)[0]
    for ext in PREVIEW_EXTS:
        p = stem + ext
        if os.path.isfile(p):
            return p
    return None


def _thumb(img_path, size=112):
    global _dirty
    try:
        key = _key(img_path)
    except OSError:
        return None
    if key in _thumbs:
        return _thumbs[key]
    try:
        from PIL import Image
        with Image.open(img_path) as im:
            im = im.convert("RGB")
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
        uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        uri = None
    _thumbs[key] = uri
    _dirty = True
    return uri


def _items(store):
    items = []
    if not os.path.isdir(EMB_DIR):
        return items
    for root, _, files in os.walk(EMB_DIR):
        for f in sorted(files, key=str.lower):
            if not f.endswith(EXTS):
                continue
            full = os.path.join(root, f)
            if not os.path.exists(full):      # битая ссылка
                continue
            name = os.path.splitext(f)[0]
            neg = store["negative"].get(name)
            items.append({
                "name": name,
                "neg": bool(NEG_RE.search(name)) if neg is None else bool(neg),
                "neg_auto": neg is None,
                "fav": name in store["favorites"],
                "sdxl": _is_sdxl(full),
                "thumb": (lambda p: _thumb(p) if p else None)(_preview(full)),
            })
    return items


def state(msg=""):
    store = _load_store()
    items = _items(store)
    names = {i["name"] for i in items}
    _flush_cache()
    return json.dumps({"items": items, "recent": [r for r in store["recent"] if r in names],
                       "folder": paths.EMBEDDINGS, "message": msg}, ensure_ascii=False)


def apply(payload):
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        cmd = {}
    op, name = cmd.get("op", "state"), cmd.get("name", "")
    store = _load_store()
    changed = True
    if op == "fav":
        if cmd.get("on") and name not in store["favorites"]:
            store["favorites"].append(name)
        elif not cmd.get("on") and name in store["favorites"]:
            store["favorites"].remove(name)
    elif op == "neg":
        store["negative"][name] = bool(cmd.get("on"))
    elif op == "used":
        store["recent"] = [name] + [r for r in store["recent"] if r != name]
        store["recent"] = store["recent"][:RECENT_MAX]
    else:
        changed = False
    if changed:
        try:
            _save_store(store)
        except OSError as e:
            return state(f"Не удалось сохранить: {e}")
    return state()


def warm_up():
    """Прогреть кэш превью в фоне при старте Fooocus — чтобы первое открытие 🧬 было мгновенным."""
    import threading
    threading.Thread(target=lambda: state(), daemon=True).start()


def wire():
    warm_up()
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-em-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-em-state"])
        btn = gr.Button("apply", elem_classes=["sud-em-op-btn"])
    btn.click(apply, [op], [out], queue=False, show_progress=False)
