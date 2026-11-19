"""Каталог моделей в links.txt (Drive): категории, «грузить при старте», правка построчно.

Формат (старый формат тоже понимается):

    [CHECKPOINTS: Реализм]
    * https://huggingface.co/.../Juggernaut_XIII.safetensors | Juggernaut_XIII.safetensors | Juggernaut XIII
      https://huggingface.co/.../RealVisXL_V5.safetensors        # только по кнопке в менеджере
    [CHECKPOINTS]                                                   # без категории
    https://...

    «*» в начале строки — грузить при старте сессии. Если в разделе-типе (CHECKPOINTS и т.п.)
    ни у одной строки нет «*» — старое поведение: грузится всё.
    Поля через «|»: ссылка | имя файла (необязательно) | название для показа (необязательно).
    Комментарии — после « #» или строкой с «#» в начале.

Правки (звёздочка, категория, добавить, убрать) меняют только нужную строку — остальной файл,
включая твои комментарии и порядок, остаётся как был. Только стандартная библиотека.
"""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

HEADER_RE = re.compile(r"^\s*\[\s*([^\]:]+?)\s*(?::\s*([^\]]*?)\s*)?\]\s*(?:#.*)?$")
COMMENT_RE = re.compile(r"(?:^|\s)#.*$")
NO_CATEGORY = ""


@dataclass
class Entry:
    kind: str                 # CHECKPOINTS / LORAS / ...
    category: str             # "" = без категории
    url: str
    name: str = ""            # имя файла из строки (необязательно)
    title: str = ""           # название для показа (необязательно)
    star: bool = False        # «*» в строке
    line: int = -1            # номер строки в файле
    autoload: bool = False    # итог с учётом старого формата

    @property
    def filename(self):
        return target_filename(self.url, self.name)

    @property
    def display(self):
        if self.title:
            return self.title
        stem = os.path.splitext(os.path.basename(self.filename))[0]
        return stem


def _hf_filename(url):
    m = re.search(r"huggingface\.co/[^/]+/[^/]+/(?:resolve|blob)/[^/]+/(.+)", url)
    return unquote(m.group(1).split("?")[0]) if m else None


def target_filename(url, name=""):
    orig = os.path.basename(_hf_filename(url) or unquote(url.split("?")[0]))
    if not name:
        return orig
    return name if os.path.splitext(name)[1] else name + os.path.splitext(orig)[1]


def _parse_entry_line(raw):
    """→ (star, url, name, title) или None."""
    line = COMMENT_RE.sub("", raw).strip()
    if not line:
        return None
    star = line.startswith("*")
    if star:
        line = line[1:].strip()
    parts = [p.strip() for p in line.split("|")]
    url = parts[0]
    if not re.match(r"https?://", url):
        return None
    name = parts[1] if len(parts) > 1 else ""
    title = parts[2] if len(parts) > 2 else ""
    return star, url, name, title


class Catalog:
    def __init__(self, path):
        self.path = path
        self.lines = []
        self.load()

    # ---------- чтение ----------
    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.lines = f.read().splitlines()
        except FileNotFoundError:
            self.lines = []
        return self

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines).rstrip("\n") + "\n")
        os.replace(tmp, self.path)

    def _scan(self):
        """→ (entries, headers) где headers = [(line, kind, category)]."""
        entries, headers = [], []
        kind = category = None
        for i, raw in enumerate(self.lines):
            h = HEADER_RE.match(raw)
            if h:
                kind, category = h.group(1).strip().upper(), (h.group(2) or "").strip()
                headers.append((i, kind, category))
                continue
            if kind is None:
                continue
            parsed = _parse_entry_line(raw)
            if parsed:
                star, url, name, title = parsed
                entries.append(Entry(kind, category, url, name, title, star, i))
        # старый формат: нет ни одной «*» в типе и нет метки перехода → грузится всё
        starred = {e.kind for e in entries if e.star} | self._marked_kinds()
        for e in entries:
            e.autoload = e.star if e.kind in starred else True
        return entries, headers

    MARK = "# fooocus-sud: «*» = грузить при старте:"

    def _marked_kinds(self):
        for raw in self.lines:
            if raw.startswith(self.MARK):
                return {k.strip().upper() for k in raw[len(self.MARK):].split(",") if k.strip()}
        return set()

    def entries(self, kind=None):
        es, _ = self._scan()
        return [e for e in es if kind is None or e.kind == kind]

    def autoload(self, kind):
        return [e for e in self.entries(kind) if e.autoload]

    def categories(self, kind):
        """Категории в порядке появления (включая пустые разделы)."""
        es, headers = self._scan()
        cats = []
        for _, k, c in headers:
            if k == kind and c not in cats:
                cats.append(c)
        for e in es:
            if e.kind == kind and e.category not in cats:
                cats.append(e.category)
        return cats

    def find(self, url):
        for e in self.entries():
            if e.url == url:
                return e
        return None

    # ---------- правки ----------
    def _format(self, star, url, name, title):
        parts = [url]
        if name or title:
            parts.append(name)
        if title:
            parts.append(title)
        return ("* " if star else "") + " | ".join(parts)

    def _rewrite(self, e, **changes):
        star = changes.get("star", e.star)
        name = changes.get("name", e.name)
        title = changes.get("title", e.title)
        comment = ""
        m = re.search(r"\s#.*$", self.lines[e.line])
        if m:
            comment = "  " + m.group(0).strip()
        self.lines[e.line] = self._format(star, e.url, name, title) + comment

    def _materialize_stars(self, kind):
        """Старый формат (без «*») → проставить «*» всем, чтобы дальше отмечать по одной."""
        marked = self._marked_kinds()
        if kind in marked:
            return
        es = self.entries(kind)
        if not any(e.star for e in es):
            for e in es:
                self._rewrite(e, star=True)
        # метка: этот тип уже в новом формате (даже если все «*» потом снимут — не возвращаться к «грузить всё»)
        line = self.MARK + " " + ", ".join(sorted(marked | {kind}))
        for i, raw in enumerate(self.lines):
            if raw.startswith(self.MARK):
                self.lines[i] = line
                return
        self.lines.insert(0, line)

    def set_autoload(self, url, on):
        e = self.find(url)
        if not e:
            return False
        self._materialize_stars(e.kind)
        e = self.find(url)
        self._rewrite(e, star=bool(on))
        self.save()
        return True

    def set_title(self, url, title):
        e = self.find(url)
        if not e:
            return False
        self._rewrite(e, title=title.strip())
        self.save()
        return True

    def _section_end(self, kind, category, create=True):
        """Индекс, куда вставить строку в раздел [kind: category] (создаёт раздел в конце)."""
        _, headers = self._scan()
        for n, (i, k, c) in enumerate(headers):
            if k == kind and c == category:
                end = headers[n + 1][0] if n + 1 < len(headers) else len(self.lines)
                while end > i + 1 and not self.lines[end - 1].strip():
                    end -= 1
                return end
        if not create:
            return None
        if self.lines and self.lines[-1].strip():
            self.lines.append("")
        self.lines.append(f"[{kind}: {category}]" if category else f"[{kind}]")
        return len(self.lines)

    def add_category(self, kind, category):
        category = category.strip()
        if category in self.categories(kind):
            return False
        self._section_end(kind, category, create=True)
        self.save()
        return True

    def add(self, kind, url, name="", title="", category=NO_CATEGORY, star=False):
        if self.find(url):
            return False
        self._materialize_stars(kind)   # новая запись с явной звёздочкой не должна «включить» старые
        pos = self._section_end(kind, category.strip())
        self.lines.insert(pos, self._format(star, url, name, title))
        self.save()
        return True

    def remove(self, url):
        e = self.find(url)
        if not e:
            return False
        del self.lines[e.line]
        self.save()
        return True

    def set_category(self, url, category):
        e = self.find(url)
        if not e or e.category == category.strip():
            return False
        line = self.lines[e.line]
        del self.lines[e.line]
        pos = self._section_end(e.kind, category.strip())
        self.lines.insert(pos, line)
        self.save()
        return True
