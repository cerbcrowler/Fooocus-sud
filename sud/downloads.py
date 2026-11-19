"""Фоновые загрузки моделей с прогрессом и отменой (для менеджера моделей).

    jobs.start(url, folder, filename)   # в фоне, файл сначала .part, потом переименование
    jobs.status(url) -> dict | None     # state: running / done / error / cancelled, done, total, speed
    jobs.cancel(url)
    remote_size(url)                    # размер по HEAD (кэшируется в файл)

Токен HuggingFace берётся из ~/.cache/huggingface/token (его кладёт ячейка 2) — для приватных моделей.
Только стандартная библиотека.
"""

import json
import os
import threading
import time
import urllib.request

UA = "fooocus-sud"
SIZE_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sud_sizes.json")
_lock = threading.Lock()


def _token():
    try:
        with open(os.path.expanduser("~/.cache/huggingface/token")) as f:
            return f.read().strip() or None
    except OSError:
        return None


def _request(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    tok = _token()
    if tok and "huggingface.co" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    return req


# ---------- размеры (HEAD) ----------
_sizes = None


def _load_sizes():
    global _sizes
    if _sizes is None:
        try:
            with open(SIZE_CACHE, encoding="utf-8") as f:
                _sizes = json.load(f)
        except Exception:
            _sizes = {}
    return _sizes


def cached_size(url):
    return _load_sizes().get(url)


def remote_size(url):
    sizes = _load_sizes()
    if url in sizes:
        return sizes[url]
    try:
        with urllib.request.urlopen(_request(url, "HEAD"), timeout=20) as r:
            size = int(r.headers.get("Content-Length") or 0) or None
    except Exception:
        size = None
    if size:
        with _lock:
            sizes[url] = size
            try:
                with open(SIZE_CACHE, "w", encoding="utf-8") as f:
                    json.dump(sizes, f)
            except OSError:
                pass
    return size


def fetch_sizes_bg(urls):
    """Узнать размеры в фоне (для таблицы), не задерживая интерфейс."""
    todo = [u for u in urls if u not in _load_sizes()]
    if todo:
        threading.Thread(target=lambda: [remote_size(u) for u in todo], daemon=True).start()


# ---------- загрузки ----------
class Jobs:
    def __init__(self):
        self._jobs = {}

    def status(self, url):
        j = self._jobs.get(url)
        return dict(j) if j else None

    def all(self):
        return {u: dict(j) for u, j in self._jobs.items()}

    def running(self, url):
        j = self._jobs.get(url)
        return bool(j and j["state"] == "running")

    def start(self, url, folder, filename):
        if self.running(url):
            return False
        job = {"state": "running", "done": 0, "total": cached_size(url), "speed": 0.0,
               "error": "", "file": filename, "cancel": False, "started": time.time()}
        self._jobs[url] = job
        threading.Thread(target=self._run, args=(url, folder, filename, job), daemon=True).start()
        return True

    def cancel(self, url):
        j = self._jobs.get(url)
        if j and j["state"] == "running":
            j["cancel"] = True
            return True
        return False

    def forget(self, url):
        j = self._jobs.get(url)
        if j and j["state"] != "running":
            del self._jobs[url]

    def _run(self, url, folder, filename, job):
        final = os.path.join(folder, filename)
        tmp = final + ".part"
        try:
            os.makedirs(folder, exist_ok=True)
            with urllib.request.urlopen(_request(url), timeout=60) as r:
                total = int(r.headers.get("Content-Length") or 0) or job["total"]
                job["total"] = total
                t0, last_t, last_n = time.time(), time.time(), 0
                with open(tmp, "wb") as f:
                    while True:
                        if job["cancel"]:
                            raise InterruptedError
                        chunk = r.read(4 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        job["done"] += len(chunk)
                        now = time.time()
                        if now - last_t >= 0.7:
                            job["speed"] = (job["done"] - last_n) / (now - last_t)
                            last_t, last_n = now, job["done"]
            if total and job["done"] < total:
                raise IOError(f"скачано {job['done']} из {total} байт")
            os.replace(tmp, final)
            job["state"] = "done"
            job["speed"] = job["done"] / max(time.time() - t0, 0.001)
        except InterruptedError:
            job["state"] = "cancelled"
        except Exception as e:
            job["state"] = "error"
            job["error"] = str(e)[:200]
        finally:
            if job["state"] != "done" and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


jobs = Jobs()
