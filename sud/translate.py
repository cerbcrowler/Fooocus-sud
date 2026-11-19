"""Перевод промпта RU → EN: DeepL, при ошибке или лимите — Google (без ключа).

Синтаксис промпта не портится: текст режется на куски, и переводятся только куски с кириллицей.
Не трогаются: <lora:...> и прочие <...>, embedding:имя (текстовые инверсии), __вайлдкарды__,
числа весов «:1.3)», скобки, запятые, английские куски. Пример:
    "(красивые глаза:1.3), девушка в саду, <lora:detail:0.8>"
 →  "(beautiful eyes:1.3), a girl in the garden, <lora:detail:0.8>"

Ключ DeepL: файл KEY_FILE (его кладёт ячейка 2 из секрета Colab DEEPL_API_KEY) или
переменная окружения DEEPL_API_KEY. Только стандартная библиотека.
"""

import json
import os
import re
import urllib.parse
import urllib.request

KEY_FILE = os.path.expanduser("~/.config/fooocus-sud/deepl.key")
CYR = re.compile(r"[А-Яа-яЁё]")
# защищённое: <...>, __name__, вес «:1.3» перед «)» или концом, скобки и разделители
TOKEN = re.compile(r"(<[^>]*>|embedding:[^\s,()\[\]{}|:]+|__[^\s_][^\s]*?__|:\s*-?\d+(?:\.\d+)?(?=\s*[)\]])|[()\[\]{}|,\n])")


def deepl_key():
    key = os.environ.get("DEEPL_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(KEY_FILE) as f:
            return f.read().strip() or None
    except OSError:
        return None


def has_cyrillic(text):
    return bool(CYR.search(text or ""))


def _deepl(texts, key):
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    body = json.dumps({"text": texts, "target_lang": "EN-US", "source_lang": "RU"}).encode()
    req = urllib.request.Request(f"https://{host}/v2/translate", data=body, method="POST", headers={
        "Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json", "User-Agent": "fooocus-sud"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return [t["text"] for t in data["translations"]]


def _google_one(text):
    q = urllib.parse.urlencode({"client": "gtx", "sl": "ru", "tl": "en", "dt": "t", "q": text})
    req = urllib.request.Request("https://translate.googleapis.com/translate_a/single?" + q,
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return "".join(part[0] for part in data[0] if part and part[0])


def _google(texts):
    """Все куски одним запросом (через перевод строки); если строки не сошлись — по одному."""
    if len(texts) > 1:
        try:
            joined = _google_one("\n".join(texts)).split("\n")
            if len(joined) == len(texts):
                return joined
        except Exception:
            pass
    return [_google_one(t) for t in texts]


def translate_texts(texts, engine="deepl"):
    """→ (переводы, какой движок сработал, предупреждение)."""
    if not texts:
        return [], "", ""
    warn = ""
    key = deepl_key()
    if engine == "deepl" and key:
        try:
            return _deepl(texts, key), "DeepL", ""
        except Exception as e:
            code = getattr(e, "code", None)
            warn = {456: "у DeepL кончился лимит", 403: "DeepL не принял ключ"}.get(code, f"DeepL недоступен ({e})")
    elif engine == "deepl":
        warn = "ключа DeepL нет"
    return _google(texts), "Google", warn


def translate_prompt(prompt, engine="deepl"):
    """→ (перевод, движок, предупреждение). Если кириллицы нет — текст как есть."""
    if not has_cyrillic(prompt):
        return prompt, "", ""
    parts = TOKEN.split(prompt)
    idx = [i for i, p in enumerate(parts) if p and not TOKEN.fullmatch(p) and has_cyrillic(p)]
    # пробелы по краям куска сохраняем как были, переводим только серединку
    cores = [parts[i].strip() for i in idx]
    translated, used, warn = translate_texts(cores, engine)
    for i, core, tr in zip(idx, cores, translated):
        lead = parts[i][:len(parts[i]) - len(parts[i].lstrip())]
        tail = parts[i][len(parts[i].rstrip()):]
        tr = tr.strip().rstrip(".") if not core.endswith(".") else tr.strip()
        parts[i] = lead + tr + tail
    return "".join(parts), used, warn
