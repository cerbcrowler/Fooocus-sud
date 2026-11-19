"""Пресеты сэмплинга: sampler, scheduler, CFG, шаги, резкость + название и заметка.

Хранятся на Drive: COLAB_MOUNTS/fooocus-sud/sampling_presets.json (если Drive не подключён —
рядом с Fooocus). Только стандартная библиотека.
"""

import json
import os

from sud.settings import DRIVE_ROOT, FOOOCUS_DIR

LOCAL_PATH = os.path.join(FOOOCUS_DIR, "sud_sampling_presets.json")
FIELDS = ("sampler", "scheduler", "cfg", "steps", "sharpness")


def path():
    from sud import paths
    return paths.settings_file("sampling_presets.json") if paths.drive_mounted() else LOCAL_PATH


def load():
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if isinstance(p, dict) and p.get("name")]
    except Exception:
        return []


def save(presets):
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _find(presets, name):
    for i, p in enumerate(presets):
        if p["name"] == name:
            return i
    return -1


def values_dict(sampler, scheduler, cfg, steps, sharpness):
    return {"sampler": sampler, "scheduler": scheduler, "cfg": round(float(cfg), 2),
            "steps": int(steps), "sharpness": round(float(sharpness), 2)}


def add(name, values, note=""):
    name = " ".join(str(name).split())
    presets = load()
    if not name:
        return "Введи название пресета"
    if _find(presets, name) >= 0:
        return f"Пресет «{name}» уже есть"
    presets.append({"name": name, "note": note, **values})
    save(presets)
    return ""


def update(name, values):
    presets = load()
    i = _find(presets, name)
    if i < 0:
        return f"Пресета «{name}» нет"
    presets[i].update(values)
    save(presets)
    return ""


def rename(name, new):
    new = " ".join(str(new).split())
    presets = load()
    i = _find(presets, name)
    if i < 0 or not new:
        return "Не получилось переименовать"
    if new != name and _find(presets, new) >= 0:
        return f"Пресет «{new}» уже есть"
    presets[i]["name"] = new
    save(presets)
    return ""


def set_note(name, note):
    presets = load()
    i = _find(presets, name)
    if i < 0:
        return f"Пресета «{name}» нет"
    presets[i]["note"] = " ".join(str(note).split())
    save(presets)
    return ""


def delete(name):
    presets = load()
    i = _find(presets, name)
    if i < 0:
        return f"Пресета «{name}» нет"
    del presets[i]
    save(presets)
    return ""


def get(name):
    presets = load()
    i = _find(presets, name)
    return presets[i] if i >= 0 else None
