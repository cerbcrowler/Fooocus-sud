"""Настройки Fooocus-sud: settings.json (на Drive) → config.txt, который читает Fooocus.

Порядок слоёв (каждый следующий перебивает предыдущий):
    1. presets/sud.json          — базовые значения форка (в git)
    2. auto_model из sud_state   — первый чекпоинт из links.txt (пишет sync)
    3. settings.json             — то, что ты задал во вкладке «⚙️ Настройки»
Результат пишется в config.txt. Fooocus запускается БЕЗ --preset, поэтому config.txt главный.

Только стандартная библиотека: вызывается и из Python Colab, и из venv Fooocus
(`python -m sud.settings apply` перед каждым запуском).
"""

import json
import os
import sys

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVE_ROOT = "/content/drive/MyDrive"
LOCAL_SETTINGS = os.path.join(FOOOCUS_DIR, "sud_settings.json")  # если Drive не смонтирован
BASE_PRESET = os.path.join(FOOOCUS_DIR, "presets", "sud.json")
STATE_FILE = os.path.join(FOOOCUS_DIR, "sud_state.json")
CONFIG_TXT = os.path.join(FOOOCUS_DIR, "config.txt")

AUTO = ""  # default_model = "" → брать автоматически (первый из links.txt)


def _read(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {} if default is None else default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)


def settings_path():
    from sud import paths
    return paths.settings_file("settings.json") if paths.drive_mounted() else LOCAL_SETTINGS


def load_user():
    """Твои настройки (только то, что ты менял)."""
    return _read(settings_path())


def save_user(data):
    _write(settings_path(), data)
    return settings_path()


def load_state():
    return _read(STATE_FILE)


def update_state(**kv):
    st = load_state()
    st.update(kv)
    _write(STATE_FILE, st)


def effective():
    """Итоговый конфиг: база + авто-модель + твои настройки."""
    cfg = _read(BASE_PRESET)
    # запасной вариант (старая сессия, где sync ещё не писал auto_model): модель из прошлого config.txt
    auto_model = load_state().get("auto_model") or _read(CONFIG_TXT).get("default_model")
    if auto_model:
        cfg["default_model"] = auto_model
    user = load_user()
    for k, v in user.items():
        if k == "default_model" and v == AUTO:
            continue
        cfg[k] = v
    # чтобы Fooocus ничего не докачивал сам по default.json (juggernaut 6 ГБ и т.п.)
    for k in ("checkpoint_downloads", "lora_downloads", "embeddings_downloads", "vae_downloads"):
        cfg.setdefault(k, {})
    return cfg


def apply():
    cfg = effective()
    _write(CONFIG_TXT, cfg)
    return cfg


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "apply":
        cfg = apply()
        n_user = len(load_user())
        print(f"[sud.settings] config.txt собран: модель {cfg.get('default_model')}, "
              f"своих настроек: {n_user} ({settings_path()})", flush=True)
    else:
        print(json.dumps(effective(), indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()
