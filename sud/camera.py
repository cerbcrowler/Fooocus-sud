"""Камера: ракурс, высота и план как добавки к промпту (идея — lllyasviel/Fooocus PR #1797).

Состояние приходит из карточки «Камера» (javascript/sud-camera.js) JSON-ом:
    {"enabled": true, "angle": "front|q_left|left|bq_left|back|bq_right|right|q_right|",
     "height": "...", "shot": "...", "weight": 1.2}
build() → строка для конца промпта, например «(three-quarter view, facing left:1.2), (close-up:1.2)».
Только стандартная библиотека.
"""

import json

# ракурс вокруг человека (лево/право — со стороны зрителя)
ANGLES = {
    "front": "front view, facing the viewer",
    "q_left": "three-quarter view, facing left",
    "left": "side view, profile, facing left",
    "bq_left": "three-quarter back view, from behind, looking left",
    "back": "back view, from behind",
    "bq_right": "three-quarter back view, from behind, looking right",
    "right": "side view, profile, facing right",
    "q_right": "three-quarter view, facing right",
}
# высота камеры (из PR: angles.json)
HEIGHTS = {
    "top": "top down view, bird's eye view",
    "high": "high angle",
    "above": "slightly above",
    "eye": "straight on, eye level",
    "low": "low angle, hero view",
    "worm": "worm's eye view",
    "selfie": "selfie",
}
# план / дистанция (из PR: distances.json)
SHOTS = {
    "ecu": "extreme close-up",
    "cu": "close-up",
    "mcu": "medium close-up",
    "ms": "medium shot",
    "cowboy": "cowboy shot",
    "full": "full body, full shot",
    "long": "long shot",
    "establishing": "establishing shot",
    "pov": "point-of-view",
}


def parse(value):
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}


def build(value):
    st = parse(value)
    if not st.get("enabled", True):
        return ""
    try:
        w = max(0.1, min(3.0, float(st.get("weight", 1.2))))
    except (TypeError, ValueError):
        w = 1.2
    parts = [table.get(st.get(key) or "") for key, table in (("angle", ANGLES), ("height", HEIGHTS), ("shot", SHOTS))]
    return ", ".join(f"({p}:{w:g})" for p in parts if p)
