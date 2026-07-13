# vc_cuelist (VCCueList)

> Cue-Stack-Steuerung der Virtuellen Konsole: zeigt die Cue-Liste eines
> Executor-Slots mit GO/BACK/STOP-Transport.

## Zweck

`VCCueList` bindet einen Executor-Slot (`stack_slot`) und zeigt dessen CueStack
als Liste (Nummer + Label), hebt die aktuelle Cue hervor und bietet drei
Transport-Buttons. Ein 200-ms-Timer hält Liste und Markierung aktuell. Erbt von
`VCWidget`.

## Bedienung / Optionen

| Element | Wirkung |
|---|---|
| `GO ►` | `executor.press_btn("go")` — nächste Cue |
| `◄◄ BACK` | `executor.press_btn("back")` — vorherige Cue |
| `■ STOP` | `executor.press_btn("stop")` |

| Feld | Wirkung | Default |
|---|---|---|
| `stack_slot` | Executor-Slot (0..19), dessen Stack angezeigt wird | 0 |

Im Edit-Modus werden Buttons und Liste deaktiviert (`set_edit_mode`), damit
Verschieben/Skalieren nicht versehentlich Transport auslöst.

## Verknüpfungen

- **AppState / Playback:** `get_state().playback_engine.executors[stack_slot]`
  liefert den Executor; gelesen werden `executor.stack.cues`,
  `stack.current_index` und `executor.press_btn(...)`.
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `stack_slot`;
  `apply_dict` synchronisiert die Titel-Beschriftung.

## Zugehörige Tests

- `tests/test_views.py` — VC-View-Smoke inkl. `VCCueList`-Konstruktion.
- `tests/test_party_demo_show.py`, `tests/test_musik_show_2026.py` — nutzen das
  Widget in Demo-Shows (Instanziierung/Serialisierung).

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_views.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_cuelist.py:12` — Klasse `VCCueList`
- `src/ui/virtualconsole/vc_cuelist.py:69` — `_executor` (Slot-Auflösung)
- `src/ui/virtualconsole/vc_cuelist.py:95` — `_refresh` (Liste/Markierung)
- `src/ui/virtualconsole/vc_cuelist.py:144` — `to_dict` · `:149` — `apply_dict`
