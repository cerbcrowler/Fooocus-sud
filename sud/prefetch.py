"""Фоновая предзагрузка вспомогательных моделей Fooocus (inpaint, IP-Adapter, SAM…).

Fooocus качает их сам при первом включении опции — посреди работы. Здесь то же самое
качается заранее, в фоне при старте, ровно в те папки и под теми именами, где Fooocus их ищет.
Какие группы качать — галочки во вкладке «⚙️ Настройки» (ключ sud_prefetch_groups).

Только стандартная библиотека. Запуск:
    python -m sud.prefetch run                    # группы из настроек
    python -m sud.prefetch run --groups a,b       # явно
    python -m sud.prefetch status
"""

import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = os.path.join(FOOOCUS_DIR, "models")
TORCH_HUB = os.path.join(os.path.expanduser("~"), ".cache", "torch", "hub", "checkpoints")
LOG = "/content/prefetch.log"
PID_FILE = "/content/prefetch.pid"

HF = "https://huggingface.co"
MISC = f"{HF}/lllyasviel/misc/resolve/main"
MASH = f"{HF}/mashb1t/misc/resolve/main"
INPAINT = f"{HF}/lllyasviel/fooocus_inpaint/resolve/main"

# id: (название, [(url, папка, имя файла, ~МБ)])
GROUPS = {
    "inpaint": ("Inpaint / Outpaint (v2.6)", [
        (f"{INPAINT}/fooocus_inpaint_head.pth", f"{M}/inpaint", "fooocus_inpaint_head.pth", 1),
        (f"{INPAINT}/inpaint_v26.fooocus.patch", f"{M}/inpaint", "inpaint_v26.fooocus.patch", 1262),
    ]),
    "image_prompt": ("Image Prompt и FaceSwap (IP-Adapter)", [
        (f"{MISC}/clip_vision_vit_h.safetensors", f"{M}/clip_vision", "clip_vision_vit_h.safetensors", 1880),
        (f"{MISC}/fooocus_ip_negative.safetensors", f"{M}/controlnet", "fooocus_ip_negative.safetensors", 1),
        (f"{MISC}/ip-adapter-plus_sdxl_vit-h.bin", f"{M}/controlnet", "ip-adapter-plus_sdxl_vit-h.bin", 966),
        (f"{MISC}/ip-adapter-plus-face_sdxl_vit-h.bin", f"{M}/controlnet", "ip-adapter-plus-face_sdxl_vit-h.bin", 966),
    ]),
    "control": ("Canny и CPDS", [
        (f"{MISC}/control-lora-canny-rank128.safetensors", f"{M}/controlnet", "control-lora-canny-rank128.safetensors", 377),
        (f"{MISC}/fooocus_xl_cpds_128.safetensors", f"{M}/controlnet", "fooocus_xl_cpds_128.safetensors", 377),
    ]),
    "describe": ("Describe (BLIP и теги для аниме)", [
        (f"{MISC}/model_base_caption_capfilt_large.pth", f"{M}/clip_vision", "model_base_caption_capfilt_large.pth", 854),
        ("https://dl.fbaipublicfiles.com/deit/deit_base_patch16_224-b5f2ef4d.pth", TORCH_HUB,
         "deit_base_patch16_224-b5f2ef4d.pth", 330),
        (f"{MISC}/wd-v1-4-moat-tagger-v2.onnx", f"{M}/clip_vision", "wd-v1-4-moat-tagger-v2.onnx", 310),
        (f"{MISC}/wd-v1-4-moat-tagger-v2.csv", f"{M}/clip_vision", "wd-v1-4-moat-tagger-v2.csv", 1),
    ]),
    "enhance": ("Enhance-маски (SAM base + GroundingDINO)", [
        (f"{MASH}/sam_vit_b_01ec64.pth", f"{M}/sam", "sam_vit_b_01ec64.pth", 357),
        ("https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth",
         f"{M}/inpaint", "groundingdino_swint_ogc.pth", 661),
    ]),
    "speed_loras": ("Ускоряющие LoRA (Extreme Speed, Lightning, Hyper-SD)", [
        (f"{MISC}/sdxl_lcm_lora.safetensors", f"{M}/loras", "sdxl_lcm_lora.safetensors", 375),
        (f"{MASH}/sdxl_lightning_4step_lora.safetensors", f"{M}/loras", "sdxl_lightning_4step_lora.safetensors", 375),
        (f"{MASH}/sdxl_hyper_sd_4step_lora.safetensors", f"{M}/loras", "sdxl_hyper_sd_4step_lora.safetensors", 750),
    ]),
    "upscale": ("Upscale / Variation", [
        (f"{MISC}/fooocus_upscaler_s409985e5.bin", f"{M}/upscale_models", "fooocus_upscaler_s409985e5.bin", 32),
    ]),
    "inpaint_old": ("Inpaint v1 и v2.5 (старые движки)", [
        (f"{INPAINT}/inpaint.fooocus.patch", f"{M}/inpaint", "inpaint.fooocus.patch", 1256),
        (f"{INPAINT}/inpaint_v25.fooocus.patch", f"{M}/inpaint", "inpaint_v25.fooocus.patch", 2461),
    ]),
    "sam_big": ("SAM large и huge (точнее маски, тяжёлые)", [
        (f"{MASH}/sam_vit_l_0b3195.pth", f"{M}/sam", "sam_vit_l_0b3195.pth", 1191),
        (f"{MASH}/sam_vit_h_4b8939.pth", f"{M}/sam", "sam_vit_h_4b8939.pth", 2445),
    ]),
    "safety": ("Проверка NSFW (safety checker)", [
        (f"{MASH}/stable-diffusion-safety-checker.bin", f"{M}/safety_checker", "stable-diffusion-safety-checker.bin", 1159),
    ]),
}
DEFAULT_GROUPS = ["inpaint", "image_prompt", "control", "describe", "enhance", "speed_loras", "upscale"]
SETTINGS_KEY = "sud_prefetch_groups"

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def group_size_mb(gid):
    return sum(f[3] for f in GROUPS[gid][1])


def group_label(gid):
    mb = group_size_mb(gid)
    size = f"{mb / 1024:.1f} ГБ" if mb >= 1024 else f"{mb} МБ"
    return f"{GROUPS[gid][0]} — {size}"


def group_status(gid):
    """'done' | 'partial' | 'none'"""
    have = [os.path.exists(os.path.join(d, n)) for _, d, n, _ in GROUPS[gid][1]]
    return "done" if all(have) else "partial" if any(have) else "none"


def selected_groups():
    from sud import settings
    groups = settings.effective().get(SETTINGS_KEY)
    return DEFAULT_GROUPS if groups is None else [g for g in groups if g in GROUPS]


def _download(url, folder, name):
    final = os.path.join(folder, name)
    if os.path.exists(final):
        return "skip"
    os.makedirs(folder, exist_ok=True)
    tmp = f"{final}.part{os.getpid()}"  # Fooocus смотрит только на готовое имя
    t = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "fooocus-sud-prefetch"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(8 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if os.path.exists(final):  # Fooocus успел скачать сам
            os.remove(tmp)
            return "skip"
        os.replace(tmp, final)
        mb = os.path.getsize(final) / 1048576
        log(f"✅ {name} ({mb:.0f} МБ за {time.time() - t:.0f} с)")
        return "ok"
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        log(f"❌ {name}: {e}")
        return "fail"


def _already_running():
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid != os.getpid()
    except Exception:
        return False


def run(groups=None, workers=3):
    if _already_running():
        log("ℹ️ Предзагрузка уже идёт, второй раз не запускаю")
        return
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    groups = selected_groups() if groups is None else groups
    jobs = [(u, d, n) for g in groups for (u, d, n, _) in GROUPS[g][1]]
    todo = [j for j in jobs if not os.path.exists(os.path.join(j[1], j[2]))]
    log(f"⏳ Предзагрузка: групп {len(groups)}, файлов к загрузке {len(todo)} из {len(jobs)}")
    t = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda j: _download(*j), todo))
    log(f"🏁 Готово за {time.time() - t:.0f} с: скачано {results.count('ok')}, "
        f"ошибок {results.count('fail')}")
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def main():
    args = sys.argv[1:]
    if not args or args[0] == "status":
        for gid in GROUPS:
            mark = {"done": "✅", "partial": "◐", "none": "·"}[group_status(gid)]
            sel = "*" if gid in selected_groups() else " "
            print(f"{mark} {sel} {gid:13} {group_label(gid)}")
        return
    if args[0] == "run":
        groups = None
        if "--groups" in args:
            raw = args[args.index("--groups") + 1]
            groups = [g for g in raw.split(",") if g in GROUPS]
        run(groups)


if __name__ == "__main__":
    main()
