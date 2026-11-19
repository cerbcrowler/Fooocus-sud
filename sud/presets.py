"""Хранилища пресетов (название + заметка + значения): сэмплинг и LoRA.

Файлы на Drive: FOOOCUS-SUD/settings/<файл>.json (без Drive — рядом с Fooocus).
Только стандартная библиотека.
"""

import json
import os

from sud.settings import FOOOCUS_DIR


class Store:
    def __init__(self, filename):
        self.filename = filename
        self.local = os.path.join(FOOOCUS_DIR, "sud_" + filename)

    def path(self):
        from sud import paths
        return paths.settings_file(self.filename) if paths.drive_mounted() else self.local

    def load(self):
        try:
            with open(self.path(), encoding="utf-8") as f:
                data = json.load(f)
            return [p for p in data if isinstance(p, dict) and p.get("name")]
        except Exception:
            return []

    def save(self, presets):
        p = self.path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)

    @staticmethod
    def _find(presets, name):
        for i, p in enumerate(presets):
            if p["name"] == name:
                return i
        return -1

    def add(self, name, values, note=""):
        name = " ".join(str(name).split())
        presets = self.load()
        if not name:
            return "Введи название пресета"
        if self._find(presets, name) >= 0:
            return f"Пресет «{name}» уже есть"
        presets.append({"name": name, "note": note, **values})
        self.save(presets)
        return ""

    def update(self, name, values):
        presets = self.load()
        i = self._find(presets, name)
        if i < 0:
            return f"Пресета «{name}» нет"
        presets[i].update(values)
        self.save(presets)
        return ""

    def rename(self, name, new):
        new = " ".join(str(new).split())
        presets = self.load()
        i = self._find(presets, name)
        if i < 0 or not new:
            return "Не получилось переименовать"
        if new != name and self._find(presets, new) >= 0:
            return f"Пресет «{new}» уже есть"
        presets[i]["name"] = new
        self.save(presets)
        return ""

    def set_note(self, name, note):
        presets = self.load()
        i = self._find(presets, name)
        if i < 0:
            return f"Пресета «{name}» нет"
        presets[i]["note"] = " ".join(str(note).split())
        self.save(presets)
        return ""

    def delete(self, name):
        presets = self.load()
        i = self._find(presets, name)
        if i < 0:
            return f"Пресета «{name}» нет"
        del presets[i]
        self.save(presets)
        return ""

    def get(self, name):
        presets = self.load()
        i = self._find(presets, name)
        return presets[i] if i >= 0 else None


SAMPLING = Store("sampling_presets.json")
LORAS = Store("lora_presets.json")


# ---- сэмплинг: sampler, scheduler, CFG, шаги, резкость ----
def sampling_values(sampler, scheduler, cfg, steps, sharpness):
    return {"sampler": sampler, "scheduler": scheduler, "cfg": round(float(cfg), 2),
            "steps": int(steps), "sharpness": round(float(sharpness), 2)}


def sampling_outputs(p):
    return [p["sampler"], p["scheduler"], p["cfg"], p["steps"], p["sharpness"]]


# ---- LoRA: список непустых слотов по порядку ----
def lora_values(*ctrls):
    loras = []
    for i in range(0, len(ctrls) - 2, 3):
        enabled, name, weight = ctrls[i:i + 3]
        if name and name != "None":
            loras.append({"name": name, "weight": round(float(weight), 2), "enabled": bool(enabled)})
    return {"loras": loras}


def lora_outputs(p, n_slots):
    out = []
    loras = list(p.get("loras", []))[:n_slots]
    for l in loras:
        out += [bool(l.get("enabled", True)), l["name"], float(l.get("weight", 1.0))]
    for _ in range(n_slots - len(loras)):
        out += [True, "None", 1.0]
    return out
