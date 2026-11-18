# Fooocus-sud: план улучшений

Движок в Colab, интерфейс в браузере ноута через `https://colab.period.pp.ua`.

## Интерфейс
- [ ] **Темы gruvbox light / dark** с переключателем в интерфейсе.
- [ ] **Вкладка «Модели»**: вставить ссылку HF/Civitai → скачать с прогрессом → модель сразу в списке;
      галочка «оставить в links.txt»; удаление/выключение; выбор модели по умолчанию.
      Использует тот же `sud/models.py`, что и ноутбук.
- [ ] **Картинки сразу на диск ноута** (File System Access API в Chrome/Edge): один раз выбрать папку,
      дальше каждая новая картинка сохраняется туда сама, без Drive и VPS.

## Модели
- [ ] Ссылки Civitai в `links.txt` (секрет `CIVITAI_TOKEN`).
- [ ] Ускорить загрузку с HF через `hf_transfer`.

## Сделано
- [x] Кэш venv на Drive (`COLAB_MOUNTS/cache/venv-fooocus-*.tar.zst`, 2,1 ГБ); восстановление в новой сессии ещё проверить.
- [x] SSH в Colab через VPS: `ssh colab` (ProxyJump vps → 127.0.0.1:2222 → sshd Colab :2201),
      лог `/content/fooocus.log`, перезапуск `/content/restart_fooocus.sh`.
- [x] Форк, Colab-ноутбук (`colab/`), логика в `sud/colab.py`, модели по `links.txt` (`sud/models.py`).
- [x] Туннель Colab → VPS → Traefik с ограниченным ключом, Python 3.10 venv, закреплённые зависимости gradio.
