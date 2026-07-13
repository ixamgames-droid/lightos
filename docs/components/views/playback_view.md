# playback_view (PlaybackView)

> Playback-Ansicht: Cuelisten mit GO/BACK, Executor-Fader-Bank und Seiten (Pages)
> für Live-Wiedergabe.

## Zweck

Live-Wiedergabe-Zentrale. Zeigt die aktive Cueliste als Tabelle (`Nr., Label,
Fade In, Fade Out, Delay, Follow, Kurve`), bietet GO/BACK, einen manuellen
Crossfade-Fader und eine Bank von `ExecutorWidget`-Slots (Fader + Label + 3
Buttons), die pro Page umgeschaltet werden. Cues lassen sich per Ein-Klick auf
die aktive Liste aufzeichnen (F-14).

## Bedienung / Optionen

| Bedienung | Wirkung | Bezug |
|---|---|---|
| GO / BACK | Nächste/vorige Cue faden | — |
| Manueller Crossfade-Fader | Aktive Cueliste von Hand scrubben | — |
| Fade-Kurven-Combo | Fade-Verlauf einer Cue wählen | F-5 |
| Ablauf-Modus | Einzel/Loop/Bounce/Ping-Pong des Stacks | F-7 |
| Quick-Record | Dialogfreies Ein-Klick-Record auf die aktive Cueliste | F-14 |
| Executor-Slot | Volume-Fader skaliert Intensität, Crossfade-Fader scrubbt | — |
| Page-Buttons | Executor-Bank umschalten (auch via MIDI/Hotkey) | — |
| `ExecutorConfigDialog` | Executor-Slot mit Funktion/Modus belegen | — |

## Verknüpfungen

- **PlaybackEngine:** GO/BACK, Executoren, Page-Wechsel und Fade laufen über die
  `playback_engine` in AppState; Page-Wechsel ist threadsicher (MIDI/Hotkey).
- **FunctionManager:** Executor-Slots binden Funktionen/Stacks.
- **Fade-Kurven:** Kurven-Combo greift auf die Kurven-Bibliothek zu
  (siehe [`curve_library_view`](curve_library_view.md)).

## Zugehörige Tests

- `tests/test_playback_manual_crossfade.py` — manueller Crossfade-Scrub.
- `tests/test_playback_page_threadsafe.py` — Page-Wechsel threadsicher.
- `tests/test_playback_quick_rec.py` — Ein-Klick-Record (F-14).
- `tests/test_vc_slider_playback_slot.py` — Executor-Slot ⇄ VC-Slider.

## Quelle (file:line)

- `src/ui/views/playback_view.py:21` — Klasse `PlaybackView`
- `src/ui/views/playback_view.py:564` — `ExecutorWidget` (Fader-Slot)
- `src/ui/views/playback_view.py:730` — `ExecutorConfigDialog`
- `src/ui/views/playback_view.py:452` — Quick-Record (F-14)
