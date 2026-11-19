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
    # bash, а не /bin/sh: в Colab sh = dash, он не знает pipefail и прочее
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True, executable="/bin/bash")
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
    if hf_token:
        # стандартное место huggingface_hub: отсюда токен возьмёт и менеджер моделей в Fooocus
        os.makedirs("/root/.cache/huggingface", exist_ok=True)
        with open("/root/.cache/huggingface/token", "w") as f:
            f.write(hf_token)
        os.chmod("/root/.cache/huggingface/token", 0o600)

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


SSH_BIND = "127.0.0.1:2222"  # на VPS: вход в Colab по SSH (виден только изнутри VPS)
AUTHORIZED_KEYS = os.path.join(FOOOCUS_DIR, "sud", "colab_authorized_keys")
SSHD_PORT = 2201  # наш sshd в Colab (порт 22 не трогаем: там может быть sshd самого Colab)


def _start_sshd():
    """sshd в Colab, только на localhost и только по ключам из sud/colab_authorized_keys."""
    if not os.path.exists("/usr/sbin/sshd"):
        print("⏳ Ставлю openssh-server...", flush=True)
        sh("apt-get -qq update > /dev/null; apt-get -qq install -y openssh-server > /dev/null", check=True)
    os.makedirs("/run/sshd", exist_ok=True)
    os.makedirs("/root/.ssh", exist_ok=True)
    sh("ssh-keygen -A > /dev/null")
    with open(AUTHORIZED_KEYS) as src:
        keys = [l for l in src if l.strip() and not l.startswith("#")]
    with open("/root/.ssh/authorized_keys", "w") as dst:
        dst.writelines(keys)
    os.chmod("/root/.ssh/authorized_keys", 0o600)
    # У Colab есть свой sshd (для встроенного терминала), его не трогаем:
    # наш — отдельный, на своём порту и со своим pid-файлом.
    listen = f"127.0.0.1:{SSHD_PORT}"
    if not _port_listening(listen):
        sh(f"/usr/sbin/sshd -o ListenAddress=127.0.0.1 -o Port={SSHD_PORT} -o PidFile=/run/sshd-sud.pid "
           f"-o PasswordAuthentication=no -o PermitRootLogin=prohibit-password", check=True)
        time.sleep(1)
    if _port_listening(listen):
        print(f"✅ sshd в Colab слушает {listen} (ключей: {len(keys)})")
    else:
        print(f"❌ sshd не слушает {listen}: вход по SSH не заработает")


def _port_listening(addr):
    return subprocess.run(f"ss -tln | grep -q '{addr} '", shell=True).returncode == 0


def tunnel(vps_host, vps_user="root", vps_bind="172.18.0.1:8080", port=7865, ssh_access=True):
    _write_auth()
    extra_forward = ""
    if ssh_access:
        _start_sshd()
        extra_forward = f"-R {SSH_BIND}:127.0.0.1:{SSHD_PORT} "

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
      -R {vps_bind}:127.0.0.1:{port} {extra_forward}{vps_user}@{vps_host}
  rc=$?
  echo "$(date '+%F %T') туннель упал (код $rc), повтор через 5 с"
  sleep 5
done
"""
    with open(TUNNEL_SCRIPT, "w") as f:
        f.write(loop)

    # '[.]' / '[-]' — чтобы pkill не убил собственную оболочку
    sh(f"pkill -f '{TUNNEL_SCRIPT.replace('.sh', '[.]sh')}'")
    sh(f"pkill -f 'ssh [-]N.*{vps_bind}'")
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


def venv_env():
    """Окружение для процессов из venv: без хвостов Jupyter/Colab (Python 3.13)."""
    env = dict(os.environ,
               PYTORCH_CUDA_ALLOC_CONF="garbage_collection_threshold:0.9,max_split_size_mb:512",
               VIRTUAL_ENV=VENV, PATH=f"{VENV}/bin:" + os.environ.get("PATH", ""))
    env.pop("PYTHONPATH", None)  # чтобы venv не подхватил пакеты Colab
    env["MPLBACKEND"] = "Agg"     # у Colab тут бэкенд Jupyter, matplotlib в venv его не знает
    env["PYTHONUNBUFFERED"] = "1"  # иначе лог Fooocus копится в буфере и в ячейке его не видно
    return env


def _venv_healthy(py):
    r = subprocess.run(f"{py} -c 'import torch, gradio'", shell=True,
                       capture_output=True, text=True, env=venv_env())
    if r.returncode != 0 and os.path.exists(py):
        print("⚠️ venv не прошёл проверку:", (r.stderr.strip().splitlines() or ["?"])[-1])
    return r.returncode == 0


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
    # '[.]' — чтобы pgrep не находил собственную оболочку, в строке которой есть этот же текст
    pattern = VENV_SAVE_SCRIPT.replace(".sh", "[.]sh")
    if subprocess.run(f"pgrep -f '{pattern}'", shell=True, capture_output=True).returncode == 0:
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
            # удаляем, только если сам архив действительно повреждён (а не наша команда упала)
            if sh(f"zstd -t -q '{archive}'").returncode != 0:
                print("⚠️ Архив на Drive повреждён, удаляю его и собираю venv заново")
                os.remove(archive)
            else:
                print("⚠️ Архив целый, но venv из него не завёлся: собираю заново (архив оставляю)")
        _build_venv(py)

    if archive and not os.path.exists(archive):
        _save_venv_bg(archive)
    return py


RUN_SCRIPT = "/content/run_fooocus.sh"          # запуск Fooocus с нужным окружением
RESTART_SCRIPT = "/content/restart_fooocus.sh"  # git pull + перезапуск в фоне (для работы по SSH)
FOOOCUS_LOG = "/content/fooocus.log"


def _write_run_scripts(py, port, extra_args):
    import shlex
    env = venv_env()
    env["PIP_CONSTRAINT"] = os.path.join(FOOOCUS_DIR, PINS)
    exports = "\n".join(f"export {k}={shlex.quote(env[k])}" for k in
                        ("PYTORCH_CUDA_ALLOC_CONF", "VIRTUAL_ENV", "PATH", "MPLBACKEND",
                         "PYTHONUNBUFFERED", "PIP_CONSTRAINT"))
    run = f"""#!/bin/bash
# Сгенерировано sud/colab.py. Запуск Fooocus из venv с Python 3.10.
unset PYTHONPATH
{exports}
cd {FOOOCUS_DIR}
{py} -m pip install -q --disable-pip-version-check -r {PINS}
{py} -m sud.settings apply  # settings.json (Drive) → config.txt
nohup {py} -m sud.prefetch run >> /content/prefetch.log 2>&1 &  # вспомогательные модели в фоне
exec {py} launch.py --port {port} --listen --always-high-vram --disable-analytics --disable-image-log {extra_args}
"""
    restart = f"""#!/bin/bash
# Подтянуть код форка и перезапустить Fooocus в фоне. Лог: {FOOOCUS_LOG}
set -e
branch=$(git -C {FOOOCUS_DIR} rev-parse --abbrev-ref HEAD)
git -C {FOOOCUS_DIR} fetch -q origin "$branch"
git -C {FOOOCUS_DIR} reset -q --hard "origin/$branch"
git -C {FOOOCUS_DIR} log --oneline -1
# пересобрать скрипты запуска свежим кодом (флаги запуска могли поменяться)
python3 -c "import sys; sys.path.insert(0, '{FOOOCUS_DIR}'); import sud.colab as c; c._write_run_scripts({py!r}, {port}, {extra_args!r})"
pkill -f '[l]aunch.py --port {port}' || true
sleep 3
nohup bash {RUN_SCRIPT} > {FOOOCUS_LOG} 2>&1 &
echo "Fooocus перезапущен (pid $!), лог: {FOOOCUS_LOG}"
"""
    for path, text in ((RUN_SCRIPT, run), (RESTART_SCRIPT, restart)):
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)


def _fooocus_running(port):
    return subprocess.run(f"pgrep -f '[l]aunch.py --port {port}'", shell=True,
                          capture_output=True).returncode == 0


def _follow(port, wait_new=90):
    """Fooocus перезапустили по SSH: ячейка не завершается, а показывает лог нового процесса.

    Пока ячейка занята, Colab не считает среду бездействующей и не отключает её.
    Выход — когда Fooocus не работает дольше wait_new секунд (или ⏹ в ячейке).
    """
    pos, idle_since = 0, time.time()
    print(f"\n🔁 Fooocus перезапущен в фоне — ячейка остаётся подключённой, лог: {FOOOCUS_LOG}\n", flush=True)
    while True:
        try:
            size = os.path.getsize(FOOOCUS_LOG)
            if size < pos:            # restart_fooocus.sh начал лог заново
                pos = 0
                print("\n🔁 ---- новый запуск Fooocus ----\n", flush=True)
            if size > pos:
                with open(FOOOCUS_LOG, encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                print(chunk, end="", flush=True)
        except FileNotFoundError:
            pass
        if _fooocus_running(port):
            idle_since = time.time()
        elif time.time() - idle_since > wait_new:
            print(f"\n⏹ Fooocus не работает уже {wait_new} с — ячейка завершается.", flush=True)
            return
        time.sleep(1)


def launch(port=7865, extra_args=""):
    if _fooocus_running(port):
        # Fooocus уже работает (например, перезапущен по SSH) — второй не поднимаем, просто подключаемся
        print("ℹ️ Fooocus уже запущен — подключаюсь к его логу, второй экземпляр не стартую.", flush=True)
        try:
            _follow(port)
        except KeyboardInterrupt:
            print("\n⏹ Ячейка остановлена (Fooocus продолжает работать в фоне).", flush=True)
        return 0
    py = ensure_venv()
    _write_run_scripts(py, port, extra_args)
    print(f"▶️ {RUN_SCRIPT}  (лог дублируется в {FOOOCUS_LOG})\n", flush=True)
    p = subprocess.Popen(f"bash {RUN_SCRIPT}", shell=True, cwd=FOOOCUS_DIR, env=venv_env(),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        with open(FOOOCUS_LOG, "w") as log:
            for line in p.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
        rc = p.wait()
        # процесс убит, но Fooocus поднят заново (перезапуск по SSH / из ⚙️ Настроек) — следим за ним
        time.sleep(5)
        if _fooocus_running(port) or os.path.exists(RESTART_SCRIPT):
            _follow(port)
        return rc
    except KeyboardInterrupt:
        print("\n⏹ Останавливаю Fooocus...", flush=True)
        p.terminate()
        sh(f"pkill -f '[l]aunch.py --port {port}'")
        return p.wait()
