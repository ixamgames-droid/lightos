# Komponenten-Doku — Index, Konvention & Template

> **Zweck / Scope.** Dieser Ordner dokumentiert die **einzelnen Bausteine** von
> LightOS aus Entwickler-/Wartungssicht: pro Komponente eine kompakte Seite mit
> festem Aufbau — was der Baustein tut, wie man ihn bedient/konfiguriert, womit er
> gekoppelt ist, welche Tests ihn absichern und wo er im Code liegt (`file:line`).
>
> Das ist **kein** Endnutzer-Handbuch. Bebilderte Schritt-für-Schritt-Anleitungen
> liegen weiterhin unter [`../ANLEITUNGEN.md`](../ANLEITUNGEN.md); Referenz zu
> Env-Flags/Config unter [`../CONFIG_REFERENCE.md`](../CONFIG_REFERENCE.md). Diese
> Seiten hier sind der schnelle „Was ist Widget X, was kann es, was bricht wenn ich
> es anfasse"-Nachschlagepunkt und die Grundlage für die Doc-Aufgaben DOC-03..07.

## Pfadkonvention

Eine Komponente = eine `.md`-Datei, einsortiert nach Subsystem:

| Subsystem | Pfad | Quelle im Code |
|---|---|---|
| Virtuelle-Konsole-Widgets | `vc/<widget>.md` | `src/ui/virtualconsole/vc_*.py` |
| Views (Editoren/Tabs) | `views/<modul>.md` | `src/ui/views/*.py` |
| Engine-Funktionstypen | `engine/<typ>.md` | `src/core/engine/*` (`FunctionType`) |
| DMX-/Output-Module | `output/<modul>.md` | `src/core/dmx/*.py` |
| Input (MIDI/OSC/Timecode/Hotkeys) | `input/<modul>.md` | `src/core/*`, `src/input/*` |

Der Dateiname folgt dem Modul-/Widget-Namen ohne Präfix-Rauschen, z. B.
`vc/vc_button.md`, `views/patch_view.md`, `engine/efx.md`, `output/artnet.md`,
`input/midi_manager.md`.

## Verbindliches Template

Jede Komponenten-Doc nutzt **genau diese Abschnitte, in dieser Reihenfolge**.
Vorlage zum Kopieren:

```markdown
# <Komponentenname>

> Einzeiler: was diese Komponente ist.

## Zweck
Wofür der Baustein da ist, welches Problem er löst, wo er im UI/Signalfluss sitzt.

## Bedienung / Optionen
Modi, Parameter, Schalter, Aktions-Kinds. Tabelle je Option:
Name · Wirkung · Werte/Default. Bei UI-Widgets: wie man es konfiguriert.

## Verknüpfungen
Womit die Komponente gekoppelt ist (Engine-Manager, Bus-Signale, AppState,
Serialisierung `to_dict`/`apply_dict`, andere Widgets). „Ändere ich X, betrifft das Y".

## Zugehörige Tests
Liste der `tests/…`-Dateien, die diese Komponente absichern, mit einem Wort,
was sie prüfen.

## Quelle (file:line)
`pfad/zur/datei.py:Zeile` je zentralem Einstiegspunkt (Klasse, Serialisierung,
Trigger-Logik). Als Inline-Code, nicht als Link — Positionen driften.
```

Regeln:
- **Abschnitts-Titel fix** (kein Umbenennen/Weglassen). Leerer Abschnitt bekommt
  ein kurzes „— entfällt (Grund)".
- **`file:line` als Inline-Code** (`` `src/...:123` ``), damit der Doc-Link-Checker
  sie nicht als toten Link wertet und niemand bei jedem Refactor rote Links erbt.
- **Querverweise** auf andere Komponenten-Docs als relative Links
  (`../engine/efx.md`), auf Anleitungen nach `../<datei>.md`.
- **Basis-/Infrastruktur-Bausteine** (z. B. `vc_widget`, `vc_canvas`) brauchen
  keine volle Doc — in der Status-Tabelle als „Basis" markieren und begründen.

## Status-Tabelle (lebend)

Pflege pro neu geschriebener Doc die Spalte **Doc** (`✅ ja` / `— nein` /
`Basis`). Beim Anlegen dieses Index ist außer dem Beispiel `vc_button` alles offen.

### VC-Widgets (`vc/`) — DOC-03

| Widget | Doc |
|---|---|
| [`vc_button`](vc/vc_button.md) | ✅ ja |
| [`vc_slider`](vc/vc_slider.md) | ✅ ja |
| [`vc_color`](vc/vc_color.md) | ✅ ja |
| [`vc_color_list`](vc/vc_color_list.md) | ✅ ja |
| [`vc_xypad`](vc/vc_xypad.md) | ✅ ja |
| [`vc_encoder`](vc/vc_encoder.md) | ✅ ja |
| [`vc_speedial`](vc/vc_speedial.md) | ✅ ja |
| [`vc_stepper`](vc/vc_stepper.md) | ✅ ja |
| [`vc_cuelist`](vc/vc_cuelist.md) | ✅ ja |
| [`vc_label`](vc/vc_label.md) | ✅ ja |
| [`vc_bpm_display`](vc/vc_bpm_display.md) | ✅ ja |
| [`vc_bus_selector`](vc/vc_bus_selector.md) | ✅ ja |
| [`vc_tempo_bus_controller`](vc/vc_tempo_bus_controller.md) | ✅ ja |
| [`vc_effect_colors`](vc/vc_effect_colors.md) | ✅ ja |
| [`vc_effect_display`](vc/vc_effect_display.md) | ✅ ja |
| [`vc_song_info`](vc/vc_song_info.md) | ✅ ja |
| `vc_widget` | Basis (Basisklasse aller VC-Widgets) |
| `vc_canvas` | Basis (Layout-/Drop-Fläche, kein eigenes Bedienelement) |
| `vc_frame` | Basis (Container/Solo-Gruppe) |
| `vc_drop_panel`, `vc_inspector_panel`, `vc_conflict_card`, `vc_effect_editor`, `vc_effect_meta`, `vc_live_editor`, `vc_multi_live_editor`, `vc_widget_gallery` | Basis/Infrastruktur (kein platzierbares Bedien-Widget) |

### Views (`views/`) — DOC-04

| View | Doc |
|---|---|
| `virtual_console_view`, `patch_view`, `fixture_group_view`, `programmer_view`, `live_view`, `playback_view`, `efx_view`, `rgb_matrix_view`, `laser_view`, `music_view`, `audio_input_view`, `midi_view`, `output_view`, `dmx_monitor_view`, `function_manager_view`, `show_manager_view`, `palette_view`, `preset_browser_view`, `snapshots_view`, `channel_groups_view`, `bpm_manager_view`, `bpm_generator_view` | — nein |
| `scene_editor`, `chaser_editor`, `sequence_editor`, `collection_editor`, `script_editor`, `snap_editor`, `carousel_editor`, `effect_layer_editor`, `audio_editor`, `curve_library_view` | — nein |
| `simple_desk`, `spectrum_bars`, `snap_file_panel` | — nein (ggf. Helfer, beim Schreiben prüfen) |

### Engine-Funktionstypen (`engine/`) — DOC-05 ✅

Index: [`engine/README.md`](engine/README.md). Alle 10 `FunctionType`-Werte dokumentiert:
[`Scene`](engine/scene.md) · [`Chaser`](engine/chaser.md) · [`Sequence`](engine/sequence.md) ·
[`Collection`](engine/collection.md) · [`Show`](engine/show.md) · [`EFX`](engine/efx.md) ·
[`RGBMatrix`](engine/rgbmatrix.md) · [`Audio`](engine/audio.md) · [`Script`](engine/script.md) ·
[`MappedChannelChange`](engine/mappedchannelchange.md).

### DMX-/Output-Module (`output/`) — DOC-06 ✅

Index: [`output/README.md`](output/README.md). Alle 8 Nicht-`__init__`-Module dokumentiert:
[`output_manager`](output/output_manager.md) · [`universe`](output/universe.md) ·
[`artnet`](output/artnet.md) · [`sacn`](output/sacn.md) · [`enttec_pro`](output/enttec_pro.md) ·
[`serial_process`](output/serial_process.md) · [`artnet_input`](output/artnet_input.md) ·
[`sacn_input`](output/sacn_input.md).

### Input-Module (`input/`) — DOC-07 ✅

Index: [`input/README.md`](input/README.md). Alle Input-Module dokumentiert:
[`midi_manager`](input/midi_manager.md) · [`midi_mapper`](input/midi_mapper.md) ·
[`midi_backend_winmm`](input/midi_backend_winmm.md) · [`osc_server`](input/osc_server.md) ·
[`mtc_reader`](input/mtc_reader.md) · [`keyboard_hotkeys`](input/keyboard_hotkeys.md) ·
[`profile`](input/profile.md).
