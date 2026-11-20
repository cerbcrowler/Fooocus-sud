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
_lock = threading.Lock()
_durations = []         # секунд на картинку — для оценки времени


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
    return [values[id(c)] for c in _ctrls], seed


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
    with _lock:
        _images[key] = path
        while len(_images) > MAX_IMAGES:
            old = _images.pop(next(iter(_images)))
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
        "sampling_presets": P.SAMPLING.load(),
        "lora_presets": P.LORAS.load(),
        "queue": len(worker.async_tasks),
        "busy": any(not r["done"] for r in _tasks.values()),
        "sec_per_image": _eta(1),
    }


# ---------------- маршруты ----------------
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
        rec = _new_task(p)
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

    async def image(key: str):
        path = _images.get(key)
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
    app.add_api_route("/sud/api/translate", translate, methods=["POST"])
    app.add_api_route("/sud/api/presets/order", presets_order, methods=["POST"])
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
