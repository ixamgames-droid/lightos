# programmer_view (ProgrammerView)

> Der Programmer: Live-Bearbeitung von Fixture-Attributen (Dimmer, Farbe, Pan/Tilt,
> Beam …) für die aktuell gewählten Geräte/Gruppen.

## Zweck

Herzstück der manuellen Steuerung. Links Fixture-/Gruppen-Auswahl, rechts nach
Attribut-Gruppen sortierte Slider-Tabs (Intensity, Color, Pan/Tilt, Beam …).
Werte, die hier gesetzt werden, landen im Programmer-State und werden mit hoher
Priorität in den DMX-Merge geschrieben. Zwei Layout-Modi (kompakt/breit) sind
umschaltbar; Präferenzen liegen in `ui_prefs.json`.

## Bedienung / Optionen

| Bereich | Wirkung |
|---|---|
| Fixture-Liste + Alle/Keine + Gruppen (LAYOUT-02) | Auswahl der zu editierenden Geräte |
| Attribut-Tabs | Slider je Attribut; Mehrkopf-Geräte bekommen Kopf-Slider (`attr#N`) |
| Layout-Umschalter | Zwischen kompaktem und breitem Body wechseln |
| Hilfe-Modus (`_PROGRAMMER_HELP`) | Kurzerklärungen je Attribut einblenden |
| Snapshot importieren | Programmer-Stand als Snapshot/Snap ablegen |

## Verknüpfungen

- **Bus:** abonniert Auswahl-/Programmer-Events (`bus.subscribe`) und baut die
  sichtbaren Slider bei Änderung neu auf (P7-Refresh, reentrancy-geschützt).
- **AppState-Programmer:** liest/schreibt die Programmer-Werte; speist DMX-Merge,
  Snapshots (`snapshots_view`), Snaps (`snap_editor`) und Szenen-Capture.
- **Konstanten:** `COLOR_ATTRS`, `PAN_TILT_ATTRS`, `INTENSITY_ATTRS` gruppieren
  Attribute für Tabs/Filter.
- **Prefs:** `ui_prefs.json` sichert Layout-Modus.

## Zugehörige Tests

- `tests/test_programmer_capture.py` — Capture in Szene/Snapshot.
- `tests/test_programmer_priority.py` / `test_programmer_cue_priority.py` — Merge-Priorität.
- `tests/test_programmer_refresh_reentrancy.py` — Refresh ohne Reentrancy-Crash.
- `tests/test_programmer_empty_state.py`, `test_programmer_caps_tabs.py`,
  `test_multihead_programmer.py`, `test_programmer_headslider_index.py`.

## Quelle (file:line)

- `src/ui/views/programmer_view.py:127` — Klasse `ProgrammerView`
- `src/ui/views/programmer_view.py:181` — Slider-Refresh aus State (P7)
- `src/ui/views/programmer_view.py:357` — Tab-Leiste (Attribut-Gruppen)
- `src/ui/views/programmer_view.py:117` — Attribut-Gruppen-Konstanten
