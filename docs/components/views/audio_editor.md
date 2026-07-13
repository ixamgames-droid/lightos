# audio_editor (AudioEditor)

> Editor einer `AudioFunction`: eine Audiodatei als Funktion einbinden
> (Wiedergabe im Show-Ablauf).

## Zweck

Bearbeitet eine Audio-Funktion — bindet eine Audiodatei als abspielbare Funktion
ein, die in Chasern/Shows/Executoren wie andere Funktionen getriggert werden kann.
Der Editor wählt die Datei und ihre Wiedergabe-Parameter und lässt sich in ein
großes, scrollbares Fenster auskoppeln.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Datei wählen | Audiodatei der Funktion zuordnen |
| Wiedergabe-Parameter | Lautstärke/Verhalten der Audio-Funktion |
| Auskoppeln | Editor in großes Fenster verschieben / zurückholen |

## Verknüpfungen

- **AudioFunction:** editiert das `AudioFunction`-Objekt; Engine-Typ unter
  [`../engine/audio.md`](../engine/audio.md).
- **FunctionManager:** eingebettet über
  [`function_manager_view`](function_manager_view.md).
- **Media/Player:** teilt die Audio-Wiedergabe-Infrastruktur mit
  [`music_view`](music_view.md).

## Zugehörige Tests

- `tests/test_audio_editor.py` — Editor + Datei-/Parameter-Handling.

## Quelle (file:line)

- `src/ui/views/audio_editor.py:13` — Klasse `AudioEditor`
- `src/ui/views/audio_editor.py:148` — Auskoppeln in großes Fenster
