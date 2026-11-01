"""
ProbablyTranslator - Universal Mod Localization Studio for 'Probably Stolen'
- v2.5.0: reworked UI (design tokens, single-canvas mod library, pooled widgets), background loading/build,
  async machine drafts (no network calls on the UI thread), autosave of manual edits
- Live auto-translation progress with cancel button (status bar)
- Crowdin-style Translation Suggestions (multiple alternative variants)
- 100% reliable layout-independent clipboard (Ctrl+C, Ctrl+V on Russian & English)
- Ollama Auto-detect: 127.0.0.1:11434 with dynamic installed models dropdown
- LLM Session Logging & Cleanup: LLMLogs/ directory with 1-click cleanup
- Visual length overflow flags (⚠️ ДЛИННАЯ) in strings table
- Proportional paired navigation buttons ([◀ Пред.] and [След. ▶])
- Dual UI Localization (RU / EN toggle)
- Native Crowdin-style workspace with live editing
- Modern Flat Dark Scrollbar (Clean clam ttk theme, zero Win95 artifacts)
- Universal Hover Tooltips for all controls
"""

import os
import sys
import json
import csv
import re
import time
import math
import shutil
import tempfile
import uuid
import argparse
import threading
import urllib.request
import urllib.parse
import subprocess
import ctypes
from ctypes import wintypes
import platform
import functools
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET

import tkinter as tk
from tkinter import ttk, filedialog
from tkinter import font as tkfont
import customtkinter as ctk

APP_VERSION = "2.8.0"

# Appearance theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Resolve paths
if getattr(sys, 'frozen', False):
    EXE_DIR = os.path.dirname(sys.executable)
    MEIPASS_DIR = getattr(sys, '_MEIPASS', EXE_DIR)
    candidates = [
        os.path.join(MEIPASS_DIR, "bin", "StringPatcher.exe"),
        os.path.join(EXE_DIR, "bin", "StringPatcher.exe"),
        os.path.join(EXE_DIR, "StringPatcher.exe"),
        os.path.join(MEIPASS_DIR, "StringPatcher.exe")
    ]
    STRING_PATCHER_EXE = next((p for p in candidates if os.path.exists(p)), candidates[-1])
    TOOL_DIR = EXE_DIR
else:
    TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
    STRING_PATCHER_EXE = os.path.join(TOOL_DIR, "bin", "StringPatcher.exe")

DEFAULT_GAME_MODS = r"G:\SteamLibrary\steamapps\common\Probably Stolen\Mods"
DEFAULT_WORKSHOP_MODS = r"G:\SteamLibrary\steamapps\workshop\content\4348910"
CONFIG_FILE = os.path.join(TOOL_DIR, "translator_config.json")
ICON_FILE = os.path.join(TOOL_DIR, "icon.ico")
LLMLOGS_DIR = os.path.join(TOOL_DIR, "LLMLogs")

# Ensure LLMLogs directory exists
try: os.makedirs(LLMLOGS_DIR, exist_ok=True)
except Exception: pass

LANGUAGES = [
    ("Russian", "ru"),
    ("English", "en"),
    ("Spanish", "es"),
    ("German", "de"),
    ("French", "fr"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Portuguese", "pt"),
    ("Italian", "it"),
    ("Polish", "pl"),
    ("Ukrainian", "uk"),
    ("Chinese Simplified", "zh-CN"),
    ("Chinese Traditional", "zh-TW"),
    ("Turkish", "tr"),
]

# -------------------------------------------------------------
# LLM Logging & Ollama Helper
# -------------------------------------------------------------

def log_llm_interaction(prompt, response, model, duration_sec):
    """Safely logs AI translation interactions to LLMLogs/ for transparency."""
    try:
        os.makedirs(LLMLOGS_DIR, exist_ok=True)
        log_file = os.path.join(LLMLOGS_DIR, f"llm_session_{time.strftime('%Y%m%d')}.jsonl")
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "duration_sec": round(duration_sec, 3),
            "prompt": prompt,
            "response": response
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as ex:
        print(f"Warning writing LLM log: {ex}")

def clear_llm_logs():
    """Removes all temporary logs from LLMLogs directory."""
    deleted_count = 0
    if os.path.exists(LLMLOGS_DIR):
        for f in os.listdir(LLMLOGS_DIR):
            fp = os.path.join(LLMLOGS_DIR, f)
            try:
                if os.path.isfile(fp):
                    os.remove(fp)
                    deleted_count += 1
            except Exception: pass
    return deleted_count

def get_llm_logs_info():
    """Returns count and size of files in LLMLogs."""
    if not os.path.exists(LLMLOGS_DIR):
        return 0, "0 KB"
    files = [f for f in os.listdir(LLMLOGS_DIR) if os.path.isfile(os.path.join(LLMLOGS_DIR, f))]
    total_size = sum(os.path.getsize(os.path.join(LLMLOGS_DIR, f)) for f in files)
    size_str = f"{total_size / 1024:.1f} KB" if total_size < 1024*1024 else f"{total_size / (1024*1024):.1f} MB"
    return len(files), size_str

def fetch_ollama_models(base_url="http://127.0.0.1:11434"):
    """Fetches list of installed models from local Ollama API or disk manifests."""
    models = []
    # 1. Try Ollama HTTP API
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            if models:
                return sorted(list(set(models)))
    except Exception:
        pass

    # 2. Try disk manifests (~/.ollama/models/manifests)
    manifests_dir = os.path.expanduser("~/.ollama/models/manifests")
    if os.path.isdir(manifests_dir):
        for root, dirs, files in os.walk(manifests_dir):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, manifests_dir)
                parts = rel.split(os.sep)
                if len(parts) >= 2:
                    models.append(f"{parts[-2]}:{parts[-1]}")
        if models:
            return sorted(list(set(models)))

    return ["Модели не найдены"]

# -------------------------------------------------------------
# Internationalization (i18n)
# -------------------------------------------------------------

CURRENT_UI_LANG = "ru"

I18N = {
    "ru": {
        "app_title": "ProbablyTranslator - Студия локализации модов для Probably Stolen",
        "btn_mods": "Моды ({count})",
        "btn_browse": "Обзор...",
        "btn_auto_translate": "Автоперевод",
        "btn_build": "Собрать",
        "btn_install": "В игру (Mods/)",
        "target_lang_label": "Целевой язык:",
        "ui_lang_label": "Язык UI:",
        "engine_label": "{engine}",
        "engine_settings_title": "Настройки движков перевода",
        "mod_lib_title": "БИБЛИОТЕКА МОДОВ",
        "search_mods_placeholder": "Поиск модов...",
        "filter_all": "Все",
        "filter_workshop": "Workshop",
        "filter_mods": "Mods/",
        "filter_untrans": "Не переведено",
        "filter_overflow": "Превышение длины",
        "filter_diff": "Обновления (Diff)",
        "btn_new_to_top": "↑ Новые наверх",
        "search_strings_placeholder": "Поиск по строкам оригинала или перевода...",
        "col_num": "#",
        "col_type": "Тип",
        "col_original": "Исходный текст (Оригинал)",
        "col_translation": "Перевод",
        "col_status": "Статус",
        "context_title": "КОНТЕКСТ И ПЕРЕВОД",
        "orig_box_title": "ОРИГИНАЛ",
        "trans_box_title": "ВАШ ПЕРЕВОД",
        "suggestions_title": "ВАРИАНТЫ ПЕРЕВОДА",
        "btn_ai_request": "Запросить у {engine}",
        "char_count": "{lang} {count} симв.",
        "btn_save_next": "✓ Сохранить и далее (Ctrl+Enter)",
        "btn_translate_row": "Перевести",
        "btn_copy_orig": "Оригинал",
        "btn_clear_row": "Очистить",
        "btn_concise": "Сократить",
        "btn_concise_action": "Сократить перевод",
        "nav_prev": "◀ Пред.",
        "nav_next": "След. ▶",
        "status_ready": "Готов к работе. Переведено: {trans}/{total} ({pct}%)",
        "status_scanning": "Сканирование мода: {name}...",
        "status_translating": "Выполняется перевод...",
        "overflow_warning": "Текст в {ratio:.1f}x длиннее оригинала (+{pct}%)! Риск вылезания за кнопку.",
        "badge_new": "● НОВАЯ",
        "badge_changed": "● ИЗМЕНЕНА",
        "badge_ok": "✓ Готово",
        "badge_empty": "○ Пусто",
        "badge_long": "▲ ДЛИННАЯ",
        "tooltip_mods": "Открыть или скрыть панель библиотеки установленных модов",
        "tooltip_browse": "Выбрать любую папку с модом вручную на диске",
        "tooltip_auto_trans": "Автоматически перевести все непереведенные строки",
        "tooltip_build": "Скомпилировать перевод мода (DLL или CSV) в папке мода",
        "tooltip_install": "Собрать и установить перевод в папку Mods/ игры с маркировкой [RU]",
        "tooltip_engine": "Настройки движков перевода (Google, DeepL, Ollama/AI, Глоссарий)",
        "tooltip_lang": "Целевой язык локализации мода",
        "tooltip_ui_lang": "Переключить язык интерфейса программы (RU / EN)",
        "tooltip_save_next": "Сохранить перевод и перейти к следующей строке (Ctrl+Enter)",
        "tooltip_concise": "Предложить краткий вариант без потери смысла",
        "tooltip_prev": "Предыдущая строка (Alt+Up)",
        "tooltip_next": "Следующая строка (Alt+Down)",
        "tooltip_new_top": "Переместить новые и измененные строки в начало таблицы",
        "up_to_date": "✓ Актуален",
        "update_badge": "Обновлен v{ver}",
        "installed_badge": "Установлен перевод",
        "diff_banner": "В обновлении мода обнаружено новых строк: {new_count}, изменено: {mod_count}.",
        "meta_file_prefix": "Метод / Файл:",
        "sec_glossary": "ИГРОВОЙ ГЛОССАРИЙ & КОНТЕКСТ",
        "sec_machine_ai": "МАШИННЫЙ & AI ПЕРЕВОД",
        "no_suggestions": "Нет доступных вариантов",
        "src_neural": "Нейросеть ({model})",
        "src_current": "Текущий перевод",
        "src_draft": "Быстрый черновик",
        "src_glossary": "Игровой глоссарий",
        "src_concise": "Компактный (Интерфейс)",
        "src_orig": "Оригинал (Сброс)",
        "stats_summary": "Строк: {total} | Переведено: {done} ({pct}%)",
        "badge_installed": "✓ Установлен",
        "tooltip_refresh_mods": "Обновить список модов",
        "tooltip_insert_token": "Вставить '{tok}' в позицию курсора",
        "tooltip_ai_req": "Запросить перевод у нейросети ({engine})",
        "tooltip_google_req": "Запросить быстрый перевод у Google Translate",
        "tooltip_mod_update_avail": "В Workshop доступна новая версия: {ver} (установлена {inst})",
        # --- v2.5.0 ---
        "empty_title": "Перетащите папку мода в окно",
        "empty_sub": "или выберите мод в библиотеке слева, либо нажмите «Обзор»",
        "browse_title": "Выберите папку мода",
        "err_mod_not_found": "Папка мода не найдена!",
        "toast_loaded": "Загружен мод «{name}»: {count} строк",
        "err_load": "Ошибка загрузки мода: {err}",
        "toast_new_top": "Новые строки из обновления перемещены в начало!",
        "toast_concise_applied": "Применен краткий вариант для интерфейса",
        "saved_flash": "✓ Сохранено!",
        "requesting": "Запрос...",
        "toast_translated_by": "✓ Перевод получен от {engine}",
        "menu_edit": "Редактировать (F2)",
        "menu_translate": "Перевести строку",
        "menu_concise": "Сократить перевод",
        "menu_copy_orig": "Копировать оригинал",
        "menu_clear": "Очистить перевод",
        "warn_pick_mod": "Сначала выберите мод из библиотеки!",
        "warn_all_translated": "Все строки уже переведены!",
        "autotr_progress": "{engine}: {done}/{total} ({pct}%)",
        "autotr_stopping": "Остановка автоперевода...",
        "autotr_done_lbl": "✓ Завершено: {count} строк!",
        "autotr_done_toast": "Автоперевод завершен! Переведено {count} строк.",
        "status_translating_n": "Перевод: {done}/{total} строк...",
        "tooltip_stop_autotr": "Остановить автоперевод",
        "building": "Сборка...",
        "toast_build_ok": "Сборка успешна: {res}",
        "err_build": "Ошибка сборки: {err}",
        "installing": "Установка в игру...",
        "toast_installed": "Установлен в Mods/ с маркировкой [{lang}]: {name}",
        "err_install": "Ошибка установки в Mods/: {err}",
        "lib_scanning": "Сканирование библиотеки...",
        "lib_empty": "Моды не найдены",
        "lib_empty_hint": "Проверьте пути к Steam Workshop и папке Mods/ или откройте мод вручную",
        "lib_no_match": "Ничего не найдено",
        "no_models": "Модели не найдены",
        "eng_google": "Google NMT (бесплатно, быстро, без ключа)",
        "eng_deepl": "DeepL Free / Pro API",
        "eng_ollama": "Ollama / локальный AI (qwen2.5, deepseek, llama3)",
        "eng_custom": "Custom OpenAI / OpenRouter API",
        "lbl_deepl_key": "DeepL Auth Key:",
        "lbl_ollama": "Ollama URL и установленная модель:",
        "lbl_custom": "Custom API: URL / ключ / модель:",
        "lbl_models_found": "Найдено моделей: {count}",
        "lbl_models_loading": "Поиск моделей...",
        "logs_info": "Папка LLMLogs: {count} сессий ({size})",
        "btn_clear_logs": "Очистить логи LLM",
        "btn_open_logs": "Открыть папку",
        "btn_save_settings": "Сохранить настройки",
        "toast_settings_saved": "Настройки движка сохранены!",
        "toast_logs_cleared": "Удалено {count} файлов логов LLM",
        "progress_total": "Прогресс",
        "legend_hotkeys": "Ctrl+Enter — сохранить и далее   Alt+↑/↓ — навигация   Ctrl+1…3 — вариант",
        "loading_mod": "Загрузка…",
    },
    "en": {
        "app_title": "ProbablyTranslator - Mod Localization Studio for Probably Stolen",
        "btn_mods": "Mods ({count})",
        "btn_browse": "Browse...",
        "btn_auto_translate": "Auto-Translate",
        "btn_build": "Build",
        "btn_install": "To Game (Mods/)",
        "target_lang_label": "Target Language:",
        "ui_lang_label": "UI Lang:",
        "engine_label": "{engine}",
        "engine_settings_title": "Translation Engine Settings",
        "mod_lib_title": "MOD LIBRARY",
        "search_mods_placeholder": "Search mods...",
        "filter_all": "All",
        "filter_workshop": "Workshop",
        "filter_mods": "Mods/",
        "filter_untrans": "Untranslated",
        "filter_overflow": "UI Overflow",
        "filter_diff": "Updates (Diff)",
        "btn_new_to_top": "↑ New to Top",
        "search_strings_placeholder": "Search original or translation...",
        "col_num": "#",
        "col_type": "Type",
        "col_original": "Original Text",
        "col_translation": "Translation",
        "col_status": "Status",
        "context_title": "CONTEXT & TRANSLATION",
        "orig_box_title": "ORIGINAL",
        "trans_box_title": "YOUR TRANSLATION",
        "suggestions_title": "TRANSLATION VARIANTS",
        "btn_ai_request": "Request from {engine}",
        "char_count": "{lang} {count} chars",
        "btn_save_next": "✓ Save & Next (Ctrl+Enter)",
        "btn_translate_row": "Translate",
        "btn_copy_orig": "Original",
        "btn_clear_row": "Clear",
        "btn_concise": "Concise",
        "btn_concise_action": "Make Concise",
        "nav_prev": "◀ Prev",
        "nav_next": "Next ▶",
        "status_ready": "Ready. Translated: {trans}/{total} ({pct}%)",
        "status_scanning": "Scanning mod: {name}...",
        "status_translating": "Translating...",
        "overflow_warning": "Text is {ratio:.1f}x longer than original (+{pct}%)! UI clipping risk.",
        "badge_new": "● NEW",
        "badge_changed": "● MODIFIED",
        "badge_ok": "✓ Done",
        "badge_empty": "○ Empty",
        "badge_long": "▲ LONG",
        "tooltip_mods": "Toggle installed mod library drawer",
        "tooltip_browse": "Browse any mod folder manually on disk",
        "tooltip_auto_trans": "Auto-translate all untranslated strings",
        "tooltip_build": "Compile mod translation (DLL or CSV) in mod folder",
        "tooltip_install": "Build and install translation to game Mods/ folder with [RU] badge",
        "tooltip_engine": "Configure translation engine (Google, DeepL, Ollama/AI, Glossary)",
        "tooltip_lang": "Target language for mod localization",
        "tooltip_ui_lang": "Switch program interface language (RU / EN)",
        "tooltip_save_next": "Save translation and advance to next item (Ctrl+Enter)",
        "tooltip_concise": "Offer a compact alternative without losing meaning",
        "tooltip_prev": "Previous string (Alt+Up)",
        "tooltip_next": "Next string (Alt+Down)",
        "tooltip_new_top": "Move new and modified update strings to the top",
        "up_to_date": "✓ Up to date",
        "update_badge": "Updated v{ver}",
        "installed_badge": "Translation Installed",
        "diff_banner": "Mod update detected: {new_count} new strings, {mod_count} modified.",
        "meta_file_prefix": "Method / File:",
        "sec_glossary": "GAMING GLOSSARY & CONTEXT",
        "sec_machine_ai": "MACHINE & AI TRANSLATION",
        "no_suggestions": "No suggestions available",
        "src_neural": "Neural Model ({model})",
        "src_current": "Current Translation",
        "src_draft": "Quick Draft",
        "src_glossary": "Gaming Glossary",
        "src_concise": "Compact (UI)",
        "src_orig": "Original (Reset)",
        "stats_summary": "Strings: {total} | Translated: {done} ({pct}%)",
        "badge_installed": "✓ Installed",
        "tooltip_refresh_mods": "Refresh mod library",
        "tooltip_insert_token": "Insert '{tok}' at cursor position",
        "tooltip_ai_req": "Request translation from neural model ({engine})",
        "tooltip_google_req": "Request quick translation from Google Translate",
        "tooltip_mod_update_avail": "Workshop update available: {ver} (installed {inst})",
        # --- v2.5.0 ---
        "empty_title": "Drop a mod folder onto the window",
        "empty_sub": "or pick a mod from the library on the left, or press Browse",
        "browse_title": "Select mod folder",
        "err_mod_not_found": "Mod folder not found!",
        "toast_loaded": "Loaded mod '{name}': {count} strings",
        "err_load": "Failed to load mod: {err}",
        "toast_new_top": "New strings from the update moved to the top!",
        "toast_concise_applied": "Compact UI variant applied",
        "saved_flash": "✓ Saved!",
        "requesting": "Requesting...",
        "toast_translated_by": "✓ Translation received from {engine}",
        "menu_edit": "Edit (F2)",
        "menu_translate": "Translate string",
        "menu_concise": "Make concise",
        "menu_copy_orig": "Copy original",
        "menu_clear": "Clear translation",
        "warn_pick_mod": "Pick a mod from the library first!",
        "warn_all_translated": "All strings are already translated!",
        "autotr_progress": "{engine}: {done}/{total} ({pct}%)",
        "autotr_stopping": "Stopping auto-translate...",
        "autotr_done_lbl": "✓ Done: {count} strings!",
        "autotr_done_toast": "Auto-translate finished! Translated {count} strings.",
        "status_translating_n": "Translating: {done}/{total} strings...",
        "tooltip_stop_autotr": "Stop auto-translate",
        "building": "Building...",
        "toast_build_ok": "Build succeeded: {res}",
        "err_build": "Build failed: {err}",
        "installing": "Installing into the game...",
        "toast_installed": "Installed into Mods/ with [{lang}] marker: {name}",
        "err_install": "Install to Mods/ failed: {err}",
        "lib_scanning": "Scanning library...",
        "lib_empty": "No mods found",
        "lib_empty_hint": "Check the Steam Workshop and Mods/ paths, or open a mod manually",
        "lib_no_match": "Nothing found",
        "no_models": "No models found",
        "eng_google": "Google NMT (free, fast, no key)",
        "eng_deepl": "DeepL Free / Pro API",
        "eng_ollama": "Ollama / local AI (qwen2.5, deepseek, llama3)",
        "eng_custom": "Custom OpenAI / OpenRouter API",
        "lbl_deepl_key": "DeepL Auth Key:",
        "lbl_ollama": "Ollama URL & installed model:",
        "lbl_custom": "Custom API: URL / key / model:",
        "lbl_models_found": "Models found: {count}",
        "lbl_models_loading": "Looking for models...",
        "logs_info": "LLMLogs folder: {count} sessions ({size})",
        "btn_clear_logs": "Clear LLM logs",
        "btn_open_logs": "Open folder",
        "btn_save_settings": "Save settings",
        "toast_settings_saved": "Engine settings saved!",
        "toast_logs_cleared": "Deleted {count} LLM log files",
        "progress_total": "Progress",
        "legend_hotkeys": "Ctrl+Enter save & next   Alt+↑/↓ navigate   Ctrl+1…3 variant",
        "loading_mod": "Loading…",
    }
}

def t(key, **kwargs):
    bundle = I18N.get(CURRENT_UI_LANG, I18N["ru"])
    text = bundle.get(key, I18N["ru"].get(key, key))
    if kwargs:
        try: return text.format(**kwargs)
        except Exception: return text
    return text

def load_app_config():
    default_cfg = {
        "ui_lang": "ru",
        "engine": "google",
        "deepl_api_key": "",
        "ollama_url": "http://127.0.0.1:11434",
        "ollama_model": "qwen2.5:7b",
        "custom_api_url": "https://api.openai.com/v1",
        "custom_api_key": "",
        "custom_api_model": "gpt-4o-mini",
        "target_lang": "ru",
        "show_library": True,
        "concise_mode": True
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_cfg.update(data)
        except Exception: pass
    return default_cfg

def save_app_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"Error saving config: {ex}")

# -------------------------------------------------------------
# Sleek Universal Tooltip System
# -------------------------------------------------------------

class CTooltip:
    def __init__(self, widget, text_provider, delay_ms=350):
        self.widget = widget
        self.text_provider = text_provider
        self.delay_ms = delay_ms
        self.tip_window = None
        self._after_id = None

        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._schedule()

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _schedule(self):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _get_text(self):
        if callable(self.text_provider):
            return self.text_provider()
        return str(self.text_provider)

    def _show(self):
        txt = self._get_text()
        if self.tip_window or not txt:
            return
        try:
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        frame = tk.Frame(tw, bg="#1e222b", bd=1, relief="solid", highlightbackground="#3b4252", highlightthickness=1)
        frame.pack()
        label = tk.Label(
            frame,
            text=txt,
            justify="left",
            background="#1e222b",
            foreground="#e2e8f0",
            font=("Segoe UI", 9),
            padx=8,
            pady=4
        )
        label.pack()

    def _hide(self):
        if self.tip_window:
            try: self.tip_window.destroy()
            except Exception: pass
            self.tip_window = None

# -------------------------------------------------------------
# 100% Reliable Layout-Independent Clipboard Shortcuts
# -------------------------------------------------------------

def setup_textbox_clipboard(textbox, is_readonly=False, on_modify=None):
    """Binds Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+A, Ctrl+Z safely across Russian & English layouts."""
    underlying = getattr(textbox, "_textbox", textbox)

    def _copy(e=None):
        try:
            sel = underlying.get(tk.SEL_FIRST, tk.SEL_LAST)
            if sel:
                underlying.clipboard_clear()
                underlying.clipboard_append(sel)
        except tk.TclError: pass
        return "break"

    def _paste(e=None):
        if is_readonly: return "break"
        try:
            clip = underlying.clipboard_get()
            if clip:
                try: underlying.delete(tk.SEL_FIRST, tk.SEL_LAST)
                except tk.TclError: pass
                underlying.insert(tk.INSERT, clip)
                if on_modify: on_modify()
        except tk.TclError: pass
        return "break"

    def _cut(e=None):
        if is_readonly: return "break"
        _copy()
        try:
            underlying.delete(tk.SEL_FIRST, tk.SEL_LAST)
            if on_modify: on_modify()
        except tk.TclError: pass
        return "break"

    def _select_all(e=None):
        underlying.tag_add(tk.SEL, "1.0", tk.END)
        underlying.mark_set(tk.INSERT, tk.END)
        underlying.see(tk.INSERT)
        return "break"

    def _undo(e=None):
        if not is_readonly:
            try:
                underlying.edit_undo()
                if on_modify: on_modify()
            except tk.TclError: pass
        return "break"

    def _on_key(event):
        ctrl = bool(event.state & 0x4) or bool(event.state & 0x20000)
        if not ctrl:
            return None
        kc = event.keycode
        ch = event.char
        # Windows Virtual Key Codes & Control Chars
        if kc == 67 or ch == '\x03': return _copy()
        if kc == 86 or ch == '\x16': return _paste()
        if kc == 88 or ch == '\x18': return _cut()
        if kc == 65 or ch == '\x01': return _select_all()
        if kc == 90 or ch == '\x1a': return _undo()
        return None

    underlying.bind("<KeyPress>", _on_key, add="+")
    underlying.bind("<<Copy>>", _copy)
    underlying.bind("<<Paste>>", _paste)
    underlying.bind("<<Cut>>", _cut)

# -------------------------------------------------------------
# Win32 Safe 64-bit Drag & Drop
# -------------------------------------------------------------

def setup_native_drag_and_drop(root_window, on_drop_callback):
    """Safely registers Win32 DragAcceptFiles on all HWND children with 64-bit pointers."""
    if platform.system() != "Windows":
        return

    try:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        root_window.update_idletasks()
        root_hwnd = root_window.winfo_id()
        parent_hwnd = user32.GetParent(root_hwnd)

        hwnds = [root_hwnd]
        if parent_hwnd:
            hwnds.append(parent_hwnd)

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _enum_child(h, l):
            hwnds.append(h)
            return True

        user32.EnumChildWindows(root_hwnd, WNDENUMPROC(_enum_child), 0)

        for h in hwnds:
            try: shell32.DragAcceptFiles(h, True)
            except Exception: pass

        WM_DROPFILES = 0x0233
        GWL_WNDPROC = -4

        if hasattr(user32, 'SetWindowLongPtrW'):
            SetWindowLongPtr = user32.SetWindowLongPtrW
            SetWindowLongPtr.restype = ctypes.c_void_p
            SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        else:
            SetWindowLongPtr = user32.SetWindowLongW
            SetWindowLongPtr.restype = ctypes.c_long
            SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]

        CallWindowProc = user32.CallWindowProcW
        CallWindowProc.restype = ctypes.c_void_p
        CallWindowProc.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        old_procs = {}

        def _wndproc_hook(hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                hdrop = wparam
                try:
                    num_files = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    dropped = []
                    for i in range(num_files):
                        buf = ctypes.create_unicode_buffer(512)
                        shell32.DragQueryFileW(hdrop, i, buf, 512)
                        dropped.append(buf.value)
                    shell32.DragFinish(hdrop)
                    if dropped:
                        root_window.after(10, lambda: on_drop_callback(dropped))
                except Exception as ex:
                    print(f"Error handling dropped files: {ex}")
                return 0

            old = old_procs.get(hwnd)
            return CallWindowProc(old, hwnd, msg, wparam, lparam) if old else 0

        hook_instance = WNDPROC(_wndproc_hook)
        root_window._drag_hook_ref = hook_instance

        for h in hwnds:
            old_p = SetWindowLongPtr(h, GWL_WNDPROC, hook_instance)
            if old_p: old_procs[h] = old_p

        print(f"[Drag&Drop] Registered {len(hwnds)} HWNDs safely.")
    except Exception as ex:
        print(f"Drag&Drop setup warning: {ex}")

# -------------------------------------------------------------
# Gaming Glossary & Translation Engine
# -------------------------------------------------------------

GAMING_GLOSSARY_ZH_RU = {
    "已为您安排，明天专人上门。": "Всё оформлено, мастер прибудет завтра.",
    "已为您安排，明天专人上门": "Всё оформлено, мастер прибудет завтра",
    "已为您安排": "Всё оформлено",
    "明天专人上门": "завтра приедет специалист",
    "专人上门": "визит специалиста",
    "品种目录收录": "Каталог товаров: добавлено",
    "品种目录扫描失败": "Ошибка сканирования каталога",
    "品种目录读取": "Чтение каталога товаров",
    "品种目录": "Каталог товаров",
    "熟练度系统": "Система навыков",
    "熟练度": "Мастерство",
    "更好的水商操作体验": "Улучшенная торговля водой",
    "更好的交易显示": "Улучшенная торговля",
    "势力股市": "Фондовый рынок фракций",
    "肥皂工坊": "Мастерская мыла",
    "声望飘字": "Всплывающая репутация",
    "声望": "Репутация",
    "关闭所有窗口": "Закрыть все окна",
    "店铺助手": "Помощник магазина",
    "智能整理": "Умная сортировка",
    "议价面板靠左": "Панель торга слева",
    "鼠标键位支持": "Назначение кнопок мыши",
    "偷窃": "Карманная кража",
    "挂钩": "Настенный крюк",
    "开关店自动保存": "Автосохранение при открытии/закрытии",
    "小窝竞拍之王": "Король аукционов",
    "夜间拍卖": "Ночной аукцион",
    "窗口标签页": "Вкладки окон",
    "瞬时注水": "Быстрый долив воды",
    "黑客": "Хакер",
    "平板电脑功能集成": "Функции планшета",
    "全谱综合检测器": "Универсальный сканер",
    "加速": "Ускорение",
    "确定": "ОК",
    "取消": "Отмена",
    "保存": "Сохранить",
    "返回": "Назад",
    "退出": "Выход",
    "设置": "Настройки",
    "开启": "Включено",
    "关闭": "Выключено",
    "刷新": "Обновить",
    "价格": "Цена",
    "购买": "Купить",
    "出售": "Продать",
    "数量": "Количество",
    "金币": "Монеты",
    "仓库": "Склад",
    "背包": "Инвентарь",
    "进货": "Закупка",
    "补货": "Пополнение",
    "收银": "Касса",
    "顾客": "Покупатель",
    "员工": "Сотрудник",
    "警报": "Тревога",
    "保安": "Охранник",
    "小偷": "Вор",
    "小偷已被抓获": "Вор пойман",
    "商品已被盗": "Товар украден",
    "锁定": "Заблокировано",
    "解锁": "Разблокировано",
    "成功": "Успешно",
    "失败": "Ошибка",
}

def post_process_translation(orig: str, trans: str, target_lang="ru") -> str:
    if not trans: return trans
    orig_clean = orig.strip()
    if target_lang == "ru" and orig_clean in GAMING_GLOSSARY_ZH_RU:
        return GAMING_GLOSSARY_ZH_RU[orig_clean]

    res = trans.strip()
    if target_lang == "ru":
        res = re.sub(r'Для вас все было сделано,?\s*и завтра кто-то придет к вашей двери\.?', 'Всё оформлено, мастер прибудет завтра.', res, flags=re.IGNORECASE)
        res = re.sub(r'кто-то придет к вашей двери', 'прибудет специалист', res, flags=re.IGNORECASE)
        res = re.sub(r'к вашей двери', '', res, flags=re.IGNORECASE)
        res = re.sub(r'\bбыл сделан для вас\b', 'оформлен', res, flags=re.IGNORECASE)
        res = re.sub(r'\bбыло сделано для вас\b', 'оформлено', res, flags=re.IGNORECASE)
        res = re.sub(r'\s{2,}', ' ', res).strip()
        if len(orig_clean) <= 12 and not orig_clean.endswith(('。', '.', '!', '?')) and res.endswith('.'):
            res = res[:-1]
    return res

def mask_text(text):
    phs = re.findall(r'\{[0-9]+(?::[^}]+)?\}|\{[a-zA-Z_][a-zA-Z0-9_]*\}|<[^>]+>', text)
    masked = text
    for i, p in enumerate(phs):
        masked = masked.replace(p, f"__PH{i}__")
    return masked, phs

def unmask_text(text, phs):
    res = text
    for i, p in enumerate(phs):
        res = re.sub(rf'__\s*PH\s*{i}\s*__', lambda m, s=p: s, res, flags=re.IGNORECASE)
    return res

def translate_batch_google(batch_texts, target_lang, source_lang="auto"):
    if not batch_texts: return []
    masked_list = []
    all_phs = []
    for t_text in batch_texts:
        m, phs = mask_text(t_text)
        masked_list.append(m)
        all_phs.append(phs)

    text_to_send = "\n".join(masked_list)
    sl = "auto" if source_lang == "auto" else source_lang
    tl = target_lang

    url = f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={sl}&tl={tl}&dt=t&q=" + urllib.parse.quote(text_to_send)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            full_res = "".join([part[0] for part in data[0] if part[0]])
            parts = full_res.split("\n")
            if len(parts) == len(batch_texts):
                return [unmask_text(parts[i], all_phs[i]) for i in range(len(batch_texts))]
    except Exception as e:
        print(f"Google batch fallback ({target_lang}): {e}")

    results = []
    for i, t_text in enumerate(batch_texts):
        if not t_text.strip():
            results.append(t_text)
            continue
        try:
            m, phs = masked_list[i], all_phs[i]
            u = f"https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl={sl}&tl={tl}&dt=t&q=" + urllib.parse.quote(m)
            r = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(r, timeout=6) as res:
                d = json.loads(res.read().decode("utf-8"))
                tr = "".join([p[0] for p in d[0] if p[0]])
                results.append(unmask_text(tr, phs))
            time.sleep(0.04)
        except Exception:
            results.append(t_text)
    return results

def translate_batch_deepl(batch_texts, api_key, target_lang="ru", source_lang="auto"):
    if not batch_texts or not api_key: return []
    url = "https://api-free.deepl.com/v2/translate" if api_key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}", "Content-Type": "application/json"}

    masked_list = []
    all_phs = []
    for t_text in batch_texts:
        m, phs = mask_text(t_text)
        masked_list.append(m)
        all_phs.append(phs)

    tl = target_lang.upper()
    if tl == "EN": tl = "EN-US"
    if tl == "PT": tl = "PT-BR"

    body = {"text": masked_list, "target_lang": tl}
    if source_lang and source_lang != "auto": body["source_lang"] = source_lang.upper()

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        translated_items = [item["text"] for item in data.get("translations", [])]
        return [unmask_text(translated_items[i], all_phs[i]) for i in range(len(translated_items))]

def translate_batch_ai(batch_texts, api_url, api_key, model, target_lang="ru"):
    results = []
    prompt_lang = "Russian" if target_lang == "ru" else target_lang

    for text in batch_texts:
        if not text.strip():
            results.append(text)
            continue

        system_msg = (
            f"You are a professional video game localizer for an indie store/theft simulator. "
            f"Translate the text into natural, idiomatic, concise {prompt_lang}. "
            f"Preserve meaning accurately, keep UI buttons short. Preserve placeholders like {{0}}, {{1}}, <tags> intact. "
            f"Output ONLY the translated text, no quotes, no explanations."
        )

        t0 = time.time()
        res_str = ""

        try:
            if "localhost" in api_url or "127.0.0.1" in api_url or "11434" in api_url:
                # Ollama endpoint
                url = f"{api_url.rstrip('/')}/api/generate"
                payload = {
                    "model": model or "qwen2.5:7b",
                    "system": system_msg,
                    "prompt": text,
                    "stream": False
                }
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    res_str = data.get("response", "").strip()
            else:
                # OpenAI / OpenRouter format
                url = f"{api_url.rstrip('/')}/chat/completions"
                payload = {
                    "model": model or "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": text}
                    ],
                    "temperature": 0.3
                }
                headers = {"Content-Type": "application/json"}
                if api_key: headers["Authorization"] = f"Bearer {api_key}"
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    res_str = data["choices"][0]["message"]["content"].strip()

            dur = time.time() - t0
            log_llm_interaction(text, res_str, model, dur)
            results.append(res_str)

        except Exception as ex:
            print(f"AI translation fallback for '{text[:20]}': {ex}")
            fb = translate_batch_google([text], target_lang)[0]
            results.append(fb)

    return results

def translate_batch(batch_texts, target_lang, source_lang="auto", engine="google", deepl_key="", ollama_url="http://127.0.0.1:11434", ollama_model="qwen2.5:7b", custom_url="https://api.openai.com/v1", custom_key="", custom_model="gpt-4o-mini"):
    raw_results = []
    needed_batch = []
    needed_indices = []
    glossary_map = GAMING_GLOSSARY_ZH_RU if target_lang == "ru" else {}

    for i, orig in enumerate(batch_texts):
        orig_clean = orig.strip()
        if orig_clean in glossary_map:
            raw_results.append(glossary_map[orig_clean])
        else:
            raw_results.append(None)
            needed_batch.append(orig)
            needed_indices.append(i)

    if needed_batch:
        engine_res = []
        if engine == "deepl" and deepl_key:
            try: engine_res = translate_batch_deepl(needed_batch, deepl_key, target_lang, source_lang)
            except Exception as ex:
                print(f"DeepL API failed, fallback to Google: {ex}")
                engine_res = translate_batch_google(needed_batch, target_lang, source_lang)
        elif engine == "ollama" and ollama_url:
            try: engine_res = translate_batch_ai(needed_batch, ollama_url, "", ollama_model, target_lang)
            except Exception as ex:
                print(f"Ollama failed, fallback to Google: {ex}")
                engine_res = translate_batch_google(needed_batch, target_lang, source_lang)
        elif engine == "custom" and custom_url:
            try: engine_res = translate_batch_ai(needed_batch, custom_url, custom_key, custom_model, target_lang)
            except Exception as ex:
                print(f"Custom AI API failed, fallback to Google: {ex}")
                engine_res = translate_batch_google(needed_batch, target_lang, source_lang)
        else:
            engine_res = translate_batch_google(needed_batch, target_lang, source_lang)

        for idx, trans_val in zip(needed_indices, engine_res):
            raw_results[idx] = trans_val

    final_results = []
    for orig, trans in zip(batch_texts, raw_results):
        final_results.append(post_process_translation(orig, trans or orig, target_lang))

    return final_results

# -------------------------------------------------------------
# Crowdin-Style Multi-Variant Suggestions Generator
# -------------------------------------------------------------

def generate_crowdin_suggestions(orig: str, current_trans: str, target_lang="ru", ai_res=None, ai_engine="google", ai_model="", draft=None):
    """Generates 2-3 distinct translation suggestions with clear source labeling.

    Pure and instant: never touches the network. A machine draft for untranslated rows
    is fetched asynchronously by the UI and passed in via `draft`."""
    suggestions = []
    if not orig or not orig.strip():
        return suggestions

    orig_clean = orig.strip()

    # 1. AI result (if freshly requested by user)
    if ai_res and ai_res.strip() and ai_res.strip() != orig_clean:
        eng_label = ai_model if (ai_engine == "ollama" and ai_model) else ai_engine.upper()
        suggestions.append({
            "source": t("src_neural", model=eng_label),
            "text": ai_res.strip(),
            "badge_color": "#10b981",
            "border_color": "#059669"
        })

    # 2. Main / Current / Literary Translation
    primary = current_trans.strip() if current_trans else ""
    if not primary and not suggestions and draft:
        primary = draft.strip()

    if primary and all(s["text"] != primary for s in suggestions):
        suggestions.append({
            "source": t("src_current") if current_trans else t("src_draft"),
            "text": primary,
            "badge_color": "#38bdf8",
            "border_color": "#0284c7"
        })

    # 3. Gaming Glossary / Contextual Normalization
    gloss_val = None
    if target_lang == "ru":
        if orig_clean in GAMING_GLOSSARY_ZH_RU:
            gloss_val = GAMING_GLOSSARY_ZH_RU[orig_clean]
        else:
            temp = primary or orig_clean
            for k, v in GAMING_GLOSSARY_ZH_RU.items():
                if len(k) >= 2 and k in temp:
                    temp = temp.replace(k, v)
            if temp != primary and temp != orig_clean:
                gloss_val = temp

    if gloss_val and all(s["text"] != gloss_val for s in suggestions):
        suggestions.append({
            "source": t("src_glossary"),
            "text": gloss_val,
            "badge_color": "#34d399",
            "border_color": "#0d9488"
        })

    # 4. Meaning-Preserving Concise Variant
    base_for_concise = primary or (suggestions[0]["text"] if suggestions else orig_clean)
    concise = make_concise(orig_clean, base_for_concise)
    if concise and all(s["text"] != concise for s in suggestions):
        suggestions.append({
            "source": t("src_concise"),
            "text": concise,
            "badge_color": "#fbbf24",
            "border_color": "#d97706"
        })

    # 5. Original Text (clean reset fallback)
    if len(suggestions) < 3 and orig_clean and all(s["text"] != orig_clean for s in suggestions):
        suggestions.append({
            "source": t("src_orig"),
            "text": orig_clean,
            "badge_color": "#94a3b8",
            "border_color": "#3a4358"
        })

    return suggestions[:3]

_CONCISE_RULES = [(re.compile(p, re.IGNORECASE), rep) for p, rep in (
    (r'Для вас все было сделано,?\s*и завтра кто-то придет к вашей двери\.?', 'Мастер будет завтра'),
    (r'Всё оформлено, мастер прибудет завтра\.', 'Мастер будет завтра'),
    (r'Ошибка сканирования каталога товаров', 'Ошибка каталога'),
    (r'Добавлено в каталог товаров', 'В каталог добавлено'),
    (r'Автосохранение при открытии/закрытии магазина', 'Автосохранение магазина'),
    (r'Пожалуйста, выберите', 'Выберите'),
    (r'Нажмите для подтверждения', 'Подтвердить'),
    (r'Подтвердить действие', 'Подтвердить'),
    (r'Отменить действие', 'Отмена'),
    (r'Сохранить изменения', 'Сохранить'),
    (r'Вернуться назад', 'Назад'),
    (r'Закрыть окно', 'Закрыть'),
    (r'В настоящее время', 'Сейчас'),
    (r'В данный момент', 'Сейчас'),
    (r'Количество предметов', 'Кол-во'),
    (r'Количество товаров', 'Кол-во'),
    (r'Количество', 'Кол-во'),
    (r'Успешно сохранено', 'Сохранено'),
    (r'Успешно загружено', 'Загружено'),
    (r'Вы действительно хотите', 'Хотите'),
    (r'Секунд\b', 'сек.'),
    (r'Минут\b', 'мин.'),
    (r'Уровень\b', 'Ур.'),
    (r'Максимальное\b', 'Макс.'),
    (r'Минимальное\b', 'Мин.'),
    (r'крепления драйвера на рамку', 'драйвера кадра'),
    (r'крепления драйвера', 'драйвера'),
    (r'не удалось выполнить', 'сбой'),
    (r'пользовательский интерфейс', 'интерфейс'),
)]
_RE_PLEASE = re.compile(r'\bпожалуйста\b,?\s*', re.IGNORECASE)
_RE_SPACES = re.compile(r'\s{2,}')

@functools.lru_cache(maxsize=8192)
def make_concise(orig: str, trans: str) -> str:
    """Produces a meaning-preserving concise equivalent without losing punctuation like colons."""
    if not trans: return trans
    orig_str = orig.strip()
    res = trans.strip()

    # Detect trailing punctuation in original or translation to preserve it strictly!
    trailing_colon = orig_str.endswith(':') or orig_str.endswith('：') or res.endswith(':') or res.endswith('：')
    trailing_qmark = orig_str.endswith('?') or orig_str.endswith('？') or res.endswith('?')
    trailing_exclam = orig_str.endswith('!') or orig_str.endswith('！') or res.endswith('!')
    trailing_dots = orig_str.endswith('...') or orig_str.endswith('…') or res.endswith('...') or res.endswith('…')

    for rx, rep in _CONCISE_RULES:
        res = rx.sub(rep, res)

    res = _RE_PLEASE.sub('', res)
    res = _RE_SPACES.sub(' ', res).strip()

    res = res.rstrip('.:：!！?？')

    # Strictly re-attach trailing punctuation from original
    if trailing_colon: res += ':'
    elif trailing_qmark: res += '?'
    elif trailing_exclam: res += '!'
    elif trailing_dots: res += '...'
    elif len(orig_str) > 25 and orig_str.endswith('.'): res += '.'

    return res

@functools.lru_cache(maxsize=8192)
def analyze_ui_fit(orig: str, trans: str) -> dict:
    """Cached by (orig, trans): the result is a pure function of both strings."""
    orig_len = max(len(orig.strip()), 1)
    trans_len = len(trans.strip())
    ratio = trans_len / orig_len

    is_cjk = any('\u4e00' <= c <= '\u9fff' for c in orig)
    threshold = 3.0 if is_cjk else 1.8

    is_overflow = (trans_len > 14 and ratio > threshold) or (orig_len <= 6 and trans_len >= 18)
    concise_cand = make_concise(orig, trans)
    has_suggestion = concise_cand != trans and len(concise_cand) < len(trans)

    return {
        "orig_len": orig_len,
        "trans_len": trans_len,
        "ratio": ratio,
        "is_overflow_risk": is_overflow,
        "has_suggestion": has_suggestion,
        "concise_text": concise_cand
    }

TOKEN_REGEX = re.compile(r'\{[0-9]+(?::[^}]+)?\}|\{[a-zA-Z_][a-zA-Z0-9_]*\}|<[^>]+>')

# -------------------------------------------------------------
# Mod Scanner & Engine
# -------------------------------------------------------------

def parse_mod_manifest(folder_path):
    manifest_path = os.path.join(folder_path, "manifest.xml")
    data = {
        "id": os.path.basename(folder_path),
        "name": os.path.basename(folder_path),
        "author": "Unknown",
        "version": "1.0.0",
        "description": "",
        "upstream_id": "",
        "upstream_ver": "",
        "upstream_ws": ""
    }
    if os.path.exists(manifest_path):
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            for key in ["ID", "Name", "Author", "ModVersion", "Description", "UpstreamID", "UpstreamVersion", "UpstreamWorkshopID"]:
                elem = root.find(key)
                if elem is not None and elem.text:
                    k = key.lower()
                    if key == "ModVersion": k = "version"
                    elif key == "UpstreamID": k = "upstream_id"
                    elif key == "UpstreamVersion": k = "upstream_ver"
                    elif key == "UpstreamWorkshopID": k = "upstream_ws"
                    data[k] = elem.text.strip()
        except Exception: pass
    return data

def compare_versions(v1, v2):
    def parse_ver(v):
        nums = re.findall(r'\d+', v)
        return [int(n) for n in nums] if nums else [0]
    return parse_ver(v1) > parse_ver(v2)

def scan_installed_mods(workshop_dir=DEFAULT_WORKSHOP_MODS, game_mods_dir=DEFAULT_GAME_MODS):
    mods = []
    installed_translations = {}

    if os.path.exists(game_mods_dir):
        for entry in os.scandir(game_mods_dir):
            if entry.is_dir() and not entry.name.startswith(('.', '_')):
                info = parse_mod_manifest(entry.path)
                m_info = {
                    "id": info["id"],
                    "name": info["name"],
                    "author": info["author"],
                    "version": info["version"],
                    "description": info["description"],
                    "source": "Game Mods",
                    "path": entry.path,
                    "has_csv": os.path.exists(os.path.join(entry.path, "Localization")) or os.path.exists(os.path.join(entry.path, "Languages")),
                    "has_dll": any(f.endswith(".dll") and not f.endswith(".bak") for f in os.listdir(entry.path)),
                    "upstream_id": info["upstream_id"],
                    "upstream_ws": info["upstream_ws"],
                    "upstream_ver": info["upstream_ver"],
                    "has_update": False
                }
                mods.append(m_info)
                if info["upstream_ws"]: installed_translations[info["upstream_ws"]] = m_info
                clean_id = re.sub(r'_[a-z]{2}$', '', info["id"], flags=re.IGNORECASE)
                installed_translations[clean_id] = m_info
                clean_name = re.sub(r'\s*\[[a-zA-Z]{2}\]$', '', info["name"]).strip()
                installed_translations[clean_name] = m_info

    if os.path.exists(workshop_dir):
        for entry in os.scandir(workshop_dir):
            if entry.is_dir() and not entry.name.startswith(('.', '_')):
                info = parse_mod_manifest(entry.path)
                ws_id = entry.name
                matched = (installed_translations.get(ws_id) or installed_translations.get(info["id"]) or installed_translations.get(info["name"]))

                has_update = False
                installed_ver = ""
                if matched:
                    installed_ver = matched["version"]
                    if compare_versions(info["version"], installed_ver):
                        has_update = True
                        matched["has_update"] = True

                m_info = {
                    "id": info["id"],
                    "name": info["name"],
                    "author": info["author"],
                    "version": info["version"],
                    "description": info["description"],
                    "source": "Workshop",
                    "workshop_id": ws_id,
                    "path": entry.path,
                    "has_csv": os.path.exists(os.path.join(entry.path, "Localization")) or os.path.exists(os.path.join(entry.path, "Languages")),
                    "has_dll": any(f.endswith(".dll") and not f.endswith(".bak") for f in os.listdir(entry.path)),
                    "matched_installed": matched["path"] if matched else None,
                    "installed_ver": installed_ver,
                    "has_update": has_update
                }
                mods.append(m_info)

    return mods

class ModProject:
    def __init__(self, mod_path):
        self.mod_path = os.path.abspath(mod_path)
        self.strings = []
        self.by_index = {}
        self.translations = {}
        self.manifest = parse_mod_manifest(self.mod_path)
        self.is_csv_mod = False
        self.csv_loc_dir = None
        self.csv_base_file = None
        self.new_strings_count = 0
        self.changed_strings_count = 0
        self.detect_csv_localization()

    def detect_csv_localization(self):
        for sub in ["Localization", "localization", "Languages", "languages", "Loc"]:
            candidate = os.path.join(self.mod_path, sub)
            if os.path.isdir(candidate):
                csvs = [f for f in os.listdir(candidate) if f.lower().endswith(".csv")]
                if csvs:
                    self.is_csv_mod = True
                    self.csv_loc_dir = candidate
                    for prefer in ["zh.csv", "zh-CN.csv", "en.csv", "default.csv", csvs[0]]:
                        p = os.path.join(candidate, prefer)
                        if os.path.exists(p):
                            self.csv_base_file = p
                            break
                    break

    def rebuild_index(self):
        """O(1) lookup of a string record by its index (the UI used linear scans)."""
        self.by_index = {st["index"]: st for st in self.strings}

    def get_translations_cache_path(self, lang):
        return os.path.join(self.mod_path, f"translations_{lang}.json")

    def load_existing_translations(self, lang):
        found_map = {}
        cache_path = self.get_translations_cache_path(lang)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    found_map = json.load(f)
            except Exception: pass

        if self.is_csv_mod and self.csv_loc_dir:
            target_csv = os.path.join(self.csv_loc_dir, f"{lang}.csv")
            if os.path.exists(target_csv):
                try:
                    with open(target_csv, "r", encoding="utf-8-sig") as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) >= 2 and row[1].strip():
                                found_map[row[0].strip()] = row[1].strip()
                except Exception: pass

        self.translations = {}
        self.new_strings_count = 0
        self.changed_strings_count = 0

        for s in self.strings:
            idx = s["index"]
            orig = s["original"]
            key = s.get("key", "")

            if key and key in found_map:
                trans_val = found_map[key]
                self.translations[idx] = trans_val
                s["translation"] = trans_val
                s["status"] = "synced"
            elif orig in found_map:
                trans_val = found_map[orig]
                self.translations[idx] = trans_val
                s["translation"] = trans_val
                s["status"] = "synced"
            else:
                s["translation"] = ""
                s["status"] = "new"
                self.new_strings_count += 1

    def scan(self, target_lang="ru"):
        self.detect_csv_localization()

        if self.is_csv_mod and self.csv_base_file:
            self.strings = []
            idx = 0
            with open(self.csv_base_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row: continue
                    k = row[0].strip()
                    val = row[1].strip() if len(row) > 1 else k
                    self.strings.append({
                        "index": idx,
                        "key": k,
                        "original": val,
                        "translation": "",
                        "type": "CSV",
                        "status": "untranslated"
                    })
                    idx += 1
            self.rebuild_index()
            self.load_existing_translations(target_lang)
            return len(self.strings)

        if not os.path.exists(STRING_PATCHER_EXE):
            raise FileNotFoundError(f"StringPatcher.exe not found at: {STRING_PATCHER_EXE}")

        dll_files = [f for f in os.listdir(self.mod_path) if f.lower().endswith(".dll") and not f.lower().endswith(".bak")]
        if not dll_files:
            raise FileNotFoundError(f"No .dll files found in {self.mod_path}")

        def _scan_dll(dll_name):
            bak_path = os.path.join(self.mod_path, dll_name + ".bak")
            target_dll = bak_path if os.path.exists(bak_path) else os.path.join(self.mod_path, dll_name)

            temp_json = os.path.join(tempfile.gettempdir(), f"scan_{uuid.uuid4().hex[:8]}.json")
            cmd = [STRING_PATCHER_EXE, target_dll, temp_json, "--all"]
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", startupinfo=startupinfo)
            if proc.returncode != 0:
                print(f"[StringPatcher] Warning: {proc.stderr}")
                return dll_name, []

            found = []
            if os.path.exists(temp_json):
                try:
                    with open(temp_json, "r", encoding="utf-8") as f:
                        raw_list = json.load(f)
                    for item in raw_list:
                        orig = (item.get("orig") or item.get("zh") or "").strip()
                        if orig:
                            found.append(orig)
                finally:
                    try: os.remove(temp_json)
                    except Exception: pass
            return dll_name, found

        # Each DLL is disassembled by an independent subprocess, so scan them in parallel.
        # Results are merged in the original DLL order to keep indexes deterministic.
        if len(dll_files) > 1:
            with ThreadPoolExecutor(max_workers=min(4, len(dll_files))) as pool:
                scanned = list(pool.map(_scan_dll, dll_files))
        else:
            scanned = [_scan_dll(dll_files[0])]

        all_strings = []
        seen_orig = set()
        str_idx = 0
        for dll_name, found in scanned:
            for orig in found:
                if orig in seen_orig:
                    continue
                seen_orig.add(orig)
                all_strings.append({
                    "index": str_idx,
                    "original": orig,
                    "translation": "",
                    "type": "DLL",
                    "dll": dll_name,
                    "status": "untranslated"
                })
                str_idx += 1

        self.strings = all_strings
        self.rebuild_index()
        self.load_existing_translations(target_lang)
        return len(self.strings)

    def save_translations_cache(self, lang):
        cache_path = self.get_translations_cache_path(lang)
        try:
            cache_data = {}
            for s in self.strings:
                idx = s["index"]
                orig = s["original"]
                key = s.get("key")
                trans = self.translations.get(idx, "")
                if trans:
                    if key: cache_data[key] = trans
                    cache_data[orig] = trans
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def auto_translate(self, target_lang, progress_callback=None, cancel_check=None, engine="google", deepl_key="", ollama_url="http://127.0.0.1:11434", ollama_model="qwen2.5:7b", custom_url="", custom_key="", custom_model=""):
        untranslated = [s for s in self.strings if not self.translations.get(s["index"])]
        if not untranslated: return 0

        batch_size = 12
        total = len(untranslated)
        completed = 0

        for i in range(0, total, batch_size):
            if cancel_check and cancel_check():
                break

            chunk = untranslated[i:i+batch_size]
            texts = [c["original"] for c in chunk]
            trans = translate_batch(
                texts, target_lang=target_lang, engine=engine, deepl_key=deepl_key,
                ollama_url=ollama_url, ollama_model=ollama_model,
                custom_url=custom_url, custom_key=custom_key, custom_model=custom_model
            )
            for j, c in enumerate(chunk):
                if j < len(trans):
                    val = trans[j]
                    self.translations[c["index"]] = val
                    c["translation"] = val
                    c["status"] = "synced"

            completed += len(chunk)
            if progress_callback:
                progress_callback(completed, total, chunk[-1]["original"], trans[-1] if trans else "")

        self.save_translations_cache(target_lang)
        return completed

    def build(self, target_lang, output_dir=None):
        self.save_translations_cache(target_lang)

        if self.is_csv_mod and self.csv_loc_dir:
            out_folder = output_dir if output_dir else self.csv_loc_dir
            os.makedirs(out_folder, exist_ok=True)
            target_file = os.path.join(out_folder, f"{target_lang}.csv")
            with open(target_file, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                for s in self.strings:
                    key = s.get("key", f"str_{s['index']}")
                    trans = self.translations.get(s["index"], s["original"])
                    writer.writerow([key, trans])
            return f"Generated {target_lang}.csv successfully."

        dll_files = [f for f in os.listdir(self.mod_path) if f.lower().endswith(".dll") and not f.lower().endswith(".bak")]
        if not dll_files: return "No DLL files found."

        target_dir = output_dir if output_dir else self.mod_path
        os.makedirs(target_dir, exist_ok=True)

        patch_list = []
        for s in self.strings:
            trans = self.translations.get(s["index"], "").strip()
            if trans: patch_list.append({"orig": s["original"], "trans": trans})

        if not patch_list: return "No translated strings to apply."

        temp_json = os.path.join(tempfile.gettempdir(), f"patch_{uuid.uuid4().hex[:8]}.json")
        with open(temp_json, "w", encoding="utf-8") as f:
            json.dump(patch_list, f, ensure_ascii=False, indent=2)

        results = []
        try:
            for dll_name in dll_files:
                src_dll = os.path.join(self.mod_path, dll_name)
                bak_dll = os.path.join(self.mod_path, dll_name + ".bak")
                if not os.path.exists(bak_dll):
                    try: shutil.copy2(src_dll, bak_dll)
                    except Exception: pass

                input_dll = bak_dll if os.path.exists(bak_dll) else src_dll
                dest_dll = os.path.join(target_dir, dll_name)

                cmd = [STRING_PATCHER_EXE, input_dll, temp_json, dest_dll, target_lang]
                startupinfo = None
                if platform.system() == "Windows":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", startupinfo=startupinfo)
                if proc.returncode != 0: raise RuntimeError(f"Patching failed: {proc.stderr}")
                results.append(proc.stdout.strip())
        finally:
            if os.path.exists(temp_json):
                try: os.remove(temp_json)
                except Exception: pass

        return "\n".join(results)

    def install_to_game(self, target_lang, game_mods_path=DEFAULT_GAME_MODS):
        if not os.path.exists(game_mods_path):
            os.makedirs(game_mods_path, exist_ok=True)

        raw_name = self.manifest.get("name") or os.path.basename(self.mod_path)
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_name).strip('_')
        if not safe_name: safe_name = os.path.basename(self.mod_path)
        dest_folder = os.path.join(game_mods_path, f"{safe_name}_{target_lang.upper()}")

        if os.path.exists(dest_folder):
            shutil.rmtree(dest_folder, ignore_errors=True)

        shutil.copytree(self.mod_path, dest_folder, ignore=shutil.ignore_patterns("*.bak", "*.tmp", "__pycache__", "temp_*"))

        temp_proj = ModProject(dest_folder)
        temp_proj.translations = dict(self.translations)
        temp_proj.strings = list(self.strings)
        temp_proj.build(target_lang, output_dir=dest_folder)

        manifest_dest = os.path.join(dest_folder, "manifest.xml")
        orig_id = self.manifest.get("id") or os.path.basename(self.mod_path)
        orig_ver = self.manifest.get("version") or "1.0.0"
        ws_id = os.path.basename(self.mod_path)

        if os.path.exists(manifest_dest):
            try:
                tree = ET.parse(manifest_dest)
                root = tree.getroot()
                name_elem = root.find("Name")
                if name_elem is not None and name_elem.text:
                    if f"[{target_lang.upper()}]" not in name_elem.text:
                        name_elem.text = f"{name_elem.text} [{target_lang.upper()}]"

                id_elem = root.find("ID")
                if id_elem is not None and id_elem.text:
                    if not id_elem.text.endswith(f"_{target_lang}"):
                        id_elem.text = f"{id_elem.text}_{target_lang}"

                up_id = root.find("UpstreamID")
                if up_id is None: up_id = ET.SubElement(root, "UpstreamID")
                up_id.text = orig_id

                up_ver = root.find("UpstreamVersion")
                if up_ver is None: up_ver = ET.SubElement(root, "UpstreamVersion")
                up_ver.text = orig_ver

                up_ws = root.find("UpstreamWorkshopID")
                if up_ws is None: up_ws = ET.SubElement(root, "UpstreamWorkshopID")
                up_ws.text = ws_id

                tree.write(manifest_dest, encoding="utf-8", xml_declaration=True)
            except Exception as e:
                print(f"Warning writing manifest upstream: {e}")

        return dest_folder

# -------------------------------------------------------------
# Modern Studio GUI Application
# -------------------------------------------------------------

class Theme:
    """Design tokens shared by every widget (single source of truth for colors). Graphite + indigo."""
    BG = "#0a0c11"
    PANEL = "#10131a"
    CENTER = "#0c0f15"
    BAR = "#12151d"
    CARD = "#161a23"
    CARD_HOVER = "#1c212d"
    CARD_ACTIVE = "#1a2144"
    BORDER = "#232936"
    FIELD = "#1a1f2a"
    LINE = "#2b3242"
    SELECT = "#252c5e"
    HEAD = "#0e1118"
    ROW_ODD = "#12161e"
    TEXT = "#eef1f7"
    TEXT_SOFT = "#d7dbe6"
    MUTED = "#98a1b5"
    DIM = "#667086"
    ACCENT = "#6366f1"
    ACCENT_HOVER = "#4f46e5"
    ACCENT_LIGHT = "#a5b4fc"
    OK = "#34d399"
    WARN = "#fbbf24"
    ERR = "#f87171"
    # (fill, hover)
    BTN = {
        "ghost": ("#1a1f2a", "#252b3a"),
        "muted": ("#262c3a", "#323a4d"),
        "primary": ("#6366f1", "#4f46e5"),
        "success": ("#059669", "#047857"),
        "info": ("#262c3a", "#323a4d"),
        "warn": ("#b45309", "#92400e"),
        "danger": ("#b91c1c", "#991b1b"),
    }
    # (fill, border, text) - pill palette from AGENTS.md invariants
    PILLS = {
        "steam": ("#0b1e3b", "#38bdf8", "#38bdf8"),
        "mods": ("#062e1e", "#10b981", "#34d399"),
        "csv": ("#042724", "#14b8a6", "#2dd4bf"),
        "dll": ("#200d3d", "#a855f7", "#c084fc"),
        "update": ("#3a1503", "#f59e0b", "#fbbf24"),
        "installed": ("#052e16", "#16a34a", "#4ade80"),
    }


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def lerp_color(c1, c2, t):
    """Linear blend between two #rrggbb colors (t in 0..1)."""
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return t * t * (3 - 2 * t)


class Animator:
    """Tiny time-based tween engine on top of Tk's after(); one running tween per key.

    Time-based (not frame-counted), so animations keep their duration even if a frame is dropped."""

    def __init__(self, widget):
        self.w = widget
        self.jobs = {}

    def run(self, key, duration_ms, step, done=None, ease=ease_out_cubic):
        self.cancel(key)
        start = time.perf_counter()

        def tick():
            p = min(1.0, (time.perf_counter() - start) * 1000.0 / max(duration_ms, 1))
            try:
                step(ease(p))
            except tk.TclError:
                self.jobs.pop(key, None)
                return
            if p >= 1.0:
                self.jobs.pop(key, None)
                if done:
                    done()
            else:
                self.jobs[key] = self.w.after(15, tick)
        tick()

    def cancel(self, key):
        job = self.jobs.pop(key, None)
        if job is not None:
            try: self.w.after_cancel(job)
            except Exception: pass

    def cancel_all(self):
        for key in list(self.jobs):
            self.cancel(key)


NO_MODELS_SENTINEL = "Модели не найдены"


def _disp(text):
    """Single-line representation of a string for the table."""
    if "\n" in text or "\r" in text:
        return text.replace("\r", "").replace("\n", " ⏎ ")
    return text


def canvas_round_rect(c, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle on a Tk canvas (smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
           x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
           x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class SlimScrollbar(tk.Canvas):
    """Thin rounded overlay-style scrollbar: no arrows, thumb grows and brightens on hover."""

    def __init__(self, master, command, scale=1.0, bg=None):
        self.k = scale
        super().__init__(master, width=int(12 * scale), bg=bg or Theme.PANEL, bd=0, highlightthickness=0)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self._hv = 0.0
        self._drag = None
        self.anim = Animator(self)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._hover(1.0))
        self.bind("<Leave>", lambda e: self._hover(0.0) if self._drag is None else None)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _hover(self, target):
        frm = self._hv

        def _step(p):
            self._hv = frm + (target - frm) * p
            self._draw()
        self.anim.run("hv", 160, _step)

    def _geom(self):
        h = max(self.winfo_height(), 1)
        y1, y2 = self.first * h, self.last * h
        if y2 - y1 < 32 * self.k:
            y2 = y1 + 32 * self.k
            if y2 > h:
                y2, y1 = h, h - 32 * self.k
        return h, y1, y2

    def _draw(self):
        self.delete("all")
        if self.last - self.first >= 0.999:
            return
        h, y1, y2 = self._geom()
        w = max(self.winfo_width(), int(12 * self.k))
        tw = int((5 + 4 * self._hv) * self.k)
        color = lerp_color(Theme.LINE, Theme.ACCENT_LIGHT if self._drag else Theme.ACCENT, 0.15 + 0.85 * self._hv) if self._hv > 0 or self._drag else Theme.LINE
        x = w / 2
        r = tw / 2
        self.create_line(x, y1 + r, x, y2 - r, width=tw, capstyle="round", fill=color)

    def _press(self, e):
        h, y1, y2 = self._geom()
        if y1 <= e.y <= y2:
            self._drag = (e.y, self.first)
        else:
            span = self.last - self.first
            self.command("moveto", max(0.0, min(1.0 - span, e.y / h - span / 2)))
        self._draw()

    def _motion(self, e):
        if self._drag is None:
            return
        h = max(self.winfo_height(), 1)
        self.command("moveto", self._drag[1] + (e.y - self._drag[0]) / h)

    def _release(self, e):
        self._drag = None
        self._draw()


STATUS_STYLES = {
    # kind: (fill, border, text)
    "new": ("#1b1f4a", "#6366f1", "#a5b4fc"),
    "changed": ("#3a2a07", "#f59e0b", "#fbbf24"),
    "long": ("#3b1d08", "#f97316", "#fdba74"),
    "ok": ("#052e1f", "#10b981", "#34d399"),
    "empty": ("#1a1f2a", "#3a4358", "#98a1b5"),
}


class StringTable(tk.Frame):
    """Virtualized canvas table (replaces ttk.Treeview).

    Only the visible rows are drawn, so any number of strings opens instantly; rows get hover/selection
    fades, smooth wheel scrolling, a save flash, and the status column is drawn as real rounded tags."""

    def __init__(self, master, scale=1.0, on_select=None, on_context=None, on_activate=None):
        super().__init__(master, bg=Theme.PANEL, bd=0, highlightthickness=0)
        self.k = scale
        self.on_select = on_select or (lambda iid: None)
        self.on_context = on_context or (lambda iid, x, y: None)
        self.on_activate = on_activate or (lambda iid: None)
        self.anim = Animator(self)

        fam = "Segoe UI"
        self.f_cell = tkfont.Font(family=fam, size=-int(13 * scale))
        self.f_head = tkfont.Font(family=fam, size=-int(11 * scale), weight="bold")
        self.f_pill = tkfont.Font(family=fam, size=-int(10 * scale), weight="bold")
        self.f_num = tkfont.Font(family=fam, size=-int(12 * scale))

        self.row_h = int(40 * scale)
        self.head_h = int(38 * scale)
        self.w_num, self.w_type, self.w_status = int(54 * scale), int(70 * scale), int(150 * scale)
        self.split = 0.5

        self.heads = {"num": "#", "type": "Type", "original": "Original", "translation": "Translation", "status": "Status"}
        self.rows = []
        self.order = []
        self.index = {}
        self.sel = None
        self.hover = None
        self._top = 0.0
        self._target = 0.0
        self._sel_p = 1.0
        self._hover_mix = {}
        self._flash = {}
        self._reveal = None   # elapsed seconds of the "rows cascade in" effect, None when idle
        self._pending = None
        self._fit_cache = {}
        self._cache_w = 0
        self._drag_split = False

        self.head = tk.Canvas(self, height=self.head_h, bg=Theme.HEAD, bd=0, highlightthickness=0)
        self.head.pack(side=tk.TOP, fill=tk.X)
        body = tk.Frame(self, bg=Theme.PANEL, bd=0, highlightthickness=0)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.sb = SlimScrollbar(body, command=self._sb_command, scale=scale)
        self.sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(body, bg=Theme.PANEL, bd=0, highlightthickness=0, takefocus=1)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        c = self.canvas
        c.bind("<Configure>", self._on_resize)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        c.bind("<Button-1>", self._on_click)
        c.bind("<Double-Button-1>", self._on_double)
        c.bind("<Button-3>", self._on_right)
        c.bind("<MouseWheel>", self._on_wheel)
        c.bind("<Up>", lambda e: self._key_move(-1))
        c.bind("<Down>", lambda e: self._key_move(1))
        c.bind("<Prior>", lambda e: self._key_move(-self._page()))
        c.bind("<Next>", lambda e: self._key_move(self._page()))
        c.bind("<Home>", lambda e: self._key_move(-10 ** 9))
        c.bind("<End>", lambda e: self._key_move(10 ** 9))
        self.head.bind("<Configure>", lambda e: self._draw_head())
        self.head.bind("<Motion>", self._head_motion)
        self.head.bind("<B1-Motion>", self._head_drag)
        self.head.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag_split", False))
        self.head.bind("<ButtonPress-1>", self._head_press)

    # ---------------- public API ----------------
    @property
    def selected(self):
        return self.sel

    def set_headings(self, **kw):
        self.heads.update(kw)
        self._draw_head()

    def set_rows(self, rows, reset=False, animate=False):
        """rows: iterable of (iid, num, type, original, translation, kind, label)."""
        self.rows = [dict(iid=r[0], num=r[1], type=r[2], orig=r[3], trans=r[4], kind=r[5], label=r[6]) for r in rows]
        self.order = [r["iid"] for r in self.rows]
        self.index = {iid: i for i, iid in enumerate(self.order)}
        self._fit_cache.clear()
        self._hover_mix.clear()
        self.hover = None
        if self.sel not in self.index:
            self.sel = None
        if reset:
            self.anim.cancel("scroll")
            self._top = self._target = 0.0
        if animate:
            self._start_reveal()
        self.invalidate()

    def exists(self, iid):
        return iid in self.index

    def pos(self, iid):
        return self.index.get(iid)

    def update_row(self, iid, trans, kind, label):
        i = self.index.get(iid)
        if i is None:
            return
        self.rows[i].update(trans=trans, kind=kind, label=label)
        self._fit_cache.clear()
        self.invalidate()

    def select(self, iid, see=True):
        if iid not in self.index:
            return
        changed = iid != self.sel
        self.sel = iid
        if changed:
            self._sel_p = 0.0

            def _step(p):
                self._sel_p = p
                self.invalidate()
            self.anim.run("sel", 180, _step)
        if see:
            self.see(iid)
        self.invalidate()

    def see(self, iid):
        i = self.index.get(iid)
        if i is None:
            return
        h = max(self.canvas.winfo_height(), 1)
        top = i * self.row_h
        if top < self._target:
            self._scroll_to(top)
        elif top + self.row_h > self._target + h:
            self._scroll_to(top + self.row_h - h)

    def flash(self, iid):
        def _step(p):
            self._flash[iid] = 1.0 - p
            self.invalidate()

        def _done():
            self._flash.pop(iid, None)
            self.invalidate()
        self.anim.run(f"fl{iid}", 700, _step, done=_done)

    # ---------------- geometry ----------------
    def _cols(self):
        w = max(self.canvas.winfo_width(), int(400 * self.k))
        rest = max(w - self.w_num - self.w_type - self.w_status, int(240 * self.k))
        w_orig = int(rest * self.split)
        x_num = 0
        x_type = x_num + self.w_num
        x_orig = x_type + self.w_type
        x_trans = x_orig + w_orig
        x_status = x_trans + (rest - w_orig)
        return w, x_num, x_type, x_orig, x_trans, x_status

    def _fit(self, text, max_w, font):
        key = (text, max_w)
        hit = self._fit_cache.get(key)
        if hit is not None:
            return hit
        if font.measure(text) <= max_w:
            res = text
        else:
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if font.measure(text[:mid] + "…") <= max_w:
                    lo = mid
                else:
                    hi = mid - 1
            res = text[:lo] + "…"
        if len(self._fit_cache) > 4000:
            self._fit_cache.clear()
        self._fit_cache[key] = res
        return res

    # ---------------- drawing ----------------
    def _draw_head(self):
        h = self.head
        h.delete("all")
        w, x_num, x_type, x_orig, x_trans, x_status = self._cols()
        cy = self.head_h / 2
        pad = int(14 * self.k)
        kw = dict(font=self.f_head, fill=Theme.MUTED)
        h.create_text(x_num + self.w_num / 2, cy, text=self.heads["num"], **kw)
        h.create_text(x_type + self.w_type / 2, cy, text=self.heads["type"], **kw)
        h.create_text(x_orig + pad, cy, text=self.heads["original"], anchor="w", **kw)
        h.create_text(x_trans + pad, cy, text=self.heads["translation"], anchor="w", **kw)
        h.create_text(x_status + self.w_status / 2, cy, text=self.heads["status"], **kw)
        h.create_line(x_trans, self.head_h * 0.3, x_trans, self.head_h * 0.7, fill=Theme.LINE)
        h.create_line(0, self.head_h - 1, w, self.head_h - 1, fill=Theme.BORDER)

    def invalidate(self):
        if self._pending is None:
            self._pending = self.after_idle(self._redraw)

    def _start_reveal(self):
        t0 = time.perf_counter()

        def _step(p):
            self._reveal = (time.perf_counter() - t0)
            self.invalidate()

        def _done():
            self._reveal = None
            self.invalidate()
        self.anim.run("reveal", 900, _step, done=_done, ease=lambda x: x)

    def _redraw(self):
        self._pending = None
        c = self.canvas
        c.delete("all")
        H = c.winfo_height()
        rh = self.row_h
        total = len(self.rows) * rh
        self._top = max(0.0, min(self._top, max(0, total - H)))
        first = int(self._top // rh)
        last = min(len(self.rows), int((self._top + H) // rh) + 2)
        cols = self._cols()
        for i in range(first, last):
            self._draw_row(i, i * rh - self._top, cols, first)
        if total <= H or total == 0:
            self.sb.set(0.0, 1.0)
        else:
            self.sb.set(self._top / total, min(1.0, (self._top + H) / total))

    def _draw_row(self, i, y0, cols, first):
        c = self.canvas
        row = self.rows[i]
        iid = row["iid"]
        W, x_num, x_type, x_orig, x_trans, x_status = cols
        rh = self.row_h
        y1 = y0 + rh
        cy = y0 + rh / 2

        # entrance cascade: colors blend in from the panel background, staggered by row
        fade = 1.0
        if self._reveal is not None:
            fade = max(0.0, min(1.0, (self._reveal - (i - first) * 0.035) / 0.25))
        base_bg = Theme.PANEL if i % 2 == 0 else Theme.ROW_ODD
        bg = base_bg
        hv = self._hover_mix.get(iid, 0.0)
        if hv > 0:
            bg = lerp_color(bg, "#1a2036", hv)
        selected = iid == self.sel
        if selected:
            bg = lerp_color(bg, Theme.SELECT, self._sel_p)
        fl = self._flash.get(iid, 0.0)
        if fl > 0:
            bg = lerp_color(bg, "#1b6b45", fl)

        def col(color):
            return color if fade >= 1.0 else lerp_color(Theme.PANEL, color, fade)

        c.create_rectangle(0, y0, W, y1, fill=bg if fade >= 1.0 else lerp_color(Theme.PANEL, bg, fade), outline="")
        if selected:
            bar_h = (rh - self.row_h * 0.3) * self._sel_p
            c.create_rectangle(0, cy - bar_h / 2, int(3 * self.k), cy + bar_h / 2, fill=Theme.ACCENT_LIGHT, outline="")

        pad = int(14 * self.k)
        c.create_text(x_num + self.w_num / 2, cy, text=str(row["num"]), font=self.f_num, fill=col(Theme.DIM))

        tkind = "csv" if row["type"] == "CSV" else "dll"
        tfill, tborder, tfg = Theme.PILLS[tkind]
        ttext = row["type"]
        tw = self.f_pill.measure(ttext) + int(14 * self.k)
        th = int(18 * self.k)
        tx = x_type + (self.w_type - tw) / 2
        canvas_round_rect(c, tx, cy - th / 2, tx + tw, cy + th / 2, th / 2, fill=col(tfill), outline=col(tborder))
        c.create_text(tx + tw / 2, cy, text=ttext, font=self.f_pill, fill=col(tfg))

        max_o = x_trans - x_orig - pad * 2
        c.create_text(x_orig + pad, cy, anchor="w", font=self.f_cell, fill=col("#ffffff" if selected else Theme.TEXT),
                      text=self._fit(_disp(row["orig"]), max_o, self.f_cell))
        if row["trans"]:
            max_t = x_status - x_trans - pad * 2
            c.create_text(x_trans + pad, cy, anchor="w", font=self.f_cell, fill=col(Theme.TEXT_SOFT),
                          text=self._fit(_disp(row["trans"]), max_t, self.f_cell))

        pfill, pborder, pfg = STATUS_STYLES.get(row["kind"], STATUS_STYLES["empty"])
        label = row["label"]
        pw = self.f_pill.measure(label) + int(22 * self.k)
        ph = int(22 * self.k)
        px = x_status + (self.w_status - pw) / 2
        canvas_round_rect(c, px, cy - ph / 2, px + pw, cy + ph / 2, ph / 2, fill=col(pfill), outline=col(pborder))
        c.create_text(px + pw / 2, cy, text=label, font=self.f_pill, fill=col(pfg))

    # ---------------- scrolling ----------------
    def _sb_command(self, *args):
        total = len(self.rows) * self.row_h
        H = self.canvas.winfo_height()
        if args and args[0] == "moveto" and total > H:
            self.anim.cancel("scroll")
            self._top = self._target = float(args[1]) * total
            self.invalidate()

    def _scroll_to(self, target, ms=170):
        total = len(self.rows) * self.row_h
        H = self.canvas.winfo_height()
        target = max(0.0, min(float(target), max(0, total - H)))
        self._target = target
        frm = self._top

        def _step(p):
            self._top = frm + (target - frm) * p
            self.invalidate()
        self.anim.run("scroll", ms, _step)

    def _on_wheel(self, e):
        step = self.row_h * 3 * (-1 if e.delta > 0 else 1)
        self._scroll_to(self._target + step, 190)
        self._on_motion(e)

    def _page(self):
        return max(1, int(self.canvas.winfo_height() // self.row_h) - 1)

    # ---------------- interaction ----------------
    def _row_at(self, y):
        i = int((y + self._top) // self.row_h)
        return self.order[i] if 0 <= i < len(self.order) else None

    def _set_hover(self, iid):
        if iid == self.hover:
            return
        old, self.hover = self.hover, iid
        for target_iid, to in ((old, 0.0), (iid, 1.0)):
            if target_iid is None:
                continue
            frm = self._hover_mix.get(target_iid, 0.0)

            def _step(p, k=target_iid, frm=frm, to=to):
                self._hover_mix[k] = frm + (to - frm) * p
                self.invalidate()
            self.anim.run(f"hv{target_iid}", 140, _step)
        self.canvas.configure(cursor="hand2" if iid else "")

    def _on_motion(self, e):
        self._set_hover(self._row_at(e.y))

    def _on_click(self, e):
        self.canvas.focus_set()
        iid = self._row_at(e.y)
        if iid:
            self.select(iid, see=False)
            self.on_select(iid)

    def _on_double(self, e):
        iid = self._row_at(e.y)
        if iid:
            self.on_activate(iid)

    def _on_right(self, e):
        iid = self._row_at(e.y)
        if iid:
            self.select(iid, see=False)
            self.on_context(iid, e.x_root, e.y_root)

    def _key_move(self, delta):
        if not self.order:
            return "break"
        if self.sel in self.index:
            nxt = max(0, min(len(self.order) - 1, self.index[self.sel] + delta))
        else:
            nxt = 0 if delta > 0 else len(self.order) - 1
        self.select(self.order[nxt], see=True)
        self.on_select(self.order[nxt])
        return "break"

    def _on_resize(self, e):
        if abs(e.width - self._cache_w) >= 2:
            self._cache_w = e.width
            self._fit_cache.clear()
            self._draw_head()
        self.invalidate()

    # ---------------- header: draggable original/translation divider ----------------
    def _divider_x(self):
        return self._cols()[4]

    def _head_motion(self, e):
        near = abs(e.x - self._divider_x()) < int(6 * self.k)
        self.head.configure(cursor="sb_h_double_arrow" if near else "")

    def _head_press(self, e):
        self._drag_split = abs(e.x - self._divider_x()) < int(6 * self.k)

    def _head_drag(self, e):
        if not self._drag_split:
            return
        w, x_num, x_type, x_orig, x_trans, x_status = self._cols()
        rest = max(w - self.w_num - self.w_type - self.w_status, 1)
        self.split = max(0.2, min(0.8, (e.x - x_orig) / rest))
        self._fit_cache.clear()
        self._draw_head()
        self.invalidate()


class ModLibraryView(tk.Frame):
    """Mod library drawn on ONE canvas.

    The old implementation built ~15 CustomTkinter widgets per card and rebuilt all of them on every
    search keystroke, filter click, language switch and mod load. A card is now ~12 canvas items and a
    full redraw takes a few milliseconds even for hundreds of mods.
    """

    def __init__(self, master, on_open, scale=1.0):
        super().__init__(master, bg=Theme.PANEL, bd=0, highlightthickness=0)
        self.on_open = on_open
        self.k = scale
        fam = "Segoe UI"
        self.f_name = tkfont.Font(family=fam, size=-int(13 * scale), weight="bold")
        self.f_meta = tkfont.Font(family=fam, size=-int(11 * scale))
        self.f_pill = tkfont.Font(family=fam, size=-int(10 * scale), weight="bold")
        self.f_msg = tkfont.Font(family=fam, size=-int(12 * scale))

        self.canvas = tk.Canvas(self, bg=Theme.PANEL, bd=0, highlightthickness=0, yscrollincrement=int(24 * scale))
        self.scroll = SlimScrollbar(self, command=lambda *a: self.canvas.yview(*a), scale=scale)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.anim = Animator(self)
        self._card_ids = []
        self.mods = []
        self.active = None
        self.message = ("", "")
        self._rects = []
        self._hover = -1
        self._redraw_job = None
        self._card_h = self.s(72)
        self._gap = self.s(8)
        self._pad = self.s(10)
        self._last_w = 0

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(-1))
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

    def s(self, v):
        return int(v * self.k)

    # ---- data ----
    def set_mods(self, mods, active_norm=None, animate=False):
        self.mods = mods
        self.active = active_norm
        self.redraw()
        if animate:
            self._fade_in_cards()

    def _fade_in_cards(self):
        """Staggered fade-in of the first cards (colors blend from the panel background)."""
        c = self.canvas
        for i, ids in enumerate(self._card_ids[:14]):
            finals = []
            for it in ids:
                for opt in ("fill", "outline"):
                    try: col = c.itemcget(it, opt)
                    except tk.TclError: continue
                    if isinstance(col, str) and col.startswith("#"):
                        finals.append((it, opt, col))
            for it, opt, col in finals:
                c.itemconfigure(it, **{opt: Theme.PANEL})

            def start(i=i, finals=finals):
                def step(p):
                    for it, opt, col in finals:
                        c.itemconfigure(it, **{opt: lerp_color(Theme.PANEL, col, p)})
                self.anim.run(f"card{i}", 300, step)
            self.after(i * 32, start)

    def set_active(self, active_norm):
        if active_norm != self.active:
            self.active = active_norm
            self.redraw()

    def set_message(self, title, hint=""):
        self.mods = []
        self.message = (title, hint)
        self.redraw()

    # ---- drawing ----
    def _on_resize(self, event):
        if abs(event.width - self._last_w) < 2:
            return
        self._last_w = event.width
        if self._redraw_job:
            try: self.after_cancel(self._redraw_job)
            except Exception: pass
        self._redraw_job = self.after(60, self.redraw)

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
               x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
               x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _pill(self, x, y, text, kind, anchor="w"):
        fill, border, fg = Theme.PILLS[kind]
        h = self.s(17)
        w = self.f_pill.measure(text) + self.s(14)
        x0 = x - w if anchor == "e" else x
        self._round_rect(x0, y, x0 + w, y + h, h // 2, fill=fill, outline=border, width=1)
        self.canvas.create_text(x0 + w / 2, y + h / 2, text=text, font=self.f_pill, fill=fg)
        return w

    def _fit(self, text, font, max_w):
        if max_w <= 0:
            return ""
        if font.measure(text) <= max_w:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + "…") <= max_w:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + "…"

    def redraw(self):
        self._redraw_job = None
        c = self.canvas
        self.anim.cancel_all()
        c.delete("all")
        self._rects = []
        self._card_ids = []
        self._hover = -1
        w = max(c.winfo_width(), self.s(220))

        if not self.mods:
            title, hint = self.message
            if title:
                c.create_text(w / 2, self.s(40), text=title, fill=Theme.MUTED, font=self.f_msg,
                              width=w - self.s(40), justify="center", anchor="n")
            if hint:
                c.create_text(w / 2, self.s(72), text=hint, fill=Theme.DIM, font=self.f_meta,
                              width=w - self.s(40), justify="center", anchor="n")
            c.configure(scrollregion=(0, 0, w, self.s(160)))
            c.yview_moveto(0)
            return

        x1, x2 = self._pad, w - self._pad
        for i, m in enumerate(self.mods):
            y1 = self._pad + i * (self._card_h + self._gap)
            y2 = y1 + self._card_h
            n0 = len(c.find_all())
            active = m.get("_norm") == self.active
            rect = self._round_rect(x1, y1, x2, y2, self.s(8),
                                    fill=Theme.CARD_ACTIVE if active else Theme.CARD,
                                    outline=Theme.ACCENT_LIGHT if active else Theme.BORDER, width=1)
            self._rects.append((rect, active))
            if active:
                c.create_rectangle(x1 + 1, y1 + self.s(12), x1 + self.s(4), y2 - self.s(12),
                                   fill=Theme.ACCENT_LIGHT, outline="")

            px = x1 + self.s(12)
            py = y1 + self.s(10)
            px += self._pill(px, py, "Steam" if m["source"] == "Workshop" else "Mods",
                             "steam" if m["source"] == "Workshop" else "mods") + self.s(5)
            self._pill(px, py, "CSV" if m["has_csv"] else "DLL", "csv" if m["has_csv"] else "dll")

            if m.get("has_update"):
                self._pill(x2 - self.s(10), py, f"Update v{m['version']}", "update", anchor="e")
            elif m.get("matched_installed") or m["source"] == "Game Mods":
                self._pill(x2 - self.s(10), py, t("badge_installed"), "installed", anchor="e")

            tx = x1 + self.s(12)
            max_w = x2 - tx - self.s(10)
            c.create_text(tx, y1 + self.s(40), anchor="w", font=self.f_name,
                          fill="#ffffff" if active else Theme.TEXT_SOFT,
                          text=self._fit(m["name"], self.f_name, max_w))
            if m.get("has_update") and m.get("installed_ver"):
                sub, sub_color = f"v{m['installed_ver']}  →  v{m['version']}", Theme.WARN
            else:
                sub = f"v{m['version']}"
                if m.get("author") and m["author"] != "Unknown":
                    sub += f"  •  {m['author']}"
                sub_color = Theme.MUTED
            c.create_text(tx, y1 + self.s(58), anchor="w", font=self.f_meta, fill=sub_color,
                          text=self._fit(sub, self.f_meta, max_w))
            self._card_ids.append(c.find_all()[n0:])

        total = self._pad * 2 + len(self.mods) * self._card_h + (len(self.mods) - 1) * self._gap
        c.configure(scrollregion=(0, 0, w, total))

    # ---- interaction ----
    def _index_at(self, y_canvas):
        step = self._card_h + self._gap
        rel = y_canvas - self._pad
        if rel < 0:
            return -1
        i = int(rel // step)
        if i >= len(self.mods) or rel - i * step > self._card_h:
            return -1
        return i

    def _set_hover(self, i):
        if i == self._hover:
            return
        c = self.canvas
        old = self._hover
        if 0 <= old < len(self._rects):
            rect, active = self._rects[old]
            self._fade_rect(rect, Theme.CARD_ACTIVE if active else Theme.CARD)
        if 0 <= i < len(self._rects):
            rect, active = self._rects[i]
            if not active:
                self._fade_rect(rect, Theme.CARD_HOVER)
        c.configure(cursor="hand2" if i >= 0 else "")
        self._hover = i

    def _fade_rect(self, rect, to):
        c = self.canvas
        try: frm = c.itemcget(rect, "fill")
        except tk.TclError: return
        if not (isinstance(frm, str) and frm.startswith("#")):
            c.itemconfigure(rect, fill=to)
            return
        self.anim.run(f"h{rect}", 130, lambda p: c.itemconfigure(rect, fill=lerp_color(frm, to, p)))

    def _on_motion(self, e):
        self._set_hover(self._index_at(self.canvas.canvasy(e.y)))

    def _on_click(self, e):
        i = self._index_at(self.canvas.canvasy(e.y))
        if i >= 0:
            if i < len(self._rects):
                self.canvas.itemconfigure(self._rects[i][0], fill=Theme.ACCENT)
                self._fade_rect(self._rects[i][0], Theme.CARD_ACTIVE if self._rects[i][1] else Theme.CARD_HOVER)
            self.on_open(self.mods[i]["path"])

    def _on_wheel(self, e):
        first, last = self.canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return
        self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units")
        self._set_hover(self._index_at(self.canvas.canvasy(e.y)))


class ModernTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_app_config()
        global CURRENT_UI_LANG
        CURRENT_UI_LANG = self.cfg.get("ui_lang", "ru")

        self.title(t("app_title"))
        self.geometry("1420x890")
        self.minsize(1280, 750)

        if os.path.exists(ICON_FILE):
            try: self.iconbitmap(ICON_FILE)
            except Exception: pass

        try:
            self.k = max(1.0, float(self.winfo_fpixels("1i")) / 96.0)
        except Exception:
            self.k = 1.0

        self.project = None
        self.installed_mods = []
        self.selected_item_id = None
        self.current_filter = "all"
        self.lib_filter = "all"
        self.show_library = self.cfg.get("show_library", True)
        self.translation_engine = self.cfg.get("engine", "google")
        self.deepl_key = self.cfg.get("deepl_api_key", "")
        self.ollama_url = self.cfg.get("ollama_url", "http://127.0.0.1:11434")
        self.ollama_model = self.cfg.get("ollama_model", "qwen2.5:7b")
        self.custom_url = self.cfg.get("custom_api_url", "https://api.openai.com/v1")
        self.custom_key = self.cfg.get("custom_api_key", "")
        self.custom_model = self.cfg.get("custom_api_model", "gpt-4o-mini")

        self.cancel_translation_flag = False
        self.active_suggestions = []

        # runtime state
        self._jobs = {}            # debounce timers by key
        self._load_token = 0       # invalidates stale background mod loads
        self._scan_token = 0
        self._toast_job = None
        self._busy_count = 0
        self._dirty = False
        self._project_lang = "ru"
        self._draft_cache = {}
        self._draft_pending = set()
        self._lib_query_cache = None
        self.anim = Animator(self)
        self._ap_val = 0.0
        self._total_val = 0.0
        self._toast_y = 60
        self._chip_kind = None
        self._chip_cols = (Theme.FIELD, Theme.LINE)
        self._shown_done = 0
        self._ap_active = False

        self._make_fonts()
        self._init_ttk_styles()
        self._build_top_bar()
        self._build_status_bar()      # packed BOTTOM before the main area so it is never squeezed out
        self._build_main_layout()

        self.update_idletasks()
        setup_native_drag_and_drop(self, self.on_files_dropped)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_toast()
        self.after(50, self.refresh_mod_library)
        self._breathe()
        try:
            self.attributes("-alpha", 0.0)
            self.after(30, self._fade_in_window)
        except Exception:
            pass

    def _fade_in_window(self):
        def _step(p):
            try: self.attributes("-alpha", p)
            except Exception: pass
        self.anim.run("win", 260, _step)

    # -------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------

    def _make_fonts(self):
        ff = "Segoe UI"
        self.F = {
            "btn": ctk.CTkFont(family=ff, size=12, weight="bold"),
            "reg": ctk.CTkFont(family=ff, size=12),
            "small": ctk.CTkFont(family=ff, size=11),
            "small_b": ctk.CTkFont(family=ff, size=11, weight="bold"),
            "tiny": ctk.CTkFont(family=ff, size=10),
            "tiny_b": ctk.CTkFont(family=ff, size=10, weight="bold"),
            "title": ctk.CTkFont(family=ff, size=14, weight="bold"),
            "mono": ctk.CTkFont(family="Consolas", size=10),
            "status": ctk.CTkFont(family=ff, size=12),
            "status_b": ctk.CTkFont(family=ff, size=12, weight="bold"),
        }
        # plain-tk fonts (pooled widgets): explicit pixel sizes scaled for DPI
        self.tkF = {
            "sugg": tkfont.Font(family=ff, size=-int(13 * self.k), weight="bold"),
            "sugg_src": tkfont.Font(family=ff, size=-int(11 * self.k)),
            "sugg_hdr": tkfont.Font(family=ff, size=-int(11 * self.k), weight="bold"),
            "kbd": tkfont.Font(family="Consolas", size=-int(11 * self.k)),
            "chip": tkfont.Font(family="Consolas", size=-int(11 * self.k)),
            "empty_t": tkfont.Font(family=ff, size=-int(20 * self.k), weight="bold"),
            "empty_s": tkfont.Font(family=ff, size=-int(13 * self.k)),
        }

    def _mk_btn(self, parent, text, command, kind="ghost", width=None, height=36, font="btn", pill=False, **kw):
        fg, hover = Theme.BTN[kind]
        pill_r = height // 2
        opts = dict(text=text, height=height, font=self.F[font], fg_color=fg, hover_color=hover,
                    corner_radius=pill_r if pill else 10, cursor="hand2", command=command)
        if width:
            opts["width"] = width
        opts.update(kw)
        return ctk.CTkButton(parent, **opts)

    def _debounce(self, key, ms, fn):
        job = self._jobs.get(key)
        if job:
            try: self.after_cancel(job)
            except Exception: pass
        self._jobs[key] = self.after(ms, fn)

    def _set_busy(self, on, text=None):
        """Reference-counted busy indicator (indeterminate bar in the status bar)."""
        self._busy_count = max(0, self._busy_count + (1 if on else -1))
        if self._busy_count > 0:
            if text:
                self.status_lbl.configure(text=text, text_color=Theme.ACCENT_LIGHT)
            if not self.busy_bar.winfo_ismapped():
                self.busy_bar.pack(side=tk.LEFT, padx=(0, 12))
                self.busy_bar.start()
        else:
            self.busy_bar.stop()
            self.busy_bar.pack_forget()

    def _build_toast(self):
        self.toast = ctk.CTkFrame(self, fg_color=Theme.CARD, corner_radius=12, border_width=1, border_color=Theme.LINE)
        self.toast_bar = ctk.CTkFrame(self.toast, width=4, height=14, corner_radius=2, fg_color=Theme.ACCENT)
        self.toast_bar.pack(side=tk.LEFT, padx=(10, 0), pady=8)
        self.toast_lbl = ctk.CTkLabel(self.toast, text="", font=self.F["small"], text_color=Theme.TEXT,
                                      wraplength=int(440 * self.k), justify="left")
        self.toast_lbl.pack(side=tk.LEFT, padx=(8, 14), pady=6)
        self._toast_visible = False

    def _toast_slide(self, to_y, done=None):
        frm = self._toast_y

        def _step(p):
            self._toast_y = int(frm + (to_y - frm) * p)
            self.toast.place(relx=0.5, rely=1.0, y=self._toast_y, anchor="s")
        self.anim.run("toast", 260, _step, done=done)

    def toast_show(self, msg, level="info", duration_ms=2500):
        """Floating snackbar: slides up above the status bar, then slides away."""
        color = {"success": Theme.OK, "warning": Theme.WARN, "error": Theme.ERR}.get(level, Theme.ACCENT_LIGHT)
        self.toast_lbl.configure(text=msg)
        self.toast_bar.configure(fg_color=color)
        self.toast.configure(border_color=lerp_color(Theme.LINE, color, 0.45))
        if not self._toast_visible:
            self._toast_y = 60
            self._toast_visible = True
        self.toast.lift()
        self._toast_slide(-50)
        self._debounce("toast_hide", max(1200, duration_ms) + 400, self._toast_hide)

    def _toast_hide(self):
        def _gone():
            self._toast_visible = False
            self.toast.place_forget()
        self._toast_slide(60, done=_gone)

    def _fade_fg(self, btn, to, ms=170):
        """Animated fg_color change for CTk buttons (filter chips, categories)."""
        try: frm = btn.cget("fg_color")
        except Exception: frm = to
        if not (isinstance(frm, str) and frm.startswith("#")) or frm == to:
            btn.configure(fg_color=to)
            return
        self.anim.run(f"fg{id(btn)}", ms, lambda p: btn.configure(fg_color=lerp_color(frm, to, p)))

    def _breathe(self):
        """Idle animation: the empty-state title gently pulses until a mod is loaded."""
        if self.project is not None:
            return
        k = (math.sin(time.perf_counter() * 1.6) + 1) / 2
        try: self.empty_title_lbl.configure(fg=lerp_color(Theme.DIM, Theme.TEXT, k))
        except Exception: pass
        self._jobs["breathe"] = self.after(70, self._breathe)

    def _on_close(self):
        try: self._autosave()
        except Exception: pass
        self.destroy()

    # -------------------------------------------------------------
    # Styles
    # -------------------------------------------------------------

    def _init_ttk_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Strip Treeview.field completely to eliminate harsh white border lines!
        self.style.layout("Crowdin.Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        self.style.configure(
            "Crowdin.Treeview",
            background=Theme.PANEL,
            foreground=Theme.TEXT,
            rowheight=int(38 * self.k),
            fieldbackground=Theme.PANEL,
            font=("Segoe UI", 10),
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            bordercolor=Theme.PANEL,
            lightcolor=Theme.PANEL,
            darkcolor=Theme.PANEL
        )
        self.style.map(
            "Crowdin.Treeview",
            background=[("selected", Theme.SELECT)],
            foreground=[("selected", "#ffffff")]
        )
        self.style.configure(
            "Crowdin.Treeview.Heading",
            background=Theme.HEAD,
            foreground=Theme.MUTED,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            borderwidth=0,
            bordercolor=Theme.HEAD,
            padding=(10, 10)
        )
        self.style.map("Crowdin.Treeview.Heading", background=[("active", Theme.FIELD)])

        self.style.configure(
            "Crowdin.Vertical.TScrollbar",
            gripcount=0,
            background=Theme.LINE,
            troughcolor=Theme.PANEL,
            bordercolor=Theme.PANEL,
            arrowcolor=Theme.MUTED,
            relief="flat",
            borderwidth=0,
            arrowsize=11
        )
        self.style.map(
            "Crowdin.Vertical.TScrollbar",
            background=[("active", "#3a4358"), ("pressed", Theme.ACCENT)],
            arrowcolor=[("active", "#ffffff")]
        )

    # -------------------------------------------------------------
    # Top bar
    # -------------------------------------------------------------

    def _build_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, fg_color=Theme.BAR, height=62, corner_radius=0)
        self.top_bar.pack(side=tk.TOP, fill=tk.X)
        self.top_bar.pack_propagate(False)

        # Right cluster is packed first so it always keeps its room; the left cluster shrinks instead.
        right_grp = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_grp.pack(side=tk.RIGHT, padx=12, pady=10)

        self.btn_install = self._mk_btn(right_grp, t("btn_install"), self.do_install, "primary", width=135)
        self.btn_install.pack(side=tk.RIGHT, padx=(6, 0))
        CTooltip(self.btn_install, lambda: t("tooltip_install"))

        self.btn_build = self._mk_btn(right_grp, t("btn_build"), self.do_build, "muted", width=95)
        self.btn_build.pack(side=tk.RIGHT, padx=4)
        CTooltip(self.btn_build, lambda: t("tooltip_build"))

        self.btn_translate = self._mk_btn(right_grp, t("btn_auto_translate"), self.start_auto_translate, "success", width=125)
        self.btn_translate.pack(side=tk.RIGHT, padx=4)
        CTooltip(self.btn_translate, lambda: t("tooltip_auto_trans"))

        self.btn_engine = self._mk_btn(right_grp, self.translation_engine.upper(), self.open_engine_settings,
                                       "ghost", width=100, font="small")
        self.btn_engine.pack(side=tk.RIGHT, padx=6)
        CTooltip(self.btn_engine, lambda: t("tooltip_engine"))

        lang_frame = ctk.CTkFrame(right_grp, fg_color="transparent")
        lang_frame.pack(side=tk.RIGHT, padx=6)

        self.lbl_target_lang = ctk.CTkLabel(lang_frame, text=t("target_lang_label"), font=self.F["small_b"], text_color=Theme.MUTED)
        self.lbl_target_lang.pack(side=tk.LEFT, padx=(0, 4))

        saved_code = self.cfg.get("target_lang", "ru")
        initial = next((f"{n} [{c}]" for n, c in LANGUAGES if c == saved_code), "Russian [ru]")
        self.lang_var = ctk.StringVar(value=initial)
        self.lang_menu = ctk.CTkOptionMenu(
            lang_frame, variable=self.lang_var, values=[f"{name} [{code}]" for name, code in LANGUAGES],
            width=135, height=34, font=self.F["small"], fg_color=Theme.FIELD, button_color=Theme.LINE,
            command=self.on_lang_changed
        )
        self.lang_menu.pack(side=tk.LEFT)
        CTooltip(self.lang_menu, lambda: t("tooltip_lang"))

        ui_lang_frame = ctk.CTkFrame(right_grp, fg_color=Theme.FIELD, corner_radius=8)
        ui_lang_frame.pack(side=tk.RIGHT, padx=(0, 8))

        self.btn_ui_ru = ctk.CTkButton(
            ui_lang_frame, text="RU", width=52, height=30, font=self.F["tiny_b"], corner_radius=6,
            fg_color=Theme.ACCENT if CURRENT_UI_LANG == "ru" else "transparent", hover_color=Theme.ACCENT_HOVER,
            cursor="hand2", command=lambda: self.switch_ui_lang("ru")
        )
        self.btn_ui_ru.pack(side=tk.LEFT, padx=2, pady=2)

        self.btn_ui_en = ctk.CTkButton(
            ui_lang_frame, text="EN", width=52, height=30, font=self.F["tiny_b"], corner_radius=6,
            fg_color=Theme.ACCENT if CURRENT_UI_LANG == "en" else "transparent", hover_color=Theme.ACCENT_HOVER,
            cursor="hand2", command=lambda: self.switch_ui_lang("en")
        )
        self.btn_ui_en.pack(side=tk.LEFT, padx=2, pady=2)
        CTooltip(ui_lang_frame, lambda: t("tooltip_ui_lang"))

        left_grp = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_grp.pack(side=tk.LEFT, padx=12, pady=10)

        self.btn_toggle_lib = self._mk_btn(left_grp, t("btn_mods", count=0), self.toggle_library, "ghost", width=115)
        self.btn_toggle_lib.pack(side=tk.LEFT, padx=(0, 6))
        CTooltip(self.btn_toggle_lib, lambda: t("tooltip_mods"))

        self.btn_browse = self._mk_btn(left_grp, t("btn_browse"), self.browse_mod_folder, "ghost", width=90, font="reg")
        self.btn_browse.pack(side=tk.LEFT, padx=4)
        CTooltip(self.btn_browse, lambda: t("tooltip_browse"))

        self.mod_badge = ctk.CTkLabel(left_grp, text="", font=self.F["small_b"], text_color=Theme.ACCENT_LIGHT)
        self.mod_badge.pack(side=tk.LEFT, padx=10)
        self._left_grp = left_grp

        # Auto-translate progress sits in the free space of the top bar (between the two clusters)
        self.top_progress_frame = ctk.CTkFrame(self.top_bar, height=38, fg_color=Theme.CARD, corner_radius=12,
                                               border_width=1, border_color=Theme.ACCENT)
        self.top_progress_frame.pack_propagate(False)
        self.top_progress_lbl = ctk.CTkLabel(self.top_progress_frame, text="", width=150, anchor="w", font=self.F["small_b"], text_color=Theme.TEXT)
        self.top_progress_lbl.pack(side=tk.LEFT, padx=(14, 6))
        self.btn_top_cancel = self._mk_btn(self.top_progress_frame, "■", self.cancel_auto_translate, "danger", width=30, height=26, font="tiny_b")
        self.btn_top_cancel.pack(side=tk.RIGHT, padx=(6, 6))
        CTooltip(self.btn_top_cancel, lambda: t("tooltip_stop_autotr"))
        self.top_progress_pct = ctk.CTkLabel(self.top_progress_frame, text="0%", width=44, anchor="e", font=self.F["small_b"], text_color=Theme.ACCENT_LIGHT)
        self.top_progress_pct.pack(side=tk.RIGHT, padx=(6, 0))
        self.top_progress_bar = ctk.CTkProgressBar(self.top_progress_frame, height=8, corner_radius=4, fg_color=Theme.PANEL, progress_color=Theme.ACCENT)
        self.top_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.top_progress_bar.set(0)

    def switch_ui_lang(self, lang_code):
        global CURRENT_UI_LANG
        CURRENT_UI_LANG = lang_code
        self.cfg["ui_lang"] = lang_code
        save_app_config(self.cfg)

        self.btn_ui_ru.configure(fg_color=Theme.ACCENT if lang_code == "ru" else "transparent")
        self.btn_ui_en.configure(fg_color=Theme.ACCENT if lang_code == "en" else "transparent")

        self.title(t("app_title"))
        self.btn_toggle_lib.configure(text=t("btn_mods", count=len(self.installed_mods)))
        self.btn_browse.configure(text=t("btn_browse"))
        self.btn_install.configure(text=t("btn_install"))
        self.btn_build.configure(text=t("btn_build"))
        self.btn_translate.configure(text=t("btn_auto_translate"))
        self.lbl_target_lang.configure(text=t("target_lang_label"))

        # Mod library
        self.lbl_lib_title.configure(text=t("mod_lib_title"))
        self.lib_search_entry.configure(placeholder_text=t("search_mods_placeholder"))
        self.btn_cat_all.configure(text=t("filter_all"))
        self.btn_cat_ws.configure(text=t("filter_workshop"))
        self.btn_cat_mods.configure(text=t("filter_mods"))
        self.render_library()

        # Table
        self.table.set_headings(type=t("col_type"), original=t("col_original"),
                                translation=t("col_translation"), status=t("col_status"))
        self.search_entry.configure(placeholder_text=t("search_strings_placeholder"))
        self.btn_filter_all.configure(text=t("filter_all"))
        self.btn_sort_new.configure(text=t("btn_new_to_top"))
        self.empty_title_lbl.configure(text=t("empty_title"))
        self.empty_sub_lbl.configure(text=t("empty_sub"))

        # Right workspace
        self.ws_context_title.configure(text=t("context_title"))
        self.ws_orig_title.configure(text=t("orig_box_title"))
        self.ws_trans_title.configure(text=t("trans_box_title"))
        self.ws_sugg_title.configure(text=t("suggestions_title"))
        self.btn_concise.configure(text=t("btn_concise_action"))
        self.update_ai_btn_text()
        self.btn_save_next.configure(text=t("btn_save_next"))
        self.btn_row_orig.configure(text=t("btn_copy_orig"))
        self.btn_row_clear.configure(text=t("btn_clear_row"))
        self.btn_concise_sec.configure(text=t("btn_concise"))
        self.btn_nav_prev.configure(text=t("nav_prev"))
        self.btn_nav_next.configure(text=t("nav_next"))
        self.hotkeys_lbl.configure(text=t("legend_hotkeys"))
        self.ws_meta_lbl.configure(text=f"{t('meta_file_prefix')} -")
        self.update_stats()
        self.apply_filter()

        if self.selected_item_id is not None and self.project:
            self._apply_selection(force=True)

    # -------------------------------------------------------------
    # Layout
    # -------------------------------------------------------------

    def _build_main_layout(self):
        self.main_container = ctk.CTkFrame(self, fg_color=Theme.BG, corner_radius=0)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self.lib_frame = ctk.CTkFrame(self.main_container, fg_color=Theme.PANEL, width=300, corner_radius=0)
        self.lib_frame.pack_propagate(False)
        if self.show_library:
            self.lib_frame.pack(side=tk.LEFT, fill=tk.Y)

        self._build_library_panel()

        # Right workspace is packed before the center so the table never pushes it out of the window.
        self.right_workspace = ctk.CTkFrame(self.main_container, fg_color=Theme.PANEL, width=430, corner_radius=0)
        self.right_workspace.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.right_workspace.pack_propagate(False)

        self.center_frame = ctk.CTkFrame(self.main_container, fg_color=Theme.CENTER, corner_radius=0, border_width=0)
        self.center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_table_panel()
        self._build_crowdin_workspace()

    def _build_library_panel(self):
        hdr = ctk.CTkFrame(self.lib_frame, fg_color="transparent", height=42)
        hdr.pack(fill=tk.X, padx=12, pady=(10, 4))
        hdr.pack_propagate(False)

        self.lbl_lib_title = ctk.CTkLabel(hdr, text=t("mod_lib_title"), font=self.F["small_b"], text_color=Theme.MUTED)
        self.lbl_lib_title.pack(side=tk.LEFT)

        btn_refresh = self._mk_btn(hdr, "↻", self.refresh_mod_library, "ghost", width=30, height=28, font="reg")
        btn_refresh.pack(side=tk.RIGHT)
        CTooltip(btn_refresh, lambda: t("tooltip_refresh_mods"))

        self.lib_search_entry = ctk.CTkEntry(
            self.lib_frame, placeholder_text=t("search_mods_placeholder"), height=32, font=self.F["small"],
            fg_color=Theme.FIELD, border_color=Theme.LINE
        )
        self.lib_search_entry.pack(fill=tk.X, padx=12, pady=4)
        self.lib_search_entry.bind("<KeyRelease>", lambda e: self._debounce("lsearch", 120, self.render_library))

        cat_bar = ctk.CTkFrame(self.lib_frame, fg_color="transparent")
        cat_bar.pack(fill=tk.X, padx=12, pady=4)

        self.btn_cat_all = self._mk_btn(cat_bar, t("filter_all"), lambda: self.set_lib_filter("all"), "primary", width=56, height=26, font="tiny", pill=True)
        self.btn_cat_all.configure(fg_color=Theme.ACCENT)
        self.btn_cat_all.pack(side=tk.LEFT, padx=1)
        self.btn_cat_ws = self._mk_btn(cat_bar, t("filter_workshop"), lambda: self.set_lib_filter("workshop"), "ghost", width=76, height=26, font="tiny", pill=True)
        self.btn_cat_ws.pack(side=tk.LEFT, padx=1)
        self.btn_cat_mods = self._mk_btn(cat_bar, t("filter_mods"), lambda: self.set_lib_filter("mods"), "ghost", width=56, height=26, font="tiny", pill=True)
        self.btn_cat_mods.pack(side=tk.LEFT, padx=1)

        self.lib_view = ModLibraryView(self.lib_frame, on_open=self.load_mod, scale=self.k)
        self.lib_view.pack(fill=tk.BOTH, expand=True, padx=(6, 4), pady=6)
        self.lib_view.set_message(t("lib_scanning"))

    def _build_table_panel(self):
        filter_bar = ctk.CTkFrame(self.center_frame, fg_color=Theme.BAR, corner_radius=0)
        filter_bar.pack(fill=tk.X)

        row1 = ctk.CTkFrame(filter_bar, fg_color="transparent")
        row1.pack(fill=tk.X, padx=12, pady=(10, 4))

        self.btn_sort_new = self._mk_btn(row1, t("btn_new_to_top"), self.sort_new_to_top, "ghost", width=110, height=30, font="small")
        self.btn_sort_new.pack(side=tk.RIGHT, padx=(8, 0))
        CTooltip(self.btn_sort_new, lambda: t("tooltip_new_top"))

        self.search_entry = ctk.CTkEntry(
            row1, placeholder_text=t("search_strings_placeholder"), height=32, font=self.F["small"],
            fg_color=Theme.FIELD, border_color=Theme.LINE
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._debounce("tsearch", 180, lambda: self.apply_filter(reset=True)))

        row2 = ctk.CTkFrame(filter_bar, fg_color="transparent")
        row2.pack(fill=tk.X, padx=12, pady=(0, 10))

        self.btn_filter_all = self._mk_btn(row2, t("filter_all"), lambda: self.set_table_filter("all"), "primary", width=50, height=28, font="small", pill=True)
        self.btn_filter_all.configure(fg_color=Theme.ACCENT)
        self.btn_filter_all.pack(side=tk.LEFT, padx=(0, 4))
        self.btn_filter_untrans = self._mk_btn(row2, t("filter_untrans"), lambda: self.set_table_filter("untranslated"), "ghost", width=105, height=28, font="small", pill=True)
        self.btn_filter_untrans.pack(side=tk.LEFT, padx=2)
        self.btn_filter_overflow = self._mk_btn(row2, t("filter_overflow"), lambda: self.set_table_filter("overflow"), "ghost", width=130, height=28, font="small", pill=True)
        self.btn_filter_overflow.pack(side=tk.LEFT, padx=2)
        self.btn_filter_diff = self._mk_btn(row2, t("filter_diff"), lambda: self.set_table_filter("diff"), "ghost", width=125, height=28, font="small", pill=True)
        self.btn_filter_diff.pack(side=tk.LEFT, padx=2)

        table_container = tk.Frame(self.center_frame, bg=Theme.PANEL, bd=0, highlightthickness=0, relief="flat")
        table_container.pack(fill=tk.BOTH, expand=True)
        self.table_container = table_container

        self.table = StringTable(table_container, scale=self.k,
                                 on_select=lambda iid: self.on_tree_select(),
                                 on_context=self.on_table_context,
                                 on_activate=lambda iid: self.focus_editor())
        self.table.pack(fill=tk.BOTH, expand=True)
        self.table.set_headings(num="#", type=t("col_type"), original=t("col_original"),
                                translation=t("col_translation"), status=t("col_status"))
        self.table.canvas.bind("<F2>", lambda e: self.focus_editor())

        # Empty state (shown until a mod is loaded). Created now so Win32 drag&drop covers it too.
        self.empty_state = tk.Frame(table_container, bg=Theme.PANEL)
        self.empty_title_lbl = tk.Label(self.empty_state, text=t("empty_title"), bg=Theme.PANEL, fg=Theme.TEXT_SOFT, font=self.tkF["empty_t"])
        self.empty_title_lbl.pack(pady=(0, 6))
        self.empty_sub_lbl = tk.Label(self.empty_state, text=t("empty_sub"), bg=Theme.PANEL, fg=Theme.DIM, font=self.tkF["empty_s"], wraplength=int(380 * self.k), justify="center")
        self.empty_sub_lbl.pack()
        self._update_empty_state()

    def _update_empty_state(self):
        if self.project is None:
            if "breathe" not in self._jobs or not self._jobs["breathe"]:
                self._breathe()
            self.empty_state.place(relx=0.5, rely=0.45, anchor="center")
            self.empty_state.lift()
        else:
            self.empty_state.place_forget()

    def _build_crowdin_workspace(self):
        ws = self.right_workspace

        hdr = ctk.CTkFrame(ws, fg_color="transparent", height=38)
        hdr.pack(fill=tk.X, padx=12, pady=(8, 2))
        hdr.pack_propagate(False)

        self.ws_context_title = ctk.CTkLabel(hdr, text=t("context_title"), font=self.F["small_b"], text_color=Theme.MUTED)
        self.ws_context_title.pack(side=tk.LEFT)

        self.ws_status_chip = ctk.CTkFrame(hdr, fg_color=Theme.FIELD, corner_radius=12, border_width=1, border_color="#64748b")
        self.ws_status_chip.pack(side=tk.RIGHT)
        self.ws_status_badge = ctk.CTkLabel(self.ws_status_chip, text=t("badge_empty"), font=self.F["tiny_b"], text_color=Theme.MUTED, padx=8, pady=2)
        self.ws_status_badge.pack()

        # 1. Original text card
        orig_card = ctk.CTkFrame(ws, fg_color=Theme.CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER)
        orig_card.pack(fill=tk.X, padx=12, pady=4)

        orig_top = ctk.CTkFrame(orig_card, fg_color="transparent")
        orig_top.pack(fill=tk.X, padx=10, pady=(6, 2))
        ctk.CTkFrame(orig_top, width=4, height=12, fg_color=Theme.ACCENT_LIGHT, corner_radius=2).pack(side=tk.LEFT, padx=(0, 6))
        self.ws_orig_title = ctk.CTkLabel(orig_top, text=t("orig_box_title"), font=self.F["tiny_b"], text_color=Theme.ACCENT_LIGHT)
        self.ws_orig_title.pack(side=tk.LEFT)
        self.ws_orig_len_lbl = ctk.CTkLabel(orig_top, text=t("char_count", lang="cn", count=0), font=self.F["tiny"], text_color=Theme.MUTED)
        self.ws_orig_len_lbl.pack(side=tk.RIGHT)

        self.ws_orig_box = ctk.CTkTextbox(orig_card, height=56, font=self.F["small"], fg_color=Theme.PANEL, text_color=Theme.TEXT, wrap="word", border_width=0,
                                      scrollbar_button_color=Theme.LINE, scrollbar_button_hover_color=Theme.ACCENT)
        self.ws_orig_box.pack(fill=tk.X, padx=8, pady=(0, 6))
        setup_textbox_clipboard(self.ws_orig_box, is_readonly=True)

        # 2. UI-fit card
        self.ws_fit_card = ctk.CTkFrame(ws, fg_color=Theme.FIELD, corner_radius=8, border_width=1, border_color=Theme.LINE)
        self.ws_fit_card.pack(fill=tk.X, padx=12, pady=3)

        fit_inner = ctk.CTkFrame(self.ws_fit_card, fg_color="transparent")
        fit_inner.pack(fill=tk.X, padx=8, pady=4)
        self.ws_meta_lbl = ctk.CTkLabel(fit_inner, text=f"{t('meta_file_prefix')} -", font=self.F["tiny"], text_color=Theme.DIM)
        self.ws_meta_lbl.pack(anchor="w")

        self.ws_overflow_alert = ctk.CTkFrame(self.ws_fit_card, fg_color="#2a1e08", corner_radius=8, border_width=1, border_color="#b45309")
        self.ws_overflow_alert_lbl = ctk.CTkLabel(self.ws_overflow_alert, text="", font=self.F["small_b"], text_color="#fef3c7", justify="left", wraplength=int(230 * self.k))
        self.ws_overflow_alert_lbl.pack(side=tk.LEFT, padx=8, pady=4, fill=tk.X, expand=True)
        self.btn_concise = self._mk_btn(self.ws_overflow_alert, t("btn_concise_action"), self.apply_concise_suggestion, "warn", height=26, font="small_b")
        self.btn_concise.pack(side=tk.RIGHT, padx=6, pady=3)
        self._alert_visible = False

        # 3. Translation editor card
        trans_card = ctk.CTkFrame(ws, fg_color=Theme.CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER)
        trans_card.pack(fill=tk.BOTH, expand=True, padx=12, pady=3)

        trans_top = ctk.CTkFrame(trans_card, fg_color="transparent")
        trans_top.pack(fill=tk.X, padx=10, pady=(6, 2))
        ctk.CTkFrame(trans_top, width=4, height=12, fg_color=Theme.OK, corner_radius=2).pack(side=tk.LEFT, padx=(0, 6))
        self.ws_trans_title = ctk.CTkLabel(trans_top, text=t("trans_box_title"), font=self.F["tiny_b"], text_color=Theme.OK)
        self.ws_trans_title.pack(side=tk.LEFT)
        self.ws_trans_len_lbl = ctk.CTkLabel(trans_top, text=t("char_count", lang="RU", count=0), font=self.F["tiny"], text_color=Theme.MUTED)
        self.ws_trans_len_lbl.pack(side=tk.RIGHT)

        # Placeholder chips: a fixed pool of lightweight labels (no widget churn per row).
        self.chips_frame = tk.Frame(trans_card, bg=Theme.CARD, height=int(24 * self.k))
        self.chips_frame.pack(fill=tk.X, padx=8, pady=(1, 3))
        self._chip_pool = []
        for _ in range(8):
            chip = tk.Label(self.chips_frame, text="", bg=Theme.LINE, fg=Theme.TEXT_SOFT, font=self.tkF["chip"], padx=6, pady=1, cursor="hand2")
            chip._tok = ""
            chip.bind("<Button-1>", lambda e, c=chip: self.insert_token(c._tok))
            chip.bind("<Enter>", lambda e, c=chip: c.configure(bg=Theme.ACCENT))
            chip.bind("<Leave>", lambda e, c=chip: c.configure(bg=Theme.LINE))
            CTooltip(chip, lambda c=chip: t("tooltip_insert_token", tok=c._tok))
            self._chip_pool.append(chip)

        self.ws_trans_box = ctk.CTkTextbox(trans_card, height=90, font=self.F["reg"], fg_color=Theme.PANEL, text_color=Theme.TEXT, wrap="word", border_width=0,
                                       scrollbar_button_color=Theme.LINE, scrollbar_button_hover_color=Theme.ACCENT)
        self.ws_trans_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        setup_textbox_clipboard(self.ws_trans_box, is_readonly=False, on_modify=self._on_translation_modified)
        self.ws_trans_box.bind("<KeyRelease>", lambda e: self._debounce("modified", 40, self._on_translation_modified))

        self.ws_trans_box.bind("<Control-Return>", lambda e: self.save_and_next())
        self.ws_trans_box.bind("<Control-KP_Enter>", lambda e: self.save_and_next())
        self.ws_trans_box.bind("<Alt-Up>", lambda e: self.nav_prev())
        self.ws_trans_box.bind("<Alt-Down>", lambda e: self.nav_next())
        for i in range(1, 6):
            self.ws_trans_box.bind(f"<Control-Key-{i}>", lambda e, idx=i - 1: self.apply_suggestion_by_index(idx))

        # 4. Suggestions panel (pooled rows)
        self.suggestions_frame = ctk.CTkFrame(ws, fg_color=Theme.BAR, corner_radius=12, border_width=1, border_color=Theme.BORDER)
        self.suggestions_frame.pack(fill=tk.X, padx=12, pady=3)

        sugg_top = ctk.CTkFrame(self.suggestions_frame, fg_color="transparent")
        sugg_top.pack(fill=tk.X, padx=8, pady=(4, 2))
        self.ws_sugg_title = ctk.CTkLabel(sugg_top, text=t("suggestions_title"), font=self.F["tiny_b"], text_color=Theme.MUTED)
        self.ws_sugg_title.pack(side=tk.LEFT)

        btns_sugg = ctk.CTkFrame(sugg_top, fg_color="transparent")
        btns_sugg.pack(side=tk.RIGHT)

        eng_name = self.ollama_model if self.translation_engine == "ollama" else self.translation_engine.upper()
        self.btn_request_ai = self._mk_btn(btns_sugg, eng_name, self.translate_active_row_ai, "ghost", height=24, font="tiny_b",
                                           border_width=1, border_color=Theme.ACCENT_HOVER, hover_color=Theme.ACCENT)
        self.btn_request_ai.pack(side=tk.LEFT, padx=(0, 4))
        CTooltip(self.btn_request_ai, lambda: t("tooltip_ai_req", engine=self.ollama_model if self.translation_engine == "ollama" else self.translation_engine.upper()))

        self.btn_request_google = self._mk_btn(btns_sugg, "Google", self.translate_active_row_google, "ghost", height=24, width=66, font="tiny_b",
                                               border_width=1, border_color=Theme.LINE, hover_color=Theme.ACCENT)
        self.btn_request_google.pack(side=tk.LEFT)
        CTooltip(self.btn_request_google, lambda: t("tooltip_google_req"))

        self.sugg_items_container = tk.Frame(self.suggestions_frame, bg=Theme.BAR)
        self.sugg_items_container.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._build_suggestion_pool()

        # 5. Action bar
        action_bar = ctk.CTkFrame(ws, fg_color="transparent")
        action_bar.pack(fill=tk.X, padx=12, pady=(4, 8))

        self.btn_save_next = self._mk_btn(action_bar, t("btn_save_next"), self.save_and_next, "success", height=38)
        self.btn_save_next.pack(fill=tk.X, pady=(0, 6))

        sec_bar = ctk.CTkFrame(action_bar, fg_color="transparent")
        sec_bar.pack(fill=tk.X)

        self.btn_row_orig = self._mk_btn(sec_bar, t("btn_copy_orig"), self.copy_from_orig, "muted", width=76, height=32, font="small")
        self.btn_row_orig.pack(side=tk.LEFT, padx=(0, 3))
        self.btn_row_clear = self._mk_btn(sec_bar, t("btn_clear_row"), self.clear_active_translation, "muted", width=72, height=32, font="small")
        self.btn_row_clear.pack(side=tk.LEFT, padx=3)
        self.btn_concise_sec = self._mk_btn(sec_bar, t("btn_concise"), self.apply_concise_suggestion, "warn", width=76, height=32, font="small")
        self.btn_concise_sec.pack(side=tk.LEFT, padx=3)
        CTooltip(self.btn_concise_sec, lambda: t("tooltip_concise"))

        self.btn_nav_next = self._mk_btn(sec_bar, t("nav_next"), self.nav_next, "ghost", width=64, height=32, font="small_b")
        self.btn_nav_next.pack(side=tk.RIGHT, padx=(3, 0))
        CTooltip(self.btn_nav_next, lambda: t("tooltip_next"))
        self.btn_nav_prev = self._mk_btn(sec_bar, t("nav_prev"), self.nav_prev, "ghost", width=64, height=32, font="small_b")
        self.btn_nav_prev.pack(side=tk.RIGHT, padx=3)
        CTooltip(self.btn_nav_prev, lambda: t("tooltip_prev"))

        self.hotkeys_lbl = ctk.CTkLabel(ws, text=t("legend_hotkeys"), font=self.F["tiny"], text_color=Theme.DIM)
        self.hotkeys_lbl.pack(pady=(0, 6))

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, fg_color=Theme.BG, height=38, corner_radius=0)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(self.status_bar, text=t("status_ready", trans=0, total=0, pct=0), font=self.F["status"], text_color=Theme.MUTED)
        self.status_lbl.pack(side=tk.LEFT, padx=(12, 8))

        self.busy_bar = ctk.CTkProgressBar(self.status_bar, width=110, height=4, mode="indeterminate", fg_color=Theme.PANEL, progress_color=Theme.ACCENT_LIGHT)

        self.stats_lbl = ctk.CTkLabel(self.status_bar, text="", font=self.F["status_b"], text_color=Theme.ACCENT_LIGHT)
        self.stats_lbl.pack(side=tk.RIGHT, padx=12)

        self.total_bar = ctk.CTkProgressBar(self.status_bar, width=140, height=8, corner_radius=4, fg_color=Theme.PANEL, progress_color=Theme.OK)
        self.total_bar.set(0)
        self.total_bar.pack(side=tk.RIGHT, padx=(0, 4))

    # -------------------------------------------------------------
    # Mod library
    # -------------------------------------------------------------

    def toggle_library(self):
        self.show_library = not self.show_library
        self.cfg["show_library"] = self.show_library
        save_app_config(self.cfg)

        def _w(width):
            self.lib_frame.configure(width=max(1, int(width)))

        if self.show_library:
            _w(1)
            self.lib_frame.pack(side=tk.LEFT, fill=tk.Y, before=self.center_frame)
            self.anim.run("lib", 240, lambda p: _w(1 + 299 * p))
        else:
            def _gone():
                self.lib_frame.pack_forget()
                _w(300)
            self.anim.run("lib", 200, lambda p: _w(300 - 299 * p), done=_gone, ease=ease_in_out)

    def refresh_mod_library(self):
        self._scan_token += 1
        token = self._scan_token
        self.lib_view.set_message(t("lib_scanning"))

        def _scan_worker():
            try:
                mods = scan_installed_mods()
                for m in mods:
                    m["_norm"] = os.path.normcase(os.path.abspath(m["path"]))
            except Exception:
                mods = []

            def _apply_ui():
                if token != self._scan_token:
                    return
                self.installed_mods = mods
                self.btn_toggle_lib.configure(text=t("btn_mods", count=len(mods)))
                self.render_library(animate=True)
            self.after(0, _apply_ui)
        threading.Thread(target=_scan_worker, daemon=True).start()

    def set_lib_filter(self, cat):
        self.lib_filter = cat
        self._fade_fg(self.btn_cat_all, Theme.ACCENT if cat == "all" else Theme.FIELD)
        self._fade_fg(self.btn_cat_ws, Theme.ACCENT if cat == "workshop" else Theme.FIELD)
        self._fade_fg(self.btn_cat_mods, Theme.ACCENT if cat == "mods" else Theme.FIELD)
        self.render_library(animate=True)

    def _active_norm(self):
        return os.path.normcase(self.project.mod_path) if self.project else None

    def render_library(self, animate=False):
        q = self.lib_search_entry.get().strip().lower()
        filtered = []
        for m in self.installed_mods:
            if self.lib_filter == "workshop" and m["source"] != "Workshop": continue
            if self.lib_filter == "mods" and m["source"] != "Game Mods": continue
            if q and (q not in m["name"].lower() and q not in m["id"].lower() and q not in m["author"].lower()):
                continue
            filtered.append(m)

        if filtered:
            self.lib_view.set_mods(filtered, self._active_norm(), animate=animate)
        elif self.installed_mods:
            self.lib_view.set_message(t("lib_no_match"))
        else:
            self.lib_view.set_message(t("lib_empty"), t("lib_empty_hint"))

    # kept for backwards compatibility with older call sites
    def filter_library_cards(self):
        self.render_library()

    render_mod_cards = render_library

    # -------------------------------------------------------------
    # Loading mods
    # -------------------------------------------------------------

    def on_files_dropped(self, dropped_paths):
        if not dropped_paths: return
        first = dropped_paths[0]
        if os.path.isdir(first): self.load_mod(first)
        else: self.load_mod(os.path.dirname(first))

    def browse_mod_folder(self):
        f = filedialog.askdirectory(title=t("browse_title"), initialdir=DEFAULT_WORKSHOP_MODS)
        if f: self.load_mod(f)

    def load_mod(self, mod_path):
        if not os.path.exists(mod_path):
            self.toast_show(t("err_mod_not_found"), "error")
            return

        lang = self.get_selected_lang_code()
        self._load_token += 1
        token = self._load_token
        name = os.path.basename(mod_path)
        self._set_busy(True, t("status_scanning", name=name))

        # Scanning may spawn StringPatcher for every DLL: keep it off the UI thread.
        def _worker():
            project, count, err = None, 0, None
            try:
                project = ModProject(mod_path)
                count = project.scan(lang)
            except Exception as ex:
                err = ex
            self.after(0, lambda: self._on_mod_loaded(token, project, count, err, lang))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_mod_loaded(self, token, project, count, err, lang):
        self._set_busy(False)
        if token != self._load_token:
            return  # a newer load superseded this one
        if err is not None or project is None:
            self.toast_show(t("err_load", err=err), "error", 5000)
            return

        self._autosave()  # persist edits of the previous mod
        self._shown_done = 0
        self._total_val = 0.0
        self.project = project
        self._project_lang = lang
        self._dirty = False
        self.selected_item_id = None
        self._clear_workspace()

        meta = project.manifest
        fmt = "CSV" if project.is_csv_mod else "DLL"
        self.mod_badge.configure(text=f"{meta['name']} • {meta['author']} [{fmt}]")
        self.anim.run("badge", 450, lambda p: self.mod_badge.configure(text_color=lerp_color(Theme.BAR, Theme.ACCENT_LIGHT, p)))

        self.render_library()
        self._update_empty_state()
        self.apply_filter(reset=True, animate=True)
        self.update_stats()

        if project.new_strings_count > 0 and project.changed_strings_count + project.new_strings_count < len(project.strings):
            self.toast_show(t("diff_banner", new_count=project.new_strings_count, mod_count=project.changed_strings_count), "info", 4000)
        else:
            self.toast_show(t("toast_loaded", name=meta['name'], count=count), "success", 2000)

        if self.table.order:
            self.table.select(self.table.order[0], see=False)
            self._apply_selection(force=True)

    # -------------------------------------------------------------
    # Table filter & sorting
    # -------------------------------------------------------------

    def set_table_filter(self, flt):
        self.current_filter = flt
        self._fade_fg(self.btn_filter_all, Theme.ACCENT if flt == "all" else Theme.FIELD)
        self._fade_fg(self.btn_filter_untrans, Theme.ACCENT if flt == "untranslated" else Theme.FIELD)
        self._fade_fg(self.btn_filter_overflow, Theme.ACCENT if flt == "overflow" else Theme.FIELD)
        self._fade_fg(self.btn_filter_diff, Theme.ACCENT if flt == "diff" else Theme.FIELD)
        self.apply_filter(reset=True, animate=True)

    def sort_new_to_top(self):
        if not self.project or not self.project.strings: return
        self.project.strings.sort(key=lambda s: 0 if s.get("status") in ("new", "changed") else 1)
        self.apply_filter(reset=True, animate=True)
        self.toast_show(t("toast_new_top"), "info")

    def _set_filter_counts(self, untrans, overflow, diff):
        self.btn_filter_untrans.configure(text=f"{t('filter_untrans')} ({untrans})")
        self.btn_filter_overflow.configure(text=f"{t('filter_overflow')} ({overflow})")
        self.btn_filter_diff.configure(text=f"{t('filter_diff')} ({diff})")

    def _status_for(self, st, is_overflow, trans):
        if st == "new": return "new", t("badge_new")
        if st == "changed": return "changed", t("badge_changed")
        if is_overflow: return "long", t("badge_long")
        if trans: return "ok", t("badge_ok")
        return "empty", t("badge_empty")

    def apply_filter(self, reset=False, animate=False):
        if not self.project:
            self.table.set_rows([], reset=True)
            self._set_filter_counts(0, 0, 0)
            return

        q = self.search_entry.get().strip().lower()
        flt = self.current_filter
        trans_map = self.project.translations

        rows = []
        untrans_count = overflow_count = diff_count = 0

        for s in self.project.strings:
            idx = s["index"]
            orig = s["original"]
            trans = trans_map.get(idx, "")
            st = s.get("status", "synced")

            is_untrans = not trans
            is_overflow = analyze_ui_fit(orig, trans)["is_overflow_risk"]  # lru-cached by (orig, trans)
            is_diff = st in ("new", "changed")

            if is_untrans: untrans_count += 1
            if is_overflow: overflow_count += 1
            if is_diff: diff_count += 1

            if flt == "untranslated" and not is_untrans: continue
            if flt == "overflow" and not is_overflow: continue
            if flt == "diff" and not is_diff: continue

            if q and q not in orig.lower() and q not in trans.lower() and q not in s.get("key", "").lower():
                continue

            kind, label = self._status_for(st, is_overflow, trans)
            rows.append((str(idx), len(rows) + 1, s.get("type", "STR"), orig, trans, kind, label))

        self._set_filter_counts(untrans_count, overflow_count, diff_count)
        self.table.set_rows(rows, reset=reset, animate=animate)

    def update_stats(self):
        if not self.project:
            self.stats_lbl.configure(text="")
            self.total_bar.set(0)
            self._shown_done = 0
            self._total_val = 0.0
            return
        total = len(self.project.strings)
        trans_map = self.project.translations
        done = sum(1 for s in self.project.strings if trans_map.get(s["index"]))
        pct = int(done / total * 100) if total > 0 else 0
        target = done / total if total else 0
        frm, frm_d = self._total_val, self._shown_done

        def _step(p):
            self._total_val = frm + (target - frm) * p
            self.total_bar.set(self._total_val)
            d = int(round(frm_d + (done - frm_d) * p))
            self._shown_done = d
            self.stats_lbl.configure(text=t("stats_summary", total=total, done=d, pct=int(d / total * 100) if total else 0))
        self.anim.run("total", 420, _step)
        self.status_lbl.configure(text=t("status_ready", trans=done, total=total, pct=pct))

    # -------------------------------------------------------------
    # Workspace
    # -------------------------------------------------------------

    def _set_box(self, box, text):
        box.delete("1.0", tk.END)
        if text:
            box.insert("1.0", text)

    def _clear_workspace(self):
        self.ws_orig_box.configure(state="normal")
        self._set_box(self.ws_orig_box, "")
        self.ws_orig_box.configure(state="disabled")
        self._set_box(self.ws_trans_box, "")
        self.ws_orig_len_lbl.configure(text=t("char_count", lang="cn", count=0))
        self.ws_meta_lbl.configure(text=f"{t('meta_file_prefix')} -")
        self._render_placeholder_chips("")
        self.active_suggestions = []
        self._render_suggestion_rows()
        self._on_translation_modified()

    def on_tree_select(self, event=None):
        # Debounced: holding an arrow key fires dozens of events, only the last one needs the full refresh.
        self._debounce("select", 20, self._apply_selection)

    def _apply_selection(self, force=False):
        if not self.project: return
        item_id = self.table.selected
        if item_id is None: return
        if item_id == self.selected_item_id and not force:
            return
        self.selected_item_id = item_id

        try:
            idx = int(item_id)
        except ValueError:
            return
        s_obj = self.project.by_index.get(idx)
        if not s_obj: return

        # Read from the model, not from tree cells: Tk converts numeric-looking cell values ("007" -> 7).
        orig = s_obj["original"]
        trans = self.project.translations.get(idx, "")

        self.ws_orig_box.configure(state="normal")
        self._set_box(self.ws_orig_box, orig)
        self.ws_orig_box.configure(state="disabled")
        self.ws_orig_len_lbl.configure(text=t("char_count", lang="cn", count=len(orig)))

        meta_val = s_obj.get("dll", s_obj.get("key", "-"))
        self.ws_meta_lbl.configure(text=f"{t('meta_file_prefix')} {meta_val}")

        self._set_box(self.ws_trans_box, trans)

        self._render_placeholder_chips(orig)
        self._on_translation_modified()
        self._refresh_suggestions(orig, trans)
        for box in (self.ws_orig_box, self.ws_trans_box):
            self.anim.run(f"tx{id(box)}", 240, lambda p, b=box: b.configure(text_color=lerp_color(Theme.DIM, Theme.TEXT, p)))

    def _render_placeholder_chips(self, orig_text):
        for chip in self._chip_pool:
            chip.pack_forget()
        tokens = list(dict.fromkeys(TOKEN_REGEX.findall(orig_text))) if orig_text else []
        for chip, tok in zip(self._chip_pool, tokens):
            chip._tok = tok
            chip.configure(text=tok)
            chip.pack(side=tk.LEFT, padx=2)

    # ---- suggestions (pooled widgets) ----

    def _build_suggestion_pool(self):
        c = self.sugg_items_container
        self._sugg_headers = []
        for _ in range(2):
            lbl = tk.Label(c, text="", bg=Theme.BAR, anchor="w", font=self.tkF["sugg_hdr"])
            self._sugg_headers.append(lbl)

        self._sugg_rows = []
        for _ in range(5):
            frame = tk.Frame(c, bg=Theme.PANEL, cursor="hand2")
            top = tk.Frame(frame, bg=Theme.PANEL)
            top.pack(fill=tk.X, padx=8, pady=(4, 0))
            txt = tk.Label(top, text="", bg=Theme.PANEL, fg=Theme.TEXT, font=self.tkF["sugg"], anchor="w", justify="left", wraplength=int(300 * self.k))
            txt.pack(side=tk.LEFT, fill=tk.X, expand=True)
            kbd = tk.Label(top, text="", bg=Theme.PANEL, fg=Theme.DIM, font=self.tkF["kbd"])
            kbd.pack(side=tk.RIGHT, padx=(6, 0))
            src = tk.Label(frame, text="", bg=Theme.PANEL, font=self.tkF["sugg_src"], anchor="w")
            src.pack(fill=tk.X, padx=8, pady=(0, 4))
            row = {"frame": frame, "top": top, "txt": txt, "kbd": kbd, "src": src, "text": ""}
            for w in (frame, top, txt, kbd, src):
                w.bind("<Enter>", lambda e, r=row: self._fade_sugg(r, Theme.FIELD, 110))
                w.bind("<Leave>", lambda e, r=row: self._fade_sugg(r, Theme.PANEL, 160))
                w.bind("<Button-1>", lambda e, r=row: self._click_sugg(r))
            self._sugg_rows.append(row)

        self._sugg_empty = tk.Label(c, text="", bg=Theme.BAR, fg=Theme.DIM, font=self.tkF["sugg_src"], anchor="w")
        c.bind("<Configure>", self._on_sugg_resize)

    def _on_sugg_resize(self, event):
        wrap = max(120, event.width - int(90 * self.k))
        for row in self._sugg_rows:
            row["txt"].configure(wraplength=wrap)

    def _fade_sugg(self, row, to, ms):
        try: frm = row["frame"].cget("bg")
        except Exception: frm = to
        if not (isinstance(frm, str) and frm.startswith("#")):
            self._paint_sugg(row, to)
            return
        self.anim.run(f"sg{id(row)}", ms, lambda p: self._paint_sugg(row, lerp_color(frm, to, p)))

    def _click_sugg(self, row):
        self._apply_text(row["text"])
        self.anim.run(f"sg{id(row)}", 420, lambda p: self._paint_sugg(row, lerp_color(Theme.ACCENT, Theme.FIELD, p)))

    def _paint_sugg(self, row, color):
        for key in ("frame", "top", "txt", "kbd", "src"):
            row[key].configure(bg=color)

    def _apply_text(self, text):
        self._set_box(self.ws_trans_box, text)
        self._on_translation_modified()

    def _refresh_suggestions(self, orig, trans, ai_res=None, ai_engine=None):
        lang = self.get_selected_lang_code()
        draft = None
        need_draft = not trans and not ai_res
        if need_draft:
            draft = self._draft_cache.get((orig, lang))
        self.active_suggestions = generate_crowdin_suggestions(
            orig, trans, target_lang=lang, ai_res=ai_res,
            ai_engine=ai_engine or self.translation_engine, ai_model=self.ollama_model, draft=draft
        )
        self._render_suggestion_rows()
        if need_draft and draft is None and orig.strip():
            # The Google draft used to be fetched synchronously right here (up to 10 s freeze per row).
            self._debounce("draft", 450, lambda: self._fetch_draft(orig, lang))

    def _fetch_draft(self, orig, lang):
        key = (orig, lang)
        if key in self._draft_cache or key in self._draft_pending:
            return
        self._draft_pending.add(key)

        def _worker():
            try:
                res = translate_batch([orig], target_lang=lang)
                text = res[0] if res else ""
            except Exception:
                text = ""

            def _done():
                self._draft_pending.discard(key)
                if text and text.strip() != orig.strip():
                    if len(self._draft_cache) > 400:
                        self._draft_cache.pop(next(iter(self._draft_cache)))
                    self._draft_cache[key] = text
                    self._on_draft_ready(orig, lang)
            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_draft_ready(self, orig, lang):
        if not self.project or self.selected_item_id is None: return
        cur_orig = self.ws_orig_box.get("1.0", tk.END).strip()
        cur_trans = self.ws_trans_box.get("1.0", tk.END).strip()
        if cur_orig == orig.strip() and not cur_trans and lang == self.get_selected_lang_code():
            self._refresh_suggestions(orig, "")

    def _render_suggestion_rows(self):
        for w in self._sugg_headers: w.pack_forget()
        for r in self._sugg_rows: r["frame"].pack_forget()
        self._sugg_empty.pack_forget()

        items = self.active_suggestions
        if not items:
            self._sugg_empty.configure(text=t("no_suggestions"))
            self._sugg_empty.pack(fill=tk.X, padx=6, pady=4)
            return

        tm_items = [s for s in items if any(k in s["source"].lower() for k in ["глоссарий", "компактный", "glossary", "compact", "concise"])]
        mt_items = [s for s in items if s not in tm_items]

        # global order == hotkey order (Ctrl+1..5)
        hdr_i = 0
        row_i = 0
        self.active_suggestions = []
        for title, group, icon, color in ((t("sec_glossary"), tm_items, "◆", Theme.ACCENT_LIGHT),
                                          (t("sec_machine_ai"), mt_items, "◆", "#c084fc")):
            if not group or hdr_i >= len(self._sugg_headers):
                continue
            hdr = self._sugg_headers[hdr_i]
            hdr_i += 1
            hdr.configure(text=f"{icon} {title}", fg=color)
            hdr.pack(fill=tk.X, padx=4, pady=(4, 1))
            for s in group:
                if row_i >= len(self._sugg_rows):
                    break
                row = self._sugg_rows[row_i]
                row["text"] = s["text"]
                row["txt"].configure(text=s["text"])
                row["kbd"].configure(text=f"Ctrl+{row_i + 1}" if row_i < 5 else "")
                row["src"].configure(text=s["source"], fg=s.get("badge_color", Theme.MUTED))
                self._paint_sugg(row, Theme.PANEL)
                row["frame"].pack(fill=tk.X, padx=2, pady=1)
                self.active_suggestions.append(s)
                row_i += 1

    def apply_suggestion_by_index(self, index):
        if index < len(self.active_suggestions):
            self._apply_text(self.active_suggestions[index]["text"])
            return "break"
        return None

    def _on_translation_modified(self):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        trans = self.ws_trans_box.get("1.0", tk.END).strip()

        lang = self.get_selected_lang_code().upper()
        self.ws_trans_len_lbl.configure(text=t("char_count", lang=lang, count=len(trans)))

        diag = analyze_ui_fit(orig, trans)

        if diag["is_overflow_risk"]:
            if not self._alert_visible:
                self.ws_overflow_alert.pack(fill=tk.X, padx=10, pady=(4, 6))
                self._alert_visible = True
            self.ws_overflow_alert_lbl.configure(text=t("overflow_warning", ratio=diag["ratio"], pct=int(diag["ratio"] * 100)))
        elif self._alert_visible:
            self.ws_overflow_alert.pack_forget()
            self._alert_visible = False

        kind, label = self._status_for("synced", diag["is_overflow_risk"], trans)
        self._set_chip(kind, label)

    def _set_chip(self, kind, label):
        fill, border, fg = STATUS_STYLES[kind]
        self.ws_status_badge.configure(text=label, text_color=fg)
        if self._chip_kind == kind:
            return
        self._chip_kind = kind
        f0, b0 = self._chip_cols

        def _step(p):
            self._chip_cols = (lerp_color(f0, fill, p), lerp_color(b0, border, p))
            self.ws_status_chip.configure(fg_color=self._chip_cols[0], border_color=self._chip_cols[1])
        self.anim.run("chip", 220, _step)

    def insert_token(self, token):
        self.ws_trans_box.insert(tk.INSERT, token)
        self.ws_trans_box.focus()
        self._on_translation_modified()

    def apply_concise_suggestion(self):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        trans = self.ws_trans_box.get("1.0", tk.END).strip()
        cand = make_concise(orig, trans)
        if cand:
            self._apply_text(cand)
            self.toast_show(t("toast_concise_applied"), "info")

    # -------------------------------------------------------------
    # Saving & navigation
    # -------------------------------------------------------------

    def save_and_next(self):
        if self.selected_item_id is None or not self.project: return

        idx = int(self.selected_item_id)
        trans = self.ws_trans_box.get("1.0", tk.END).strip()
        orig = self.ws_orig_box.get("1.0", tk.END).strip()

        self.project.translations[idx] = trans
        s_obj = self.project.by_index.get(idx)
        if s_obj:
            s_obj["translation"] = trans
            s_obj["status"] = "synced"
        self._dirty = True
        self._debounce("autosave", 2000, self._autosave)

        diag = analyze_ui_fit(orig, trans)

        if self.table.exists(self.selected_item_id):
            kind, label = self._status_for("synced", diag["is_overflow_risk"], trans)
            self.table.update_row(self.selected_item_id, trans, kind, label)
            self.table.flash(self.selected_item_id)

        self.update_stats()

        self.btn_save_next.configure(fg_color="#047857", text=t("saved_flash"))
        self.after(250, lambda: self.btn_save_next.configure(fg_color=Theme.BTN["success"][0], text=t("btn_save_next")))

        order = self.table.order
        pos = self.table.pos(self.selected_item_id)
        if pos is None:
            return
        tr_map = self.project.translations
        for nxt in order[pos + 1:]:
            if not tr_map.get(int(nxt)):
                self._goto(nxt)
                return
        if pos + 1 < len(order):
            self._goto(order[pos + 1])

    def _goto(self, iid):
        self.table.select(iid, see=True)
        self._apply_selection()

    def nav_next(self):
        order = self.table.order
        if not order: return "break"
        pos = self.table.pos(self.selected_item_id)
        if pos is None:
            self._goto(order[0])
        elif pos + 1 < len(order):
            self._goto(order[pos + 1])
        return "break"

    def nav_prev(self):
        order = self.table.order
        if not order: return "break"
        pos = self.table.pos(self.selected_item_id)
        if pos is not None and pos > 0:
            self._goto(order[pos - 1])
        return "break"

    def _autosave(self):
        """Persist manual edits to translations_<lang>.json (they used to be lost unless Build was pressed)."""
        if self.project and self._dirty:
            self._dirty = False
            try: self.project.save_translations_cache(self._project_lang)
            except Exception as ex: print(f"Autosave failed: {ex}")

    # -------------------------------------------------------------
    # Row translation
    # -------------------------------------------------------------

    def update_ai_btn_text(self):
        eng_name = self.ollama_model if self.translation_engine == "ollama" else self.translation_engine.upper()
        self.btn_request_ai.configure(text=eng_name)

    def translate_active_row_ai(self):
        self._translate_active_row_custom(engine=self.translation_engine, button_ref=self.btn_request_ai)

    def translate_active_row_google(self):
        self._translate_active_row_custom(engine="google", button_ref=self.btn_request_google)

    def translate_active_row(self):
        self.translate_active_row_ai()

    def _translate_active_row_custom(self, engine="google", button_ref=None):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        if not orig: return
        lang = self.get_selected_lang_code()
        row_id = self.selected_item_id

        eng_label = self.ollama_model if (engine == "ollama" and self.ollama_model) else engine.upper()
        orig_btn_txt = button_ref.cget("text") if button_ref else ""
        if button_ref:
            button_ref.configure(text=t("requesting"), state="disabled")

        def _worker():
            try:
                res = translate_batch(
                    [orig], target_lang=lang, engine=engine, deepl_key=self.deepl_key,
                    ollama_url=self.ollama_url, ollama_model=self.ollama_model,
                    custom_url=self.custom_url, custom_key=self.custom_key, custom_model=self.custom_model
                )
                ai_text = res[0] if (res and res[0]) else orig
            except Exception:
                ai_text = orig

            def _finish():
                if button_ref:
                    button_ref.configure(text=orig_btn_txt, state="normal")
                    self.update_ai_btn_text()
                if row_id != self.selected_item_id:
                    return  # user moved to another row while the request was running
                if ai_text:
                    self._apply_text(ai_text)
                    self._refresh_suggestions(orig, ai_text, ai_res=ai_text, ai_engine=engine)
                    self.toast_show(t("toast_translated_by", engine=eng_label), "success", 2000)

            self.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def copy_from_orig(self):
        self._apply_text(self.ws_orig_box.get("1.0", tk.END).strip())

    def clear_active_translation(self):
        self._apply_text("")

    def focus_editor(self):
        self.ws_trans_box.focus()

    def on_table_context(self, iid, x_root, y_root):
        self._apply_selection()
        menu = tk.Menu(self, tearoff=0, bg="#1e222b", fg=Theme.TEXT, activebackground=Theme.ACCENT)
        menu.add_command(label=t("menu_edit"), command=self.focus_editor)
        menu.add_command(label=t("menu_translate"), command=self.translate_active_row)
        menu.add_command(label=t("menu_concise"), command=self.apply_concise_suggestion)
        menu.add_separator()
        menu.add_command(label=t("menu_copy_orig"), command=lambda: self.clipboard_clear() or self.clipboard_append(self.ws_orig_box.get("1.0", tk.END).strip()))
        menu.add_command(label=t("menu_clear"), command=self.clear_active_translation)
        menu.tk_popup(x_root, y_root)

    def get_selected_lang_code(self):
        val = self.lang_var.get()
        m = re.search(r'\[([a-zA-Z\-]+)\]', val)
        return m.group(1) if m else "ru"

    def on_lang_changed(self, choice):
        lang = self.get_selected_lang_code()
        self.cfg["target_lang"] = lang
        save_app_config(self.cfg)
        if self.project:
            self._autosave()  # flush edits under the previous language first
            self.project.load_existing_translations(lang)
            self._project_lang = lang
            self.apply_filter()
            self.update_stats()
            if self.selected_item_id is not None:
                self._apply_selection(force=True)

    # -------------------------------------------------------------
    # Auto-translate (progress lives in the status bar)
    # -------------------------------------------------------------

    def start_auto_translate(self):
        if not self.project:
            self.toast_show(t("warn_pick_mod"), "warning")
            return

        project = self.project
        untrans = [s for s in project.strings if not project.translations.get(s["index"])]
        if not untrans:
            self.toast_show(t("warn_all_translated"), "info")
            return

        lang = self.get_selected_lang_code()
        total_count = len(untrans)
        self.cancel_translation_flag = False
        self.btn_translate.configure(state="disabled")

        engine = self.translation_engine.upper()
        self._show_top_progress(engine, total_count)

        def _worker():
            def _prog(done, total, last_orig, last_trans):
                pct = int(done / total * 100) if total > 0 else 0
                sample = (last_orig[:11] + "…") if len(last_orig) > 11 else last_orig
                self.after(0, lambda: self._autotr_progress(done, total, pct, engine, sample))

            cnt = project.auto_translate(
                lang,
                progress_callback=_prog,
                cancel_check=lambda: self.cancel_translation_flag,
                engine=self.translation_engine,
                deepl_key=self.deepl_key,
                ollama_url=self.ollama_url,
                ollama_model=self.ollama_model,
                custom_url=self.custom_url,
                custom_key=self.custom_key,
                custom_model=self.custom_model
            )
            self.after(0, lambda: self._autotr_done(project, cnt))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_top_progress(self, engine, total):
        self.mod_badge.pack_forget()  # free the space for the progress card
        self._ap_val = 0.0
        self.top_progress_bar.set(0)
        self.top_progress_bar.configure(progress_color=Theme.ACCENT)
        self.top_progress_frame.configure(border_color=Theme.ACCENT)
        self.top_progress_lbl.configure(text=f"{engine}  0/{total}")
        self.top_progress_pct.configure(text="0%")
        self.btn_top_cancel.configure(state="normal")
        self.top_progress_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=16, pady=12)
        self._ap_active = True
        self._pulse_progress()

    def _pulse_progress(self):
        if not self._ap_active:
            return
        k = (math.sin(time.perf_counter() * 3.2) + 1) / 2
        self.top_progress_frame.configure(border_color=lerp_color(Theme.ACCENT_HOVER, Theme.ACCENT_LIGHT, k))
        self._jobs["pulse"] = self.after(70, self._pulse_progress)

    def _hide_top_progress(self):
        self.top_progress_frame.pack_forget()
        self.mod_badge.pack(side=tk.LEFT, padx=10)

    def _autotr_progress(self, done, total, pct, engine, sample):
        self.top_progress_lbl.configure(text=f"{engine}  {done}/{total}")
        self.top_progress_pct.configure(text=f"{pct}%")
        target = done / total if total else 0
        frm = self._ap_val

        def _step(p):
            self._ap_val = frm + (target - frm) * p
            self.top_progress_bar.set(self._ap_val)
        self.anim.run("autobar", 320, _step)

    def _autotr_done(self, project, cnt):
        self._ap_active = False
        self.btn_translate.configure(state="normal")
        self.top_progress_lbl.configure(text=t("autotr_done_lbl", count=cnt))
        self.top_progress_pct.configure(text="100%")
        self.top_progress_bar.configure(progress_color=Theme.OK)
        self.top_progress_frame.configure(border_color=Theme.OK)
        frm = self._ap_val
        self.anim.run("autobar", 300, lambda p: self.top_progress_bar.set(frm + (1 - frm) * p))
        self.after(2600, self._hide_top_progress)
        if project is self.project:
            self.apply_filter()
            self.update_stats()
            if self.selected_item_id is not None:
                self._apply_selection(force=True)
        self.toast_show(t("autotr_done_toast", count=cnt), "success", 3000)

    def cancel_auto_translate(self):
        self.cancel_translation_flag = True
        self.btn_top_cancel.configure(state="disabled")
        self.top_progress_lbl.configure(text=t("autotr_stopping"))

    # -------------------------------------------------------------
    # Engine settings dialog
    # -------------------------------------------------------------

    def open_engine_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title(t("engine_settings_title"))
        dlg.geometry("580x720")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.after(100, lambda: dlg.winfo_exists() and dlg.grab_set())

        frame = ctk.CTkFrame(dlg, fg_color=Theme.BAR, corner_radius=12)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ctk.CTkLabel(frame, text=t("engine_settings_title"), font=self.F["title"], text_color=Theme.ACCENT_LIGHT).pack(pady=(10, 6))

        engine_var = ctk.StringVar(value=self.translation_engine)
        for key, val in (("eng_google", "google"), ("eng_deepl", "deepl"), ("eng_ollama", "ollama"), ("eng_custom", "custom")):
            ctk.CTkRadioButton(frame, text=t(key), variable=engine_var, value=val).pack(anchor="w", padx=24, pady=3)

        ctk.CTkLabel(frame, text=t("lbl_deepl_key"), font=self.F["small"]).pack(anchor="w", padx=24, pady=(8, 2))
        ent_deepl = ctk.CTkEntry(frame, width=500, placeholder_text="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx")
        ent_deepl.insert(0, self.deepl_key)
        ent_deepl.pack(padx=24, pady=2)

        ctk.CTkLabel(frame, text=t("lbl_ollama"), font=self.F["small_b"], text_color=Theme.ACCENT_LIGHT).pack(anchor="w", padx=24, pady=(10, 2))
        f_ollama = ctk.CTkFrame(frame, fg_color="transparent")
        f_ollama.pack(fill=tk.X, padx=24, pady=2)

        ent_ollama_url = ctk.CTkEntry(f_ollama, width=230)
        ent_ollama_url.insert(0, self.ollama_url or "http://127.0.0.1:11434")
        ent_ollama_url.pack(side=tk.LEFT, padx=(0, 6))

        ollama_model_var = ctk.StringVar(value=self.ollama_model or t("no_models"))
        menu_ollama_model = ctk.CTkOptionMenu(f_ollama, variable=ollama_model_var, values=[self.ollama_model or t("no_models")], width=170)
        menu_ollama_model.pack(side=tk.LEFT, padx=3)

        lbl_ollama_status = ctk.CTkLabel(frame, text=t("lbl_models_loading"), font=self.F["tiny"], text_color=Theme.MUTED)

        def _load_models():
            lbl_ollama_status.configure(text=t("lbl_models_loading"))
            url = ent_ollama_url.get().strip()

            def _worker():
                models = fetch_ollama_models(url)  # network/disk: never on the UI thread

                def _apply():
                    if not dlg.winfo_exists():
                        return
                    valid = [m for m in models if m != NO_MODELS_SENTINEL]
                    menu_ollama_model.configure(values=valid or [t("no_models")])
                    if valid:
                        ollama_model_var.set(self.ollama_model if self.ollama_model in valid else valid[0])
                    else:
                        ollama_model_var.set(t("no_models"))
                    lbl_ollama_status.configure(text=t("lbl_models_found", count=len(valid)))
                self.after(0, _apply)

            threading.Thread(target=_worker, daemon=True).start()

        self._mk_btn(f_ollama, "↻", _load_models, "ghost", width=34, height=28, font="reg").pack(side=tk.LEFT, padx=3)
        lbl_ollama_status.pack(anchor="w", padx=24, pady=(1, 4))
        _load_models()

        ctk.CTkLabel(frame, text=t("lbl_custom"), font=self.F["small_b"], text_color=Theme.ACCENT_LIGHT).pack(anchor="w", padx=24, pady=(8, 2))
        ent_c_url = ctk.CTkEntry(frame, width=500, placeholder_text="https://api.openai.com/v1")
        ent_c_url.insert(0, self.custom_url)
        ent_c_url.pack(padx=24, pady=2)
        f_c = ctk.CTkFrame(frame, fg_color="transparent")
        f_c.pack(fill=tk.X, padx=24, pady=2)
        ent_c_key = ctk.CTkEntry(f_c, width=300, show="•", placeholder_text="API key")
        ent_c_key.insert(0, self.custom_key)
        ent_c_key.pack(side=tk.LEFT, padx=(0, 6))
        ent_c_model = ctk.CTkEntry(f_c, width=190, placeholder_text="gpt-4o-mini")
        ent_c_model.insert(0, self.custom_model)
        ent_c_model.pack(side=tk.LEFT)

        log_box = ctk.CTkFrame(frame, fg_color=Theme.CARD, corner_radius=8, border_width=1, border_color=Theme.BORDER)
        log_box.pack(fill=tk.X, padx=24, pady=(10, 10))
        log_top = ctk.CTkFrame(log_box, fg_color="transparent")
        log_top.pack(fill=tk.X, padx=10, pady=6)

        num_logs, sz_logs = get_llm_logs_info()
        lbl_log_info = ctk.CTkLabel(log_top, text=t("logs_info", count=num_logs, size=sz_logs), font=self.F["small"], text_color=Theme.TEXT_SOFT)
        lbl_log_info.pack(side=tk.LEFT)

        def _clear_logs():
            c = clear_llm_logs()
            lbl_log_info.configure(text=t("logs_info", count=0, size="0 KB"))
            self.toast_show(t("toast_logs_cleared", count=c), "info")

        def _open_logs():
            if os.path.exists(LLMLOGS_DIR) and hasattr(os, "startfile"):
                os.startfile(LLMLOGS_DIR)

        self._mk_btn(log_top, t("btn_clear_logs"), _clear_logs, "muted", width=130, height=26, font="small", hover_color="#dc2626").pack(side=tk.RIGHT, padx=4)
        self._mk_btn(log_top, t("btn_open_logs"), _open_logs, "muted", width=110, height=26, font="small").pack(side=tk.RIGHT, padx=4)

        def _save():
            self.translation_engine = engine_var.get()
            self.deepl_key = ent_deepl.get().strip()
            self.ollama_url = ent_ollama_url.get().strip()
            chosen = ollama_model_var.get().strip()
            if chosen and chosen not in (t("no_models"), NO_MODELS_SENTINEL):
                self.ollama_model = chosen
            self.custom_url = ent_c_url.get().strip() or self.custom_url
            self.custom_key = ent_c_key.get().strip()
            self.custom_model = ent_c_model.get().strip() or self.custom_model

            self.cfg.update({
                "engine": self.translation_engine,
                "deepl_api_key": self.deepl_key,
                "ollama_url": self.ollama_url,
                "ollama_model": self.ollama_model,
                "custom_api_url": self.custom_url,
                "custom_api_key": self.custom_key,
                "custom_api_model": self.custom_model,
            })
            save_app_config(self.cfg)

            self.btn_engine.configure(text=self.translation_engine.upper())
            self.update_ai_btn_text()
            dlg.destroy()
            self.toast_show(t("toast_settings_saved"), "success")

        self._mk_btn(frame, t("btn_save_settings"), _save, "success", width=180, height=36).pack(pady=(4, 10))

    # -------------------------------------------------------------
    # Build & install (run in the background: StringPatcher can take seconds)
    # -------------------------------------------------------------

    def _run_bg(self, busy_text, work, on_done):
        self.btn_build.configure(state="disabled")
        self.btn_install.configure(state="disabled")
        self._set_busy(True, busy_text)

        def _worker():
            res, err = None, None
            try:
                res = work()
            except Exception as ex:
                err = ex

            def _finish():
                self._set_busy(False)
                self.btn_build.configure(state="normal")
                self.btn_install.configure(state="normal")
                on_done(res, err)
            self.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def do_build(self):
        if not self.project:
            self.toast_show(t("warn_pick_mod"), "warning")
            return
        lang = self.get_selected_lang_code()
        project = self.project

        def _done(res, err):
            if err is not None:
                self.toast_show(t("err_build", err=err), "error", 5000)
            else:
                self.toast_show(t("toast_build_ok", res=str(res)[:60]), "success")

        self._run_bg(t("building"), lambda: project.build(lang), _done)

    def do_install(self):
        if not self.project:
            self.toast_show(t("warn_pick_mod"), "warning")
            return
        lang = self.get_selected_lang_code()
        project = self.project

        def _done(res, err):
            if err is not None:
                self.toast_show(t("err_install", err=err), "error", 5000)
            else:
                self.toast_show(t("toast_installed", lang=lang.upper(), name=os.path.basename(res)), "success", 4000)
                self.refresh_mod_library()

        self._run_bg(t("installing"), lambda: project.install_to_game(lang), _done)

def main():
    parser = argparse.ArgumentParser(description="ProbablyTranslator - Universal Mod Localization Studio")
    parser.add_argument("mod_path", nargs="?", help="Path to mod directory")
    parser.add_argument("--lang", default="ru", help="Target language code (e.g. ru, en, es)")
    parser.add_argument("--auto-translate", action="store_true", help="Auto-translate via NMT")
    parser.add_argument("--build", action="store_true", help="Build translated mod")
    parser.add_argument("--install", action="store_true", help="Install into game Mods directory")

    args = parser.parse_args()

    if args.mod_path and (args.auto_translate or args.build or args.install):
        project = ModProject(args.mod_path)
        project.scan(args.lang)
        if args.auto_translate: project.auto_translate(args.lang)
        if args.build: project.build(args.lang)
        if args.install: project.install_to_game(args.lang)
        return

    app = ModernTranslatorApp()
    if args.mod_path:
        app.after(150, lambda: app.load_mod(args.mod_path))
    app.mainloop()

if __name__ == "__main__":
    main()
