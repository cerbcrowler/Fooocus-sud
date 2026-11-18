import json, sys

out = sys.argv[1]

md_intro = """# Fooocus-sud в Colab

Движок (Fooocus + GPU) работает здесь, интерфейс открываешь в браузере ноута: **https://colab.period.pp.ua**
(обратный SSH-туннель Colab → VPS → Traefik).

**Секреты Colab** (значок 🔑 слева, включи «доступ из блокнота»):

| Имя | Что |
|---|---|
| `HF_TOKEN` | токен HuggingFace (для приватных моделей; без него качаются только публичные) |
| `VPS_SSH_KEY` | приватный ключ туннеля: весь текст файла `~/.ssh/colab_vps` с ноута |
| `FOOOCUS_USER` / `FOOOCUS_PASS` | *(необязательно)* второй пароль уже в самом Fooocus; Traefik и так спрашивает свой |

Запускай ячейки по порядку 1 → 4. Картинки сохраняются только в `/content` и пропадают вместе с сессией.
"""

cell1 = r'''# @title 1️⃣ Настройки + GPU + клон форка
BRANCH     = "main"  # @param {type:"string"}
DRIVE_BASE = "/content/drive/MyDrive/COLAB_MOUNTS/models/loras2"  # @param {type:"string"}
VPS_HOST   = "128.140.12.50"  # @param {type:"string"}
VPS_USER   = "root"  # @param {type:"string"}
VPS_BIND   = "172.18.0.1:8080"  # @param {type:"string"}
PUBLIC_URL = "https://colab.period.pp.ua"  # @param {type:"string"}

import os, subprocess

REPO        = "https://github.com/cerbcrowler/Fooocus-sud.git"
FOOOCUS_DIR = "/content/Fooocus"
PORT        = 7865

def sh(cmd, check=True):
    """Выполнить команду и показать вывод."""
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (r.stdout + r.stderr).strip()
    if out:
        print(out)
    if check and r.returncode != 0:
        raise RuntimeError(f"Команда упала ({r.returncode}): {cmd}")
    return r

print("=== GPU ===")
if sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", check=False).returncode != 0:
    print("❌ GPU нет! Среда выполнения → Сменить тип → GPU")

print(f"\n=== ФОРК: {REPO} ({BRANCH}) ===")
if os.path.isdir(f"{FOOOCUS_DIR}/.git"):
    sh(f"git -C {FOOOCUS_DIR} fetch origin {BRANCH}")
    sh(f"git -C {FOOOCUS_DIR} checkout -B {BRANCH} origin/{BRANCH}")
    sh(f"git -C {FOOOCUS_DIR} reset --hard origin/{BRANCH}")
else:
    sh(f"git clone -b {BRANCH} {REPO} {FOOOCUS_DIR}")
sh(f"git -C {FOOOCUS_DIR} log --oneline -1")

# вся логика ячеек 2–4 живёт в форке (sud/colab.py) и обновляется вместе с git pull
import sys, importlib
if FOOOCUS_DIR not in sys.path:
    sys.path.insert(0, FOOOCUS_DIR)
import sud.colab as sc
importlib.reload(sc)
print("✅ Код на месте")
'''

cell2 = r'''# @title 2️⃣ Google Drive + модели (links.txt)
sc.models(DRIVE_BASE)
'''

cell3 = r'''# @title 3️⃣ Пароль + туннель на VPS
sc.tunnel(VPS_HOST, VPS_USER, VPS_BIND, PORT)
'''

cell4 = r'''# @title 4️⃣ Запуск Fooocus
print(f"🌐 Интерфейс: {PUBLIC_URL}  (появится, когда ниже напишет 'App started')")
sc.launch(PORT)
'''


def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {"cellView": "form"},
            "outputs": [], "source": src.splitlines(keepends=True)}


nb = {
    "cells": [
        {"cell_type": "markdown", "metadata": {}, "source": md_intro.splitlines(keepends=True)},
        code(cell1), code(cell2), code(cell3), code(cell4),
    ],
    "metadata": {
        "accelerator": "GPU",
        "colab": {"gpuType": "L4", "provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
    f.write("\n")
print("ok", out)
