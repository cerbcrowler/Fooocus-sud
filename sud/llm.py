"""Нейронка через OpenRouter: «✨ придумать» сцены (локация / свет), позже — обогащение промпта.

Ключ: файл KEY_FILE (его кладёт ячейка Colab из секрета OPENROUTER_API_KEY) или переменная
окружения OPENROUTER_API_KEY. Модель и инструкции — в ⚙️ Настройках (sud/settings.py).
Только стандартная библиотека.
"""

import json
import os
import re
import time
import urllib.request

KEY_FILE = os.path.expanduser("~/.config/fooocus-sud/openrouter.key")
API = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash-1017"

INSTR = {
    "loc": (
        "You write LOCATION descriptions for Stable Diffusion XL photo prompts.\n"
        "The user gives an idea (often in Russian). Invent a vivid, photographable place.\n"
        "Return ONLY a JSON object, no other text:\n"
        '{"name": "short Russian name, 2-4 words",\n'
        ' "prompt": "English comma-separated phrases: the place, interior or exterior details, materials, '
        'props, colors, atmosphere. 15-35 words. No people, no camera or lens terms, no lighting",\n'
        ' "light": "English: light and shadows that suit this place, 8-20 words",\n'
        ' "negative": "English comma-separated things to avoid in this scene, 0-8 words, may be empty",\n'
        ' "note": "very short Russian note: what it is good for"}'
    ),
    "light": (
        "You write LIGHTING presets for Stable Diffusion XL photo prompts.\n"
        "The user gives an idea (often in Russian). Describe light only — not the place.\n"
        "Return ONLY a JSON object, no other text:\n"
        '{"name": "short Russian name, 2-4 words",\n'
        ' "light": "English comma-separated phrases: light source and direction, quality (hard/soft), shadows, '
        'color temperature, color grading, mood. 10-30 words",\n'
        ' "negative": "English comma-separated things to avoid, 0-8 words, may be empty",\n'
        ' "note": "very short Russian note: when to use it"}'
    ),
}


def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    try:
        with open(KEY_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _post(path, body, timeout=90):
    k = key()
    if not k:
        raise RuntimeError("нет ключа OpenRouter — добавь секрет OPENROUTER_API_KEY в Colab и перезапусти ячейку")
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {k}", "Content-Type": "application/json",
        "X-Title": "Fooocus-sud", "User-Agent": "fooocus-sud"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"OpenRouter {e.code}: {msg or e.reason}")


def chat(system, user, model=None, temperature=0.9):
    """→ (текст ответа, модель, секунд)."""
    t = time.time()
    r = _post("/chat/completions", {"model": model or DEFAULT_MODEL, "temperature": temperature,
                                    "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": user}]})
    try:
        text = r["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"странный ответ OpenRouter: {str(r)[:200]}")
    return text, r.get("model", model), time.time() - t


def parse_json(text):
    """JSON из ответа модели (даже если он обёрнут в ```json … ``` или с текстом вокруг)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise RuntimeError("модель ответила не JSON: " + (text or "")[:160])
    return json.loads(m.group(0))


def scene(kind, idea, model=None, instructions=None):
    """«✨ придумать» сцену: kind = loc | light → поля карточки."""
    system = instructions or INSTR[kind]
    text, used, sec = chat(system, idea, model)
    d = parse_json(text)
    out = {k: " ".join(str(d.get(k) or "").split()) for k in ("name", "prompt", "light", "negative", "note")}
    if kind == "light":
        out["prompt"] = ""
    out.update(model=used, seconds=round(sec, 1))
    return out


_models_cache = {"t": 0, "list": []}


def models():
    """Модели OpenRouter для текста: [{id, name, free}] (кеш на час)."""
    if time.time() - _models_cache["t"] < 3600 and _models_cache["list"]:
        return _models_cache["list"]
    req = urllib.request.Request(API + "/models", headers={"User-Agent": "fooocus-sud"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode()).get("data", [])
    out = []
    for m in data:
        arch = (m.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in arch:
            continue
        p = m.get("pricing") or {}
        free = str(p.get("prompt", "1")) in ("0", "0.0") and str(p.get("completion", "1")) in ("0", "0.0")
        out.append({"id": m["id"], "name": m.get("name", m["id"]), "free": free})
    out.sort(key=lambda x: (not x["free"], x["id"]))
    _models_cache.update(t=time.time(), list=out)
    return out
