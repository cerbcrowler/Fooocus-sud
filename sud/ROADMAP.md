# Fooocus-sud: план улучшений

Движок в Colab, интерфейс в браузере ноута через `https://colab.period.pp.ua`.

## Интерфейс
- [ ] **Вкладка «Модели»**: вставить ссылку HF/Civitai → скачать с прогрессом → модель сразу в списке;
      галочка «оставить в links.txt»; удаление/выключение; выбор модели по умолчанию.
      Использует тот же `sud/models.py`, что и ноутбук.

## Модели
- [ ] Ссылки Civitai в `links.txt` (секрет `CIVITAI_TOKEN`).
- [ ] Ускорить загрузку с HF через `hf_transfer`.

## Сделано
- [x] Картинки сразу в папку на ноуте (`javascript/sud-autosave.js`, кнопка 📁), Fooocus с `--disable-image-log`.
- [x] Темы gruvbox light/dark (`css/sud-gruvbox.css`, `javascript/sud-theme.js`), кнопка 🌙/☀️ внизу справа.
- [x] Вкладка «📦 Менеджер» v1: скачать по ссылке HF, links.txt, таблица с поиском (`sud/ui_models.py`).
      Дальше: Civitai, удаление, выбор лор по умолчанию, широкая таблица.
- [x] Кэш venv на Drive (`COLAB_MOUNTS/cache/venv-fooocus-*.tar.zst`, 2,1 ГБ); восстановление в новой сессии ещё проверить.
- [x] SSH в Colab через VPS: `ssh colab` (ProxyJump vps → 127.0.0.1:2222 → sshd Colab :2201),
      лог `/content/fooocus.log`, перезапуск `/content/restart_fooocus.sh`.
- [x] Форк, Colab-ноутбук (`colab/`), логика в `sud/colab.py`, модели по `links.txt` (`sud/models.py`).
- [x] Туннель Colab → VPS → Traefik с ограниченным ключом, Python 3.10 venv, закреплённые зависимости gradio.
