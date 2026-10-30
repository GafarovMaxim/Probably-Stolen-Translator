"""
ProbablyTranslator - Universal Mod Localization Studio for 'Probably Stolen'
- Top-bar integrated live auto-translation progress with cancel button
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
import xml.etree.ElementTree as ET

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk

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
        "btn_mods": "📚 Моды ({count})",
        "btn_browse": "📁 Обзор...",
        "btn_auto_translate": "✨ Автоперевод",
        "btn_build": "📦 Собрать",
        "btn_install": "🚀 В игру (Mods/)",
        "target_lang_label": "🎯 Целевой язык:",
        "ui_lang_label": "Язык UI:",
        "engine_label": "🌐 {engine}",
        "engine_settings_title": "Настройки движков перевода",
        "mod_lib_title": "БИБЛИОТЕКА МОДОВ",
        "search_mods_placeholder": "Поиск модов...",
        "filter_all": "Все",
        "filter_workshop": "Workshop",
        "filter_mods": "Mods/",
        "filter_untrans": "Не переведено",
        "filter_overflow": "⚠️ Превышение длины",
        "filter_diff": "⚡ Обновления (Diff)",
        "btn_new_to_top": "🔼 Новые наверх",
        "search_strings_placeholder": "🔍 Поиск по строкам оригинала или перевода...",
        "col_num": "#",
        "col_type": "Тип",
        "col_original": "Исходный текст (Оригинал)",
        "col_translation": "Перевод",
        "col_status": "Статус",
        "context_title": "КОНТЕКСТ И ПЕРЕВОД",
        "orig_box_title": "ОРИГИНАЛ",
        "trans_box_title": "ВАШ ПЕРЕВОД",
        "suggestions_title": "💡 ВАРИАНТЫ ПЕРЕВОДА",
        "btn_ai_request": "✨ Запросить у {engine}",
        "char_count": "{lang} {count} симв.",
        "btn_save_next": "✓ Сохранить и далее (Ctrl+Enter)",
        "btn_translate_row": "✨ Перевести",
        "btn_copy_orig": "🔁 Оригинал",
        "btn_clear_row": "🧹 Очистить",
        "btn_concise": "✂ Сократить",
        "btn_concise_action": "✂ Сократить перевод",
        "nav_prev": "◀ Пред.",
        "nav_next": "След. ▶",
        "status_ready": "Готов к работе. Переведено: {trans}/{total} ({pct}%)",
        "status_scanning": "Сканирование мода: {name}...",
        "status_translating": "Выполняется перевод...",
        "overflow_warning": "⚠️ Текст в {ratio:.1f}x длиннее оригинала (+{pct}%)! Риск вылезания за кнопку.",
        "badge_new": "⚡ НОВАЯ",
        "badge_changed": "✏️ ИЗМЕНЕНА",
        "badge_ok": "✓ Готово",
        "badge_empty": "⏳ Пусто",
        "badge_long": "⚠️ ДЛИННАЯ",
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
        "update_badge": "🔄 Обновлен v{ver}",
        "installed_badge": "Установлен перевод",
        "diff_banner": "⚡ В обновлении мода обнаружено новых строк: {new_count}, изменено: {mod_count}.",
        "meta_file_prefix": "Метод / Файл:",
        "sec_glossary": "ИГРОВОЙ ГЛОССАРИЙ & КОНТЕКСТ",
        "sec_machine_ai": "МАШИННЫЙ & AI ПЕРЕВОД",
        "no_suggestions": "Нет доступных вариантов",
        "src_neural": "✨ Нейросеть ({model})",
        "src_current": "⚡ Текущий перевод",
        "src_draft": "⚡ Быстрый черновик",
        "src_glossary": "📖 Игровой глоссарий",
        "src_concise": "✂️ Компактный (Интерфейс)",
        "src_orig": "📄 Оригинал (Сброс)",
        "stats_summary": "Строк: {total} | Переведено: {done} ({pct}%)",
        "badge_installed": "✓ Установлен",
        "tooltip_refresh_mods": "Обновить список модов",
        "tooltip_insert_token": "Вставить '{tok}' в позицию курсора",
        "tooltip_ai_req": "Запросить перевод у нейросети ({engine})",
        "tooltip_google_req": "Запросить быстрый перевод у Google Translate",
        "tooltip_mod_update_avail": "В Workshop доступна новая версия: {ver} (установлена {inst})",
    },
    "en": {
        "app_title": "ProbablyTranslator - Mod Localization Studio for Probably Stolen",
        "btn_mods": "📚 Mods ({count})",
        "btn_browse": "📁 Browse...",
        "btn_auto_translate": "✨ Auto-Translate",
        "btn_build": "📦 Build",
        "btn_install": "🚀 To Game (Mods/)",
        "target_lang_label": "🎯 Target Language:",
        "ui_lang_label": "UI Lang:",
        "engine_label": "🌐 {engine}",
        "engine_settings_title": "Translation Engine Settings",
        "mod_lib_title": "MOD LIBRARY",
        "search_mods_placeholder": "Search mods...",
        "filter_all": "All",
        "filter_workshop": "Workshop",
        "filter_mods": "Mods/",
        "filter_untrans": "Untranslated",
        "filter_overflow": "⚠️ UI Overflow",
        "filter_diff": "⚡ Updates (Diff)",
        "btn_new_to_top": "🔼 New to Top",
        "search_strings_placeholder": "🔍 Search original or translation...",
        "col_num": "#",
        "col_type": "Type",
        "col_original": "Original Text",
        "col_translation": "Translation",
        "col_status": "Status",
        "context_title": "CONTEXT & TRANSLATION",
        "orig_box_title": "ORIGINAL",
        "trans_box_title": "YOUR TRANSLATION",
        "suggestions_title": "💡 TRANSLATION VARIANTS",
        "btn_ai_request": "✨ Request from {engine}",
        "char_count": "{lang} {count} chars",
        "btn_save_next": "✓ Save & Next (Ctrl+Enter)",
        "btn_translate_row": "✨ Translate",
        "btn_copy_orig": "🔁 Original",
        "btn_clear_row": "🧹 Clear",
        "btn_concise": "✂ Concise",
        "btn_concise_action": "✂ Make Concise",
        "nav_prev": "◀ Prev",
        "nav_next": "Next ▶",
        "status_ready": "Ready. Translated: {trans}/{total} ({pct}%)",
        "status_scanning": "Scanning mod: {name}...",
        "status_translating": "Translating...",
        "overflow_warning": "⚠️ Text is {ratio:.1f}x longer than original (+{pct}%)! UI clipping risk.",
        "badge_new": "⚡ NEW",
        "badge_changed": " ✏️ MODIFIED ",
        "badge_ok": "✓ Done",
        "badge_empty": "⏳ Empty",
        "badge_long": "⚠️ LONG",
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
        "update_badge": "🔄 Updated v{ver}",
        "installed_badge": "Translation Installed",
        "diff_banner": "⚡ Mod update detected: {new_count} new strings, {mod_count} modified.",
        "meta_file_prefix": "Method / File:",
        "sec_glossary": "GAMING GLOSSARY & CONTEXT",
        "sec_machine_ai": "MACHINE & AI TRANSLATION",
        "no_suggestions": "No suggestions available",
        "src_neural": "✨ Neural Model ({model})",
        "src_current": "⚡ Current Translation",
        "src_draft": "⚡ Quick Draft",
        "src_glossary": "📖 Gaming Glossary",
        "src_concise": "✂️ Compact (UI)",
        "src_orig": "📄 Original (Reset)",
        "stats_summary": "Strings: {total} | Translated: {done} ({pct}%)",
        "badge_installed": "✓ Installed",
        "tooltip_refresh_mods": "Refresh mod library",
        "tooltip_insert_token": "Insert '{tok}' at cursor position",
        "tooltip_ai_req": "Request translation from neural model ({engine})",
        "tooltip_google_req": "Request quick translation from Google Translate",
        "tooltip_mod_update_avail": "Workshop update available: {ver} (installed {inst})",
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

def generate_crowdin_suggestions(orig: str, current_trans: str, target_lang="ru", ai_res=None, ai_engine="google", ai_model=""):
    """Generates 2-3 distinct translation suggestions with clear source labeling."""
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
    if not primary and not suggestions:
        prim_list = translate_batch([orig_clean], target_lang=target_lang)
        primary = prim_list[0] if prim_list else orig_clean

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
            "border_color": "#475569"
        })

    return suggestions[:3]

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

    replacements = [
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
    ]
    for pattern, rep in replacements:
        res = re.sub(pattern, rep, res, flags=re.IGNORECASE)

    res = re.sub(r'\bпожалуйста\b,?\s*', '', res, flags=re.IGNORECASE)
    res = re.sub(r'\s{2,}', ' ', res).strip()

    res = res.rstrip('.:：!！?？')

    # Strictly re-attach trailing punctuation from original
    if trailing_colon: res += ':'
    elif trailing_qmark: res += '?'
    elif trailing_exclam: res += '!'
    elif trailing_dots: res += '...'
    elif len(orig_str) > 25 and orig_str.endswith('.'): res += '.'

    return res

def analyze_ui_fit(orig: str, trans: str) -> dict:
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
            self.load_existing_translations(target_lang)
            return len(self.strings)

        if not os.path.exists(STRING_PATCHER_EXE):
            raise FileNotFoundError(f"StringPatcher.exe not found at: {STRING_PATCHER_EXE}")

        dll_files = [f for f in os.listdir(self.mod_path) if f.lower().endswith(".dll") and not f.lower().endswith(".bak")]
        if not dll_files:
            raise FileNotFoundError(f"No .dll files found in {self.mod_path}")

        all_strings = []
        seen_orig = set()
        str_idx = 0

        for dll_name in dll_files:
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
                continue

            if os.path.exists(temp_json):
                try:
                    with open(temp_json, "r", encoding="utf-8") as f:
                        raw_list = json.load(f)
                    for item in raw_list:
                        orig = (item.get("orig") or item.get("zh") or "").strip()
                        if orig and orig not in seen_orig:
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
                finally:
                    try: os.remove(temp_json)
                    except Exception: pass

        self.strings = all_strings
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

class ModernTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.cfg = load_app_config()
        global CURRENT_UI_LANG
        CURRENT_UI_LANG = self.cfg.get("ui_lang", "ru")

        self.title(t("app_title"))
        self.geometry("1420x890")
        self.minsize(1180, 750)

        if os.path.exists(ICON_FILE):
            try: self.iconbitmap(ICON_FILE)
            except Exception: pass

        self.project = None
        self.installed_mods = []
        self.selected_item_id = None
        self.current_filter = "all"
        self.show_library = self.cfg.get("show_library", True)
        self.translation_engine = self.cfg.get("engine", "google")
        self.deepl_key = self.cfg.get("deepl_api_key", "")
        self.ollama_url = self.cfg.get("ollama_url", "http://127.0.0.1:11434")
        self.ollama_model = self.cfg.get("ollama_model", "qwen2.5:7b")
        self.custom_url = self.cfg.get("custom_api_url", "https://api.openai.com/v1")
        self.custom_key = self.cfg.get("custom_api_key", "")
        self.custom_model = self.cfg.get("custom_api_model", "gpt-4o-mini")

        self.cancel_translation_flag = False

        self._init_ttk_styles()
        self._build_top_bar()
        self._build_main_layout()
        self._build_status_bar()

        setup_native_drag_and_drop(self, self.on_files_dropped)
        self.after(80, self.refresh_mod_library)

    def _init_ttk_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Strip Treeview.field completely to eliminate harsh white border lines!
        self.style.layout("Crowdin.Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        self.style.configure(
            "Crowdin.Treeview",
            background="#0f172a",
            foreground="#f8fafc",
            rowheight=34,
            fieldbackground="#0f172a",
            font=("Segoe UI", 10),
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            bordercolor="#0f172a",
            lightcolor="#0f172a",
            darkcolor="#0f172a"
        )
        self.style.map(
            "Crowdin.Treeview",
            background=[("selected", "#1a365d")],
            foreground=[("selected", "#ffffff")]
        )
        self.style.configure(
            "Crowdin.Treeview.Heading",
            background="#131b2c",
            foreground="#94a3b8",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            borderwidth=0,
            bordercolor="#131b2c",
            padding=(8, 8)
        )
        self.style.map("Crowdin.Treeview.Heading", background=[("active", "#1e293b")])

        self.style.configure(
            "Crowdin.Vertical.TScrollbar",
            gripcount=0,
            background="#334155",
            troughcolor="#0f172a",
            bordercolor="#0f172a",
            arrowcolor="#94a3b8",
            relief="flat",
            borderwidth=0,
            arrowsize=11
        )
        self.style.map(
            "Crowdin.Vertical.TScrollbar",
            background=[("active", "#475569"), ("pressed", "#0284c7")],
            arrowcolor=[("active", "#ffffff")]
        )

    def _build_top_bar(self):
        self.top_bar = ctk.CTkFrame(self, fg_color="#111827", height=58, corner_radius=0)
        self.top_bar.pack(side=tk.TOP, fill=tk.X)
        self.top_bar.pack_propagate(False)

        # 1. Left Cluster
        left_grp = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_grp.pack(side=tk.LEFT, padx=12, pady=10)

        self.btn_toggle_lib = ctk.CTkButton(
            left_grp,
            text=t("btn_mods", count=0),
            width=115,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.toggle_library
        )
        self.btn_toggle_lib.pack(side=tk.LEFT, padx=(0, 6))
        CTooltip(self.btn_toggle_lib, lambda: t("tooltip_mods"))

        self.btn_browse = ctk.CTkButton(
            left_grp,
            text=t("btn_browse"),
            width=90,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.browse_mod_folder
        )
        self.btn_browse.pack(side=tk.LEFT, padx=4)
        CTooltip(self.btn_browse, lambda: t("tooltip_browse"))

        self.mod_badge = ctk.CTkLabel(
            left_grp,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.mod_badge.pack(side=tk.LEFT, padx=10)

        # 2. Right Action Cluster
        right_grp = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        right_grp.pack(side=tk.RIGHT, padx=12, pady=10)

        self.btn_install = ctk.CTkButton(
            right_grp,
            text=t("btn_install"),
            width=135,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            cursor="hand2",
            command=self.do_install
        )
        self.btn_install.pack(side=tk.RIGHT, padx=(6, 0))
        CTooltip(self.btn_install, lambda: t("tooltip_install"))

        self.btn_build = ctk.CTkButton(
            right_grp,
            text=t("btn_build"),
            width=95,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#0891b2",
            hover_color="#0e7490",
            cursor="hand2",
            command=self.do_build
        )
        self.btn_build.pack(side=tk.RIGHT, padx=4)
        CTooltip(self.btn_build, lambda: t("tooltip_build"))

        self.btn_translate = ctk.CTkButton(
            right_grp,
            text=t("btn_auto_translate"),
            width=125,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            cursor="hand2",
            command=self.start_auto_translate
        )
        self.btn_translate.pack(side=tk.RIGHT, padx=4)
        CTooltip(self.btn_translate, lambda: t("tooltip_auto_trans"))

        engine_label = self.translation_engine.upper()
        self.btn_engine = ctk.CTkButton(
            right_grp,
            text=f"🌐 {engine_label}",
            width=100,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.open_engine_settings
        )
        self.btn_engine.pack(side=tk.RIGHT, padx=6)
        CTooltip(self.btn_engine, lambda: t("tooltip_engine"))

        # Target language selector with renamed label: "Целевой язык:"
        lang_frame = ctk.CTkFrame(right_grp, fg_color="transparent")
        lang_frame.pack(side=tk.RIGHT, padx=6)

        self.lbl_target_lang = ctk.CTkLabel(
            lang_frame,
            text=t("target_lang_label"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94a3b8"
        )
        self.lbl_target_lang.pack(side=tk.LEFT, padx=(0, 4))

        self.lang_var = ctk.StringVar(value="Russian [ru]")
        self.lang_menu = ctk.CTkOptionMenu(
            lang_frame,
            variable=self.lang_var,
            values=[f"{name} [{code}]" for name, code in LANGUAGES],
            width=135,
            height=34,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#1e293b",
            button_color="#334155",
            command=self.on_lang_changed
        )
        self.lang_menu.pack(side=tk.LEFT)
        CTooltip(self.lang_menu, lambda: t("tooltip_lang"))

        # UI Language Switcher (RU / EN toggle button)
        ui_lang_frame = ctk.CTkFrame(right_grp, fg_color="#1e293b", corner_radius=6)
        ui_lang_frame.pack(side=tk.RIGHT, padx=(0, 8))

        self.btn_ui_ru = ctk.CTkButton(
            ui_lang_frame,
            text="🇷🇺 RU",
            width=48,
            height=30,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284c7" if CURRENT_UI_LANG == "ru" else "transparent",
            hover_color="#0369a1",
            cursor="hand2",
            command=lambda: self.switch_ui_lang("ru")
        )
        self.btn_ui_ru.pack(side=tk.LEFT, padx=1, pady=1)

        self.btn_ui_en = ctk.CTkButton(
            ui_lang_frame,
            text="🇬🇧 EN",
            width=48,
            height=30,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284c7" if CURRENT_UI_LANG == "en" else "transparent",
            hover_color="#0369a1",
            cursor="hand2",
            command=lambda: self.switch_ui_lang("en")
        )
        self.btn_ui_en.pack(side=tk.LEFT, padx=1, pady=1)
        CTooltip(ui_lang_frame, lambda: t("tooltip_ui_lang"))

        # 3. Dedicated Top-Bar Auto-Translate Live Progress Bar (Requested in Image 1!)
        self.top_progress_frame = ctk.CTkFrame(self.top_bar, width=370, height=34, fg_color="#182234", corner_radius=8, border_width=1, border_color="#0284c7")
        self.top_progress_frame.pack_propagate(False)
        self.top_progress_lbl = ctk.CTkLabel(
            self.top_progress_frame,
            text="✨ Автоперевод...",
            width=180,
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#f8fafc"
        )
        self.top_progress_lbl.pack(side=tk.LEFT, padx=(10, 8))

        self.top_progress_bar = ctk.CTkProgressBar(self.top_progress_frame, width=170, height=8, fg_color="#0f172a", progress_color="#10b981")
        self.top_progress_bar.pack(side=tk.LEFT, padx=4)
        self.top_progress_bar.set(0)

        self.btn_top_cancel = ctk.CTkButton(
            self.top_progress_frame,
            text="⏹",
            width=28,
            height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#dc2626",
            hover_color="#b91c1c",
            cursor="hand2",
            command=self.cancel_auto_translate
        )
        self.btn_top_cancel.pack(side=tk.LEFT, padx=(6, 8))
        CTooltip(self.btn_top_cancel, "Остановить автоперевод")

    def switch_ui_lang(self, lang_code):
        global CURRENT_UI_LANG
        CURRENT_UI_LANG = lang_code
        self.cfg["ui_lang"] = lang_code
        save_app_config(self.cfg)

        self.btn_ui_ru.configure(fg_color="#0284c7" if CURRENT_UI_LANG == "ru" else "transparent")
        self.btn_ui_en.configure(fg_color="#0284c7" if CURRENT_UI_LANG == "en" else "transparent")

        self.title(t("app_title"))
        self.btn_toggle_lib.configure(text=t("btn_mods", count=len(self.installed_mods)))
        self.btn_browse.configure(text=t("btn_browse"))
        self.btn_install.configure(text=t("btn_install"))
        self.btn_build.configure(text=t("btn_build"))
        self.btn_translate.configure(text=t("btn_auto_translate"))
        self.lbl_target_lang.configure(text=t("target_lang_label"))

        # Mod Library controls
        if hasattr(self, "lbl_lib_title"):
            self.lbl_lib_title.configure(text=t("mod_lib_title"))
        if hasattr(self, "lib_search_entry"):
            self.lib_search_entry.configure(placeholder_text=t("search_mods_placeholder"))
        if hasattr(self, "btn_cat_all"):
            self.btn_cat_all.configure(text=t("filter_all"))
        if hasattr(self, "btn_cat_ws"):
            self.btn_cat_ws.configure(text=t("filter_workshop"))
        if hasattr(self, "btn_cat_mods"):
            self.btn_cat_mods.configure(text=t("filter_mods"))

        # Central Table headings & search
        self.tree.heading("type", text=t("col_type"))
        self.tree.heading("original", text=t("col_original"))
        self.tree.heading("translation", text=t("col_translation"))
        self.tree.heading("status", text=t("col_status"))

        if hasattr(self, "search_entry"):
            self.search_entry.configure(placeholder_text=t("search_strings_placeholder"))
        self.btn_filter_all.configure(text=t("filter_all"))
        self.btn_filter_untrans.configure(text=t("filter_untrans"))
        self.btn_filter_overflow.configure(text=t("filter_overflow"))
        self.btn_filter_diff.configure(text=t("filter_diff"))
        self.btn_sort_new.configure(text=t("btn_new_to_top"))

        # Right Workspace
        self.ws_context_title.configure(text=t("context_title"))
        self.ws_orig_title.configure(text=t("orig_box_title"))
        self.ws_trans_title.configure(text=t("trans_box_title"))
        self.ws_sugg_title.configure(text=t("suggestions_title"))
        if hasattr(self, "btn_concise"):
            self.btn_concise.configure(text=t("btn_concise_action"))
        if hasattr(self, "btn_request_ai"):
            self.update_ai_btn_text()
        self.btn_save_next.configure(text=t("btn_save_next"))
        if hasattr(self, "btn_row_orig"):
            self.btn_row_orig.configure(text=t("btn_copy_orig"))
        if hasattr(self, "btn_row_clear"):
            self.btn_row_clear.configure(text=t("btn_clear_row"))
        if hasattr(self, "btn_concise_sec"):
            self.btn_concise_sec.configure(text=t("btn_concise"))
        if hasattr(self, "btn_nav_prev"):
            self.btn_nav_prev.configure(text=t("nav_prev"))
        if hasattr(self, "btn_nav_next"):
            self.btn_nav_next.configure(text=t("nav_next"))

        # Re-render active cards, filters and status
        self.render_mod_cards()
        self.apply_filter()
        self.update_stats()

        # Update right workspace labels if row is active
        if hasattr(self, "selected_item_id") and self.selected_item_id:
            orig = self.ws_orig_box.get("1.0", tk.END).strip()
            trans = self.ws_trans_box.get("1.0", tk.END).strip()
            self._on_translation_modified()
            if orig:
                self._render_crowdin_suggestions(orig, trans)

    def _build_main_layout(self):
        self.main_container = ctk.CTkFrame(self, fg_color="#090d16", corner_radius=0)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self.lib_frame = ctk.CTkFrame(self.main_container, fg_color="#0f172a", width=310, corner_radius=0)
        if self.show_library:
            self.lib_frame.pack(side=tk.LEFT, fill=tk.Y)
            self.lib_frame.pack_propagate(False)

        self._build_library_panel()

        self.center_frame = ctk.CTkFrame(self.main_container, fg_color="#0b1120", corner_radius=0, border_width=0)
        self.center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_table_panel()

        self.right_workspace = ctk.CTkFrame(self.main_container, fg_color="#0f172a", width=460, corner_radius=0)
        self.right_workspace.pack(side=tk.RIGHT, fill=tk.BOTH)
        self.right_workspace.pack_propagate(False)

        self._build_crowdin_workspace()

    def _build_library_panel(self):
        hdr = ctk.CTkFrame(self.lib_frame, fg_color="transparent", height=42)
        hdr.pack(fill=tk.X, padx=12, pady=(10, 4))
        hdr.pack_propagate(False)

        self.lbl_lib_title = ctk.CTkLabel(
            hdr,
            text=t("mod_lib_title"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94a3b8"
        )
        self.lbl_lib_title.pack(side=tk.LEFT)

        btn_refresh = ctk.CTkButton(
            hdr,
            text="🔄",
            width=28,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.refresh_mod_library
        )
        btn_refresh.pack(side=tk.RIGHT)
        CTooltip(btn_refresh, t("tooltip_refresh_mods"))

        self.lib_search_entry = ctk.CTkEntry(
            self.lib_frame,
            placeholder_text=t("search_mods_placeholder"),
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#1e293b",
            border_color="#334155"
        )
        self.lib_search_entry.pack(fill=tk.X, padx=12, pady=4)
        self.lib_search_entry.bind("<KeyRelease>", lambda e: self.filter_library_cards())

        cat_bar = ctk.CTkFrame(self.lib_frame, fg_color="transparent")
        cat_bar.pack(fill=tk.X, padx=12, pady=4)

        self.lib_filter = "all"
        self.btn_cat_all = ctk.CTkButton(cat_bar, text=t("filter_all"), width=56, height=26, font=ctk.CTkFont(size=10), fg_color="#0284c7", command=lambda: self.set_lib_filter("all"))
        self.btn_cat_all.pack(side=tk.LEFT, padx=1)
        self.btn_cat_ws = ctk.CTkButton(cat_bar, text=t("filter_workshop"), width=76, height=26, font=ctk.CTkFont(size=10), fg_color="#1e293b", command=lambda: self.set_lib_filter("workshop"))
        self.btn_cat_ws.pack(side=tk.LEFT, padx=1)
        self.btn_cat_mods = ctk.CTkButton(cat_bar, text=t("filter_mods"), width=56, height=26, font=ctk.CTkFont(size=10), fg_color="#1e293b", command=lambda: self.set_lib_filter("mods"))
        self.btn_cat_mods.pack(side=tk.LEFT, padx=1)

        self.cards_scroll = ctk.CTkScrollableFrame(self.lib_frame, fg_color="transparent", corner_radius=0)
        self.cards_scroll.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _build_table_panel(self):
        filter_bar = ctk.CTkFrame(self.center_frame, fg_color="#111827", height=48, corner_radius=0)
        filter_bar.pack(fill=tk.X, padx=0, pady=0)
        filter_bar.pack_propagate(False)

        self.search_entry = ctk.CTkEntry(
            filter_bar,
            placeholder_text=t("search_strings_placeholder"),
            width=270,
            height=32,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#1e293b",
            border_color="#334155"
        )
        self.search_entry.pack(side=tk.LEFT, padx=(12, 6), pady=8)
        self.search_entry.bind("<KeyRelease>", lambda e: self.apply_filter())

        self.btn_filter_all = ctk.CTkButton(filter_bar, text=t("filter_all"), width=50, height=28, font=ctk.CTkFont(size=11), fg_color="#0284c7", command=lambda: self.set_table_filter("all"))
        self.btn_filter_all.pack(side=tk.LEFT, padx=2)

        self.btn_filter_untrans = ctk.CTkButton(filter_bar, text=t("filter_untrans"), width=105, height=28, font=ctk.CTkFont(size=11), fg_color="#1e293b", command=lambda: self.set_table_filter("untranslated"))
        self.btn_filter_untrans.pack(side=tk.LEFT, padx=2)

        self.btn_filter_overflow = ctk.CTkButton(filter_bar, text=t("filter_overflow"), width=130, height=28, font=ctk.CTkFont(size=11), fg_color="#1e293b", command=lambda: self.set_table_filter("overflow"))
        self.btn_filter_overflow.pack(side=tk.LEFT, padx=2)

        self.btn_filter_diff = ctk.CTkButton(filter_bar, text=t("filter_diff"), width=125, height=28, font=ctk.CTkFont(size=11), fg_color="#1e293b", command=lambda: self.set_table_filter("diff"))
        self.btn_filter_diff.pack(side=tk.LEFT, padx=2)

        self.btn_sort_new = ctk.CTkButton(filter_bar, text=t("btn_new_to_top"), width=105, height=28, font=ctk.CTkFont(size=11), fg_color="#1e293b", hover_color="#334155", command=self.sort_new_to_top)
        self.btn_sort_new.pack(side=tk.RIGHT, padx=(0, 12))
        CTooltip(self.btn_sort_new, lambda: t("tooltip_new_top"))

        table_container = tk.Frame(self.center_frame, bg="#0f172a", bd=0, highlightthickness=0, relief="flat")
        table_container.pack(fill=tk.BOTH, expand=True)

        cols = ("#", "type", "original", "translation", "status")
        self.tree = ttk.Treeview(table_container, columns=cols, show="headings", style="Crowdin.Treeview", selectmode="browse")

        self.tree.heading("#", text="#")
        self.tree.heading("type", text=t("col_type"))
        self.tree.heading("original", text=t("col_original"))
        self.tree.heading("translation", text=t("col_translation"))
        self.tree.heading("status", text=t("col_status"))

        self.tree.column("#", width=45, minwidth=40, anchor="center")
        self.tree.column("type", width=55, minwidth=50, anchor="center")
        self.tree.column("original", width=260, minwidth=180)
        self.tree.column("translation", width=260, minwidth=180)
        self.tree.column("status", width=115, minwidth=100, anchor="center")

        scroll_y = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=self.tree.yview, style="Crowdin.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll_y.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("even", background="#0f172a", foreground="#f8fafc")
        self.tree.tag_configure("odd", background="#131d33", foreground="#f8fafc")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.tree.bind("<F2>", lambda e: self.focus_editor())
        self.tree.bind("<Down>", lambda e: self.after(10, self.on_tree_select))
        self.tree.bind("<Up>", lambda e: self.after(10, self.on_tree_select))

    def _build_crowdin_workspace(self):
        hdr = ctk.CTkFrame(self.right_workspace, fg_color="transparent", height=38)
        hdr.pack(fill=tk.X, padx=12, pady=(8, 2))
        hdr.pack_propagate(False)

        self.ws_context_title = ctk.CTkLabel(
            hdr,
            text=t("context_title"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#94a3b8"
        )
        self.ws_context_title.pack(side=tk.LEFT)

        self.ws_status_chip = ctk.CTkFrame(hdr, fg_color="#1e293b", corner_radius=6, border_width=1, border_color="#64748b")
        self.ws_status_chip.pack(side=tk.RIGHT)
        self.ws_status_badge = ctk.CTkLabel(
            self.ws_status_chip,
            text=t("badge_empty"),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#cbd5e1",
            padx=8,
            pady=2
        )
        self.ws_status_badge.pack()

        # 1. Original Text Card
        orig_card = ctk.CTkFrame(self.right_workspace, fg_color="#182234", corner_radius=8, border_width=1, border_color="#1e293b")
        orig_card.pack(fill=tk.X, padx=12, pady=4)

        orig_top = ctk.CTkFrame(orig_card, fg_color="transparent")
        orig_top.pack(fill=tk.X, padx=10, pady=(6, 2))

        self.ws_orig_title = ctk.CTkLabel(orig_top, text=t("orig_box_title"), font=ctk.CTkFont(size=10, weight="bold"), text_color="#38bdf8")
        self.ws_orig_title.pack(side=tk.LEFT)

        self.ws_orig_len_lbl = ctk.CTkLabel(orig_top, text=t("char_count", lang="cn", count=0), font=ctk.CTkFont(size=10), text_color="#94a3b8")
        self.ws_orig_len_lbl.pack(side=tk.RIGHT)

        self.ws_orig_box = ctk.CTkTextbox(
            orig_card,
            height=50,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#0f172a",
            text_color="#f8fafc",
            wrap="word",
            border_width=0
        )
        self.ws_orig_box.pack(fill=tk.X, padx=8, pady=(0, 6))
        setup_textbox_clipboard(self.ws_orig_box, is_readonly=True)

        # 2. UI Fit Card
        self.ws_fit_card = ctk.CTkFrame(self.right_workspace, fg_color="#1e293b", corner_radius=6, border_width=1, border_color="#334155")
        self.ws_fit_card.pack(fill=tk.X, padx=12, pady=3)

        fit_inner = ctk.CTkFrame(self.ws_fit_card, fg_color="transparent")
        fit_inner.pack(fill=tk.X, padx=8, pady=4)

        self.ws_meta_lbl = ctk.CTkLabel(fit_inner, text=f"{t('meta_file_prefix')} -", font=ctk.CTkFont(size=10), text_color="#64748b")
        self.ws_meta_lbl.pack(anchor="w")

        self.ws_overflow_alert = ctk.CTkFrame(self.ws_fit_card, fg_color="#451a03", corner_radius=6, border_width=1, border_color="#b45309")
        self.ws_overflow_alert_lbl = ctk.CTkLabel(
            self.ws_overflow_alert,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#fef3c7",
            justify="left"
        )
        self.ws_overflow_alert_lbl.pack(side=tk.LEFT, padx=8, pady=4, fill=tk.X, expand=True)

        self.btn_concise = ctk.CTkButton(
            self.ws_overflow_alert,
            text=t("btn_concise_action"),
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            fg_color="#d97706",
            hover_color="#b45309",
            cursor="hand2",
            height=26,
            command=self.apply_concise_suggestion
        )
        self.btn_concise.pack(side=tk.RIGHT, padx=6, pady=3)

        # 3. Translation Editor Card
        trans_card = ctk.CTkFrame(self.right_workspace, fg_color="#182234", corner_radius=8, border_width=1, border_color="#1e293b")
        trans_card.pack(fill=tk.BOTH, expand=True, padx=12, pady=3)

        trans_top = ctk.CTkFrame(trans_card, fg_color="transparent")
        trans_top.pack(fill=tk.X, padx=10, pady=(6, 2))

        self.ws_trans_title = ctk.CTkLabel(trans_top, text=t("trans_box_title"), font=ctk.CTkFont(size=10, weight="bold"), text_color="#10b981")
        self.ws_trans_title.pack(side=tk.LEFT)

        self.ws_trans_len_lbl = ctk.CTkLabel(trans_top, text=t("char_count", lang="RU", count=0), font=ctk.CTkFont(size=10), text_color="#94a3b8")
        self.ws_trans_len_lbl.pack(side=tk.RIGHT)

        self.chips_frame = ctk.CTkFrame(trans_card, fg_color="transparent", height=22)
        self.chips_frame.pack(fill=tk.X, padx=8, pady=(1, 3))

        self.ws_trans_box = ctk.CTkTextbox(
            trans_card,
            height=90,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#0f172a",
            text_color="#f8fafc",
            wrap="word",
            border_width=0
        )
        self.ws_trans_box.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        setup_textbox_clipboard(self.ws_trans_box, is_readonly=False, on_modify=self._on_translation_modified)
        self.ws_trans_box.bind("<KeyRelease>", lambda e: self._on_translation_modified())

        self.ws_trans_box.bind("<Control-Return>", lambda e: self.save_and_next())
        self.ws_trans_box.bind("<Control-KP_Enter>", lambda e: self.save_and_next())
        self.ws_trans_box.bind("<Alt-Up>", lambda e: self.nav_prev())
        self.ws_trans_box.bind("<Alt-Down>", lambda e: self.nav_next())
        self.ws_trans_box.bind("<Control-Key-1>", lambda e: self.apply_suggestion_by_index(0))
        self.ws_trans_box.bind("<Control-Key-2>", lambda e: self.apply_suggestion_by_index(1))

        # 4. Crowdin Suggestions Panel (Interactive alternative variants)
        self.suggestions_frame = ctk.CTkFrame(self.right_workspace, fg_color="#111827", corner_radius=8, border_width=1, border_color="#1e293b")
        self.suggestions_frame.pack(fill=tk.X, padx=12, pady=3)

        sugg_top = ctk.CTkFrame(self.suggestions_frame, fg_color="transparent")
        sugg_top.pack(fill=tk.X, padx=8, pady=(4, 2))
        self.ws_sugg_title = ctk.CTkLabel(sugg_top, text=t("suggestions_title"), font=ctk.CTkFont(size=9, weight="bold"), text_color="#94a3b8")
        self.ws_sugg_title.pack(side=tk.LEFT)

        btns_sugg = ctk.CTkFrame(sugg_top, fg_color="transparent")
        btns_sugg.pack(side=tk.RIGHT)

        eng_name = self.ollama_model if self.translation_engine == "ollama" else self.translation_engine.upper()
        self.btn_request_ai = ctk.CTkButton(
            btns_sugg,
            text=f"✨ {eng_name}",
            height=22,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#1e293b",
            hover_color="#0284c7",
            border_width=1,
            border_color="#0369a1",
            cursor="hand2",
            command=self.translate_active_row_ai
        )
        self.btn_request_ai.pack(side=tk.LEFT, padx=(0, 4))
        CTooltip(self.btn_request_ai, t("tooltip_ai_req", engine=eng_name))

        self.btn_request_google = ctk.CTkButton(
            btns_sugg,
            text="🌐 Google",
            height=22,
            width=62,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#1e293b",
            hover_color="#0284c7",
            border_width=1,
            border_color="#334155",
            cursor="hand2",
            command=self.translate_active_row_google
        )
        self.btn_request_google.pack(side=tk.LEFT)
        CTooltip(self.btn_request_google, t("tooltip_google_req"))

        self.sugg_items_container = ctk.CTkFrame(self.suggestions_frame, fg_color="transparent")
        self.sugg_items_container.pack(fill=tk.X, padx=6, pady=(0, 6))

        # 5. Workspace Action Bar with Proportional Buttons
        action_bar = ctk.CTkFrame(self.right_workspace, fg_color="transparent")
        action_bar.pack(fill=tk.X, padx=12, pady=(4, 10))

        self.btn_save_next = ctk.CTkButton(
            action_bar,
            text=t("btn_save_next"),
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color="#16a34a",
            hover_color="#15803d",
            cursor="hand2",
            command=self.save_and_next
        )
        self.btn_save_next.pack(fill=tk.X, pady=(0, 6))

        sec_bar = ctk.CTkFrame(action_bar, fg_color="transparent")
        sec_bar.pack(fill=tk.X)

        

        self.btn_row_orig = ctk.CTkButton(
            sec_bar,
            text=t("btn_copy_orig"),
            width=76,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            cursor="hand2",
            command=self.copy_from_orig
        )
        self.btn_row_orig.pack(side=tk.LEFT, padx=3)

        self.btn_row_clear = ctk.CTkButton(
            sec_bar,
            text=t("btn_clear_row"),
            width=72,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            cursor="hand2",
            command=self.clear_active_translation
        )
        self.btn_row_clear.pack(side=tk.LEFT, padx=3)

        self.btn_concise_sec = ctk.CTkButton(
            sec_bar,
            text=t("btn_concise"),
            width=76,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color="#d97706",
            hover_color="#b45309",
            cursor="hand2",
            command=self.apply_concise_suggestion
        )
        self.btn_concise_sec.pack(side=tk.LEFT, padx=3)
        CTooltip(self.btn_concise_sec, lambda: t("tooltip_concise"))

        # Proportional & Symmetrical Navigation Buttons
        self.btn_nav_next = ctk.CTkButton(
            sec_bar,
            text=t("nav_next"),
            width=64,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.nav_next
        )
        self.btn_nav_next.pack(side=tk.RIGHT, padx=(3, 0))
        CTooltip(self.btn_nav_next, lambda: t("tooltip_next"))

        self.btn_nav_prev = ctk.CTkButton(
            sec_bar,
            text=t("nav_prev"),
            width=64,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1e293b",
            hover_color="#334155",
            cursor="hand2",
            command=self.nav_prev
        )
        self.btn_nav_prev.pack(side=tk.RIGHT, padx=3)
        CTooltip(self.btn_nav_prev, lambda: t("tooltip_prev"))

    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, fg_color="#090d16", height=28, corner_radius=0)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)

        self.status_lbl = ctk.CTkLabel(
            self.status_bar,
            text=t("status_ready", trans=0, total=0, pct=0),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#94a3b8"
        )
        self.status_lbl.pack(side=tk.LEFT, padx=12)

        self.stats_lbl = ctk.CTkLabel(
            self.status_bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38bdf8"
        )
        self.stats_lbl.pack(side=tk.RIGHT, padx=12)

    # -------------------------------------------------------------
    # Interactive Mod Library Cards & Drag-and-Drop
    # -------------------------------------------------------------

    def toggle_library(self):
        self.show_library = not self.show_library
        if self.show_library:
            self.lib_frame.pack(side=tk.LEFT, fill=tk.Y, before=self.center_frame)
            self.lib_frame.pack_propagate(False)
        else:
            self.lib_frame.pack_forget()
        self.cfg["show_library"] = self.show_library
        save_app_config(self.cfg)

    def refresh_mod_library(self):
        def _scan_worker():
            mods = scan_installed_mods()
            def _apply_ui():
                self.installed_mods = mods
                self.btn_toggle_lib.configure(text=t("btn_mods", count=len(self.installed_mods)))
                self.render_mod_cards()
            self.after(0, _apply_ui)
        threading.Thread(target=_scan_worker, daemon=True).start()

    def set_lib_filter(self, cat):
        self.lib_filter = cat
        self.btn_cat_all.configure(fg_color="#0284c7" if cat == "all" else "#1e293b")
        self.btn_cat_ws.configure(fg_color="#0284c7" if cat == "workshop" else "#1e293b")
        self.btn_cat_mods.configure(fg_color="#0284c7" if cat == "mods" else "#1e293b")
        self.render_mod_cards()

    def filter_library_cards(self):
        self.render_mod_cards()

    def render_mod_cards(self):
        for w in self.cards_scroll.winfo_children():
            w.destroy()

        q = self.lib_search_entry.get().strip().lower()

        filtered = []
        for m in self.installed_mods:
            if self.lib_filter == "workshop" and m["source"] != "Workshop": continue
            if self.lib_filter == "mods" and m["source"] != "Game Mods": continue
            if q and (q not in m["name"].lower() and q not in m["id"].lower() and q not in m["author"].lower()):
                continue
            filtered.append(m)

        for mod in filtered:
            self._create_mod_card(mod)

    def _create_mod_card(self, mod):
        is_active = self.project and os.path.samefile(self.project.mod_path, mod["path"]) if self.project and os.path.exists(mod["path"]) else False

        card = ctk.CTkFrame(
            self.cards_scroll,
            fg_color="#0284c7" if is_active else "#182234",
            corner_radius=8,
            border_width=1,
            border_color="#0ea5e9" if is_active else "#223048",
            cursor="hand2"
        )
        card.pack(fill=tk.X, pady=4, padx=2)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill=tk.X, padx=8, pady=(6, 2))

        # High-contrast rounded pill badges (Variant 2 style)
        if mod["source"] == "Workshop":
            src_chip = ctk.CTkFrame(top, fg_color="#0b1e3b", corner_radius=10, border_width=1, border_color="#38bdf8")
            src_lbl = ctk.CTkLabel(src_chip, text="Steam", font=ctk.CTkFont(size=9, weight="bold"), text_color="#38bdf8", padx=7, pady=0)
        else:
            src_chip = ctk.CTkFrame(top, fg_color="#062e1e", corner_radius=10, border_width=1, border_color="#10b981")
            src_lbl = ctk.CTkLabel(src_chip, text="Mods", font=ctk.CTkFont(size=9, weight="bold"), text_color="#34d399", padx=7, pady=0)
        src_chip.pack(side=tk.LEFT, padx=(0, 4))
        src_lbl.pack()

        if mod["has_csv"]:
            fmt_chip = ctk.CTkFrame(top, fg_color="#042724", corner_radius=10, border_width=1, border_color="#14b8a6")
            fmt_lbl = ctk.CTkLabel(fmt_chip, text="CSV", font=ctk.CTkFont(size=9, weight="bold"), text_color="#2dd4bf", padx=6, pady=0)
        else:
            fmt_chip = ctk.CTkFrame(top, fg_color="#200d3d", corner_radius=10, border_width=1, border_color="#a855f7")
            fmt_lbl = ctk.CTkLabel(fmt_chip, text="DLL", font=ctk.CTkFont(size=9, weight="bold"), text_color="#c084fc", padx=6, pady=0)
        fmt_chip.pack(side=tk.LEFT, padx=(0, 4))
        fmt_lbl.pack()

        upd_chip = None
        upd_lbl = None
        inst_chip = None
        inst_lbl = None

        if mod.get("has_update"):
            upd_chip = ctk.CTkFrame(top, fg_color="#3a1503", corner_radius=10, border_width=1, border_color="#f59e0b")
            upd_lbl = ctk.CTkLabel(
                upd_chip,
                text=f"🔄 Update v{mod['version']}",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color="#fbbf24",
                padx=7,
                pady=0
            )
            upd_chip.pack(side=tk.RIGHT)
            upd_lbl.pack()
            CTooltip(upd_chip, t("tooltip_mod_update_avail", ver=mod['version'], inst=mod.get('installed_ver', '')))
        elif mod.get("matched_installed") or mod["source"] == "Game Mods":
            inst_chip = ctk.CTkFrame(top, fg_color="#052e16", corner_radius=10, border_width=1, border_color="#16a34a")
            inst_lbl = ctk.CTkLabel(
                inst_chip,
                text=t("badge_installed"),
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color="#4ade80",
                padx=6,
                pady=0
            )
            inst_chip.pack(side=tk.RIGHT)
            inst_lbl.pack()
            CTooltip(inst_chip, t("installed_badge"))

        name_lbl = ctk.CTkLabel(
            card,
            text=mod["name"][:38],
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#ffffff" if is_active else "#e2e8f0",
            anchor="w"
        )
        name_lbl.pack(fill=tk.X, padx=8, pady=(2, 2))

        sub = ctk.CTkFrame(card, fg_color="transparent")
        sub.pack(fill=tk.X, padx=8, pady=(0, 6))

        ver_txt = f"v{mod['version']}"
        if mod.get("author") and mod["author"] != "Unknown":
            ver_txt += f" • {mod['author'][:16]}"
        ctk.CTkLabel(sub, text=ver_txt, font=ctk.CTkFont(size=10), text_color="#94a3b8").pack(side=tk.LEFT)

        def _on_click(e=None, m=mod):
            self.load_mod(m["path"])

        click_targets = [card, name_lbl, top, sub, src_chip, src_lbl, fmt_chip, fmt_lbl]
        if upd_chip: click_targets.extend([upd_chip, upd_lbl])
        if inst_chip: click_targets.extend([inst_chip, inst_lbl])
        for w in click_targets: w.bind("<Button-1>", _on_click)

    def on_files_dropped(self, dropped_paths):
        if not dropped_paths: return
        first = dropped_paths[0]
        if os.path.isdir(first): self.load_mod(first)
        else: self.load_mod(os.path.dirname(first))

    def browse_mod_folder(self):
        f = filedialog.askdirectory(title="Выберите папку мода", initialdir=DEFAULT_WORKSHOP_MODS)
        if f: self.load_mod(f)

    def load_mod(self, mod_path):
        if not os.path.exists(mod_path):
            self.toast_show("Папка мода не найдена!", "error")
            return

        lang = self.get_selected_lang_code()
        self.status_lbl.configure(text=t("status_scanning", name=os.path.basename(mod_path)))
        self.update_idletasks()

        try:
            self.project = ModProject(mod_path)
            count = self.project.scan(lang)

            meta = self.project.manifest
            fmt = "CSV" if self.project.is_csv_mod else "DLL"
            self.mod_badge.configure(text=f"📦 {meta['name']} • {meta['author']} [{fmt}]")

            self.render_mod_cards()
            self.apply_filter()
            self.update_stats()

            if self.project.new_strings_count > 0:
                self.toast_show(t("diff_banner", new_count=self.project.new_strings_count, mod_count=self.project.changed_strings_count), "info", 4000)
            else:
                self.toast_show(f"Загружен мод '{meta['name']}': {count} строк", "success", 2000)

            children = self.tree.get_children()
            if children:
                self.tree.selection_set(children[0])
                self.tree.focus(children[0])
                self.on_tree_select()

        except Exception as ex:
            self.toast_show(f"Ошибка загрузки мода: {ex}", "error")

    # -------------------------------------------------------------
    # Table Filter & Sorting Logic
    # -------------------------------------------------------------

    def set_table_filter(self, flt):
        self.current_filter = flt
        self.btn_filter_all.configure(fg_color="#0284c7" if flt == "all" else "#1e293b")
        self.btn_filter_untrans.configure(fg_color="#0284c7" if flt == "untranslated" else "#1e293b")
        self.btn_filter_overflow.configure(fg_color="#0284c7" if flt == "overflow" else "#1e293b")
        self.btn_filter_diff.configure(fg_color="#0284c7" if flt == "diff" else "#1e293b")
        self.apply_filter()

    def sort_new_to_top(self):
        if not self.project or not self.project.strings: return
        self.project.strings.sort(key=lambda s: 0 if s.get("status") in ("new", "changed") else 1)
        self.apply_filter()
        self.toast_show("Новые строки из обновления перемещены в начало!", "info")

    def apply_filter(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.project: return

        q = self.search_entry.get().strip().lower()
        filtered = []
        untrans_count = 0
        overflow_count = 0
        diff_count = 0

        for s in self.project.strings:
            idx = s["index"]
            orig = s["original"]
            trans = self.project.translations.get(idx, "")
            st = s.get("status", "synced")

            is_untrans = not trans
            diag = s.get("_diag")
            if diag is None:
                diag = analyze_ui_fit(orig, trans)
                s["_diag"] = diag

            is_overflow = diag["is_overflow_risk"]
            is_diff = st in ("new", "changed")

            if is_untrans: untrans_count += 1
            if is_overflow: overflow_count += 1
            if is_diff: diff_count += 1

            if self.current_filter == "untranslated" and not is_untrans: continue
            if self.current_filter == "overflow" and not is_overflow: continue
            if self.current_filter == "diff" and not is_diff: continue

            if q:
                if q not in orig.lower() and q not in trans.lower() and q not in s.get("key", "").lower():
                    continue

            if st == "new": status_badge = t("badge_new")
            elif st == "changed": status_badge = t("badge_changed")
            elif is_overflow: status_badge = t("badge_long")
            elif trans: status_badge = t("badge_ok")
            else: status_badge = t("badge_empty")

            fmt_badge = f"[{s.get('type', 'STR')}]"
            filtered.append((idx, fmt_badge, orig, trans, status_badge))

        # Instant progressive streaming: first 100 rows appear in <5ms, rest stream smoothly
        def _stream_rows(items, start_idx=0, chunk=200):
            end_idx = min(start_idx + chunk, len(items))
            for i in range(start_idx, end_idx):
                item_idx, ftype, o_text, t_text, s_badge = items[i]
                row_tag = "even" if i % 2 == 0 else "odd"
                self.tree.insert("", tk.END, iid=str(item_idx), values=(
                    i + 1,
                    ftype,
                    o_text,
                    t_text,
                    s_badge
                ), tags=(row_tag,))
            if end_idx < len(items):
                self.after(5, lambda: _stream_rows(items, end_idx, chunk))

        _stream_rows(filtered, 0, 100)

        self.btn_filter_untrans.configure(text=f"{t('filter_untrans')} ({untrans_count})")
        self.btn_filter_overflow.configure(text=f"{t('filter_overflow')} ({overflow_count})")
        self.btn_filter_diff.configure(text=f"{t('filter_diff')} ({diff_count})")

    def update_stats(self):
        if not self.project:
            self.stats_lbl.configure(text="")
            return
        total = len(self.project.strings)
        done = sum(1 for s in self.project.strings if self.project.translations.get(s["index"]))
        pct = int(done / total * 100) if total > 0 else 0
        self.stats_lbl.configure(text=t("stats_summary", total=total, done=done, pct=pct))
        self.status_lbl.configure(text=t("status_ready", trans=done, total=total, pct=pct))

    # -------------------------------------------------------------
    # Workspace & Crowdin Suggestions
    # -------------------------------------------------------------

    def on_tree_select(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        item_id = sel[0]
        self.selected_item_id = item_id

        values = self.tree.item(item_id, "values")
        if not values or len(values) < 4: return

        idx = int(values[0]) - 1
        orig = values[2]
        trans = values[3]

        self.ws_orig_box.configure(state="normal")
        self.ws_orig_box.delete("1.0", tk.END)
        self.ws_orig_box.insert("1.0", orig)
        self.ws_orig_box.configure(state="disabled")

        self.ws_orig_len_lbl.configure(text=t("char_count", lang="cn", count=len(orig)))

        s_obj = next((s for s in self.project.strings if s["index"] == idx), None) if self.project else None
        meta_val = s_obj.get('dll', s_obj.get('key', '-')) if s_obj else "-"
        self.ws_meta_lbl.configure(text=f"{t('meta_file_prefix')} {meta_val}")

        self.ws_trans_box.delete("1.0", tk.END)
        self.ws_trans_box.insert("1.0", trans)

        self._render_placeholder_chips(orig)
        self._on_translation_modified()
        self._render_crowdin_suggestions(orig, trans)

    def _render_placeholder_chips(self, orig_text):
        for w in self.chips_frame.winfo_children(): w.destroy()
        tokens = TOKEN_REGEX.findall(orig_text)
        if tokens:
            for t_tok in set(tokens):
                btn = ctk.CTkButton(
                    self.chips_frame,
                    text=t_tok,
                    height=20,
                    width=max(28, len(t_tok)*7+8),
                    font=ctk.CTkFont(family="Consolas", size=9),
                    fg_color="#334155",
                    hover_color="#0284c7",
                    cursor="hand2",
                    command=lambda tok=t_tok: self.insert_token(tok)
                )
                btn.pack(side=tk.LEFT, padx=2)
                CTooltip(btn, t("tooltip_insert_token", tok=t_tok))

    def _render_crowdin_suggestions(self, orig, current_trans, ai_res=None, ai_engine=None):
        """Renders Crowdin-style list items grouped into Glossary/TM and Machine/AI."""
        for w in self.sugg_items_container.winfo_children():
            w.destroy()

        lang = self.get_selected_lang_code()
        self.active_suggestions = generate_crowdin_suggestions(
            orig, current_trans,
            target_lang=lang,
            ai_res=ai_res,
            ai_engine=ai_engine or self.translation_engine,
            ai_model=self.ollama_model
        )

        if not self.active_suggestions:
            ctk.CTkLabel(
                self.sugg_items_container,
                text=t("no_suggestions"),
                font=ctk.CTkFont(size=10),
                text_color="#64748b"
            ).pack(anchor="w", padx=6, pady=4)
            return

        # Separate items into groups like Crowdin
        tm_items = [s for s in self.active_suggestions if any(k in s["source"].lower() for k in ["глоссарий", "компактный", "glossary", "compact", "concise"])]
        mt_items = [s for s in self.active_suggestions if s not in tm_items]

        for i in range(1, 6):
            self.ws_trans_box.bind(f"<Control-Key-{i}>", lambda e, idx=i-1: self.apply_suggestion_by_index(idx))

        global_idx = 0

        def _render_section(title, items, icon, title_color):
            nonlocal global_idx
            if not items: return

            sec_hdr = ctk.CTkFrame(self.sugg_items_container, fg_color="transparent")
            sec_hdr.pack(fill=tk.X, padx=4, pady=(4, 1))
            ctk.CTkLabel(
                sec_hdr,
                text=f"{icon} {title}",
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color=title_color
            ).pack(side=tk.LEFT)

            for s in items:
                idx = global_idx
                global_idx += 1
                row = ctk.CTkFrame(
                    self.sugg_items_container,
                    fg_color="#0f172a",
                    corner_radius=4,
                    border_width=0,
                    cursor="hand2"
                )
                row.pack(fill=tk.X, padx=2, pady=1)

                top_line = ctk.CTkFrame(row, fg_color="transparent")
                top_line.pack(fill=tk.X, padx=6, pady=(3, 0))

                txt_lbl = ctk.CTkLabel(
                    top_line,
                    text=s["text"],
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color="#f8fafc",
                    anchor="w",
                    justify="left"
                )
                txt_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

                kbd_lbl = ctk.CTkLabel(
                    top_line,
                    text=f"Ctrl+{idx+1}" if idx < 5 else "",
                    font=ctk.CTkFont(family="Consolas", size=9),
                    text_color="#64748b"
                )
                kbd_lbl.pack(side=tk.RIGHT)

                sub_line = ctk.CTkFrame(row, fg_color="transparent")
                sub_line.pack(fill=tk.X, padx=6, pady=(0, 3))

                src_lbl = ctk.CTkLabel(
                    sub_line,
                    text=s["source"],
                    font=ctk.CTkFont(size=9),
                    text_color=s.get("badge_color", "#94a3b8")
                )
                src_lbl.pack(side=tk.LEFT)

                def _on_enter(e, r=row): r.configure(fg_color="#1e293b")
                def _on_leave(e, r=row): r.configure(fg_color="#0f172a")
                def _apply(e=None, text_to_set=s["text"]):
                    self.ws_trans_box.delete("1.0", tk.END)
                    self.ws_trans_box.insert("1.0", text_to_set)
                    self._on_translation_modified()

                for w in [row, top_line, sub_line, txt_lbl, kbd_lbl, src_lbl]:
                    w.bind("<Enter>", _on_enter)
                    w.bind("<Leave>", _on_leave)
                    w.bind("<Button-1>", _apply)

        if tm_items:
            _render_section(t("sec_glossary"), tm_items, "📖", "#38bdf8")
        if mt_items:
            _render_section(t("sec_machine_ai"), mt_items, "🤖", "#a855f7")

    def apply_suggestion_by_index(self, index):
        if hasattr(self, "active_suggestions") and index < len(self.active_suggestions):
            s_text = self.active_suggestions[index]["text"]
            self.ws_trans_box.delete("1.0", tk.END)
            self.ws_trans_box.insert("1.0", s_text)
            self._on_translation_modified()
            return "break"
        return None

    def _on_translation_modified(self):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        trans = self.ws_trans_box.get("1.0", tk.END).strip()

        lang = self.get_selected_lang_code().upper()
        self.ws_trans_len_lbl.configure(text=t("char_count", lang=lang, count=len(trans)))

        diag = analyze_ui_fit(orig, trans)

        if diag["is_overflow_risk"]:
            self.ws_overflow_alert.pack(fill=tk.X, padx=10, pady=(4, 6))
            ratio_pct = int(diag["ratio"] * 100)
            self.ws_overflow_alert_lbl.configure(
                text=t("overflow_warning", ratio=diag["ratio"], pct=ratio_pct)
            )
            self.btn_concise.pack(side=tk.RIGHT, padx=6, pady=3)
        else:
            self.ws_overflow_alert.pack_forget()

        if trans:
            if diag["is_overflow_risk"]:
                self.ws_status_chip.configure(fg_color="#451a03", border_color="#f59e0b")
                self.ws_status_badge.configure(text=t("badge_long"), text_color="#fde68a")
            else:
                self.ws_status_chip.configure(fg_color="#064e3b", border_color="#10b981")
                self.ws_status_badge.configure(text=t("badge_ok"), text_color="#6ee7b7")
        else:
            self.ws_status_chip.configure(fg_color="#1e293b", border_color="#64748b")
            self.ws_status_badge.configure(text=t("badge_empty"), text_color="#cbd5e1")

    def insert_token(self, token):
        self.ws_trans_box.insert(tk.INSERT, token)
        self.ws_trans_box.focus()
        self._on_translation_modified()

    def apply_concise_suggestion(self):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        trans = self.ws_trans_box.get("1.0", tk.END).strip()
        cand = make_concise(orig, trans)
        if cand:
            self.ws_trans_box.delete("1.0", tk.END)
            self.ws_trans_box.insert("1.0", cand)
            self._on_translation_modified()
            self.toast_show("Применен краткий вариант для интерфейса", "info")

    def save_and_next(self):
        if not self.selected_item_id or not self.project: return

        idx = int(self.selected_item_id)
        trans = self.ws_trans_box.get("1.0", tk.END).strip()

        self.project.translations[idx] = trans

        s_obj = next((s for s in self.project.strings if s["index"] == idx), None)
        if s_obj:
            s_obj["translation"] = trans
            s_obj["status"] = "synced"

        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        diag = analyze_ui_fit(orig, trans)
        if diag["is_overflow_risk"]: status_badge = t("badge_long")
        elif trans: status_badge = t("badge_ok")
        else: status_badge = t("badge_empty")

        values = list(self.tree.item(self.selected_item_id, "values"))
        values[3] = trans
        values[4] = status_badge
        self.tree.item(self.selected_item_id, values=values)

        self.update_stats()

        self.btn_save_next.configure(fg_color="#059669", text="✓ Сохранено!")
        self.after(250, lambda: self.btn_save_next.configure(fg_color="#16a34a", text=t("btn_save_next")))

        all_items = self.tree.get_children()
        try:
            curr_pos = all_items.index(self.selected_item_id)
            for nxt in all_items[curr_pos+1:]:
                vals = self.tree.item(nxt, "values")
                if not vals[3]:
                    self.tree.selection_set(nxt)
                    self.tree.see(nxt)
                    self.on_tree_select()
                    return
            if curr_pos + 1 < len(all_items):
                nxt = all_items[curr_pos + 1]
                self.tree.selection_set(nxt)
                self.tree.see(nxt)
                self.on_tree_select()
        except Exception: pass

    def nav_next(self):
        all_items = self.tree.get_children()
        if not all_items: return
        if self.selected_item_id and self.selected_item_id in all_items:
            idx = all_items.index(self.selected_item_id)
            if idx + 1 < len(all_items):
                nxt = all_items[idx + 1]
                self.tree.selection_set(nxt)
                self.tree.see(nxt)
                self.on_tree_select()
        else:
            self.tree.selection_set(all_items[0])
            self.on_tree_select()

    def nav_prev(self):
        all_items = self.tree.get_children()
        if not all_items: return
        if self.selected_item_id and self.selected_item_id in all_items:
            idx = all_items.index(self.selected_item_id)
            if idx - 1 >= 0:
                prev_i = all_items[idx - 1]
                self.tree.selection_set(prev_i)
                self.tree.see(prev_i)
                self.on_tree_select()

    def update_ai_btn_text(self):
        if hasattr(self, "btn_request_ai"):
            eng_name = self.ollama_model if self.translation_engine == "ollama" else self.translation_engine.upper()
            self.btn_request_ai.configure(text=f"✨ {eng_name}")

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

        eng_label = self.ollama_model if (engine == "ollama" and self.ollama_model) else engine.upper()
        orig_btn_txt = button_ref.cget("text") if button_ref else ""
        if button_ref:
            button_ref.configure(text="⏳ Запрос...", state="disabled")

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

                if ai_text:
                    self.ws_trans_box.delete("1.0", tk.END)
                    self.ws_trans_box.insert("1.0", ai_text)
                    self._on_translation_modified()
                    self._render_crowdin_suggestions(orig, ai_text, ai_res=ai_text, ai_engine=engine)
                    self.toast_show(f"✓ Перевод получен от {eng_label}", "success", 2000)

            self.after(0, _finish)

        threading.Thread(target=_worker, daemon=True).start()

    def copy_from_orig(self):
        orig = self.ws_orig_box.get("1.0", tk.END).strip()
        self.ws_trans_box.delete("1.0", tk.END)
        self.ws_trans_box.insert("1.0", orig)
        self._on_translation_modified()

    def clear_active_translation(self):
        self.ws_trans_box.delete("1.0", tk.END)
        self._on_translation_modified()

    def focus_editor(self):
        self.ws_trans_box.focus()

    def on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.on_tree_select()

            menu = tk.Menu(self, tearoff=0, bg="#1e222b", fg="#f8fafc", activebackground="#0284c7")
            menu.add_command(label="Редактировать (F2)", command=self.focus_editor)
            menu.add_command(label="Перевести строку", command=self.translate_active_row)
            menu.add_command(label="✂ Сократить перевод", command=self.apply_concise_suggestion)
            menu.add_separator()
            menu.add_command(label="Копировать оригинал", command=lambda: self.clipboard_clear() or self.clipboard_append(self.ws_orig_box.get("1.0", tk.END).strip()))
            menu.add_command(label="Очистить перевод", command=self.clear_active_translation)
            menu.tk_popup(event.x_root, event.y_root)

    def get_selected_lang_code(self):
        val = self.lang_var.get()
        m = re.search(r'\[([a-zA-Z\-]+)\]', val)
        return m.group(1) if m else "ru"

    def on_lang_changed(self, choice):
        lang = self.get_selected_lang_code()
        if self.project:
            self.project.load_existing_translations(lang)
            self.apply_filter()
            self.update_stats()

    # -------------------------------------------------------------
    # Top-Bar Integrated Auto-Translate Progress (Image 1 feature!)
    # -------------------------------------------------------------

    def start_auto_translate(self):
        if not self.project:
            self.toast_show("Сначала выберите мод из библиотеки!", "warning")
            return

        untrans = [s for s in self.project.strings if not self.project.translations.get(s["index"])]
        if not untrans:
            self.toast_show("Все строки уже переведены!", "info")
            return

        lang = self.get_selected_lang_code()
        total_count = len(untrans)
        self.cancel_translation_flag = False

        self.btn_translate.configure(state="disabled")

        # Show top progress bar in the empty center space
        self.top_progress_frame.pack(side=tk.LEFT, fill=tk.Y, expand=True, padx=16, pady=8)
        self.top_progress_bar.set(0)
        self.top_progress_lbl.configure(text=f"✨ {self.translation_engine.upper()}: 0/{total_count} (0%)")

        def _worker():
            def _prog(done, total, last_orig, last_trans):
                pct = int(done / total * 100) if total > 0 else 0
                sample = (last_orig[:11] + "…") if len(last_orig) > 11 else last_orig
                self.after(0, lambda: [
                    self.top_progress_bar.set(done / total),
                    self.top_progress_lbl.configure(text=f"✨ {self.translation_engine.upper()}: {done}/{total} ({pct}%) • {sample}"),
                    self.status_lbl.configure(text=f"Перевод: {done}/{total} строк...")
                ])

            cnt = self.project.auto_translate(
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

            self.after(0, lambda: [
                self.apply_filter(),
                self.update_stats(),
                self.btn_translate.configure(state="normal"),
                self.top_progress_lbl.configure(text=f"✓ Завершено: {cnt} строк!"),
                self.after(2500, self.top_progress_frame.pack_forget),
                self.toast_show(f"Автоперевод завершен! Переведено {cnt} строк.", "success", 3000)
            ])

        threading.Thread(target=_worker, daemon=True).start()

    def cancel_auto_translate(self):
        self.cancel_translation_flag = True
        self.top_progress_lbl.configure(text="Остановка автоперевода...")

    # -------------------------------------------------------------
    # Engine Settings Dialog with Ollama Dropdown & LLMLogs Manager
    # -------------------------------------------------------------

    def open_engine_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title(t("engine_settings_title"))
        dlg.geometry("560x520")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        frame = ctk.CTkFrame(dlg, fg_color="#111827", corner_radius=12)
        frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ctk.CTkLabel(frame, text=t("engine_settings_title"), font=ctk.CTkFont(size=14, weight="bold"), text_color="#38bdf8").pack(pady=(10, 6))

        engine_var = ctk.StringVar(value=self.translation_engine)

        ctk.CTkRadioButton(frame, text="Google NMT (Бесплатно, быстро, без ограничений)", variable=engine_var, value="google").pack(anchor="w", padx=24, pady=3)
        ctk.CTkRadioButton(frame, text="DeepL Free / Pro API", variable=engine_var, value="deepl").pack(anchor="w", padx=24, pady=3)
        ctk.CTkRadioButton(frame, text="Ollama / Локальный AI (qwen2.5, deepseek, llama3)", variable=engine_var, value="ollama").pack(anchor="w", padx=24, pady=3)
        ctk.CTkRadioButton(frame, text="Custom OpenAI / OpenRouter API", variable=engine_var, value="custom").pack(anchor="w", padx=24, pady=3)

        # DeepL Key
        ctk.CTkLabel(frame, text="DeepL Auth Key (для DeepL API):", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=24, pady=(8, 2))
        ent_deepl = ctk.CTkEntry(frame, width=480, placeholder_text="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx")
        ent_deepl.insert(0, self.deepl_key)
        ent_deepl.pack(padx=24, pady=2)

        # Ollama section with auto IP and Model dropdown
        ctk.CTkLabel(frame, text="Ollama URL & Выбор установленной модели:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8").pack(anchor="w", padx=24, pady=(10, 2))
        f_ollama = ctk.CTkFrame(frame, fg_color="transparent")
        f_ollama.pack(fill=tk.X, padx=24, pady=2)

        ent_ollama_url = ctk.CTkEntry(f_ollama, width=220)
        ent_ollama_url.insert(0, self.ollama_url or "http://127.0.0.1:11434")
        ent_ollama_url.pack(side=tk.LEFT, padx=(0, 6))

        ollama_models = fetch_ollama_models(ent_ollama_url.get().strip())
        valid_models = [m for m in ollama_models if m != "Модели не найдены"]
        current_m = self.ollama_model if self.ollama_model in valid_models else (valid_models[0] if valid_models else "Модели не найдены")
        ollama_model_var = ctk.StringVar(value=current_m)

        menu_ollama_model = ctk.CTkOptionMenu(f_ollama, variable=ollama_model_var, values=ollama_models, width=160)
        menu_ollama_model.pack(side=tk.LEFT, padx=3)

        def _refresh_models():
            m_list = fetch_ollama_models(ent_ollama_url.get().strip())
            menu_ollama_model.configure(values=m_list)
            v_list = [m for m in m_list if m != "Модели не найдены"]
            if v_list:
                ollama_model_var.set(v_list[0])
            else:
                ollama_model_var.set("Модели не найдены")
            lbl_ollama_status.configure(text=f"Найдено моделей: {len(v_list)}")

        btn_refresh_m = ctk.CTkButton(f_ollama, text="🔄", width=32, command=_refresh_models)
        btn_refresh_m.pack(side=tk.LEFT, padx=3)

        lbl_ollama_status = ctk.CTkLabel(frame, text=f"Обнаружено моделей: {len(ollama_models)}", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lbl_ollama_status.pack(anchor="w", padx=24, pady=(1, 4))

        # LLMLogs Storage & Safe Cleanup Section (Requested by user!)
        log_box = ctk.CTkFrame(frame, fg_color="#182234", corner_radius=8, border_width=1, border_color="#223048")
        log_box.pack(fill=tk.X, padx=24, pady=(6, 10))

        log_top = ctk.CTkFrame(log_box, fg_color="transparent")
        log_top.pack(fill=tk.X, padx=10, pady=6)

        num_logs, sz_logs = get_llm_logs_info()
        lbl_log_info = ctk.CTkLabel(
            log_top,
            text=f"📁 Папка LLMLogs: {num_logs} сессий ({sz_logs})",
            font=ctk.CTkFont(size=11),
            text_color="#e2e8f0"
        )
        lbl_log_info.pack(side=tk.LEFT)

        def _clear_logs():
            c = clear_llm_logs()
            lbl_log_info.configure(text="📁 Папка LLMLogs: 0 сессий (0 KB)")
            self.toast_show(f"Удалено {c} файлов логов LLM", "info")

        btn_clear_log = ctk.CTkButton(log_top, text="🧹 Очистить логи LLM", width=130, height=26, fg_color="#475569", hover_color="#dc2626", command=_clear_logs)
        btn_clear_log.pack(side=tk.RIGHT, padx=4)

        btn_open_log = ctk.CTkButton(log_top, text="📂 Открыть папку", width=110, height=26, fg_color="#334155", hover_color="#475569", command=lambda: os.startfile(LLMLOGS_DIR) if os.path.exists(LLMLOGS_DIR) else None)
        btn_open_log.pack(side=tk.RIGHT, padx=4)

        def _save():
            self.translation_engine = engine_var.get()
            self.deepl_key = ent_deepl.get().strip()
            self.ollama_url = ent_ollama_url.get().strip()
            self.ollama_model = ollama_model_var.get().strip()

            self.cfg["engine"] = self.translation_engine
            self.cfg["deepl_api_key"] = self.deepl_key
            self.cfg["ollama_url"] = self.ollama_url
            self.cfg["ollama_model"] = self.ollama_model
            save_app_config(self.cfg)

            self.btn_engine.configure(text=f"🌐 {self.translation_engine.upper()}")
            if hasattr(self, "update_ai_btn_text"): self.update_ai_btn_text()
            dlg.destroy()
            self.toast_show("Настройки движка сохранены!", "success")

        ctk.CTkButton(frame, text="Сохранить настройки", width=160, height=34, fg_color="#16a34a", hover_color="#15803d", font=ctk.CTkFont(size=12, weight="bold"), command=_save).pack(pady=(4, 10))

    # -------------------------------------------------------------
    # Build & Install to Game Operations
    # -------------------------------------------------------------

    def do_build(self):
        if not self.project:
            self.toast_show("Сначала выберите мод!", "warning")
            return
        lang = self.get_selected_lang_code()
        try:
            res = self.project.build(lang)
            self.toast_show(f"Сборка успешна: {res[:60]}", "success")
        except Exception as ex:
            self.toast_show(f"Ошибка сборки: {ex}", "error")

    def do_install(self):
        if not self.project:
            self.toast_show("Сначала выберите мод!", "warning")
            return
        lang = self.get_selected_lang_code()
        try:
            dest = self.project.install_to_game(lang)
            self.toast_show(f"Установлен в Mods/ с маркировкой [RU]: {os.path.basename(dest)}", "success", 4000)
            self.refresh_mod_library()
        except Exception as ex:
            self.toast_show(f"Ошибка установки в Mods/: {ex}", "error")

    def toast_show(self, msg, level="info", duration_ms=2500):
        prefix = "✓ " if level == "success" else ("⚠️ " if level == "warning" else ("❌ " if level == "error" else "ℹ️ "))
        color = "#10b981" if level == "success" else ("#f59e0b" if level == "warning" else ("#ef4444" if level == "error" else "#38bdf8"))
        self.status_lbl.configure(text=prefix + msg, text_color=color)
        self.after(duration_ms, lambda: self.status_lbl.configure(text_color="#94a3b8"))

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
