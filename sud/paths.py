"""Все пути Fooocus-sud на Google Drive — в одном месте.

    MyDrive/FOOOCUS-SUD/
    ├── links.txt          каталог моделей (sud/catalog.py)
    ├── models/
    │   ├── checkpoints/   чекпоинты, которые лежат прямо на Drive (подключаются ссылками)
    │   ├── loras/         лоры, подпапки = категории
    │   └── embeddings/    эмбеддинги + превью (.jpeg/.png с тем же именем)
    ├── wildcards/         .txt
    ├── settings/          settings.json, sampling_presets.json, embeddings.json
    └── cache/             кэш venv (служебное)

Старые места (COLAB_MOUNTS/…) — запасные: модели оттуда тоже подключаются, пока ты их не перенёс;
маленькие файлы (links.txt, настройки, пресеты) один раз копируются сюда автоматически.
Только стандартная библиотека.
"""

import os
import shutil

DRIVE_ROOT = "/content/drive/MyDrive"
PROJECT = os.path.join(DRIVE_ROOT, "FOOOCUS-SUD")
LINKS_FILE = os.path.join(PROJECT, "links.txt")
MODELS = os.path.join(PROJECT, "models")
CHECKPOINTS = os.path.join(MODELS, "checkpoints")
LORAS = os.path.join(MODELS, "loras")
EMBEDDINGS = os.path.join(MODELS, "embeddings")
WILDCARDS = os.path.join(PROJECT, "wildcards")
SETTINGS_DIR = os.path.join(PROJECT, "settings")
CACHE = os.path.join(PROJECT, "cache")

# ---- старые места (до 2026-11-19) ----
LEGACY_BASE = os.path.join(DRIVE_ROOT, "COLAB_MOUNTS", "models", "loras2")
LEGACY_LINKS = os.path.join(LEGACY_BASE, "LINKS", "links.txt")
LEGACY_LORAS = LEGACY_BASE                       # в ней же лежат служебные LINKS/ и EMBEDDINGS/
LEGACY_EMBEDDINGS = os.path.join(LEGACY_BASE, "EMBEDDINGS")
LEGACY_SKIP_DIRS = {"LINKS", "EMBEDDINGS"}
LEGACY_SETTINGS_DIR = os.path.join(DRIVE_ROOT, "COLAB_MOUNTS", "fooocus-sud")
LEGACY_CACHE = os.path.join(DRIVE_ROOT, "COLAB_MOUNTS", "cache")

README = """Fooocus-sud — файлы на Google Drive
====================================

links.txt          каталог моделей: ссылки HF, категории [CHECKPOINTS: Реализм],
                   «*» в начале строки = качать при старте сессии, комментарий после « #» = заметка
models/checkpoints чекпоинты прямо на Drive (необязательно — обычно они качаются с HF по links.txt)
models/loras       лоры; подпапки = категории
models/embeddings  эмбеддинги (SDXL!) + превью-картинки с тем же именем (.jpeg/.png/.webp)
wildcards          вайлдкарды .txt (в промпте: __имя__)
settings           настройки интерфейса, пресеты сэмплинга, избранные эмбеддинги — правятся из интерфейса
cache              служебное (кэш окружения Python)

Старые папки COLAB_MOUNTS/... пока тоже подключаются; их можно перенести сюда в веб-Drive
(перетаскивание внутри Drive мгновенное) и потом удалить.
"""


def is_legacy(target):
    """Ссылка ведёт в старые папки COLAB_MOUNTS/… (их больше не подключаем)."""
    t = os.path.normpath(target)
    return t.startswith(os.path.normpath(os.path.join(DRIVE_ROOT, "COLAB_MOUNTS")) + os.sep)


def drive_mounted():
    return os.path.isdir(DRIVE_ROOT)


def _migrate(new, old):
    """Один раз скопировать маленький файл со старого места на новое."""
    if not os.path.exists(new) and os.path.isfile(old):
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.copy2(old, new)
        return True
    return False


def ensure_layout(log=print):
    """Создать папки проекта, README и перенести маленькие файлы со старых мест. Без Drive — ничего."""
    if not drive_mounted():
        return False
    for d in (CHECKPOINTS, LORAS, EMBEDDINGS, WILDCARDS, SETTINGS_DIR, CACHE):
        os.makedirs(d, exist_ok=True)
    readme = os.path.join(PROJECT, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(README)
    moved = []
    if _migrate(LINKS_FILE, LEGACY_LINKS):
        moved.append("links.txt")
    for name in ("settings.json", "sampling_presets.json"):
        if _migrate(os.path.join(SETTINGS_DIR, name), os.path.join(LEGACY_SETTINGS_DIR, name)):
            moved.append(name)
    if moved:
        log(f"📦 Скопировано в {PROJECT}: {', '.join(moved)} (старые файлы не тронуты)")
    return True


def links_file():
    if drive_mounted():
        _migrate(LINKS_FILE, LEGACY_LINKS)
    return LINKS_FILE


def settings_file(name):
    """Файл в settings/ (с переносом со старого места при первом обращении)."""
    path = os.path.join(SETTINGS_DIR, name)
    if drive_mounted():
        _migrate(path, os.path.join(LEGACY_SETTINGS_DIR, name))
    return path


def sources(kind):
    """Папки на Drive, откуда подключаются модели: [(папка, пропустить_подпапки, главная?)]."""
    # старые папки COLAB_MOUNTS/… больше не подключаются (решение 2026-11-19: разбираю постепенно,
    # в Fooocus видно только то, что уже перенесено в FOOOCUS-SUD)
    if kind == "loras":
        return [(LORAS, set(), True)]
    if kind == "embeddings":
        return [(EMBEDDINGS, set(), True)]
    if kind == "checkpoints":
        return [(CHECKPOINTS, set(), True)]
    if kind == "wildcards":
        return [(WILDCARDS, set(), True)]
    return []
