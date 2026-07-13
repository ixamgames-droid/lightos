# UI Tooltip-/Label-Coverage (QA-13)

Automatisch erzeugt von `tools/audit_tooltip_coverage.py` und
abgesichert durch `tests/test_tooltip_coverage.py`. Ein **Verstoss** ist
ein `QAbstractButton`, dessen `text()` UND `toolTip()` beide leer sind —
er ist weder sichtbar beschriftet noch per Hover/Screenreader benennbar.

Das Gate fordert nicht hart 0 Verstoesse, sondern haelt die unten
dokumentierte Baseline: es wird rot, sobald eine View NEUE textlose
Buttons ohne Tooltip bekommt (Regressionsschutz). Bestehende Verstoesse
abzubauen ist jederzeit erlaubt (Baseline in der Skript-Datei nachziehen).

**Stand:** 24 no-arg Views geprueft, 35 Verstoesse in der aktuellen Baseline.

## Uebersicht

| View (`src/ui/views/…`) | Klasse | Buttons | textlos & tooltiplos | Baseline |
|---|---|---:|---:|---:|
| `audio_input_view.py` | `AudioInputView` | 4 | 0 | 0 |
| `bpm_generator_view.py` | `BpmGeneratorView` | 13 | 0 | 0 |
| `bpm_manager_view.py` | `BpmManagerView` | 37 | 1 | 1 |
| `channel_groups_view.py` | `ChannelGroupsView` | 4 | 1 | 1 |
| `curve_library_view.py` | `CurveLibraryView` | 5 | 0 | 0 |
| `dmx_monitor_view.py` | `DmxMonitorView` | 0 | 0 | 0 |
| `efx_view.py` | `EfxView` | 25 | 0 | 0 |
| `fixture_group_view.py` | `FixtureGroupView` | 9 | 0 | 0 |
| `function_manager_view.py` | `FunctionManagerView` | 14 | 0 | 0 |
| `laser_view.py` | `LaserView` | 8 | 0 | 0 |
| `live_view.py` | `LiveView` | 15 | 4 | 4 |
| `midi_view.py` | `MidiView` | 19 | 1 | 1 |
| `music_view.py` | `MusicView` | 10 | 1 | 1 |
| `output_view.py` | `OutputView` | 0 | 0 | 0 |
| `palette_view.py` | `PaletteView` | 27 | 7 | 7 |
| `patch_view.py` | `PatchView` | 6 | 1 | 1 |
| `playback_view.py` | `PlaybackView` | 61 | 1 | 1 |
| `preset_browser_view.py` | `PresetBrowserView` | 1 | 1 | 1 |
| `programmer_view.py` | `ProgrammerView` | 119 | 14 | 14 |
| `rgb_matrix_view.py` | `RgbMatrixView` | 18 | 3 | 3 |
| `show_manager_view.py` | `ShowManagerView` | 6 | 0 | 0 |
| `simple_desk.py` | `SimpleDeskView` | 5 | 0 | 0 |
| `snapshots_view.py` | `SnapshotsView` | 58 | 0 | 0 |
| `virtual_console_view.py` | `VirtualConsoleView` | 38 | 0 | 0 |

## Verstoesse im Detail

Pro betroffener View die Button-Kennungen (`Klasse(objectName)`), die weder Text noch Tooltip tragen — Ansatzpunkte fuer kuenftige Verbesserung.

### `bpm_manager_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `channel_groups_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `live_view.py` (4)

- `QToolButton(ScrollLeftButton)`
- `QToolButton(ScrollRightButton)`
- `QCheckBox(<unbenannt>)`
- `QCheckBox(<unbenannt>)`

### `midi_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `music_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `palette_view.py` (7)

- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(ScrollLeftButton)`
- `QToolButton(ScrollRightButton)`

### `patch_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `playback_view.py` (1)

- `QAbstractButton(qt_tableview_cornerbutton)`

### `preset_browser_view.py` (1)

- `QToolButton(<unbenannt>)`

### `programmer_view.py` (14)

- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(<unbenannt>)`
- `QToolButton(ScrollLeftButton)`
- `QToolButton(ScrollRightButton)`
- `ColorButton(<unbenannt>)`
- `ColorButton(<unbenannt>)`
- `ColorButton(<unbenannt>)`
- `QToolButton(ScrollLeftButton)`
- `QToolButton(ScrollRightButton)`
- `QToolButton(<unbenannt>)`

### `rgb_matrix_view.py` (3)

- `ColorButton(<unbenannt>)`
- `ColorButton(<unbenannt>)`
- `ColorButton(<unbenannt>)`
