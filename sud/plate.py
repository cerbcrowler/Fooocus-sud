"""🏷 Плашка с параметрами генерации внизу картинки (для тестов и сравнений).

Включается в ⚙️ Настройках (sud_info_plate). Рисуется только на сохраняемой копии — дальше по цепочке
(Enhance, Upscale) идёт чистая картинка. Шрифт Roboto (sud/fonts, Apache-2.0).
"""

import os

import numpy as np

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
TEXT = (235, 219, 178)      # gruvbox fg
ACCENT = (250, 189, 47)     # gruvbox yellow
DIM = (189, 174, 147)


def enabled():
    try:
        from sud import settings
        return bool(settings.effective().get("sud_info_plate", False))
    except Exception:
        return False


def _font(size, bold=False):
    from PIL import ImageFont
    name = "Roboto-Medium.ttf" if bold else "Roboto-Regular.ttf"
    try:
        return ImageFont.truetype(os.path.join(FONTS, name), size)
    except OSError:
        return ImageFont.load_default()


def _short(name):
    base = os.path.basename(str(name))
    for ext in (".safetensors", ".ckpt", ".pt", ".bin"):
        if base.lower().endswith(ext):
            base = base[: -len(ext)]
    return base


CLEAN = {}   # путь сохранённой картинки (с плашкой) → путь чистой копии (для апскейла/вариаций в /sud/)


def remember_clean(saved_path, clean_img):
    """Сохранить чистую (без плашки) копию рядом во временной папке и запомнить соответствие."""
    import tempfile
    import uuid
    from PIL import Image
    if not isinstance(saved_path, str):
        return
    path = os.path.join(tempfile.gettempdir(), f"sud_clean_{uuid.uuid4().hex}.png")
    Image.fromarray(np.asarray(clean_img)).save(path)
    CLEAN[saved_path] = path
    while len(CLEAN) > 300:
        old = CLEAN.pop(next(iter(CLEAN)))
        try:
            os.remove(old)
        except OSError:
            pass


def lines_for(sampler, scheduler, steps, cfg, seed, model, loras, width, height, seconds=None, extra=None):
    l1 = f"{sampler} · {scheduler} · {steps} шагов · CFG {cfg:g} · seed {seed}"
    l2 = f"{_short(model)} · {width}×{height}" + (f" · {seconds:.1f} с" if seconds else "")
    lr = [f"{_short(n)} ×{w:g}" for n, w in (loras or []) if n and n != "None"]
    out = [l1, l2]
    if lr:
        out.append("LoRA: " + ", ".join(lr))
    if extra:
        out += [e for e in extra if e]
    return out


def draw(img, lines):
    """img: HxWx3 uint8 → новая картинка с полупрозрачной плашкой внизу."""
    from PIL import Image, ImageDraw
    im = Image.fromarray(np.asarray(img)).convert("RGBA")
    W, H = im.size
    size = max(13, round(W / 62))
    pad, gap = round(size * 0.8), round(size * 0.35)
    fonts = [_font(round(size * 1.05), bold=True)] + [_font(size)] * (len(lines) - 1)
    draw0 = ImageDraw.Draw(im)

    # длинные строки переносим по словам
    wrapped = []
    for i, (text, f) in enumerate(zip(lines, fonts)):
        words, cur = text.split(" "), ""
        for w in words:
            test = (cur + " " + w).strip()
            if draw0.textlength(test, font=f) > W - 2 * pad and cur:
                wrapped.append((cur, f, i))
                cur = w
            else:
                cur = test
        wrapped.append((cur, f, i))

    heights = [f.getbbox("Ag")[3] for _, f, _ in wrapped]
    band = pad * 2 + sum(heights) + gap * (len(wrapped) - 1)
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, H - band, W, H], fill=(29, 32, 33, 175))
    d.rectangle([0, H - band, W, H - band + max(2, size // 8)], fill=ACCENT + (200,))
    y = H - band + pad
    for (text, f, i), h in zip(wrapped, heights):
        d.text((pad, y), text, font=f, fill=(ACCENT if i == 0 else (TEXT if i == 1 else DIM)) + (255,))
        y += h + gap
    return np.array(Image.alpha_composite(im, overlay).convert("RGB"))
