# LightOS — Technische Architektur

> **Stand: 2026-06-10** — komplett gegen den Code verifiziert (Komplett-Scan,
> Testsuite: 517 passed + 358 subtests). Diese Datei ist die **kanonische
> Architektur-Übersicht**. Vertiefungen:
> [docs/OUTPUT_MERGE_CONTRACT.md](docs/OUTPUT_MERGE_CONTRACT.md) (verbindlicher
> Render-Vertrag), [docs/EFFEKTE.md](docs/EFFEKTE.md),
> [docs/SHOW_FILE_FORMAT.md](docs/SHOW_FILE_FORMAT.md) (.lshow),
> [docs/FEATURE_MAP.md](docs/FEATURE_MAP.md) (UI-Inventar),
> [docs/OPEN_POINTS_OVERVIEW.md](docs/OPEN_POINTS_OVERVIEW.md) (offene Punkte).

## Übersicht

```
┌──────────────────────────────────────────────────────────────────┐
│                        UI-Layer (PySide6)                        │
│ MainWindow (7 Sektionen): Live View · Patchen · Programmer ·     │
│ Virtual Console · Simple Desk · Playback · Eingabe/Ausgabe       │
└──────────────┬───────────────────────────────▲───────────────────┘
               │ Setter (set_programmer_value, │ Events
               │ start/stop Funktionen, …)     │ (subscribe/_emit,
┌──────────────▼───────────────────────────────┴───────────────────┐
│              AppState (src/core/app_state.py, Singleton)         │
│  Patch · Programmer · base_levels · Simple Desk · cue_stacks     │
│  FunctionManager · PlaybackEngine · OutputManager · Event-Bus    │
└──────────────┬───────────────────────────────────────────────────┘
               │ _render_frame (44-Hz-Tick-Callback)
┌──────────────▼───────────────────────────────────────────────────┐
│        OutputManager-Loop (EIN Output-Thread, 44 Hz)             │
│  Render (Schichten-Merge) → Channel-Modifier → GM/Blackout →     │
│  Enttec Pro (USB) · Art-Net (UDP) · sACN/E1.31 (Multicast)       │
└──────────────────────────────────────────────────────────────────┘
```

Persistenz daneben: `.lshow`-ZIPs (Shows), `data/*.json` (Output/MIDI/Gruppen),
`data/current_show.db` (SQLite-Fixture-DB), `%APPDATA%\LightOS\ui_prefs.json`.

---

## Kern: `AppState` (src/core/app_state.py)

Singleton über `get_state()`. Hält:

- **Patch**: `_patch_cache` (Liste `PatchedFixture`), Fixture-Profile aus der
  SQLite-DB (`data/current_show.db`, `fixture_db.ensure_builtins()` hält
  Builtin-Profile per Signatur-Vergleich in-place aktuell).
- **Programmer**: `state.programmer` = `{fid: {attr: val}}`, geschützt durch
  `_prog_lock`. Wird vom Programmer-UI **und** Matrix-Programmer geteilt.
- **base_levels**: `{fid: {attr: val}}` — Grundhelligkeit (z. B. PAR-Dimmer auf
  255), wird in den **Default-Frame** gebacken → Farb-only-Quellen sind sofort
  sichtbar, Dimmer-Effekte können trotzdem bis 0 dunkeln. Persistiert in der Show.
- **Simple Desk**: `state.simple_desk` (`{universe: {ch: val}}`, `_sd_lock`);
  wirkt **nur** bei `simple_desk_override=True` (sonst reine Anzeige).
- **Render-Plan-Caches** (neu berechnet bei jeder Patch-Änderung,
  `_rebuild_render_plan()`): `_fix_index` (fid → Fixture+Kanäle),
  `_default_frame` (Kanal-Defaults + base_levels), `_commit_spans`
  (zusammenhängende gepatchte Adressbereiche), `_patched_set`,
  Grand-Master-Adressmaske (nur Intensitäts-/Farbadressen).
- **Event-Bus**: `subscribe(cb)` → `_emit(event, data)`; über
  `set_ui_marshaller()` in den UI-Thread marshalled; parallel zentrales Routing
  über `src/core/sync.py` (`SyncEvent`).

## Der Render-Pfad (das Herzstück)

**Genau ein** Thread schreibt in die Universen: `OutputManager._loop` (44 Hz)
ruft die Tick-Callbacks auf, darunter `AppState._render_frame(dt)`. Jeder Frame
wird **komplett neu** aufgebaut (Per-Frame-Clear in Scratch-Universen) — keine
hängenden Werte gestoppter Quellen. Verbindlich spezifiziert in
[docs/OUTPUT_MERGE_CONTRACT.md](docs/OUTPUT_MERGE_CONTRACT.md); Kurzfassung:

| # | Schicht | Quelle | Semantik |
|---|---------|--------|----------|
| 1 | Default-Frame | Kanal-Defaults + `base_levels` | Basis jedes Frames |
| 2 | Funktionen | `FunctionManager.tick` | LTP in **Start-Reihenfolge** (zuletzt gestartet gewinnt) |
| 3 | Executoren | `PlaybackEngine.compute_merged` (Cues) | LTP über Funktionen |
| 4 | Programmer | `state.programmer` | LTP, eingeschränkt durch WP-6/EE-02 |
| 4b | Dimmer-Master | Submaster · Fixture-/Gruppen-Dimmer · Programmer-Dimmer | multiplikativ auf Intensitätskanäle |
| 4c | Simple Desk | nur bei aktivem Override | oberste Schicht, nur gesetzte Kanäle |
| 5 | Commit | gepatchte Spans atomar; freie Kanäle über Engine-Extra | ins Live-Universe |
| — | Channel-Modifier → Grand Master/Blackout | `_send_all` beim Senden | GM dimmt nur Intensitäts-/Farbadressen (Maske) |

**Schutzregeln** (warum nichts „durchfunkt"):
- **WP-6**: Treibt eine laufende Funktion in diesem Frame einen
  Nicht-Intensitäts-Kanal (Scratch ≠ Default), überschreibt der Programmer ihn
  **nicht** (eine laufende Matrix-Farbe wird nicht vom Color-Tab weggebügelt).
- **EE-02**: Läuft ein Effekt auf den Intensitätskanälen eines Fixtures,
  **multipliziert** der Programmer-Dimmer (0..1) statt per LTP zu ersetzen.
- **Cues > Funktionen** ist gewollt: ein Cue ersetzt Effektwerte per LTP.

## Funktionstypen (`FunctionType`, src/core/engine/)

Basisklasse `Function` (function.py): `id`, `name`, `intensity` (0..1,
Per-Effekt-Master), `speed`, Lifecycle `start()/stop()/_on_start()/_on_stop()`,
pro Frame `write(universes, patch_cache, dt, function_registry)`,
Persistenz `to_dict()/from_dict()`.

| Typ | Datei | Treibt | Besonderheiten |
|-----|-------|--------|----------------|
| Scene | scene.py | beliebige Attr-Werte pro Fixture | statisch; aus Programmer aufnehmbar |
| Chaser | chaser.py | Werte der Schritte | Schritte = Kind-Funktionen/Werte, Crossfade-Blending (`_render_and_blend`) |
| Sequence | sequence.py | Schritt-Werte | aus Programmer aufgenommene Schritte (`add_step_from_programmer`) |
| Collection | collection.py | nichts selbst | startet/tickt Kind-Funktionen; Stop stoppt Kinder mit |
| Show | show_engine.py | nichts selbst | Timeline: Tracks mit zeitgesteuerten Kind-Funktionen |
| EFX | efx.py | Pan/Tilt (+ `open_beam`) | Bewegungsformen (Kreis, Acht, …) auf Fixture-Auswahl/Gruppe |
| RGBMatrix | rgb_matrix.py | Farb-/Dim-/Shutter-Kanäle einer Gruppe | 29 Algorithmen, `MatrixStyle` (RGB/RGBW/Dimmer/Shutter), `ColorSequence` kanonisch, Live-Override/Preset-Commit |
| Audio | audio_func.py | nichts (spielt Audio) | Qt-MediaPlayer + Fades |
| Script | script_func.py | beliebige Roh-Kanäle (`setdmx`) | auch ungepatchte Adressen (Engine-Extra-Pfad mit Freigabe) |

Dazu: `effect_func.py` (`LayeredEffect`, generischer Ein-Attribut-Effekt aus
`EffectLayer`-Pipeline, effect_layers.py), `effect_live.py` (einheitliche
Param-/Action-API für VC/MIDI-Live-Zugriff auf laufende Effekte),
`bpm_manager.py` (globale BPM: Tap/Audio; Beat-Subscriber wie Carousel),
`snap_library.py` (Show-Bibliothek: Snaps + Effekte, Ordner),
`palette.py`, `curve_library.py`, `fade_curve.py`, `channel_modifier.py`.

**`FunctionManager`** (function_manager.py): Registry aller Funktionen,
`_running_ids` + `_start_order` (unter `_lock`); `tick()` schreibt Funktionen in
Start-Reihenfolge (deterministisches LTP). Funktionen mit `intensity < 1`
rendern in ein **privates Universum**; nur ihre geänderten Kanäle werden
skaliert (Dim-/Farbadressen × intensity) ins gemeinsame Scratch gemerged.

## Wie sich Effekte kombinieren (Regeln für Show-Bau)

1. **Farbe + Dimmer als getrennte Ebenen**: Farb-Kacheln/COLOR-Paletten setzen
   nur Farbkanäle; `base_levels` machen Fixtures „scharf"; ein Dimmer-Effekt
   (voll abdeckend) übernimmt die Helligkeit. Beides parallel = Farbwechsel +
   Lauflicht ohne Strobe-Artefakte.
2. **Zwei Funktionen auf demselben Kanal**: die **zuletzt gestartete** gewinnt
   (Start-Reihenfolge-LTP). Stoppt sie, kommt die ältere wieder durch
   (Per-Frame-Rebuild).
3. **Programmer über Effekten**: Farben laufender Effekte sind geschützt
   (WP-6); Programmer-Dimmer skaliert laufende Dimmer-Effekte (EE-02).
4. **Cues** ersetzen Effektwerte per LTP (Schicht 3 > 2).
5. **Simple Desk** nur mit „Manueller Override" wirksam — dann absolute
   Oberhand auf explizit gesetzten Kanälen.
6. **Grand Master/Blackout** wirken erst beim Senden und nur auf
   Intensitäts-/Farbadressen (Moving Heads behalten Position/Gobo).

**Bekannte Grenzfälle** (by design, bei Showbau wissen):
- Die WP-6-/EE-02-Erkennung ist ein Per-Frame-**Diff gegen den Default-Frame**:
  Schreibt ein Effekt in einem Frame *exakt* den Default-Wert, gilt der Kanal in
  diesem Frame als „nicht getrieben" (theoretisch 1-Frame-Übernahme durch den
  Programmer; praktisch kaum sichtbar).
- `compute_merged` merged Executoren **aller Pages** in fester
  Page-/Slot-Reihenfolge (nicht nach Startzeit) — zwei aktive Executoren auf
  dasselbe Fixture: der spätere Slot gewinnt.
- Software-Farbwechsel der Moving-Head-Schnellwahl läuft als **UI-Timer** im
  Programmer (nicht als Function) → nicht in Snaps/Shows persistierbar
  (dokumentiert, open-points T-12).

## Executoren & Cues

`PlaybackEngine` (executor.py): Pages × `Executor` (Fader + Go/Back/Flash),
gebunden an `CueStack` (cue_stack.py: `go/back/go_to`, `FadeState`-Echtzeit-Fades,
Auto-Follow). `compute_merged()` tickt alle Stacks und liefert
`{fid: {attr: val}}` an den Renderer — **schreibt nie selbst** in Universen.

## DMX-Ausgabe (src/core/dmx/)

- `Universe`: 512-Byte-Puffer, threadsafe Setter/Getter.
- `OutputManager`: hält Universen + Geräte je Universum
  (`add_enttec/add_artnet/add_sacn`), `_io_lock` gegen Close/Send-Races,
  Grand Master + Blackout + Submaster, 44-Hz-Loop. Verbindungen persistieren in
  `data/universes.json` (`apply_output_config`).
- Treiber: `enttec_pro.py` (USB-seriell, mit `write_timeout` gegen Freezes),
  `artnet.py` (UDP 6454), `sacn.py` (E1.31, 2026-06-08 spec-konform neu —
  Hardwaretest steht aus, open-points B-1).
- Eingänge: `artnet_input.py` / `sacn_input.py` — RX-Threads mergen eingehende
  Daten auf **freie (ungepatchte)** Kanäle.

## MIDI & Virtual Console

- `MidiManager` (midi/midi_manager.py): unter Windows **WinMM-Backend**
  (midi_backend_winmm.py), rtmidi optional; RX-Thread → Subscriber.
- `MidiMapper` (midi_mapper.py): **globale** Mappings in
  `data/midi_mappings.json` (nicht pro Show! → Konfliktquelle mit
  VC-Bindings, siehe Memory „VC-Seiten-Fix" 2026-06-02). Aktionen: Executor
  Go/Back/Flash/Fader, Programmer-Wert, Grand Master, Page-Select/Next/Prev,
  Funktion Start/Stop, Effekt-Param/-Action. Learn-Modus + Feedback-Loop.
- **Virtual Console** (ui/virtualconsole/ + views/virtual_console_view.py):
  Canvas mit Widgets (Button, Slider, Color, XYPad, Encoder, SpeedDial,
  CueList, Frame, Label), mehrere **Banks/Seiten**, Edit-/Touch-Lock-Modus,
  MIDI-Learn pro Widget, Sidebar = echte Show-Bibliothek (Drag aufs Canvas).
  `ButtonAction`: Toggle, Flash, FunctionToggle, FunctionFlash, Blackout,
  StopAll, Snapshot, LibrarySnap (set/flash/toggle), Clear, Tap, AudioBpm,
  EffectAction. VC-Layout wird in der Show gespeichert.
- **APC mini**: `apc_mini_feedback.py` (LED-Push: grün/rot/gelb + blink),
  `controller_templates.py` (Raster-Vorlagen), Seitenwechsel über Pads.

## Weitere Subsysteme

- **Audio**: capture.py + beat_detector.py (Live-BPM), os2l.py.
- **OSC** (osc/osc_server.py), **Web-Remote** (web/app.py),
  **Timecode** (timecode/mtc_reader.py).
- **Live View** (views/live_view.py): 2D-Arbeitsfläche (Drag/Snap/Gruppen),
  eigene Positions-Persistenz in der Show; **Visualizer** (3D) separat.
- **Undo** (core/undo.py), **Command Line** (core/cmdline/).
- **Stage-Definitionen** (stage/stage_definition.py).
- **Import**: QLC+ QXF (Fixtures) + QXW (Shows).

## Threading-Modell (real, Stand 2026-06-10)

| Thread | Aufgabe |
|--------|---------|
| UI-Thread (PySide6) | gesamtes UI; schreibt **nie** direkt in Universen, nur über AppState-Setter |
| Output-Thread (`OutputManager._loop`, 44 Hz) | **einziger** Universe-Writer: Render (`_render_frame`) + Senden (`_send_all`) |
| MIDI-RX | eingehende MIDI → Mapper/VC (via UI-Marshaller) |
| Art-Net-/sACN-RX | Input-Merge auf freie Kanäle |
| BPM-Manager | Beat-Timer (Tap/Audio) |

Locks: `_prog_lock` (Programmer), `_sd_lock` (Simple Desk),
`FunctionManager._lock` (Running-Set/Start-Order), `OutputManager._io_lock`
(Geräte-Open/Close/Send). Der Renderer arbeitet auf **Snapshots**
(Programmer-Kopie, Universen-Liste) — kein „dict changed size during iteration".

## Persistenz

| Ort | Inhalt |
|-----|--------|
| `shows/*.lshow` | ZIP mit **einem** `show.json` (Version 1.1): Patch, Programmer, base_levels, Cue-Stacks, Executoren, Paletten, Kurven, **Funktionen** (inkl. EFX/Matrix), VC-Layout, Visualizer-/Live-View-Positionen, Snapshots, Channel-/Fixture-Gruppen, Bibliothek. Details: [docs/SHOW_FILE_FORMAT.md](docs/SHOW_FILE_FORMAT.md) |
| `data/current_show.db` | SQLite: Fixture-Profile (Builtins via `ensure_builtins` in-place aktualisiert) + aktueller Patch |
| `data/universes.json` | Output-Verbindungen (Enttec/Art-Net/sACN je Universum) |
| `data/midi_mappings.json` | globale MIDI-Mappings (+ `.bak`) |
| `data/channel_groups.json` | Kanal-Gruppen |
| `%APPDATA%\LightOS\ui_prefs.json` | UI-Präferenzen (Programmer-Zonen-Layout, Live-View) |
| `crash.log` | Crash-Ausgaben des Starters |

## Tests & Werkzeuge

- `tests/` — 517 Tests (+358 Subtests), pytest; wichtige Regressionen:
  `test_render_frame.py`, `test_function_layer_order.py`,
  `test_programmer_priority.py`, `test_dimmer_master.py`,
  `test_iso_simple_desk.py`, `test_output_manager.py`.
- `tools/build_*.py` — selbstverifizierende Show-Generatoren
  (`build_feature_showcase.py` assertet volle Enum-Coverage; Demos:
  `Komplett_Demo.lshow`, `Buehnen_Show.lshow`, `APC_Test_Komplett.lshow`,
  `MovingHead_Demo.lshow`).
- Start: `start.bat`/`LightOS.lnk` → venv (Python 3.14) → `main.py --touch`.
