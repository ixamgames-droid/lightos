# LightOS — Contributor Guide

Danke für dein Interesse an LightOS! Diese Anleitung erklärt, wie du die Entwicklungsumgebung einrichtest und Beiträge einreichst.

---

## Entwicklungsumgebung einrichten

### Voraussetzungen

| Tool | Mindestversion | Download |
|------|---------------|---------|
| Python | 3.11 | https://python.org |
| Git | 2.40 | https://git-scm.com |
| Visual Studio Code oder PyCharm | aktuell | optional |

**Windows ARM64:** Verwende das native ARM64-Python-Installer von python.org (nicht x64-Emulation).

### Repository klonen und Setup

```powershell
git clone https://github.com/<org>/lightos.git
cd lightos

# Virtuelle Umgebung erstellen
python -m venv venv
venv\Scripts\activate          # Windows CMD
# oder:
. venv\Scripts\Activate.ps1    # PowerShell

# Abhängigkeiten installieren
pip install -r requirements.txt

# App starten
python main.py
```

### Optionale Dev-Tools

```powershell
pip install pytest pytest-qt black ruff mypy
```

---

## Tests ausführen

```powershell
# Alle Tests
pytest tests/ -v

# Nur Core-Engine
pytest tests/test_core_engine.py -v

# Mit Coverage
pytest tests/ --cov=src --cov-report=term-missing
```

**Wichtig:** Tests laufen ohne laufende Qt-Anwendung. UI-Tests benötigen `pytest-qt` und ein Display.

### Teststruktur

```
tests/
├── test_core_engine.py     # DMX-Merge, Cue, CueStack, UndoStack (93 Tests)
├── test_show_file.py       # Show-Datei laden/speichern
└── test_views.py           # UI-Smoke-Tests (erfordern Qt)
```

---

## Code-Standards

### Stil

- **Formatter:** `black` (Zeilenlänge 100)
- **Linter:** `ruff` (pyflakes + isort + pycodestyle)
- **Typen:** `mypy` für neue Dateien (strict optional)

```powershell
black src/ tests/
ruff check src/ tests/
```

### Konventionen

- Klassenname: `PascalCase`
- Funktionen/Variablen: `snake_case`
- Konstanten: `UPPER_SNAKE_CASE`
- Qt-Signals: `signal_name` (lowercase, kein `on_`-Prefix)
- Keine Magic Numbers — benannte Konstanten oder Enum-Werte

### Commits

Format: `<typ>: <kurze Beschreibung>` (Englisch oder Deutsch)

| Typ | Wann |
|-----|------|
| `feat` | Neues Feature |
| `fix` | Bugfix |
| `refactor` | Umbau ohne Verhaltensänderung |
| `test` | Tests hinzufügen oder korrigieren |
| `docs` | Dokumentation |
| `chore` | Build, Dependencies, CI |

Beispiel: `feat: add MIDI learn to VC fader`

---

## Branch-Strategie

```
main          ← stabil, CI muss grün sein
dev           ← Integration-Branch, PRs gehen hierher
feature/xyz   ← Feature-Branches, von dev abzweigen
fix/xyz       ← Bugfix-Branches
```

- PRs immer gegen `dev`, nicht `main`
- Squash-Merge bevorzugt (saubere History)
- Mindestens 1 Review vor Merge in `dev`

---

## Projektstruktur

```
src/
├── core/
│   ├── engine/     # Show-Engine: Executor, Cue, Chaser, Effekte
│   ├── dmx/        # Art-Net, sACN, Enttec-Treiber
│   ├── midi/       # MIDI-Manager, APC-Mini-Feedback
│   ├── audio/      # Beat-Detection, WASAPI-Capture
│   ├── osc/        # OSC-Server
│   └── show/       # Show-Datei laden/speichern
└── ui/
    ├── views/      # Hauptansichten (Patch, Programmer, Playback…)
    ├── widgets/    # Wiederverwendbare Widgets
    └── virtualconsole/  # VC-Canvas, VC-Widgets
```

---

## Pull Request einreichen

1. Fork erstellen (GitHub-Button „Fork")
2. Feature-Branch anlegen: `git checkout -b feature/mein-feature dev`
3. Änderungen committen (Tests nicht vergessen!)
4. PR gegen `dev` öffnen — Template ausfüllen
5. CI muss grün sein (pytest + ruff)

**Vor dem PR:** `pytest tests/ -v` und `ruff check src/` lokal ausführen.

---

## Fragen?

- [Issue öffnen](https://github.com/<org>/lightos/issues) mit Label `question`
- Diskussionen im [Discussions-Tab](https://github.com/<org>/lightos/discussions)
