# vc_bpm_display (VCBpmDisplay)

> Anzeige-Widget der Virtuellen Konsole: zeigt das aktuelle globale Tempo (große
> BPM-Zahl) plus eine kurze Quelle/Modus-Zeile; optional die BPM eines Tempo-Bus.

## Zweck

`VCBpmDisplay` ist eine reine Live-Tempo-Anzeige. Standardmäßig spiegelt es die
BPM des globalen BPM-Leaders samt kurzer Quelle/Modus-Kennung (AUTO/MANUAL/OS2L/Tap);
mit gesetztem `tempo_bus_id` zeigt es stattdessen die BPM eines benannten Tempo-Bus.
Gesteuert wird das Tempo über andere Widgets (Tap/Nudge-Buttons, BPM-Fader) — dieses
Widget ist nicht-interaktiv. Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `_font_size` | Schriftgröße (7..28), skaliert die große BPM-Zahl | 11 |
| `tempo_bus_id` | „" = globaler Leader, sonst Bus A/B/C/D | `""` |

Der BPMManager ruft seine Callbacks aus einem Worker-Thread; die Updates werden
über Qt-Signale (`_bpm_changed_sig`/`_state_changed_sig`) in den GUI-Thread
marshallt. Im Bus-Modus pollt ein 10-Hz-GUI-Timer die Bus-BPM (TempoBus hat keine
Subscribe-API). Beim Zerstören meldet sich das Widget zuverlässig wieder ab.

## Verknüpfungen

- **BPM-Manager:** `src/core/engine/bpm_manager.get_bpm_manager()`
  (`subscribe_bpm_change`/`subscribe_state_change` + Gegenstücke im Teardown).
- **Tempo-Bus:** `src/core/engine/tempo_bus.get_tempo_bus_manager().resolve(...)`
  (Bus-Modus, GUI-Thread-Poll).
- **Threading-Falle:** Callbacks berühren keine Widgets; nur `*.emit()` in den
  GUI-Thread. `_teardown` ist idempotent (aus `destroyed` UND `closeEvent`).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `font_size` und
  `tempo_bus_id`; `apply_dict` startet/stoppt danach den Poll-Timer passend.

## Zugehörige Tests

- `tests/test_vc_bpm.py` — BPM-Anzeige, Quelle/Modus, Marshalling/Teardown.
- `tests/test_vc_tempo_widgets.py` — Tempo-Widget-Gruppe inkl. Bus-Modus.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_bpm.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_bpm_display.py:36` — Klasse `VCBpmDisplay`
- `src/ui/virtualconsole/vc_bpm_display.py:81` — `_connect_manager`
- `src/ui/virtualconsole/vc_bpm_display.py:96` — `_teardown` (idempotente Abmeldung)
- `src/ui/virtualconsole/vc_bpm_display.py:164` — `_poll_bus` (Bus-BPM)
- `src/ui/virtualconsole/vc_bpm_display.py:253` — `to_dict` · `:259` — `apply_dict`
