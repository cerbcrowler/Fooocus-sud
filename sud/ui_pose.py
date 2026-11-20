"""Редактор позы 🦴 (OpenPose, этап 2): распознать позу на фото и нарисовать скелет для Image Prompt.

Интерфейс — javascript/sud-pose.js (полноэкранный редактор). Связь — скрытые поле+кнопка:
  {"op": "detect", "image": "data:image/...;base64,..."}       → позы (доли 0..1 от размеров фото)
  {"op": "render", "poses": [...], "w": 1024, "h": 1024,
   "hands": true, "face": true}                                 → PNG скелета (data URI)
Позы: [{"body": [[x, y] | null × 18], "left_hand": [...] | null, "right_hand": ..., "face": ...}].
"""

import base64
import io
import json

import gradio as gr
import numpy as np


def _decode(uri):
    from PIL import Image
    raw = base64.b64decode(uri.split(",", 1)[1] if "," in uri else uri)
    return np.array(Image.open(io.BytesIO(raw)).convert("RGB"))


def _encode(arr):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _clean(part):
    if not part:
        return None
    out = [None if p is None else (float(p[0]), float(p[1])) for p in part]
    return None if all(p is None for p in out) else out


def apply(payload):
    try:
        cmd = json.loads(payload or "{}")
    except ValueError:
        cmd = {}
    op, res = cmd.get("op"), {"op": cmd.get("op"), "nonce": cmd.get("nonce")}
    try:
        if op == "detect":
            import modules.config
            from extras import dwpose
            img = _decode(cmd["image"])
            h, w = img.shape[:2]
            _, poses = dwpose.detect(img, *modules.config.downloading_dwpose())
            res.update(poses=[{k: (list(v) if v else None) for k, v in p.items()} for p in poses], w=w, h=h)
            if not poses:
                res["error"] = "На фото не нашлось людей"
        elif op == "render":
            from extras import dwpose
            w, h = int(cmd.get("w", 1024)), int(cmd.get("h", 1024))
            poses = [{"body": _clean(p.get("body")) or [None] * 18, "left_hand": _clean(p.get("left_hand")),
                      "right_hand": _clean(p.get("right_hand")), "face": _clean(p.get("face"))}
                     for p in cmd.get("poses", [])]
            res["png"] = _encode(dwpose.draw(poses, w, h, hands=bool(cmd.get("hands", True)),
                                             face=bool(cmd.get("face", True))))
        else:
            res["error"] = f"Неизвестная команда {op}"
    except Exception as e:
        res["error"] = f"Ошибка: {e}"
        print(f"[Pose editor] {e}")
    return json.dumps(res, ensure_ascii=False)


def wire():
    with gr.Column(elem_classes=["sud-hidden-btn"]):
        op = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-pose-op"])
        out = gr.Textbox(value="", show_label=False, container=False, elem_classes=["sud-pose-state"])
        btn = gr.Button("apply", elem_classes=["sud-pose-op-btn"])
    btn.click(apply, [op], [out], queue=False, show_progress=False)
