# ProbablyTranslator

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-windows-lightgrey.svg)](https://www.microsoft.com/windows)

A modern, standalone GUI localization studio for translating mods of **Probably Stolen** to any language (Russian, English, Spanish, German, French, Japanese, etc.).

---

## ✨ Features

- **Fluent Dark & Crowdin-Style UX:** Modern Windows 11 Fluent Dark interface with clean typography, zebra striping, and interactive translation variant suggestions (`Ctrl+1`..`Ctrl+5`).
- **Universal Mod Support:**
  - Standard localization mods (`Localization/*.csv`, `Languages/`).
  - Hardcoded C# string mods (IL decompilation and binary string patching for `.dll` assemblies via `StringPatcher`).
- **Interactive Mod Library:**
  - Auto-scans Steam Workshop (`G:\SteamLibrary\steamapps\workshop\content\4348910`) and game mods folder.
  - One-click mod switching, format badges (`Steam`, `Mods`, `CSV`, `DLL`), and auto-detection of Workshop updates.
- **Multiple Translation Engines:**
  - **Google Translate:** instant drafts with zero setup.
  - **DeepL API:** high quality context-aware translations.
  - **Ollama (Local AI / SLM):** runs fully offline on your GPU/CPU (Qwen 2.5, Llama 3, Gemma 2) with auto-filtered installed models list.
  - **Custom OpenAI-compatible API:** support for external LLM endpoints.
- **Gaming Glossary & Context Normalization:** Built-in domain dictionary for consistent gaming terminology.
- **UI Overflow Protection:** Real-time character ratio analysis and meaning-preserving concise alternative generator (`✂ Concise`).
- **Native Win32 Drag & Drop:** Drop any mod folder or archive anywhere on the application window.
- **Full Bilingual Interface:** One-click toggle between English and Russian UI (`RU` / `EN`).

---

## 🚀 How to Run

### Option 1: Standalone Binary (Recommended)
Download the latest `ProbablyTranslator.exe` from Releases and run it directly — no Python or .NET SDK installation required.

### Option 2: From Source
```powershell
# Clone the repository
git clone https://github.com/GafarovMaxim/Probably-Stolen-Translator.git
cd Probably-Stolen-Translator

# Install dependencies
pip install customtkinter packaging

# Run application
python ProbablyTranslator.py
```

### Build Executable
```powershell
python -m PyInstaller --noconfirm --onefile --windowed --name "ProbablyTranslator" --icon "icon.ico" --distpath "." --add-data "bin;bin" --add-data "icon.ico;." "ProbablyTranslator.py"
```

---

## 📖 Documentation

- [AGENTS.md](AGENTS.md) — Comprehensive technical documentation for AI agents and developers (architecture, Win32 hooks, i18n invariants, compiler pipeline).
- [CHANGELOG.md](CHANGELOG.md) — Detailed version history and change logs.

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0) — see the [LICENSE](LICENSE) file for details.
