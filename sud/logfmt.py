"""Короткий и понятный лог Fooocus для ячейки Colab.

Полный «сырой» лог остаётся в /content/fooocus.log, а в ячейку идёт выжимка:
по строке на событие (GPU, модель, LoRA, загрузки, генерации), без прогресс-баров,
повторов и служебного шума. Ошибки и traceback показываются целиком.

    fmt = LogFormatter(public_url)
    for text in fmt.feed(raw_chunk):   # куски любого размера, строки через \\n или \\r
        print(text, end="")
"""

import os
import re
import time

STEP_RE = re.compile(r"^\s*(\d+)%\|.*?\|\s*(\S+)/(\S+)\s*\[([^\]]*)\]")
NOISE = (
    "[System ARGV]", "Python 3.", "Fooocus version", "[Cleanup]", "Set vram state", "Always offload VRAM",
    "VAE dtype", "Using pytorch", "Refiner unloaded", "To create a public link", "model_type ",
    "UNet ADM", "Working with z", "extra {", "left over keys", "loaded straight to GPU", "Requested to load",
    "Loading 1 new model", "Loading 2 new models", "[Fooocus Model Management]", "VAE loaded",
    "Fooocus V2 Expansion", "Fooocus Expansion engine", "Started worker", "Running on local URL",
    "UserWarning: TypedStorage", "return self.fget", "unload clone", "[Fooocus] Loading control models",
    "[Fooocus] Initializing", "[Fooocus] Loading models", "[Fooocus] Processing prompts",
    "[Fooocus] Encoding", "Using karras", "Using ", "[Sampler]", "[Cache]", "[Fooocus] Saving image",
    "Request to load LoRAs", "Terminated", "[Enhance] Skipping", "Processing time (total)",
    "[Parameters] Adaptive CFG", "[Parameters] CLIP Skip", "[Parameters] Sharpness", "[Parameters] ControlNet",
    "[Parameters] ADM Scale", "[Parameters] Denoising", "Downloading model", "Total VRAM",
)
ERROR_HINTS = ("Traceback", "Error", "Exception", "CUDA out of memory", "Killed", "FAILED", "failed")

GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _stem(path):
    name = path.replace("\\", "/")
    for root in ("/models/loras/", "/loras2/", "/models/checkpoints/"):
        if root in name:
            name = name.split(root, 1)[1]
            break
    else:
        name = os.path.basename(name)
    return re.sub(r"\.(safetensors|ckpt|pt|pth|bin)$", "", name)


def _gb(mb):
    return f"{int(mb) / 1024:.0f} ГБ"


class LogFormatter:
    def __init__(self, public_url=None):
        self.url = public_url
        self.buf = ""
        self.t0 = time.time()
        self.ram = self.vram = None
        self.download = None
        self.task = {}
        self.task_no = 0
        self.loras = []
        self.in_traceback = False
        self.progress_shown = False
        self.started_once = False

    # ---------- приём ----------
    def feed(self, chunk):
        """Вернуть список готовых строк (с \\n в конце; прогресс — с \\r без \\n)."""
        self.buf += chunk
        out = []
        while True:
            m = re.search(r"[\r\n]", self.buf)
            if not m:
                break
            line, self.buf = self.buf[:m.start()], self.buf[m.end():]
            res = self.line(line)
            if res:
                out.append(res)
        return out

    def restarted(self):
        self.__init__(self.url)
        return f"\n{DIM}🔁 Fooocus перезапущен — слежу за новым процессом{RESET}\n"

    # ---------- разбор строки ----------
    def _end_progress(self):
        if self.progress_shown:
            self.progress_shown = False
            return "\r" + " " * 60 + "\r"
        return ""

    def line(self, raw):
        s = raw.rstrip()
        if not s.strip():
            return None

        # traceback — целиком, красным
        if self.in_traceback:
            if not s.startswith((" ", "\t")) and not s.startswith("Traceback"):
                self.in_traceback = False
            return f"{RED}{s}{RESET}\n"
        if s.startswith("Traceback"):
            self.in_traceback = True
            return self._end_progress() + f"{RED}{s}{RESET}\n"

        # прогресс-бары (tqdm): живая строка во время рендера, загрузки — молча
        m = STEP_RE.match(s)
        if m:
            pct, done, total, tail = m.groups()
            if self.download:
                if pct == "100":
                    name, self.download = self.download, None
                    return f"⬇️  {name} · {total}Б\n".replace("kБ", " КБ").replace("MБ", " МБ").replace("GБ", " ГБ")
                return None
            speed = re.search(r"([\d.]+\s*(?:it/s|s/it))", tail)
            self.task["speed"] = speed.group(1) if speed else ""
            mmss = re.match(r"(?:(\d+):)?(\d+):(\d+)", tail.split("<")[0].strip())
            if mmss:
                h, mi, se = (int(x or 0) for x in mmss.groups())
                self.task["render"] = f"{h * 3600 + mi * 60 + se} с"
            self.progress_shown = True
            return f"\r   ⏳ шаг {done}/{total}"

        if s.startswith("[sud.settings]"):
            m = re.search(r"модель (.+?), своих настроек: (\d+)", s)
            if m:
                return f"⚙️  Настройки: {m.group(2)} своих · модель {_stem(m.group(1))}\n"
        if s.startswith("Total VRAM"):
            m = re.search(r"Total VRAM (\d+) MB, total RAM (\d+) MB", s)
            if m:
                self.vram, self.ram = m.groups()
            return None
        if s.startswith("Device:"):
            if self.started_once:
                return None
            m = re.match(r"Device:\s*\S+\s+(.*?)(?:\s*:\s*\w+)?\s*$", s)   # "Device: cuda:0 NVIDIA L4 : native"
            gpu = m.group(1) if m else s
            extra = f" · VRAM {_gb(self.vram)} · RAM {_gb(self.ram)}" if self.vram else ""
            return f"🖥  {gpu}{extra}\n"
        if s.startswith("Downloading:"):
            m = re.search(r'Downloading: "([^"]+)"', s)
            self.download = os.path.basename(m.group(1)) if m else "файл"
            return None
        if s.startswith("Base model loaded:"):
            return f"🧱 Модель: {_stem(s.split(':', 1)[1].strip())}\n"
        if s.startswith("Lora file not found:"):
            return f"{YELLOW}⚠️  LoRA не найдена: {_stem(s.split(':', 1)[1].strip())}{RESET}\n"
        if s.startswith("Loaded LoRA ["):
            m = re.match(r"Loaded LoRA \[(.+?)\].*?at weight (-?\d+(?:\.\d+)?)", s)
            if m:
                self.loras.append(f"{_stem(m.group(1))} ×{float(m.group(2)):g}")
            return None
        if s.startswith("App started successful"):
            if self.started_once:
                return None
            self.started_once = True
            url = f" → {self.url}" if self.url else ""
            return f"{GREEN}🚀 Готово за {time.time() - self.t0:.0f} с{url}{RESET}\n"

        # параметры генерации — собираем, печатаем одной строкой на старте задачи
        if s.startswith("[Parameters] Seed ="):
            self.task = {"seed": s.split("=", 1)[1].strip()}
            self.loras = []
            return None
        if s.startswith("[Parameters] CFG ="):
            self.task["cfg"] = s.split("=", 1)[1].strip()
            return None
        if s.startswith("[Parameters] Sampler ="):
            self.task["sampler"] = s.split("=", 1)[1].strip().replace(" - ", "/")
            return None
        if s.startswith("[Parameters] Steps ="):
            self.task["steps"] = s.split("=", 1)[1].split("-")[0].strip()
            return None
        if s.startswith("[Parameters] Initial Latent shape"):
            m = re.search(r"\((\d+),\s*(\d+)\)", s)
            if m:
                self.task["size"] = f"{m.group(1)}×{m.group(2)}"
            return None
        if s.startswith("Preparation time:"):
            self.task["prep"] = float(re.findall(r"[\d.]+", s)[0])
            return None
        if s.startswith("[Fooocus] Preparing task"):
            m = re.search(r"(\d+)/(\d+)", s)
            self.task_no += 1
            t = self.task
            head = " · ".join(x for x in (
                f"🎨 #{self.task_no}" + (f" ({m.group(1)}/{m.group(2)})" if m and m.group(2) != "1" else ""),
                t.get("size"), t.get("sampler"),
                f"{t['steps']} шагов" if t.get("steps") else None,
                f"CFG {t['cfg']}" if t.get("cfg") else None,
                f"seed {t['seed']}" if t.get("seed") else None) if x)
            lora = f"\n   {DIM}LoRA: {', '.join(self.loras)}{RESET}" if self.loras else ""
            return f"{head}{lora}\n"
        if s.startswith("Generating and saving time:"):
            self.task["gen"] = float(re.findall(r"[\d.]+", s)[0])
            return None
        if s.startswith("Total time:"):
            total = float(re.findall(r"[\d.]+", s)[0])
            t = self.task
            details = []
            if t.get("prep", 0) >= 1:
                details.append(f"подготовка {t['prep']:.1f} с")
            if t.get("render"):
                details.append(f"рендер {t['render']}")
            if t.get("speed"):
                details.append(t["speed"])
            tail = f"  {DIM}({' · '.join(details)}){RESET}" if details else ""
            return self._end_progress() + f"   {GREEN}✓ {total:.1f} с{RESET}{tail}\n"
        if s.startswith("[Enhance]") and "Skipping" not in s:
            return f"   ✨ {s[len('[Enhance]'):].strip()}\n"

        if s.startswith(NOISE):
            return None
        if any(h in s for h in ERROR_HINTS):
            return self._end_progress() + f"{RED}❌ {s}{RESET}\n"
        return None
