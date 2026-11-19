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

Жми ▶ у ячейки «🚀 Запуск» — и можно отходить: доступ к Drive спрашивается в самом начале.
Остановить — ⏹ у ячейки (Fooocus остановится). Картинки сохраняются только в `/content` и пропадают вместе с сессией.
"""

cell1 = r'''# @title 🚀 Запуск Fooocus-sud
BRANCH     = "main"  # @param {type:"string"}
VPS_HOST   = "128.140.12.50"  # @param {type:"string"}
VPS_USER   = "root"  # @param {type:"string"}
VPS_BIND   = "172.18.0.1:8080"  # @param {type:"string"}
PUBLIC_URL = "https://colab.period.pp.ua"  # @param {type:"string"}

import os, subprocess, sys, importlib

# 1. Google Drive — первым делом: окно доступа всплывает сразу, дальше всё идёт без вопросов
from google.colab import drive
if not os.path.ismount("/content/drive"):
    drive.mount("/content/drive")

REPO, FOOOCUS_DIR, PORT = "https://github.com/cerbcrowler/Fooocus-sud.git", "/content/Fooocus", 7865

def sh(cmd):
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if (r.stdout + r.stderr).strip():
        print((r.stdout + r.stderr).strip())
    if r.returncode:
        raise RuntimeError(f"Команда упала ({r.returncode}): {cmd}")

# 2. GPU
if subprocess.run("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", shell=True).returncode:
    print("❌ GPU нет! Среда выполнения → Сменить тип → GPU")

# 3. свежий код форка (вся логика — в sud/colab.py, ячейка не устаревает)
if os.path.isdir(f"{FOOOCUS_DIR}/.git"):
    sh(f"git -C {FOOOCUS_DIR} fetch -q origin {BRANCH} && git -C {FOOOCUS_DIR} checkout -q -B {BRANCH} origin/{BRANCH} && git -C {FOOOCUS_DIR} reset -q --hard origin/{BRANCH}")
else:
    sh(f"git clone -q -b {BRANCH} {REPO} {FOOOCUS_DIR}")
sh(f"git -C {FOOOCUS_DIR} log --oneline -1")
if FOOOCUS_DIR not in sys.path:
    sys.path.insert(0, FOOOCUS_DIR)
import sud.colab as sc
importlib.reload(sc)

# 4. модели → туннель → Fooocus (ячейка дальше крутится и показывает лог)
sc.run_all(VPS_HOST, VPS_USER, VPS_BIND, PORT, public_url=PUBLIC_URL)
'''


def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {"cellView": "form"},
            "outputs": [], "source": src.splitlines(keepends=True)}


nb = {
    "cells": [
        {"cell_type": "markdown", "metadata": {}, "source": md_intro.splitlines(keepends=True)},
        code(cell1),
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
