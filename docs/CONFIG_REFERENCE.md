# Config-Referenz — Env-Flags & Config-Dateien

Nachschlagewerk für die Konfiguration von LightOS über die Umgebung (Environment-
Variablen) und die persistenten Config-Dateien unter `data/`. Alle Angaben sind aus
dem tatsächlichen Code recherchiert (Fundstellen als `datei:zeile`).

> Boolesche Flags werten „gesetzt = an" — außer wo eine explizite Wahrheitsmenge
> genannt ist. `LIGHTOS_DEBUG`/`LIGHTOS_STRICT` prüfen z. B. gegen
> `{1, true, yes, on}` (case-insensitiv, `strict` zusätzlich `y`/`ja`).

## (a) `LIGHTOS_*`-Env-Flags

| Flag | Wirkung | Default | Gelesen in (`file:line`) | Test-Relevanz |
|---|---|---|---|---|
| `LIGHTOS_DEBUG` | Aktiviert `debug_swallow()` — sonst still verschluckte `except`-Fehler werden (dedupliziert, je Kombination genau einmal) auf stdout geloggt. Werte: `1/true/yes/on`. | aus | `src/core/debug_log.py:22` | Debug-Hilfe; `set_debug()`/`reset()` steuern es in Tests direkt. |
| `LIGHTOS_STRICT` | Strict-Show-Loader: kaputte Subsysteme/Funktionen werden beim Laden NICHT still übersprungen, sondern re-raisen mit vollem Traceback. Werte: `1/true/yes/on/y/ja`. | aus (tolerant) | `src/core/strict.py:27`, verwendet in `src/core/engine/function_manager.py:532`, `src/core/show/show_file.py:61` | Von `tests/test_strict_loader.py` gezielt gesetzt. |
| `LIGHTOS_SHOW_DB` | Pfad der Show-Datenbank (SQLite). Lenkt Lese-/Schreibzugriff auf eine andere DB um, ohne die echte App-DB anzufassen. | `data/current_show.db` | `src/core/app_state.py:20` | `tests/conftest.py:26` setzt eine Temp-DB pro Session. |
| `LIGHTOS_NO_OUTPUT_THREAD` | Unterbindet den Autostart des 44-Hz-DMX-Output-Threads (und des Laser-Streaming-Threads) — verhindert Cross-Thread-Qt-Marshalling gegen den pytest-Teardown. | nicht gesetzt (Thread startet) | `src/core/app_state.py:1248`, `:1266`, `:2509`; `src/ui/main_window.py:87` | `tests/conftest.py:75` setzt es global; von vielen `tools/`-Skripten genutzt. |
| `LIGHTOS_NO_AUDIO_AUTOSTART` | Unterdrückt den Auto-Start der Audio-/BPM-Erkennung (WASAPI-Loopback-Capture). | nicht gesetzt (Auto an) | `src/core/audio/bpm_settings.py:98`; `src/ui/main_window.py:715` | `tests/conftest.py:78` setzt es; kein Test fährt echten Audio-Capture hoch. |
| `LIGHTOS_SERIAL_INPROC` | Enttec-Serial-Ausgabe direkt in-process (`EnttecPro`) statt prozess-isoliertem Proxy (`EnttecProcessProxy`, STAB-08). | nicht gesetzt (Proxy) | `src/core/dmx/output_manager.py:24` | `tests/conftest.py:83` setzt es (kein `multiprocessing`-spawn je Test). |
| `LIGHTOS_FLASK_SECRET` | `SECRET_KEY` des Web-Remote-Flask-Servers. Fehlt der Wert, wird pro Start ein zufälliger Key generiert (nie hardcoded). | zufällig (`secrets.token_hex(32)`) | `src/web/app.py:47` | — |
| `LIGHTOS_NO_RECOVERY_PROMPT` | Unterdrückt den modalen Autosave-Recovery-Dialog beim MainWindow-Bau (headless würde ihn niemand beantworten). | nicht gesetzt | `src/ui/main_window.py:94` | `tests/conftest.py:91` setzt es; Regressionstest `tests/test_autosave_recovery_headless.py`. Zweites Netz: `QT_QPA_PLATFORM=offscreen`. |
| `LIGHTOS_WEBENGINE_FLAGS` | Zusätzliche Chromium-Flags für den QWebEngine-3D-Visualizer (z. B. `--disable-gpu`), an die Anti-Drossel-Basis-Flags angehängt. | leer | `main.py:210` | Debugging von 3D-Renderer-Abstürzen. |
| `LIGHTOS_HARDEN_EXIT` | Nur im Lock-Runner/Test-Gate: beendet den Prozess nach QtWebEngine-Tests per `os._exit`, um den crashenden Teardown zu überspringen (QA-24). | nicht gesetzt | `tests/conftest.py:131` | Reines Test-Gate-Flag; bei interaktivem pytest NICHT setzen. |
| `LIGHTOS_TEST_HEAVY` | Schaltet rechenintensive Zusatz-Assertions in einzelnen Tests frei. | nicht gesetzt | `tests/test_bpm_beatgrid.py:156` | Reines Test-Flag (opt-in). |

`main.py:197` liest `LIGHTOS_WEBENGINE_FLAGS` referenziell im Docstring; die
tatsächliche Verwendung steht auf Zeile 210.

## (b) Config-Dateien unter `data/`

Alle Pfade sind relativ zum Repo-Root (dem Arbeitsverzeichnis der App).

| Datei | Schema (Kurzform) | Gelesen/geschrieben von (Subsystem) |
|---|---|---|
| `data/current_show.db` | SQLite-Show-Datenbank (Patch, Funktionen, Gruppen usw.); Pfad via `LIGHTOS_SHOW_DB` überschreibbar. | Show-/App-State (`src/core/app_state.py:20`), Migrationen `src/core/database/models.py`. |
| `data/universes.json` | JSON-Array von Zeilen `{"num", "name", "output", "patch"}` — `output` ∈ `Enttec`/`ArtNet`/`sACN`/`Disabled`, `patch` = COM-Port bzw. Ziel-IP. | Ausgabe-Konfiguration: gelesen beim Start (`src/core/app_state.py:744`, `apply_output_config`), geschrieben vom Dialog (`src/ui/widgets/output_config.py:16`). |
| `data/midi_mappings.json` | JSON-Array von Mapping-Objekten `{"id", "name", "target", "midi_in", "button_mode", "midi_out", "continuous_min", "continuous_max"}`. | MIDI-Mapping-Engine: geladen beim Start (`src/core/app_state.py:273`), gespeichert u. a. aus `src/ui/views/midi_view.py:557`. |
| `data/channel_groups.json` | JSON-Array von Gruppen `{"name", "universe", "channels": [int], "value": 0-255}`. | Channel-Groups-View (`src/ui/views/channel_groups_view.py:16`). |
| `data/channel_modifiers.json` | JSON der Kanal-Modifikatoren (Kurven/Invert je Kanal). | Channel-Modifier-Dialog (`src/ui/widgets/channel_modifier_dialog.py:143`). |
| `data/controller_library/*.json` | Ein Controller-Profil je Datei, `{"schema", "id", "manufacturer", "model", "device_type", "controls": [...]}`; siehe `data/controller_library/README.md`. Nutzer-Importe (QLC+ `.qxi`) landen unter `%APPDATA%/LightOS/controller_library/`. | Controller-Library (`src/core/controllers/controller_library.py:30`), UI: `src/ui/widgets/controller_browser.py`. |

Weitere JSON-Ablagen liegen NICHT unter `data/`, sondern im Nutzer-Profil
(`%APPDATA%/LightOS/`, z. B. `ui_prefs.json`, `recent.json`, `snapshots.json`,
Stage-/Input-Profile) und sind hier bewusst nicht als globale Config gelistet.

---

Verwandt: [SHOW_FILE_FORMAT.md](SHOW_FILE_FORMAT.md) · [ARTNET.md](ARTNET.md) ·
[DMX_PROTOCOL.md](DMX_PROTOCOL.md)
