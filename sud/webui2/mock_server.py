"""Заглушка API для разработки нового интерфейса без Colab: python sud/webui2/mock_server.py [порт]
Открывать http://localhost:7899/sud/ — ответы похожи на настоящий sud/api.py, «картинки» — SVG-градиенты.
Только стандартная библиотека.
"""

import json
import os
import random
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS = {}
STATE = {
    "models": ["redcraftHybridH3A2A_illust3relustion.safetensors", "epicrealismXL_pureFix.safetensors", "juggernautXL_v9.safetensors"],
    "loras": ["TECH/TECH-dmd2_sdxl_4step_lora_fp16.safetensors", "AGE/age_slider.safetensors",
              "SLIDERS/W-body_weight_slider_v1.safetensors", "STYLE/0-shiny_nai_pdxl.safetensors"],
    "lora_slots": 3, "lora_min": -5, "lora_max": 5,
    "samplers": ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde_gpu", "lcm", "tcd", "er_sde", "seeds_2"],
    "schedulers": ["normal", "karras", "sgm_uniform", "simple", "lcm", "tcd", "beta", "kl_optimal"],
    "aspects": ["704×1408", "832×1216", "896×1152", "1024×1024", "1152×896", "1216×832", "1344×768"],
    "performances": ["Quality", "Speed", "Extreme Speed", "Lightning", "Hyper-SD"],
    "output_formats": ["png", "jpeg", "webp"], "max_images": 8,
    "defaults": {"model": "redcraftHybridH3A2A_illust3relustion.safetensors",
                 "loras": [[True, "TECH/TECH-dmd2_sdxl_4step_lora_fp16.safetensors", 1.0]],
                 "sampler": "lcm", "scheduler": "sgm_uniform", "steps": 6, "cfg": 1.0, "sharpness": 5.0,
                 "aspect": "1024×1024", "performance": "Speed", "output_format": "png", "image_number": 1, "negative": ""},
    "sampling_presets": [
        {"name": "LCM/SGM_6", "sampler": "lcm", "scheduler": "sgm_uniform", "cfg": 1.0, "steps": 6, "sharpness": 5.0, "note": "как старый DMD2, но быстрее"},
        {"name": "TCD/TCD_6", "sampler": "tcd", "scheduler": "tcd", "cfg": 1.0, "steps": 6, "sharpness": 5.0, "note": "максимум текстуры"},
        {"name": "SEEDS/Beta_4", "sampler": "seeds_2", "scheduler": "beta", "cfg": 1.0, "steps": 4, "sharpness": 5.0, "note": "самая чистая"},
    ],
    "lora_presets": [
        {"name": "Test1", "loras": [{"name": "TECH/TECH-dmd2_sdxl_4step_lora_fp16.safetensors", "weight": 1.0, "enabled": True},
                                    {"name": "AGE/age_slider.safetensors", "weight": -2.0, "enabled": True},
                                    {"name": "SLIDERS/W-body_weight_slider_v1.safetensors", "weight": -2.0, "enabled": True}]},
        {"name": "Shiny", "loras": [{"name": "TECH/TECH-dmd2_sdxl_4step_lora_fp16.safetensors", "weight": 1.0, "enabled": True},
                                    {"name": "STYLE/0-shiny_nai_pdxl.safetensors", "weight": 1.0, "enabled": True}]},
    ],
    "queue": 0, "busy": False, "sec_per_image": 7.4,
}


def _svg(seed, w=1024, h=1024):
    r = random.Random(seed)
    c1 = "#%02x%02x%02x" % (r.randint(120, 230), r.randint(60, 160), r.randint(20, 120))
    c2 = "#%02x%02x%02x" % (r.randint(200, 250), r.randint(190, 240), r.randint(150, 210))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
            f'<rect width="100%" height="100%" fill="url(#g)"/><circle cx="{w/2}" cy="{h*0.42}" r="{w*0.18}" fill="#f2d5b8" opacity=".9"/>'
            f'<text x="20" y="{h-24}" font-family="sans-serif" font-size="28" fill="#1d2021">заглушка · seed {seed}</text></svg>')


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if ctype == "application/json" else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/sud"):
            self.send_response(302); self.send_header("Location", "/sud/"); self.end_headers(); return
        if p == "/sud/":
            return self._send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html")
        if p.startswith("/sud/static/"):
            name = p[len("/sud/static/"):]
            path = os.path.join(HERE, name)
            if not os.path.isfile(path):
                return self._send(404, {"error": "нет"})
            ctype = {"js": "application/javascript", "css": "text/css"}.get(name.rsplit(".", 1)[-1], "application/octet-stream")
            return self._send(200, open(path, "rb").read(), ctype)
        if p == "/sud/api/state":
            return self._send(200, STATE)
        if p.startswith("/sud/api/task/"):
            t = TASKS.get(p.rsplit("/", 1)[-1])
            if not t:
                return self._send(404, {"error": "нет такой задачи"})
            el = time.time() - t["start"]
            total = 2.5 * t["n"]
            pct = min(100, int(el / total * 100))
            out = {"id": t["id"], "seed": t["seed"], "percent": pct, "title": f"Шаг {min(6, int(pct / 16) + 1)}/6 …",
                   "done": pct >= 100 or t.get("stop"), "images": [], "seconds": round(el, 1)}
            if out["done"]:
                out["images"] = [f"{t['seed'] + i}" for i in range(t["n"])]
                out["names"] = [time.strftime("%Y-%m-%d_%H-%M-%S") + f"_{(t['seed'] + i) % 10000:04d}.svg" for i in range(t["n"])]
            return self._send(200, out)
        if p.startswith("/sud/api/image/"):
            return self._send(200, _svg(int(p.rsplit("/", 1)[-1])), "image/svg+xml")
        return self._send(404, {"error": "нет"})

    def do_POST(self):
        p = self.path.split("?")[0]
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        if p == "/sud/api/generate":
            seed = int(body["seed"]) if str(body.get("seed") or "").isdigit() else random.randint(0, 10**9)
            tid = uuid.uuid4().hex
            TASKS[tid] = {"id": tid, "seed": seed, "n": int(body.get("image_number", 1)), "start": time.time()}
            print("generate:", {k: body[k] for k in ("prompt", "sampler", "scheduler", "steps", "cfg", "aspect", "loras", "camera") if k in body})
            return self._send(200, {"id": tid, "seed": seed, "eta": 7.4})
        if p.endswith("/stop"):
            t = TASKS.get(p.split("/")[-2])
            if t:
                t["stop"] = True
            return self._send(200, {"ok": True})
        if p == "/sud/api/presets/order":
            key = {"sampling": "sampling_presets", "loras": "lora_presets"}[body["kind"]]
            by = {x["name"]: x for x in STATE[key]}
            STATE[key] = [by.pop(n) for n in body["names"] if n in by] + list(by.values())
            return self._send(200, {"ok": True, "presets": STATE[key]})
        if p == "/sud/api/translate":
            return self._send(200, {"text": "[перевод-заглушка] " + body.get("text", ""), "engine": "mock", "warn": ""})
        return self._send(404, {"error": "нет"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7899
    print(f"Заглушка нового интерфейса: http://localhost:{port}/sud/")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
