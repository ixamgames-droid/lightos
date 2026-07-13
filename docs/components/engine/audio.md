# `Audio` (`AudioFunction`) — Audiodatei als getriggerte Funktion

Teil der [Engine-Funktionstypen](README.md) · `FunctionType.Audio`

## Zweck / Verhalten

Eine AudioFunction spielt eine Audiodatei ab, sobald sie wie eine Cue getriggert
wird. Sie nutzt `QMediaPlayer` + `QAudioOutput` aus `PySide6.QtMultimedia`; ist
QtMultimedia nicht verfügbar, läuft ein Mock-Fallback (Pfad wird protokolliert,
Auto-Stop nach kurzer Zeit). Optionale Fade-In/Fade-Out-Rampen auf der
Lautstärke, optionaler Loop. **Kein DMX-Output** — Audio schreibt in keine
Universen.

## Parameter

**Instanzfelder** (`AudioFunction.__init__`, `src/core/engine/audio_func.py:17`):

| Feld | Typ | Bedeutung |
|---|---|---|
| `file_path` | `str` | abzuspielende Datei |
| `volume` | `float` 0–1 | Ziel-Lautstärke |
| `loop` | `bool` | am Ende neu starten |
| `fade_in` | `float` s | Lautstärke 0→`volume` beim Start |
| `fade_out` | `float` s | Lautstärke→0 beim Stop |

Interne Player-/Fade-Rampen-Felder (`_player`, `_audio_out`, `_available`,
`_fade_*`) sind nicht serialisiert. Keine `list_params`/`set_param` — Audio wird
über den Audio-Editor bearbeitet.

## Render-Beitrag

`AudioFunction.write` (`src/core/engine/audio_func.py:166`): schreibt **nichts**
ins DMX, treibt nur `_elapsed` und stoppt im Mock-Modus nach künstlicher Dauer.
Der eigentliche Ton läuft über den Qt-Media-Player (`_on_start`/`_on_stop`,
Fade-Rampe per `QTimer` in `_fade_step`). Loop-Handling über
`mediaStatusChanged` → `_on_media_status`.

## Serialisierung

`to_dict` (`src/core/engine/audio_func.py:175`) ergänzt `file_path`, `volume`,
`loop`, `fade_in`, `fade_out`. `from_dict` (`:186`). Loader:
`FunctionType.Audio.value` (`src/core/engine/function_manager.py:510`).

## Gekoppelte Module

- `PySide6.QtMultimedia` (`QMediaPlayer`, `QAudioOutput`) / `QtCore.QTimer`,
  `QUrl` — optionale Abhängigkeit
- `src/ui/views/audio_editor.py` — UI-Editor
- Als Timeline-Kind in Shows (`show_engine.py`) einsetzbar

## Tests

- `tests/test_audio_editor.py`

## Quelle

`src/core/engine/audio_func.py:12` (Klasse) · `:166` (`write`) · `:175` (`to_dict`)
