"""Вкладка «⚙️ Настройки» Fooocus-sud: нормальные настройки вместо JSON-пресетов.

Значения хранятся в settings.json на Drive (sud/settings.py) и при каждом запуске
собираются в config.txt. Слоты лор и т.п. gradio создаёт при старте, поэтому
сохранение = перезапуск Fooocus (~40 с), страница обновится сама.

В webui.py две вставки:
    with gr.Tab(label='⚙️ Настройки'):
        sud_settings = sud.ui_settings.build()
    ...
    sud.ui_settings.wire_capture(sud_settings, {...компоненты интерфейса...})
"""

import os
import re
import subprocess
import sys

import gradio as gr

from sud import prefetch as P
from sud import settings as S

AUTO_LABEL = "(авто: первый чекпоинт из links.txt)"
RESTART_SCRIPT = "/content/restart_fooocus.sh"
RESTART_LOG = "/content/restart.log"

# JS: дождаться, пока Fooocus упадёт и поднимется снова, и обновить страницу
RELOAD_JS = """() => {
    let down = false; const t0 = Date.now();
    const poll = () => {
        if (Date.now() - t0 > 240000) return;
        fetch('./config', {cache: 'no-store'})
            .then(r => { if (r.ok && down) location.reload(); else { if (!r.ok) down = true; setTimeout(poll, 2000); } })
            .catch(() => { down = true; setTimeout(poll, 2000); });
    };
    setTimeout(poll, 3000);
}"""


# ---------- преобразования поле ↔ значение конфига ----------

def loras_to_text(loras):
    lines = []
    for item in loras or []:
        if len(item) == 3:
            enabled, name, weight = item
        else:
            (name, weight), enabled = item, True
        if not name or name == "None":
            continue
        lines.append(f"{'' if enabled else '# '}{name} | {weight}")
    return "\n".join(lines)


def text_to_loras(text):
    loras = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        enabled = not line.startswith("#")
        line = line.lstrip("#").strip()
        name, _, weight = line.partition("|")
        name = name.strip()
        try:
            weight = float(weight.strip()) if weight.strip() else 1.0
        except ValueError:
            weight = 1.0
        if name:
            loras.append([enabled, name, weight])
    return loras


def ratios_to_text(ratios):
    return ", ".join(ratios or [])


def text_to_ratios(text):
    out = []
    for w, h in re.findall(r"(\d+)\s*[*x×]\s*(\d+)", text or ""):
        r = f"{w}*{h}"
        if r not in out:
            out.append(r)
    return out


def ratio_label_to_value(label):
    """'1024×1024 <span>∣ 1:1</span>' → '1024*1024'."""
    m = re.match(r"\s*(\d+)\s*[*x×]\s*(\d+)", label or "")
    return f"{m.group(1)}*{m.group(2)}" if m else None


# ---------- вкладка ----------

def build():
    import modules.config as C
    import modules.flags as flags
    from modules.sdxl_styles import legal_style_names

    cfg = S.effective()
    user = S.load_user()
    f = {}

    gr.Markdown("Твои настройки Fooocus. Хранятся на Drive и действуют в каждой новой сессии. "
                "**Сохранение перезапускает Fooocus (~40 с)**, страница потом обновится сама.")

    with gr.Accordion("Интерфейс", open=True):
        f["default_max_lora_number"] = gr.Slider(1, 20, step=1, label="Слотов LoRA",
                                                 value=cfg.get("default_max_lora_number", 5))
        with gr.Row():
            f["default_loras_min_weight"] = gr.Number(label="Мин. вес LoRA",
                                                      value=cfg.get("default_loras_min_weight", -2))
            f["default_loras_max_weight"] = gr.Number(label="Макс. вес LoRA",
                                                      value=cfg.get("default_loras_max_weight", 2))
        f["default_max_image_number"] = gr.Slider(1, 64, step=1, label="Максимум картинок за раз",
                                                  value=cfg.get("default_max_image_number", 32))
        f["available_aspect_ratios"] = gr.Textbox(
            label="Пропорции (ширина*высота через запятую)", lines=3,
            value=ratios_to_text(cfg.get("available_aspect_ratios") or C.available_aspect_ratios))
        f["default_advanced_checkbox"] = gr.Checkbox(label="Панель Advanced открыта при запуске",
                                                     value=cfg.get("default_advanced_checkbox", True))
        f["sud_hide_styles_tab"] = gr.Checkbox(label="Скрыть вкладку Styles (стили по умолчанию продолжат работать)",
                                               value=bool(cfg.get("sud_hide_styles_tab", False)))

    with gr.Accordion("Значения по умолчанию", open=True):
        capture_btn = gr.Button("📥 Взять из текущих настроек интерфейса", variant="secondary")
        model_value = user.get("default_model", S.AUTO) or AUTO_LABEL
        f["default_model"] = gr.Dropdown([AUTO_LABEL] + C.model_filenames, value=model_value,
                                         label="Модель", allow_custom_value=True)
        f["default_loras"] = gr.Textbox(
            label="LoRA по умолчанию: «имя | вес», по одной в строке; «#» в начале = выключена",
            lines=4, value=loras_to_text(cfg.get("default_loras")))
        f["default_performance"] = gr.Radio(flags.Performance.values(), label="Performance",
                                            value=cfg.get("default_performance", "Speed"))
        with gr.Row():
            f["default_sampler"] = gr.Dropdown(flags.sampler_list, label="Sampler",
                                               value=cfg.get("default_sampler", "dpmpp_2m_sde_gpu"))
            f["default_scheduler"] = gr.Dropdown(flags.scheduler_list, label="Scheduler",
                                                 value=cfg.get("default_scheduler", "karras"))
        f["default_cfg_scale"] = gr.Slider(1.0, 30.0, step=0.1, label="CFG (Guidance Scale)",
                                           value=cfg.get("default_cfg_scale", 4.0))
        f["default_sample_sharpness"] = gr.Slider(0.0, 30.0, step=0.1, label="Резкость (Sharpness)",
                                                  value=cfg.get("default_sample_sharpness", 2.0))
        f["default_overwrite_step"] = gr.Number(label="Шаги (-1 = как в Performance)", precision=0,
                                                value=cfg.get("default_overwrite_step", -1))
        f["default_styles"] = gr.Dropdown(legal_style_names, multiselect=True, label="Стили",
                                          value=[s for s in cfg.get("default_styles", []) if s in legal_style_names])
        with gr.Row():
            f["default_aspect_ratio"] = gr.Textbox(label="Пропорция по умолчанию", max_lines=1,
                                                   value=cfg.get("default_aspect_ratio", "1152*896"))
            f["default_image_number"] = gr.Slider(1, 64, step=1, label="Картинок по умолчанию",
                                                  value=cfg.get("default_image_number", 2))
        f["default_output_format"] = gr.Radio(flags.output_formats, label="Формат файла",
                                              value=cfg.get("default_output_format", "png"))
        f["default_prompt_negative"] = gr.Textbox(label="Негативный промпт по умолчанию", lines=2,
                                                  value=cfg.get("default_prompt_negative", ""))

    with gr.Accordion("Предзагрузка вспомогательных моделей", open=False):
        gr.Markdown("Fooocus сам докачивает модели при первом включении опции. Отмеченное здесь "
                    "качается заранее, **в фоне при каждом старте** (с HuggingFace, на диск Colab).")
        selected = P.selected_groups()
        f[P.SETTINGS_KEY] = gr.CheckboxGroup([P.group_label(g) for g in P.GROUPS],
                                             value=[P.group_label(g) for g in selected],
                                             label="Предзагружать при старте")
        prefetch_status = gr.Markdown(_prefetch_status_md())
        with gr.Row():
            prefetch_now_btn = gr.Button("⬇️ Скачать отмеченное сейчас", variant="secondary")
            prefetch_refresh_btn = gr.Button("🔄 Статус", variant="secondary")

    with gr.Row():
        save_btn = gr.Button("💾 Сохранить и перезапустить", variant="primary")
        reset_btn = gr.Button("↩️ Сбросить к базовым", variant="secondary")
    status = gr.Markdown(f"Файл настроек: `{S.settings_path()}`")

    keys = list(f)
    comps = [f[k] for k in keys]

    def on_save(*values):
        data = dict(zip(keys, values))
        err = _validate_and_convert(data)
        if err:
            return f"⚠️ {err}"
        path = S.save_user(data)
        S.apply()
        return f"✅ Сохранено в `{path}`. {_restart()}"

    def on_reset():
        try:
            os.remove(S.settings_path())
        except FileNotFoundError:
            pass
        S.apply()
        return f"↩️ Настройки сброшены к базовым (presets/sud.json). {_restart()}"

    def on_prefetch_now(labels):
        groups = _labels_to_groups(labels)
        if not groups:
            return "Ничего не отмечено", _prefetch_status_md()
        subprocess.Popen(f"{sys.executable} -m sud.prefetch run --groups {','.join(groups)} >> {P.LOG} 2>&1",
                         shell=True, cwd=S.FOOOCUS_DIR, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "⏳ Загрузка пошла в фоне. Жми «🔄 Статус», чтобы посмотреть.", _prefetch_status_md()

    prefetch_now_btn.click(on_prefetch_now, f[P.SETTINGS_KEY], [status, prefetch_status], queue=False)
    prefetch_refresh_btn.click(_prefetch_status_md, [], prefetch_status, queue=False)
    save_btn.click(on_save, comps, status, queue=False).then(None, _js=RELOAD_JS)
    reset_btn.click(on_reset, [], status, queue=False).then(None, _js=RELOAD_JS)
    return {"fields": f, "capture_btn": capture_btn}


def _labels_to_groups(labels):
    by_label = {P.group_label(g): g for g in P.GROUPS}
    return [by_label[l] for l in (labels or []) if l in by_label]


def _prefetch_status_md():
    marks = {"done": "✅ скачано", "partial": "◐ частично", "none": "· нет"}
    lines = [f"- {marks[P.group_status(g)]}: {P.GROUPS[g][0]}" for g in P.GROUPS]
    tail = ""
    try:
        with open(P.LOG, encoding="utf-8") as fh:
            last = [l.strip() for l in fh.readlines()[-3:] if l.strip()]
        if last:
            tail = "\n\nПоследнее в логе:\n" + "\n".join(f"`{l}`" for l in last)
    except OSError:
        pass
    return "\n".join(lines) + tail


def _validate_and_convert(d):
    d[P.SETTINGS_KEY] = _labels_to_groups(d.get(P.SETTINGS_KEY))
    d["default_max_lora_number"] = int(d["default_max_lora_number"])
    d["default_max_image_number"] = int(d["default_max_image_number"])
    d["default_image_number"] = min(int(d["default_image_number"]), d["default_max_image_number"])
    d["default_overwrite_step"] = int(d["default_overwrite_step"] if d["default_overwrite_step"] is not None else -1)
    lo, hi = float(d["default_loras_min_weight"]), float(d["default_loras_max_weight"])
    if lo >= hi:
        return "мин. вес LoRA должен быть меньше максимального"
    d["default_loras_min_weight"], d["default_loras_max_weight"] = lo, hi
    d["default_model"] = S.AUTO if d["default_model"] in (None, AUTO_LABEL) else d["default_model"]
    d["default_loras"] = text_to_loras(d["default_loras"])
    if len(d["default_loras"]) > d["default_max_lora_number"]:
        return f"LoRA по умолчанию ({len(d['default_loras'])}) больше, чем слотов ({d['default_max_lora_number']})"
    d["available_aspect_ratios"] = text_to_ratios(d["available_aspect_ratios"])
    if not d["available_aspect_ratios"]:
        return "список пропорций пуст"
    ar = ratio_label_to_value(d["default_aspect_ratio"]) or ""
    if ar not in d["available_aspect_ratios"]:
        return f"пропорции по умолчанию «{d['default_aspect_ratio']}» нет в списке пропорций"
    d["default_aspect_ratio"] = ar
    d["default_cfg_scale"] = float(d["default_cfg_scale"])
    d["default_sample_sharpness"] = float(d["default_sample_sharpness"])
    d["default_styles"] = list(d["default_styles"] or [])
    return None


def _restart():
    if not os.path.exists(RESTART_SCRIPT):
        return "Перезапусти Fooocus вручную (скрипт перезапуска есть только в Colab)."
    subprocess.Popen(f"sleep 2; bash {RESTART_SCRIPT} > {RESTART_LOG} 2>&1", shell=True,
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Fooocus перезапускается (~40 с), страница обновится сама."


def wire_capture(ui, c):
    """Кнопка «Взять из текущих»: значения из интерфейса Fooocus → в поля настроек.

    c: base_model, lora_ctrls, performance, sampler, scheduler, cfg, sharpness, overwrite_step,
       styles, aspect_ratio, image_number, output_format, negative_prompt
    """
    f = ui["fields"]
    lora_ctrls = c["lora_ctrls"]
    inputs = [c["base_model"], c["performance"], c["sampler"], c["scheduler"], c["cfg"], c["sharpness"],
              c["overwrite_step"], c["styles"], c["aspect_ratio"], c["image_number"], c["output_format"],
              c["negative_prompt"]] + lora_ctrls
    outputs = [f["default_model"], f["default_performance"], f["default_sampler"], f["default_scheduler"],
               f["default_cfg_scale"], f["default_sample_sharpness"], f["default_overwrite_step"],
               f["default_styles"], f["default_aspect_ratio"], f["default_image_number"],
               f["default_output_format"], f["default_prompt_negative"], f["default_loras"]]

    def capture(model, perf, sampler, scheduler, cfg, sharp, steps, styles, aspect, n, fmt, neg, *loras):
        triples = [list(loras[i:i + 3]) for i in range(0, len(loras), 3)]
        return [model, perf, sampler, scheduler, cfg, sharp, steps, styles,
                ratio_label_to_value(aspect) or aspect, n, fmt, neg, loras_to_text(triples)]

    ui["capture_btn"].click(capture, inputs, outputs, queue=False, show_progress=False)
