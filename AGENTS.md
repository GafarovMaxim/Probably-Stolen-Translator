# AGENTS.md — Документация для AI-агентов и разработчиков

> **Проект:** ProbablyTranslator — Автономная студия локализации модов для игры *Probably Stolen*.  
> **Основная кодовая база:** [`G:\Modding\ProbablyTranslator`](file:///G:/Modding/ProbablyTranslator)  
> **Главный исполняемый файл:** [`ProbablyTranslator.py`](file:///G:/Modding/ProbablyTranslator/ProbablyTranslator.py)  
> **Бинарный релиз:** [`ProbablyTranslator.exe`](file:///G:/Modding/ProbablyTranslator/ProbablyTranslator.exe)  
> **История изменений:** [`CHANGELOG.md`](file:///G:/Modding/ProbablyTranslator/CHANGELOG.md)

---

## 1. Назначение и Архитектура

`ProbablyTranslator` — настольное GUI-приложение в стиле Windows 11 Fluent Dark / Crowdin, предназначенное для перевода модификаций игры *Probably Stolen* (китайский оригинал → русский / английский).

### Ключевые возможности:
1. **Бинарная локализация C# DLL модов:**
   - Дизассемблирование через `ildasm.exe` (расположен в папке `bin/`).
   - Парсинг инструкций `ldstr` в IL-коде, извлечение строк оригинала.
   - Патчинг строк на целевой язык с безопасным экранированием UTF-16 (`\uXXXX`).
   - Сборка модифицированной DLL через `ilasm.exe` (папка `bin/`).
2. **Локализация текстовых модов (CSV / Languages):**
   - Автодетект папок `Localization/`, `Languages/`, `Loc/`.
   - Поддержка кодировок UTF-8, UTF-8-BOM, GBK, GB2312, UTF-16.
   - Сборка и экспорт локализованных CSV в целевую папку мода.
3. **Библиотека модов (Drawer & Auto-detection):**
   - Автоматическое сканирование мастерской Steam: `G:\SteamLibrary\steamapps\workshop\content\4348910`.
   - Автоматическое сканирование модов игры: `G:\SteamLibrary\steamapps\common\Probably Stolen\Mods`.
   - Определение формата (Steam / Mods, CSV / DLL), версий и доступных обновлений (`compare_versions`).
4. **Движки перевода:**
   - **Google Translate:** быстрый встроенный драфт (через web-endpoint без обязательного API-ключа).
   - **DeepL API:** высококачественный контекстный перевод.
   - **Ollama / Локальные SLM:** локальные нейросети (Qwen2.5, Llama3, Gemma2 и др.) через `http://127.0.0.1:11434`. В настройках отображаются только реально установленные у пользователя модели.
   - **Custom OpenAI-compatible API:** поддержка любых удаленных моделей (OpenAI, OpenRouter, Groq).
5. **Crowdin-Style UX & Варианты перевода:**
   - Иерархический список подсказок: блок `📖 ИГРОВОЙ ГЛОССАРИЙ` (`GAMING_GLOSSARY_ZH_RU`) и блок `🤖 МАШИННЫЙ & AI ПЕРЕВОД`.
   - Хоткеи быстрого применения вариантов: `Ctrl+1` .. `Ctrl+5`.
   - `Ctrl+Enter` — сохранение и автопереход к следующей строке.
   - Интеллектуальный контроль переполнения UI (`analyze_ui_fit`) и генератор компактных формулировок (`make_concise`) с сохранением пунктуации (`:`, `!`, `?`).

---

## 2. Структура проекта

```text
G:\Modding\ProbablyTranslator\
├── bin\                           # Внешние бинарники .NET для DLL-моддинга
│   ├── ildasm.exe                 # Дизассемблер IL
│   ├── ildasm.exe.config
│   ├── ilasm.exe                  # Ассемблер IL
│   └── ilasm.exe.config
├── LLMLogs\                       # Логи запросов к LLM (создаются автоматически)
├── icon.ico                       # Иконка приложения
├── ProbablyTranslator.py          # Основной монолитный файл исходного кода
├── ProbablyTranslator.exe         # Скомпилированный standalone исполняемый файл
├── translator_config.json         # Сохраненные настройки пользователя
├── AGENTS.md                      # Данный документ архитектуры для агентов
├── CHANGELOG.md                   # Журнал версий и изменений
├── README.md                      # Краткая справка
├── run_gui.bat                    # Быстрый запуск python GUI
└── drag_mod_here_to_translate.bat # Батник для drag-and-drop модов
```

---

## 3. Критические соглашения и архитектурные правила (Invariants)

Любой агент, работающий с кодом, ОБЯЗАН соблюдать следующие правила:

### 1. Win32 Drag-and-Drop перехват (`setup_native_drag_and_drop`):
- `CustomTkinter` создает более 115 дочерних Win32 окон (`TkChild`, `Static`, `Canvas`).
- Обычный `DragAcceptFiles` на главный `root_hwnd` **НЕ РАБОТАЕТ** (при наведении мыши появляется знак 🚫).
- **Инвариант:** Перехват обязан рекурсивно регистрировать `DragAcceptFiles(hwnd, True)` и подменять `WNDPROC` через `EnumChildWindows(root_hwnd)`.

### 2. Стилизация Treeview в Dark Theme (`clam`):
- Стандартный Tkinter `ttk.Treeview` в темной теме рисует некрасивую белую рамку в 1px.
- **Инвариант:** Белая рамка удаляется переопределением макета стиля:
  ```python
  self.style.layout("Crowdin.Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
  ```
- Не назначать ядовитые `foreground` на теги строк таблицы (`even` / `odd`), иначе весь текст строки окрашивается в чужой цвет. Цвета статусов отображаются в отдельной колонке `#4 (Status)`.

### 3. Интернационализация (i18n):
- Язык UI поддерживается через словарь `I18N = {"ru": {...}, "en": {...}}` и функцию `t(key, **kwargs)`.
- **Инвариант:** Все новые тексты интерфейса ОБЯЗАНЫ регистрироваться в обеих локалях (`ru` и `en`) и обновляться внутри метода `switch_ui_lang(lang_code)`.

### 4. Тэги карточек модов:
- Тэги модов (`Steam`, `Mods`, `CSV`, `DLL`, `🔄 Update`, `✓ Installed`) оформляются в виде скругленных контурных пиллов:
  - `corner_radius=10`, `border_width=1`.
  - Steam: `#0b1e3b` / border `#38bdf8` / text `#38bdf8`.
  - Mods: `#062e1e` / border `#10b981` / text `#34d399`.
  - CSV: `#042724` / border `#14b8a6` / text `#2dd4bf`.
  - DLL: `#200d3d` / border `#a855f7` / text `#c084fc`.
  - Update: `#3a1503` / border `#f59e0b` / text `#fbbf24`.
  - Installed: `#052e16` / border `#16a34a` / text `#4ade80`.

---

## 4. Сборка и тестирование

### Проверка синтаксиса перед сборкой:
```powershell
python -c "import ast; ast.parse(open(r'G:\Modding\ProbablyTranslator\ProbablyTranslator.py', encoding='utf-8').read()); print('Syntax OK')"
```

### Сборка standalone .exe:
```powershell
Set-Location "G:\Modding\ProbablyTranslator"
python -m PyInstaller --noconfirm --onefile --windowed --name "ProbablyTranslator" --icon "icon.ico" --distpath "G:\Modding\ProbablyTranslator" --add-data "bin;bin" --add-data "icon.ico;." "ProbablyTranslator.py"
```

После сборки PyInstaller генерирует папки `build/` и файл `ProbablyTranslator.spec`. Они временные и могут быть удалены.

---

## 5. Правила производительности (v2.5.0)

- Никаких сетевых/дисковых/subprocess-вызовов в UI-потоке: только `threading.Thread` + `self.after(0, ...)`.
- Динамические списки — пул виджетов или canvas (`ModLibraryView`), а не пересоздание CTk-виджетов.
- Цвета берутся из `Theme` (палитра «графит + индиго»); тексты — из `I18N` (ru и en). Эмодзи в UI не использовать: на Windows они рисуются мелкими монохромными значками — только простые символы (●, ○, ▲, ↑, ↻).
- Все виджеты создаются ДО `setup_native_drag_and_drop`, иначе над ними появится знак 🚫.
- Данные строки читать из `ModProject.by_index`, а не из ячеек Treeview.
