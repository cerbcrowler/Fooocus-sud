"""Логика Colab-ноутбука Fooocus-sud.

Ноутбук только вызывает эти функции, поэтому после `git pull` в ячейке 1
подхватывается свежий код, и переоткрывать ноутбук не нужно.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

FOOOCUS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "/root/.ssh/id_vps"
TUNNEL_SCRIPT = "/content/tunnel_loop.sh"
TUNNEL_LOG = "/content/tunnel.log"


def sh(cmd, check=False):
    """Выполнить команду, показать вывод, вернуть CompletedProcess."""
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    out = (r.stdout + r.stderr).strip()
    if out:
        print(out, flush=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"Команда упала ({r.returncode}): {cmd}")
    return r


def _secret(name):
    """Секрет Colab или None, если его нет / нет доступа."""
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return None


# ---------- ячейка 2: Drive + модели ----------

def models(drive_base):
    from google.colab import drive
    import importlib
    import sud.models

    if not os.path.ismount("/content/drive"):
        drive.mount("/content/drive")
    print("✅ Drive смонтирован")

    hf_token = _secret("HF_TOKEN")
    print(f"✅ HF-токен: {hf_token[:7]}..." if hf_token
          else "⚠️ HF-токена нет: приватные модели не скачаются")

    importlib.reload(sud.models)
    print()
    return sud.models.sync(FOOOCUS_DIR, drive_base, hf_token=hf_token)


# ---------- ячейка 3: пароль + туннель ----------

def normalize_key(raw):
    """Чинит ключ после Colab Secrets: убирает \\r, восстанавливает переносы строк."""
    raw = raw.replace("\r", "").strip()
    m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", raw, re.S)
    if not m:
        raise ValueError("в VPS_SSH_KEY нет строк -----BEGIN/END----- (скопирован не весь файл?)")
    kind, body = m.group(1), re.sub(r"\s+", "", m.group(2))
    lines = "\n".join(body[i:i + 70] for i in range(0, len(body), 70))
    return f"-----BEGIN {kind}-----\n{lines}\n-----END {kind}-----\n"


def _write_auth():
    """Второй пароль в самом Fooocus (необязательно: Traefik и так спрашивает свой)."""
    path = os.path.join(FOOOCUS_DIR, "auth.json")
    user, password = _secret("FOOOCUS_USER"), _secret("FOOOCUS_PASS")
    if user and password:
        with open(path, "w") as f:
            json.dump([{"user": user, "pass": password}], f)
        print(f"✅ auth.json: пользователь {user} (вход будет двойной: Traefik + Fooocus)")
    else:
        if os.path.exists(path):
            os.remove(path)
        print("ℹ️ Секретов FOOOCUS_USER/FOOOCUS_PASS нет: вход только по паролю Traefik")


def _ssh_opts():
    return (f"-i {KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
            f"-o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o ConnectTimeout=10")


def tunnel_status(vps_host, vps_user="root"):
    """Ключ на VPS вместо шелла запускает /root/colab-status.sh: порт туннеля + Traefik."""
    out = sh(f"ssh -T {_ssh_opts()} {vps_user}@{vps_host}").stdout
    return "OK:" in out


def tunnel(vps_host, vps_user="root", vps_bind="172.18.0.1:8080", port=7865):
    _write_auth()

    raw = _secret("VPS_SSH_KEY")
    if not raw:
        raise RuntimeError("❌ Нет секрета VPS_SSH_KEY (или не включён доступ из блокнота)")
    os.makedirs("/root/.ssh", exist_ok=True)
    with open(KEY, "w") as f:
        f.write(normalize_key(raw))
    os.chmod(KEY, 0o600)
    if sh(f"ssh-keygen -l -f {KEY}").returncode != 0:
        raise RuntimeError("❌ Ключ не читается: перескопируй ~/.ssh/colab_vps в секрет VPS_SSH_KEY")
    print("✅ Ключ для VPS записан")

    loop = f"""#!/bin/bash
while true; do
  echo "$(date '+%F %T') подключаюсь к {vps_host}"
  ssh -N {_ssh_opts()} -o ExitOnForwardFailure=yes \\
      -R {vps_bind}:localhost:{port} {vps_user}@{vps_host}
  rc=$?
  echo "$(date '+%F %T') туннель упал (код $rc), повтор через 5 с"
  sleep 5
done
"""
    with open(TUNNEL_SCRIPT, "w") as f:
        f.write(loop)

    sh(f"pkill -f {TUNNEL_SCRIPT}")
    sh(f"pkill -f 'ssh -N.*{vps_bind}'")
    subprocess.Popen(f"nohup bash {TUNNEL_SCRIPT} > {TUNNEL_LOG} 2>&1 &", shell=True)
    time.sleep(6)

    print("\n=== ПРОВЕРКИ (статус с VPS) ===")
    ok = tunnel_status(vps_host, vps_user)
    print("✅ Туннель поднят" if ok else "❌ Туннель НЕ поднят, смотри лог ниже")
    print("\n--- tunnel.log ---")
    sh(f"tail -n 5 {TUNNEL_LOG}")
    return ok


# ---------- ячейка 4: запуск ----------

VENV = "/content/venv-fooocus"
VENV_PYTHON_VERSION = "3.10"  # под неё закреплены requirements_versions.txt и torch 2.1


TORCH_SPEC = "torch==2.1.0 torchvision==0.16.0"  # как в launch.py
TORCH_INDEX = "https://download.pytorch.org/whl/cu121"
VENV_CACHE_DIR = "/content/drive/MyDrive/COLAB_MOUNTS/cache"
VENV_CACHE_FORMAT = 1  # поднять, если поменяется способ упаковки
VENV_CACHE_LOG = "/content/venv-cache.log"
VENV_SAVE_SCRIPT = "/content/venv_save.sh"
REQS = "requirements_versions.txt"
PINS = "sud/requirements-pins.txt"


def _venv_cache_key():
    """Код зависимостей: поменялись версии → другой архив."""
    h = hashlib.sha256()
    for rel in (REQS, PINS):
        with open(os.path.join(FOOOCUS_DIR, rel), "rb") as f:
            h.update(f.read())
    h.update(f"{VENV_PYTHON_VERSION}|{TORCH_SPEC}|{TORCH_INDEX}|{VENV_CACHE_FORMAT}".encode())
    return h.hexdigest()[:12]


def _uv_python_dir():
    """Где uv хранит скачанный Python 3.10 (venv ссылается на него, его тоже кладём в архив)."""
    r = subprocess.run(f"{sys.executable} -m uv python dir", shell=True, text=True, capture_output=True)
    return r.stdout.strip()


def _ensure_tools():
    sh(f"{sys.executable} -m pip install -q uv", check=True)
    if not shutil.which("zstd"):
        sh("apt-get -qq update > /dev/null && apt-get -qq install -y zstd > /dev/null", check=True)


def _venv_healthy(py):
    return subprocess.run(f"{py} -c 'import torch, gradio'", shell=True,
                          capture_output=True).returncode == 0


def _build_venv(py):
    print(f"⏳ Собираю venv с Python {VENV_PYTHON_VERSION} (несколько минут, только в первый раз)...",
          flush=True)
    sh(f"rm -rf {VENV}")
    sh(f"{sys.executable} -m uv venv -q --seed --python {VENV_PYTHON_VERSION} {VENV}", check=True)
    print("⏳ torch 2.1 (~2 ГБ)...", flush=True)
    sh(f"{py} -m pip install -q --disable-pip-version-check {TORCH_SPEC} --extra-index-url {TORCH_INDEX}",
       check=True)
    print("⏳ зависимости Fooocus...", flush=True)
    pins = os.path.join(FOOOCUS_DIR, PINS)
    sh(f"cd {FOOOCUS_DIR} && {py} -m pip install -q --disable-pip-version-check "
       f"-r {REQS} -r {PINS} -c {pins}", check=True)


def _restore_venv(archive):
    print(f"⏳ Распаковываю готовый venv с Drive: {os.path.basename(archive)}...", flush=True)
    t = time.time()
    sh(f"rm -rf {VENV}")
    r = sh(f"set -o pipefail; zstd -dc -T0 '{archive}' | tar -x -C /")
    if r.returncode == 0:
        print(f"✅ venv восстановлен за {time.time() - t:.0f} с")
        return True
    return False


def _save_venv_bg(archive):
    """Упаковать venv на Drive в фоне: Fooocus в это время уже работает."""
    if subprocess.run(f"pgrep -f {VENV_SAVE_SCRIPT}", shell=True, capture_output=True).returncode == 0:
        print(f"💾 venv уже сохраняется на Drive в фоне (лог: {VENV_CACHE_LOG})")
        return
    cache_dir = os.path.dirname(archive)
    os.makedirs(cache_dir, exist_ok=True)
    uv_dir = _uv_python_dir().lstrip("/")
    script = f"""#!/bin/bash
set -o pipefail
start=$(date +%s)
echo "$(date '+%F %T') упаковываю venv → {archive}"
cd / && nice -n 19 tar -cf - {VENV.lstrip('/')} {uv_dir} | nice -n 19 zstd -T0 -3 -q -f -o '{archive}.part' \\
  && mv -f '{archive}.part' '{archive}' \\
  && find '{cache_dir}' -maxdepth 1 -name 'venv-fooocus-*' ! -name '{os.path.basename(archive)}' -delete \\
  && echo "$(date '+%F %T') ✅ сохранено за $(( $(date +%s) - start )) с, размер $(du -h '{archive}' | cut -f1)" \\
  || {{ rm -f '{archive}.part'; echo "$(date '+%F %T') ❌ не удалось сохранить venv"; }}
"""
    with open(VENV_SAVE_SCRIPT, "w") as f:
        f.write(script)
    subprocess.Popen(f"nohup bash {VENV_SAVE_SCRIPT} > {VENV_CACHE_LOG} 2>&1 &", shell=True)
    print(f"💾 venv сохраняется на Drive в фоне (лог: {VENV_CACHE_LOG}); "
          f"не выключай среду пару минут после старта")


def ensure_venv(cache_dir=VENV_CACHE_DIR):
    """Fooocus заморожен на зависимостях 2024 года, а в Colab Python 3.13.

    Поэтому Fooocus живёт в своём venv с Python 3.10 (uv) + torch 2.1 + закреплённые версии.
    Готовый venv лежит архивом на Drive и в новой сессии просто распаковывается.
    """
    py = f"{VENV}/bin/python"
    _ensure_tools()
    archive = None
    if os.path.ismount("/content/drive"):
        archive = os.path.join(cache_dir, f"venv-fooocus-{_venv_cache_key()}.tar.zst")
    else:
        print("ℹ️ Drive не смонтирован (ячейка 2): кэш venv не используется")

    if os.path.exists(py) and _venv_healthy(py):
        print(f"✅ venv уже есть: {VENV}")
    else:
        if archive and os.path.exists(archive):
            if _restore_venv(archive) and _venv_healthy(py):
                return py  # из кэша: сохранять заново не нужно
            print("⚠️ Архив на Drive битый, удаляю его и собираю venv заново")
            os.remove(archive)
        _build_venv(py)

    if archive and not os.path.exists(archive):
        _save_venv_bg(archive)
    return py


def launch(port=7865, extra_args=""):
    py = ensure_venv()
    env = dict(os.environ,
               PYTORCH_CUDA_ALLOC_CONF="garbage_collection_threshold:0.9,max_split_size_mb:512",
               VIRTUAL_ENV=VENV, PATH=f"{VENV}/bin:" + os.environ.get("PATH", ""))
    env.pop("PYTHONPATH", None)  # чтобы venv не подхватил пакеты Colab (Python 3.13)
    env["MPLBACKEND"] = "Agg"     # у Colab тут бэкенд Jupyter, matplotlib в venv его не знает
    env["PYTHONUNBUFFERED"] = "1"  # иначе лог Fooocus копится в буфере и в ячейке его не видно

    # закрепить зависимости gradio 3.x (без этого новый starlette ломает страницу);
    # PIP_CONSTRAINT — чтобы и launch.py при своей установке не притащил свежие версии
    pins = os.path.join(FOOOCUS_DIR, "sud", "requirements-pins.txt")
    env["PIP_CONSTRAINT"] = pins
    print("⏳ Проверяю закреплённые версии зависимостей...", flush=True)
    sh(f"{py} -m pip install -q --disable-pip-version-check -r {pins}", check=True)
    cmd = (f"{py} launch.py --port {port} --listen --always-high-vram "
           f"--preset sud --disable-analytics {extra_args}")
    print(f"▶️ {cmd}\n", flush=True)
    p = subprocess.Popen(cmd, shell=True, cwd=FOOOCUS_DIR, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        for line in p.stdout:
            print(line, end="", flush=True)
    except KeyboardInterrupt:
        print("\n⏹ Останавливаю Fooocus...")
        p.terminate()
    return p.wait()
