"""Синхронизация моделей для Fooocus-sud.

Источник правды — links.txt на Google Drive:

    [CHECKPOINTS]
    https://huggingface.co/user/repo/resolve/main/file.safetensors | новое_имя   # комментарий
    # закомментированная строка
    [LORAS]
    ...
    [WILDCARDS]
    ...
    [EMBEDDING ZIP]
    ...

Что делает sync():
  1. лоры и эмбеддинги с Drive подключает симлинками (без копирования);
  2. всё из links.txt качает с HuggingFace в локальные папки Fooocus;
  3. выбирает default_model (первый чекпоинт из списка) и пишет config.txt.

Модуль не зависит от Colab: тот же код потом будет вызывать вкладка «Модели» в GUI.
Запуск из консоли:  HF_TOKEN=... python -m sud.models sync --drive-base /content/drive/...
"""

import argparse
import json
import os
import re
import shutil
import zipfile
from urllib.parse import unquote

KNOWN_SECTIONS = {"CHECKPOINTS", "LORAS", "EMBEDDINGS", "WILDCARDS", "EMBEDDING ZIP"}
LORA_EXTS = (".safetensors", ".ckpt", ".pt")
EMBED_EXTS = (".safetensors", ".pt", ".bin")
SKIP_DIRS = {"LINKS", "EMBEDDINGS"}  # служебные папки на Drive, это не лоры
FALLBACK_MODEL = "juggernautXL_v8Rundiffusion.safetensors"


def log(msg=""):
    print(msg, flush=True)


# ---------- пути ----------

class Paths:
    """Локальные папки Fooocus + каталог на Drive (пути Drive — в sud/paths.py)."""

    def __init__(self, fooocus_dir, drive_base=None):
        from sud import paths
        self.fooocus = fooocus_dir
        self.links_file = paths.links_file()
        self.checkpoints = os.path.join(fooocus_dir, "models", "checkpoints")
        self.loras = os.path.join(fooocus_dir, "models", "loras")
        self.embeddings = os.path.join(fooocus_dir, "models", "embeddings")
        self.wildcards = os.path.join(fooocus_dir, "wildcards")
        self.config_txt = os.path.join(fooocus_dir, "config.txt")


# ---------- links.txt ----------

_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")  # комментарий: '#' в начале строки или после пробела


def parse_links_file(path, autoload_only=True):
    """Возвращает {СЕКЦИЯ: [(url, новое_имя | None), ...]}.

    Формат — см. sud/catalog.py (категории «[CHECKPOINTS: Реализм]», «*» = грузить при старте).
    autoload_only=True — только то, что грузится при старте (для старого формата без «*» — всё).
    """
    from sud.catalog import Catalog
    if not os.path.isfile(path):
        log(f"❌ Файл со ссылками не найден: {path}")
        return {}
    sections = {}
    for e in Catalog(path).entries():
        sections.setdefault(e.kind, [])
        if e.autoload or not autoload_only:
            sections[e.kind].append((e.url, e.name or None))
    return sections


# ---------- симлинки с Drive ----------

def clean_broken_links(dst_dir):
    removed = 0
    if not os.path.isdir(dst_dir):
        return removed
    for root, _, files in os.walk(dst_dir):
        for name in files:
            p = os.path.join(root, name)
            if os.path.islink(p) and not os.path.exists(p):
                os.unlink(p)
                removed += 1
    return removed


def link_tree_from_drive(src_dir, dst_dir, exts, skip_dirs=None, keep_structure=True, overwrite=True, quiet_missing=False):
    """Зеркалит дерево папок с Drive, подставляя симлинки на файлы.

    overwrite=False — не перебивать уже существующие ссылки (для запасных старых папок).
    """
    if not os.path.isdir(src_dir):
        if not quiet_missing:
            log(f"❌ Папка на Drive не найдена: {src_dir}")
        return

    os.makedirs(dst_dir, exist_ok=True)
    broken = clean_broken_links(dst_dir)
    if broken:
        log(f"🧹 Убрано битых симлинков: {broken}")

    linked = skipped = 0
    for root, dirs, files in os.walk(src_dir):
        if skip_dirs:
            dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel = os.path.relpath(root, src_dir)
        target_dir = dst_dir if (not keep_structure or rel == ".") else os.path.join(dst_dir, rel)
        os.makedirs(target_dir, exist_ok=True)

        for fname in files:
            if not fname.endswith(exts):
                continue
            src = os.path.join(root, fname)
            dst = os.path.join(target_dir, fname)

            if os.path.islink(dst):
                if os.readlink(dst) == src or not overwrite:
                    skipped += 1
                    continue
                os.unlink(dst)
            elif os.path.exists(dst):
                log(f"⚠️ Пропуск (есть локальный файл): {fname}")
                continue

            os.symlink(src, dst)
            linked += 1

    total = sum(len([f for f in fs if f.endswith(exts)]) for _, _, fs in os.walk(dst_dir))
    log(f"🔗 Новых: {linked} | уже было: {skipped} | всего видит Fooocus: {total}")


# ---------- HuggingFace ----------

def parse_hf_url(url):
    m = re.search(r"huggingface\.co/([^/]+/[^/]+)/(?:resolve|blob)/[^/]+/(.+)", url)
    if not m:
        return None, None
    return m.group(1), unquote(m.group(2).split("?")[0])


def resolve_target_name(filename, new_name):
    """Если новое имя без расширения — подставляем оригинальное."""
    orig = os.path.basename(filename)
    if not new_name:
        return orig
    return new_name if os.path.splitext(new_name)[1] else new_name + os.path.splitext(orig)[1]


def download_from_hf(url, new_name, destination_dir, token=None, min_size_mb=0):
    from huggingface_hub import hf_hub_download

    os.makedirs(destination_dir, exist_ok=True)
    repo_id, filename = parse_hf_url(url)
    if not repo_id:
        log(f"   ⚠️ Неверная ссылка HF: {url}")
        return None

    target = resolve_target_name(filename, new_name)
    final_path = os.path.join(destination_dir, target)

    if os.path.exists(final_path) and os.path.getsize(final_path) > min_size_mb * 1024 ** 2:
        log(f"   ✅ Уже есть: {target}")
        return final_path

    label = target if not new_name else f"{os.path.basename(filename)} → {target}"
    log(f"   ⏳ Качаем {label}...")
    try:
        downloaded = hf_hub_download(repo_id=repo_id, filename=filename,
                                     local_dir=destination_dir, token=token)
        if os.path.abspath(downloaded) != os.path.abspath(final_path):
            shutil.move(downloaded, final_path)
            nested = os.path.join(destination_dir, filename.split("/")[0])
            if os.path.isdir(nested) and os.path.abspath(nested) != os.path.abspath(destination_dir):
                shutil.rmtree(nested, ignore_errors=True)
        log(f"   ⚡ Готово: {target}")
        return final_path
    except Exception as e:
        log(f"   ❌ Ошибка {target}: {e}")
        return None


def download_and_extract_zip(url, destination_dir, token=None):
    from huggingface_hub import hf_hub_download

    ignore = {"put_embeddings_or_textual_inversion_concepts_here", ".gitkeep", ".placeholder"}
    repo_id, filename = parse_hf_url(url)
    if not repo_id:
        log(f"   ⚠️ Неверная ссылка HF: {url}")
        return

    os.makedirs(destination_dir, exist_ok=True)
    # «Уже распаковано», если есть реальные файлы (симлинки с Drive не считаем)
    real = [f for f in os.listdir(destination_dir)
            if f not in ignore and not os.path.islink(os.path.join(destination_dir, f))]
    if real:
        log(f"   ✅ Уже распаковано ({len(real)} файлов)")
        return

    log(f"   ⏳ Качаем архив {os.path.basename(filename)}...")
    try:
        zip_path = hf_hub_download(repo_id=repo_id, filename=filename, token=token)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(destination_dir)
            log(f"   ✅ Распаковано файлов: {len(z.namelist())}")
    except Exception as e:
        log(f"   ❌ Ошибка: {e}")


# ---------- default_model + config.txt ----------

def detect_default_model(links, checkpoints_dir):
    ckpts = links.get("CHECKPOINTS", [])
    if ckpts:
        url, new_name = ckpts[0]
        _, filename = parse_hf_url(url)
        if filename:
            name = resolve_target_name(filename, new_name)
            if os.path.exists(os.path.join(checkpoints_dir, name)):
                return name
            log(f"⚠️ Первый из списка не найден на диске: {name}")

    if os.path.isdir(checkpoints_dir):
        found = sorted(f for f in os.listdir(checkpoints_dir) if f.endswith(".safetensors"))
        if found:
            log(f"ℹ️ Берём первый доступный из папки ({len(found)} шт.)")
            return found[0]
    return None


# ---------- для менеджера в GUI ----------

# тип в интерфейсе → (секция links.txt, папка в Paths, расширения)
KINDS = {
    "Чекпоинт": ("CHECKPOINTS", "checkpoints", (".safetensors", ".ckpt")),
    "LoRA": ("LORAS", "loras", LORA_EXTS),
    "Эмбеддинг": ("EMBEDDINGS", "embeddings", EMBED_EXTS),
}
STATE_FILE = "sud_state.json"  # в папке Fooocus (не в git): где Drive и links.txt этой сессии


def save_state(fooocus_dir, drive_base):
    path = os.path.join(fooocus_dir, STATE_FILE)
    state = {}
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        pass
    state["drive_base"] = drive_base
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def load_paths(fooocus_dir):
    """Paths текущей сессии (пути Drive — sud/paths.py)."""
    return Paths(fooocus_dir)


def add_link(links_file, section, url, new_name=None):
    """Дописать ссылку в links.txt с пометкой «грузить при старте». True — если добавлена."""
    from sud.catalog import Catalog
    return Catalog(links_file).add(section, url, name=new_name or "", star=True)


def human_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit in ("Б", "КБ") else f"{n:.1f} {unit}"
        n /= 1024


def list_files(paths):
    """Строки таблицы: [тип, файл, размер, откуда]."""
    links = parse_links_file(paths.links_file, autoload_only=False) if os.path.isfile(paths.links_file) else {}
    from_links = {}
    for section, items in links.items():
        for url, new_name in items:
            _, filename = parse_hf_url(url)
            if filename:
                from_links[(section, resolve_target_name(filename, new_name))] = True

    rows = []
    for kind, (section, attr, exts) in KINDS.items():
        root = getattr(paths, attr)
        if not os.path.isdir(root):
            continue
        for dirpath, _, files in os.walk(root):
            for fname in sorted(files):
                if not fname.endswith(exts):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root)
                try:
                    size = human_size(os.path.getsize(full))
                except OSError:
                    size = "?"
                if os.path.islink(full):
                    source = "Google Drive"
                elif (section, fname) in from_links:
                    source = "links.txt"
                else:
                    source = "локально"
                rows.append([kind, rel, size, source])
    return rows


def download(paths, kind, url, new_name=None, token=None):
    """Скачать одну модель по ссылке HF в папку нужного типа. Возвращает путь или None."""
    section, attr, _ = KINDS[kind]
    min_mb = {"CHECKPOINTS": 10, "LORAS": 1}.get(section, 0)
    return download_from_hf(url, new_name, getattr(paths, attr), token=token, min_size_mb=min_mb)


# ---------- главное ----------

def sync(fooocus_dir, drive_base=None, hf_token=None):
    """drive_base — устаревший параметр (пути теперь в sud/paths.py), оставлен для старых ноутбуков."""
    from sud import paths
    paths.ensure_layout(log)
    p = Paths(fooocus_dir)

    log(f"=== 1️⃣ СПИСОК: {p.links_file} ===")
    links = parse_links_file(p.links_file)
    for sec, items in links.items():
        mark = "✅" if sec in KNOWN_SECTIONS else "❓"
        log(f"  {mark} [{sec}]: {len(items)} шт.")
    if not links:
        log("  ⚠️ Список пуст")

    from sud import paths
    for title, kind, dest, exts, keep in (
        ("2️⃣ ЛОРЫ С GOOGLE DRIVE", "loras", p.loras, LORA_EXTS, True),
        ("3️⃣ ЭМБЕДДИНГИ С GOOGLE DRIVE", "embeddings", p.embeddings, EMBED_EXTS, False),
        ("➕ ЧЕКПОИНТЫ С GOOGLE DRIVE", "checkpoints", p.checkpoints, (".safetensors", ".ckpt"), True),
        ("➕ WILDCARDS С GOOGLE DRIVE", "wildcards", p.wildcards, (".txt",), False),
    ):
        log(f"\n=== {title} ===")
        for src, skip, main in paths.sources(kind):
            if not os.path.isdir(src):
                continue
            log(f"   {'📁' if main else '🕰 старая папка:'} {src}")
            link_tree_from_drive(src, dest, exts, skip_dirs=skip, keep_structure=keep, overwrite=main)

    log("\n=== 4️⃣ СКАЧИВАНИЕ С HUGGINGFACE ===")
    for section, dest, min_mb in [
        ("CHECKPOINTS", p.checkpoints, 10),
        ("LORAS", p.loras, 1),
        ("EMBEDDINGS", p.embeddings, 0),
        ("WILDCARDS", p.wildcards, 0),
    ]:
        items = links.get(section, [])
        if not items:
            continue
        log(f"\n[{section}] → {dest}")
        for url, new_name in items:
            download_from_hf(url, new_name, dest, token=hf_token, min_size_mb=min_mb)

    if links.get("EMBEDDING ZIP"):
        log(f"\n[EMBEDDING ZIP] → {p.embeddings}")
        for url, _ in links["EMBEDDING ZIP"]:
            download_and_extract_zip(url, p.embeddings, token=hf_token)

    log("\n=== 5️⃣ DEFAULT_MODEL ===")
    default_model = detect_default_model(links, p.checkpoints)
    if default_model:
        log(f"🎯 default_model: {default_model}")
    else:
        default_model = FALLBACK_MODEL
        log(f"⚠️ Чекпоинтов нет! Будет {default_model} (если его нет — Fooocus ругнётся)")

    # авто-модель запоминаем, а config.txt собираем вместе с твоими настройками (sud/settings.py)
    from sud import settings
    settings.update_state(auto_model=default_model)
    cfg = settings.apply()
    log(f"✅ config.txt собран: модель {cfg.get('default_model')}"
        f"{' (задана в настройках)' if cfg.get('default_model') != default_model else ''}")
    return default_model


def main():
    ap = argparse.ArgumentParser(description="Fooocus-sud: синхронизация моделей")
    ap.add_argument("command", choices=["sync"])
    ap.add_argument("--fooocus-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--drive-base", default="/content/drive/MyDrive/COLAB_MOUNTS/models/loras2")
    a = ap.parse_args()
    if a.command == "sync":
        sync(a.fooocus_dir, a.drive_base, hf_token=os.getenv("HF_TOKEN"))


if __name__ == "__main__":
    main()
