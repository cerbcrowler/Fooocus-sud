"""API для нового интерфейса Fooocus-sud (/sud/) — внутри того же процесса Fooocus, рядом с Gradio.

    GET  /sud/                    новый интерфейс (sud/webui2/index.html)
    GET  /sud/static/<file>       его файлы
    GET  /sud/api/state           модели, LoRA, пресеты, варианты, значения по умолчанию, очередь
    POST /sud/api/generate        {prompt, negative, model, loras, sampler, ...} → {"id": ...}
    GET  /sud/api/task/<id>       прогресс, превью (data URI), готовые картинки
    POST /sud/api/task/<id>/stop  остановить (или {"skip": true} — пропустить текущую)
    GET  /sud/api/image/<key>     готовая картинка
    POST /sud/api/translate       {text} → перевод RU→EN (как кнопка RU→EN)
    POST /sud/api/presets/order   {kind: sampling|loras, names: [...]} → новый порядок пресетов (Drive)
    POST /sud/api/presets         {kind, op: add|update|edit|delete, name, new?, note?, values?} → пресеты (Drive)
    POST /sud/api/upload          картинка (тело запроса) или {"from": key} → {"key"} для «Образцов» (Image Prompt)
    POST /sud/api/pose            {op: detect, key} → позы с фото (DWPose); {op: render, poses, w, h} → {key} скелета
    GET  /sud/api/embeddings      эмбеддинги (папки, превью, избранное…), POST {op: fav|neg|used} — изменить

Генерация идёт через ту же очередь, что кнопка Generate (modules.async_worker.async_tasks).
Аргументы AsyncTask собираются из значений по умолчанию всех полей Gradio (ctrls) + того, что
прислал новый интерфейс. Подключение: sud.api.install(ctrls, named) перед shared.gradio_root.launch().
"""

import base64
import io
import json
import os
import random
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "webui2")
MAX_TASKS = 30          # сколько последних задач помним
MAX_IMAGES = 200        # сколько картинок отдаём (старые файлы удаляются)

_ctrls = []             # компоненты Gradio в порядке get_task (без currentTask)
_named = {}             # имя → компонент или список компонентов
_tasks = {}             # id → dict
_images = {}            # key → путь к файлу
_clean = {}             # key → путь к чистой копии (если на картинке плашка)
_lock = threading.Lock()
_durations = []         # секунд на картинку — для оценки времени
UPLOADS = "/content/sud_uploads" if os.path.isdir("/content") else os.path.join(
    __import__("tempfile").gettempdir(), "sud_uploads")   # образцы: переживают перезапуск Fooocus


# ---------------- сборка аргументов AsyncTask ----------------
def _default(c):
    v = getattr(c, "value", None)
    return v() if callable(v) else v


def _build_args(p):
    import modules.constants as constants
    values = {id(c): _default(c) for c in _ctrls}

    def put(name, value):
        c = _named.get(name)
        if c is not None and value is not None:
            values[id(c)] = value

    put("prompt", p.get("prompt", ""))
    put("negative_prompt", p.get("negative", ""))
    put("performance", p.get("performance"))
    put("aspect", p.get("aspect"))
    put("image_number", int(p.get("image_number", 1)))
    put("output_format", p.get("output_format"))
    put("sharpness", p.get("sharpness"))
    put("cfg", p.get("cfg"))
    put("base_model", p.get("model"))
    put("sampler", p.get("sampler"))
    put("scheduler", p.get("scheduler"))
    put("steps", p.get("steps"))
    put("composition", json.dumps(p["composition"]) if isinstance(p.get("composition"), dict) else p.get("composition"))
    put("camera", json.dumps(p["camera"]) if isinstance(p.get("camera"), dict) else p.get("camera"))
    put("styles", p.get("styles"))
    if p.get("action"):
        _apply_action(p.get("action"), put)
    else:
        _apply_ip(p.get("ip"), put)

    seed = p.get("seed")
    try:
        seed = int(seed)
        if not (constants.MIN_SEED <= seed <= constants.MAX_SEED):
            raise ValueError
    except (TypeError, ValueError):
        seed = random.randint(constants.MIN_SEED, constants.MAX_SEED)
    put("seed", str(seed))

    # LoRA: [(вкл, имя, вес)] на все слоты; лишние слоты — None
    lora_ctrls = _named.get("loras") or []
    loras = list(p.get("loras") or [])
    for i in range(len(lora_ctrls) // 3):
        on, name, w = (loras[i] + [True, "None", 1.0][len(loras[i]):]) if i < len(loras) else (True, "None", 1.0)
        values[id(lora_ctrls[i * 3])] = bool(on)
        values[id(lora_ctrls[i * 3 + 1])] = name or "None"
        values[id(lora_ctrls[i * 3 + 2])] = float(w)
    values.update(_overrides)
    _overrides.clear()
    return [values[id(c)] for c in _ctrls], seed


# ---------------- действия над готовой картинкой (кнопки у картинки) ----------------
ACTIONS = {
    "upscale_tiled": ("uov", "Upscale (Tiled Detail 2x)"),
    "upscale": ("uov", "Upscale (2x)"),
    "upscale_15": ("uov", "Upscale (1.5x)"),
    "vary_subtle": ("uov", "Vary (Subtle)"),
    "vary_strong": ("uov", "Vary (Strong)"),
    "faces": ("enhance", None),
    "inpaint": ("inpaint", None),
}
INPAINT_MODES = {   # как inpaint_mode_change в webui.py: (без начального латента, движок, сила, охват)
    "replace": ("Inpaint or Outpaint (default)", False, "engine", 1.0, 0.618),
    "detail": ("Improve Detail (face, hand, eyes, etc.)", False, "None", 0.5, 0.0),
    "modify": ("Modify Content (add objects, change background, etc.)", True, "engine", 1.0, 0.0),
}


def _decode_mask(uri, h, w):
    """data:image/png;base64 (белое — перерисовать) → HxWx3 uint8 размером с картинку."""
    import numpy as np
    from PIL import Image
    if not uri:
        return np.zeros((h, w, 3), dtype=np.uint8)
    raw = base64.b64decode(str(uri).split(",", 1)[-1])
    im = Image.open(io.BytesIO(raw)).convert("L")
    if im.size != (w, h):
        im = im.resize((w, h), Image.NEAREST)
    m = (np.array(im) > 127).astype(np.uint8) * 255
    return np.stack([m, m, m], axis=-1)


def _apply_inpaint(action, img, put):
    import modules.config as C
    put_c = lambda c, v: _overrides.__setitem__(id(c), v)  # noqa: E731
    mode = action.get("mode") if action.get("mode") in INPAINT_MODES else "replace"
    _, no_latent, engine, d_strength, d_field = INPAINT_MODES[mode]
    if engine == "engine":
        engine = C.default_inpaint_engine_version
    mask = _decode_mask(action.get("mask"), img.shape[0], img.shape[1])
    out = [d for d in (action.get("outpaint") or []) if d in ("Left", "Right", "Top", "Bottom")]
    if mode != "replace":
        out = []   # дорисовка краёв — только в обычном режиме (как в Fooocus)
    if not mask.any() and not out:
        raise ValueError("закрась кистью, что перерисовать (или выбери стрелку — дорисовать край)")
    put("inpaint_image", {"image": img, "mask": mask})
    put("inpaint_prompt", str(action.get("prompt") or ""))
    put("outpaint", out)
    c = _named.get("inpaint_ctrls") or []
    if len(c) >= 8:
        put_c(c[1], no_latent)
        put_c(c[2], engine)
        put_c(c[3], min(1.0, max(0.0, float(action.get("strength", d_strength)))))
        put_c(c[4], min(1.0, max(0.0, float(action.get("field", d_field)))))
        put_c(c[5], False)                       # без продвинутой маски (SAM и т.п.)
        put_c(c[6], bool(action.get("invert")))  # инвертировать маску
        put_c(c[7], 0)


def _load_image(key):
    import numpy as np
    from PIL import Image
    path = _clean.get(key) or _images.get(key) or _upload_path(key)
    if not path or not os.path.isfile(path):
        raise ValueError("картинки уже нет (Fooocus перезапускался?) — сгенерируй заново")
    return np.array(Image.open(path).convert("RGB"))


def _upload_path(key):
    key = str(key or "")
    if len(key) == 17 and key[0] == "u" and all(c in "0123456789abcdef" for c in key[1:]):
        return os.path.join(UPLOADS, key + ".png")
    return None


def _save_upload(img):
    """PIL/массив → PNG в UPLOADS, ключ = хэш содержимого (одно фото — один файл)."""
    import hashlib
    import numpy as np
    from PIL import Image
    im = img if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img))
    im = im.convert("RGB")
    if max(im.size) > 3072:
        im.thumbnail((3072, 3072))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    data = buf.getvalue()
    key = "u" + hashlib.sha1(data).hexdigest()[:16]
    os.makedirs(UPLOADS, exist_ok=True)
    path = _upload_path(key)
    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(data)
    return key, im.size


def _apply_ip(slots, put):
    """«Образцы» → Image Prompt: вкладка ip + 4 слота (картинка, стоп, вес, тип)."""
    import modules.flags as F
    ctrls = _named.get("ip_ctrls") or []
    slots = [s for s in (slots or []) if isinstance(s, dict) and s.get("key")]
    if not slots or not ctrls:
        return
    put("input_image", True)
    put("current_tab", "ip")
    for i in range(len(ctrls) // 4):
        img = stop = weight = None
        typ = F.default_ip
        if i < len(slots):
            s = slots[i]
            typ = s.get("type") if s.get("type") in F.ip_list else F.default_ip
            d_stop, d_weight = F.default_parameters[typ]
            img = _load_image(s["key"])
            stop = min(1.0, max(0.0, float(s.get("stop", d_stop))))
            weight = min(2.0, max(0.0, float(s.get("weight", d_weight))))
        else:
            stop, weight = F.default_parameters[F.default_ip]
        for c, v in zip(ctrls[i * 4:i * 4 + 4], (img, stop, weight, typ)):
            _overrides[id(c)] = v


def _apply_action(action, put):
    if not action:
        return
    kind = action.get("type")
    if kind not in ACTIONS:
        raise ValueError(f"неизвестное действие {kind}")
    tab, uov = ACTIONS[kind]
    img = _load_image(action.get("key"))
    put("input_image", True)
    put("current_tab", tab)
    put("composition", '{"enabled": false, "boxes": []}')
    put("camera", '{"enabled": false}')
    if tab == "uov":
        put("uov_method", uov)
        put("uov_image", img)
    elif tab == "inpaint":
        _apply_inpaint(action, img, put)
    else:
        # Enhance #1: найти лица и перерисовать каждое отдельно (как ADetailer)
        put("enhance", True)
        put("enhance_image", img)
        e = _named.get("enhance_ctrls") or []
        if len(e) >= 17:
            put_c = lambda c, v: _overrides.__setitem__(id(c), v)  # noqa: E731
            put_c(e[0], True)       # Enable
            put_c(e[1], "face")     # Detection prompt
            put_c(e[16], True)      # Каждый объект отдельно


_overrides = {}


# ---------------- задачи ----------------
def _jpeg_uri(img, max_side=768):
    from PIL import Image
    import numpy as np
    im = Image.fromarray(np.asarray(img)).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _keep_image(item):
    """Путь или массив → ключ для /sud/api/image/<key>."""
    path = item
    if not isinstance(item, str):
        from PIL import Image
        import numpy as np
        import tempfile
        path = os.path.join(tempfile.gettempdir(), f"sud_{uuid.uuid4().hex}.png")
        Image.fromarray(np.asarray(item)).save(path)
    key = uuid.uuid4().hex
    try:
        from sud import plate
        if isinstance(item, str) and item in plate.CLEAN:
            _clean[key] = plate.CLEAN[item]
    except Exception:
        pass
    with _lock:
        _images[key] = path
        while len(_images) > MAX_IMAGES:
            k_old = next(iter(_images))
            _clean.pop(k_old, None)
            old = _images.pop(k_old)
            try:
                os.remove(old)
            except OSError:
                pass
    return key


def _drain(rec):
    """Разобрать накопившиеся task.yields (как generate_clicked в webui.py)."""
    task = rec["task"]
    while task.yields:
        flag, product = task.yields.pop(0)
        if flag == "preview":
            pct, title, image = product
            rec["percent"], rec["title"] = int(pct), title
            if image is not None and not isinstance(image, str):
                rec["_preview_img"] = image
        elif flag == "results":
            rec["results_n"] = len(product)
        elif flag == "finish":
            items = [x for x in product if x is not None]
            rec["images"] = [_keep_image(x) for x in items]
            rec["names"] = [os.path.basename(x) if isinstance(x, str) else f"{rec['id'][:8]}_{i}.png" for i, x in enumerate(items)]
            rec["done"], rec["percent"] = True, 100
            rec["seconds"] = round(time.time() - rec["started"], 1)
            n = max(1, len(rec["images"]))
            _durations.append(rec["seconds"] / n)
            del _durations[:-20]
            print(f"[sud api] готово {rec['id'][:8]}: {len(rec['images'])} шт. за {rec['seconds']} с")


def _new_task(p):
    import modules.async_worker as worker
    import ldm_patched.modules.model_management as mm
    args, seed = _build_args(p)
    task = worker.AsyncTask(args=args)
    with mm.interrupt_processing_mutex:
        mm.interrupt_processing = False
    tid = uuid.uuid4().hex
    rec = {"id": tid, "task": task, "seed": seed, "started": time.time(), "percent": 0,
           "title": "В очереди…", "done": False, "images": [], "params": {k: v for k, v in p.items() if k != "composition"}}
    with _lock:
        _tasks[tid] = rec
        while len(_tasks) > MAX_TASKS:
            _tasks.pop(next(iter(_tasks)))
    worker.async_tasks.append(task)
    return rec


def _eta(n):
    if not _durations:
        return None
    # медиана: первая генерация с загрузкой модели (минута) не должна портить оценку
    d = sorted(_durations)
    return round(d[len(d) // 2] * n, 1)


# ---------------- состояние для интерфейса ----------------
def _choices(c):
    out = []
    for ch in getattr(c, "choices", None) or []:
        out.append(ch[1] if isinstance(ch, (list, tuple)) else ch)
    return out


def _sys():
    """Видеопамять, память, сколько работает машина Colab (/proc/uptime ≈ с начала сессии)."""
    out = {}
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            out.update(gpu=torch.cuda.get_device_name(0), vram_used=total - free, vram_total=total)
    except Exception:
        pass
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k] = int(v.split()[0]) * 1024
        out.update(ram_used=mem["MemTotal"] - mem["MemAvailable"], ram_total=mem["MemTotal"])
        with open("/proc/uptime") as f:
            out["uptime"] = float(f.read().split()[0])
    except Exception:
        pass
    return out


def _auto_translate():
    try:
        from sud import settings as S
        return bool(S.effective().get("sud_auto_translate", False))
    except Exception:
        return False


def _state():
    import modules.config as C
    import modules.flags as F
    import modules.async_worker as worker
    from sud import presets as P
    n = _named
    lora_ctrls = n.get("loras") or []
    return {
        "models": C.model_filenames,
        "loras": C.lora_filenames,
        "lora_slots": len(lora_ctrls) // 3,
        "lora_min": C.default_loras_min_weight, "lora_max": C.default_loras_max_weight,
        "samplers": F.sampler_list, "schedulers": F.scheduler_list,
        "aspects": _choices(n["aspect"]) if "aspect" in n else [],
        "performances": _choices(n["performance"]) if "performance" in n else [],
        "output_formats": _choices(n["output_format"]) if "output_format" in n else [],
        "max_images": getattr(n.get("image_number"), "maximum", 32),
        "defaults": {
            "model": _default(n["base_model"]) if "base_model" in n else None,
            "loras": [[_default(lora_ctrls[i]), _default(lora_ctrls[i + 1]), _default(lora_ctrls[i + 2])]
                      for i in range(0, len(lora_ctrls), 3) if _default(lora_ctrls[i + 1]) not in (None, "None")],
            "sampler": _default(n["sampler"]) if "sampler" in n else None,
            "scheduler": _default(n["scheduler"]) if "scheduler" in n else None,
            "steps": _default(n["steps"]) if "steps" in n else -1,
            "cfg": _default(n["cfg"]) if "cfg" in n else 4,
            "sharpness": _default(n["sharpness"]) if "sharpness" in n else 2,
            "aspect": _default(n["aspect"]) if "aspect" in n else None,
            "performance": _default(n["performance"]) if "performance" in n else None,
            "output_format": _default(n["output_format"]) if "output_format" in n else "png",
            "image_number": _default(n["image_number"]) if "image_number" in n else 1,
            "negative": _default(n["negative_prompt"]) if "negative_prompt" in n else "",
        },
        "ip": {"types": F.ip_list, "defaults": {k: list(v) for k, v in F.default_parameters.items()},
               "slots": len(_named.get("ip_ctrls") or []) // 4},
        "sampling_presets": P.SAMPLING.load(),
        "lora_presets": P.LORAS.load(),
        "queue": len(worker.async_tasks),
        "busy": any(not r["done"] for r in _tasks.values()),
        "sec_per_image": _eta(1),
        "auto_translate": _auto_translate(),
        "sys": _sys(),
        "inpaint_modes": {k: {"strength": v[3], "field": v[4]} for k, v in INPAINT_MODES.items()},
    }


# ---------------- маршруты ----------------
def _preset_values(kind, v):
    """Значения пресета из нового интерфейса → формат файлов пресетов (как в классическом)."""
    from sud import presets as P
    v = v or {}
    if kind == "sampling":
        return P.sampling_values(v["sampler"], v["scheduler"], v["cfg"], v["steps"], v["sharpness"])
    loras = []
    for l in v.get("loras") or []:
        if l.get("name") and l["name"] != "None":
            loras.append({"name": str(l["name"]), "weight": round(float(l.get("weight", 1.0)), 2),
                          "enabled": bool(l.get("enabled", True))})
    return {"loras": loras}


def _routes(app):
    from fastapi import Request
    from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse

    async def index(request: Request):
        return FileResponse(os.path.join(WEB, "index.html"), headers={"Cache-Control": "no-cache"})

    async def static(name: str):
        path = os.path.realpath(os.path.join(WEB, name))
        if not path.startswith(os.path.realpath(WEB) + os.sep) or not os.path.isfile(path):
            return Response(status_code=404)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    async def state():
        return JSONResponse(_state())

    async def generate(request: Request):
        p = await request.json()
        try:
            rec = _new_task(p)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse({"id": rec["id"], "seed": rec["seed"], "eta": _eta(int(p.get("image_number", 1)))})

    async def task(tid: str):
        rec = _tasks.get(tid)
        if not rec:
            return JSONResponse({"error": "нет такой задачи"}, status_code=404)
        _drain(rec)
        out = {k: rec.get(k) for k in ("id", "seed", "percent", "title", "done", "images", "names", "seconds")}
        img = rec.pop("_preview_img", None)
        if img is not None:
            out["preview"] = _jpeg_uri(img)
        return JSONResponse(out)

    async def stop(tid: str, request: Request):
        import ldm_patched.modules.model_management as mm
        rec = _tasks.get(tid)
        if not rec:
            return JSONResponse({"error": "нет такой задачи"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        rec["task"].last_stop = "skip" if body.get("skip") else "stop"
        if rec["task"].processing:
            mm.interrupt_current_processing()
        return JSONResponse({"ok": True})

    async def upload(request: Request):
        ctype = request.headers.get("content-type", "")
        try:
            if ctype.startswith("application/json"):
                key, size = _save_upload(_load_image((await request.json()).get("from")))
            else:
                from PIL import Image
                key, size = _save_upload(Image.open(io.BytesIO(await request.body())))
        except Exception as e:
            return JSONResponse({"error": f"не получилось взять картинку: {e}"}, status_code=400)
        return JSONResponse({"key": key, "w": size[0], "h": size[1]})

    async def pose(request: Request):
        import asyncio
        body = await request.json()

        def work():
            import numpy as np
            from extras import dwpose
            if body.get("op") == "detect":
                import modules.config
                img = _load_image(body.get("key"))
                h, w = img.shape[:2]
                _, poses = dwpose.detect(img, *modules.config.downloading_dwpose())
                return {"w": w, "h": h, "poses": [{k: (list(v) if v else None) for k, v in p.items()} for p in poses]}
            if body.get("op") == "render":
                w, h = int(body.get("w", 1024)), int(body.get("h", 1024))
                clean = lambda part: None if not part or all(p is None for p in part) else [None if p is None else (float(p[0]), float(p[1])) for p in part]  # noqa: E731
                poses = [{"body": clean(p.get("body")) or [None] * 18, "left_hand": clean(p.get("left_hand")),
                          "right_hand": clean(p.get("right_hand")), "face": clean(p.get("face"))}
                         for p in body.get("poses") or [] if not p.get("hidden")]
                arr = dwpose.draw(poses, w, h, hands=bool(body.get("hands", True)), face=bool(body.get("face", True)))
                key, _ = _save_upload(np.asarray(arr))
                return {"key": key}
            raise ValueError("неизвестная команда")
        try:
            return JSONResponse(await asyncio.get_running_loop().run_in_executor(None, work))
        except Exception as e:
            print(f"[sud api] поза: {e}")
            return JSONResponse({"error": str(e)}, status_code=400)

    async def image(key: str):
        path = _images.get(key) or _upload_path(key)
        if not path or not os.path.isfile(path):
            return Response(status_code=404)
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    async def translate(request: Request):
        from sud import translate as T, settings as S
        body = await request.json()
        text = body.get("text", "")
        engine = S.effective().get("sud_translate_engine", "deepl")
        try:
            tr, used, warn = T.translate_prompt(text, engine)
            return JSONResponse({"text": tr, "engine": used, "warn": warn})
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    async def presets_order(request: Request):
        from sud import presets as P
        body = await request.json()
        store = {"sampling": P.SAMPLING, "loras": P.LORAS}.get(body.get("kind"))
        if store is None:
            return JSONResponse({"error": "неизвестный вид пресетов"}, status_code=400)
        store.reorder([str(n) for n in body.get("names") or []])
        return JSONResponse({"ok": True, "presets": store.load()})

    async def presets_edit(request: Request):
        from sud import presets as P
        body = await request.json()
        kind = body.get("kind")
        store = {"sampling": P.SAMPLING, "loras": P.LORAS}.get(kind)
        if store is None:
            return JSONResponse({"error": "неизвестный вид пресетов"}, status_code=400)
        op, name = body.get("op"), str(body.get("name") or "")
        try:
            values = _preset_values(kind, body.get("values")) if op in ("add", "update") else None
            if op == "add":
                err = store.add(name, values, " ".join(str(body.get("note") or "").split()))
            elif op == "update":
                err = store.update(name, values)
            elif op == "edit":
                err = store.rename(name, body.get("new") or name) if (body.get("new") or name) != name else ""
                if not err and "note" in body:
                    err = store.set_note(" ".join(str(body.get("new") or name).split()), body.get("note") or "")
            elif op == "delete":
                err = store.delete(name)
            else:
                err = "неизвестное действие"
        except (TypeError, ValueError, KeyError) as e:
            err = f"плохие значения: {e}"
        if err:
            return JSONResponse({"error": err}, status_code=400)
        return JSONResponse({"ok": True, "presets": store.load()})

    async def embeddings(request: Request):
        """GET — список (как панель 🧬 в классическом), POST {op: fav|neg|used, name, on} — изменить."""
        from sud import ui_embeddings as E
        import asyncio
        if request.method == "POST":
            body = await request.json()
            out = await asyncio.get_event_loop().run_in_executor(None, E.apply, json.dumps(body))
        else:
            out = await asyncio.get_event_loop().run_in_executor(None, E.state)
        return Response(out, media_type="application/json")

    async def to_index():
        return RedirectResponse("/sud/")

    app.add_api_route("/sud", to_index, methods=["GET"])
    app.add_api_route("/sud/", index, methods=["GET"])
    app.add_api_route("/sud/static/{name:path}", static, methods=["GET"])
    app.add_api_route("/sud/api/state", state, methods=["GET"])
    app.add_api_route("/sud/api/generate", generate, methods=["POST"])
    app.add_api_route("/sud/api/task/{tid}", task, methods=["GET"])
    app.add_api_route("/sud/api/task/{tid}/stop", stop, methods=["POST"])
    app.add_api_route("/sud/api/image/{key}", image, methods=["GET"])
    app.add_api_route("/sud/api/upload", upload, methods=["POST"])
    app.add_api_route("/sud/api/pose", pose, methods=["POST"])
    app.add_api_route("/sud/api/translate", translate, methods=["POST"])
    app.add_api_route("/sud/api/presets/order", presets_order, methods=["POST"])
    app.add_api_route("/sud/api/presets", presets_edit, methods=["POST"])
    app.add_api_route("/sud/api/embeddings", embeddings, methods=["GET", "POST"])
    # наши маршруты — первыми, чтобы общие маршруты Gradio их не перехватили
    ours = [r for r in app.router.routes if getattr(r, "path", "").startswith("/sud")]
    for r in ours:
        app.router.routes.remove(r)
    app.router.routes[0:0] = ours


def install(ctrls, named):
    """ctrls — список из webui.py (с currentTask первым), named — словарь имя → компонент(ы)."""
    global _ctrls, _named
    _ctrls = list(ctrls[1:])
    _named = dict(named)
    import gradio.routes as gr_routes
    original = gr_routes.App.create_app

    def create_app(*args, **kwargs):
        app = original(*args, **kwargs)
        try:
            _routes(app)
            print("[sud api] новый интерфейс: /sud/")
        except Exception as e:
            print(f"[sud api] не удалось подключить /sud/: {e}")
        return app

    gr_routes.App.create_app = staticmethod(create_app)
