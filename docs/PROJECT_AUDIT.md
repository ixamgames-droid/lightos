# LightOS — Projekt-Audit & Architektur-Übersicht

> Stand: 2026-05-30. Erstellt aus einem Multi-Agent-Audit (5 Domänen: Core-Engine/Persistenz,
> DMX/Output, MIDI, UI/Views, Virtual Console). `[verifiziert]` = im Code direkt nachgeprüft.

---

## 1. Architektur in Kurzform

LightOS ist eine QLC+-ähnliche Lichtsteuerung (Python 3.14 / PySide6). Grobe Schichten:

```
  UI (PySide6)                Engine / Core                     Output
  ─────────────               ──────────────                    ────────
  main_window                 app_state (Singleton)             OutputManager (44 Hz)
   ├─ Views (Tabs)            ├─ programmer {fid:{attr:val}}      ├─ EnttecPro (serial)
   ├─ Virtual Console         ├─ universes {1..32: Universe}      ├─ ArtNetSender (UDP)
   ├─ Visualizer (WebEngine)  ├─ function_manager  ─tick(44Hz)→   └─ SACNSender (E1.31)
   └─ Tool-Widgets            ├─ playback_engine  ─loop(50Hz)→   Input: ArtNet/sACN-RX,
                              └─ cue_stacks / palettes           MIDI, OSC, Audio/OS2L, MTC
```

**Zwei Render-Threads** schreiben in dieselben `Universe`-Buffer (512-Byte, **1-basierte** Kanäle):
1. `OutputManager._loop` (44 Hz) ruft Tick-Callbacks → `FunctionManager.tick()` → jede laufende
   `Function.write()` schreibt per `set_channel`/`set_range`. Danach Channel-Modifier, Blackout,
   Grand-Master, Versand an alle Backends.
2. `PlaybackEngine._loop` (50 Hz, `executor.py`) tickt CueStacks aller Executor-Pages, merged (LTP),
   und `_flush_to_dmx` schreibt mit **Programmer-Priorität** (`final = {**attrs, **prog}`).

**Event-Busse (zwei, parallel):** Legacy `AppState.subscribe/_emit` (String-Events) + zentraler
`StateSync` (`sync.py`, `SyncEvent`-Enum). `_emit` routet Legacy-Events automatisch in `SyncEvent`,
daher abonnieren Views oft beides (Doppel-Zustellung).

**Persistenz:** Show = ZIP `.lshow` mit `show.json` (`SHOW_VERSION` 1.1). Enthält patch, programmer,
cue_stacks, palettes, functions, efx, rgb_matrix, virtual_console, visualizer, layout. Fixture-DB =
SQLAlchemy (Manufacturer→Profile→Mode→Channel→Range) + `PatchedFixture`. Zentrale Mapping-Achse sind
Attribut-Strings (`color_r/g/b`, `pan`, `tilt`, `intensity`, …).

### Funktionstypen (Engine)
`Function`-Basis mit `start/stop/write/to_dict/from_dict`. Subtypen: **Scene** (Kanal-Snapshot+Fade),
**Chaser** (verkettet Functions als Steps; RunOrder Loop/SingleShot/PingPong/Random; optional Beat),
**Sequence** (eigene Step-Werte auf gebundene Fixtures), **Collection** (parallel), **Show** (Timeline/
Tracks), **AudioFunction** (QMediaPlayer), **ScriptFunction** (Mini-Sprache), **LayeredEffect** &
**Carousel** (teilen `EFX`-Tag, unterschieden über Keys `layers`/`pattern`).

### Virtual Console
`VCCanvas` (Free-Form) mit Kind-Widgets: VCButton, VCSlider, VCXYPad, VCLabel, VCCueList, VCSpeedDial,
VCFrame (Multipage+Solo), **VCColor** (neu). Edit-/Run-Modus, JSON-Serialisierung, Popout, MIDI per
Rechtsklick→Teach (APC-Abbild) bzw. Learn. APC-mini(-mk2)-LED-Feedback spiegelt Zustände auf die Pads.

### MIDI
WinMM-Backend (ctypes) → `MidiManager` (Queue) → `MidiDispatch`-Thread → Callbacks. UI-Updates **müssen**
per `Signal(object)` in den UI-Thread marshallen (kein Qt-Event-Loop im MIDI-Thread). Features:
Learn, Teach, Mapping-Engine (`midi_mapper`), Input-Profile, bidirektionales LED-Feedback.

---

## ✅ Behoben am 2026-05-30 (Quick-Win-Batch)

C1 (ID-Kollision: `bump_next_id` nach Laden), C2 (VCFrame-Solo `_pressed`), C3 (Klemmung in
`executor._flush_to_dmx`), C4 (VCCanvas `unsubscribe` + Dispatch-Guard), EFX `x_phase`/`y_phase`
serialisiert, RGB-Matrix `direction` geladen, Grand-Master gerundet, `_rx_loop`-Listenkopie,
VCColor in VC-Toolbar, VCColor CC-Flankenlogik. Alle mit Headless-Tests verifiziert.

## ✅ Behoben am 2026-05-30 (C6/C7 — Output-Render-Umbau)

Zentraler **Per-Frame-Renderer** `AppState._render_frame` ersetzt die zwei konkurrierenden
Render-Loops. PlaybackEngine läuft **ohne eigenen Thread** mehr (`compute_merged()`); alles rendert
in **einem** Thread (44 Hz): Default → Funktionen → Executoren → Programmer (LTP), dann **atomarer
Commit** der gepatchten Adress-Spans per `set_range`. Ergebnis: **kein Tearing** (C7) und
**Per-Frame-Clear** → gestoppte Cues/Scenes fallen auf Default zurück (C6, hängende Werte weg).
Nicht gepatchte Roh-Kanäle (SimpleDesk/OSC/Input-Merge) bleiben erhalten; rohe ScriptFunction-
`setdmx`-Ausgaben werden committed **und** beim Stoppen freigegeben. **Channel-Cache** ersetzt die
DB-Session-pro-Fixture-pro-Frame. Thread-sicher per Snapshots von `programmer`/`universes`.
Verifiziert: 108 Tests grün (inkl. 6 neue `tests/test_render_frame.py`), Boot-/End-to-End-Test
(Programmer→DMX), Nebenläufigkeits-Stresstest (3 Threads, 0 Races). Verhaltensänderung wie
abgesprochen: Engine besitzt gepatchte Fixture-Kanäle.

**Noch offen:** C5 (sACN — Hardware-Test), C8 (restliche Thread-Disziplin: Legacy-`_emit`
cross-thread) + MITTEL/NIEDRIG unten.

## ✅ Behoben am 2026-06-08 (Multi-Agent-Audit-Runde 3)

Frische Audit-Runde (3 Sub-Agents: Netzwerk/Eingabe, Concurrency, Engine-Logik),
jeder Befund im Code verifiziert. Umgesetzte Fixes:

- **B1/C8 — UI-Thread-Marshalling [behoben].** `AppState._emit` aus Worker-Threads
  (MIDI/OSC/Web/Audio) rief Legacy-Callbacks (und damit `setText`/`update()`)
  direkt im Fremd-Thread → sporadische Qt-Crashes. Jetzt: `set_ui_marshaller`
  (vom `MainWindow` via `Signal(object)` gesetzt) verlagert die komplette
  Event-Zustellung off-thread in den UI-Thread; auf dem UI-Thread laeuft `_emit`
  unveraendert synchron. `_emit` in `_emit`/`_emit_impl` aufgeteilt.
- **B2 — `programmer` jetzt unter `_prog_lock` (RLock).** `set_programmer_value`,
  `clear_programmer`, `_clear_programmer_attr` und der Render-Snapshot in
  `_render_frame` sind serialisiert → kein „dict changed size during iteration".
- **B3 — `FunctionManager` jetzt unter `_lock`.** `start`/`stop`/`tick`
  (Reihenfolge-Snapshot + Finalisierung) serialisiert; der Lock wird NICHT
  waehrend `f.write()` gehalten.
- **B4 — Grand-Master skaliert nur Intensitaet/Farbe.** Neue GM-Adressmaske
  (`_rebuild_render_plan` → `OutputManager.set_gm_address_mask`); `_send_all`
  dimmt nur Maske, Pan/Tilt/Gobo/Prism bleiben unberuehrt. Universen ohne Patch
  (rohes DMX) dimmen weiter global (Fallback).
- **B5 — `_emit` iteriert ueber Listenkopie** und loggt Callback-Exceptions
  (statt sie stumm zu verschlucken).
- **B6 — `_send_all` iteriert `_tick_callbacks` ueber Kopie** (UI-Thread mutiert).
- **B7 — `Universe.set_channel` gehaertet:** `assert` → echte Validierung
  (Out-of-range-Kanal verworfen, Wert auf 0–255 geklemmt). `-O`-sicher, kein
  Negativ-Index-Wraparound mehr. Web-`/api/channel` validiert `channel` zusaetzlich.
- **B8 — ArtNet/sACN-Input klemmen die Laengenfelder** (`length` bzw.
  `prop_count`) gegen reale Paketlaenge und 512 → DMX nie > 512 Slots.
- **C5/D2 — sACN-Sender E1.31-spec-konform neu** (`sacn.py`): korrekte
  Flags+Length (`0x7000|pdu_len`) je Layer, Root-/Framing-Vector als 4-Byte,
  638-Byte-Paket fuer 512 Kanaele, Multicast `239.255.<hi>.<lo>`. Verifiziert:
  PDU-Laengen 622/600/523, Round-Trip durch den eigenen Receiver.
  **⚠ Noch offen:** Verifikation gegen echte sACN-Hardware/Wireshark.

**Bewusst NICHT geaendert (Design-Entscheidung des Bedieners):** Web-/OSC-Server
binden weiter auf `0.0.0.0` ohne Auth (beide Server standardmaessig aus; Schutz =
Netz-Isolation). Realistisch nur bei aktivem Server relevant.

Tests: 397 grün (+ neue `tests/test_audit_fixes_2026_06_08.py`: GM-Maske,
set_channel-Haertung, sACN-Konformitaet/Parser-Clamp, Concurrency-Smoke).

## 2. Befunde nach Schweregrad

### 🔴 KRITISCH

| # | Ort | Problem | Auswirkung |
|---|-----|---------|-----------|
| C1 | `engine/function.py:35` + `function_manager.py:136` | `_next_id` wird beim Laden nie auf `max(IDs)+1` gesetzt **[verifiziert]** | Neue Funktion bekommt kollidierende ID → überschreibt geladene Funktion (stiller Datenverlust) |
| C2 | `virtualconsole/vc_frame.py:40` | Solo prüft `_state` statt `_pressed` **[verifiziert]** | Solo-Frame schaltet andere Buttons nie aus — Feature wirkungslos |
| C3 | `engine/executor.py:168` | `set_channel(val)` ohne Klemmung; `default_value` kann `None` sein **[verifiziert]** | `AssertionError` killt den Playback-Thread → Wiedergabe steht still |
| C4 | `virtualconsole/vc_canvas.py:75` | MIDI-`subscribe` ohne jedes `unsubscribe` **[verifiziert]** | Bei Neu-Erzeugung der Canvas: Doppel-Dispatch + Zugriff auf gelöschte Widgets (Crash/Leak) |
| C5 | `dmx/sacn.py:21` + `sacn_input.py:188` | E1.31-Paketaufbau nicht spec-konform; Sender/Receiver zueinander inkompatibel *(Agent-Analyse, Hardware-Test offen)* | sACN-Output mit echter Hardware praktisch funktionslos |
| C6 | `dmx/output_manager.py` + `executor.py` | Kein Per-Frame-`universe.clear()` im Render-Pfad **[verifiziert]** | Werte gestoppter Cues/Scenes bleiben hängen; kein echtes HTP-Merge |
| C7 | `app_state.py` + `executor.py` + `output_manager.py` | Zwei Threads schreiben dieselben Universen ohne Frame-Atomarität *(plausibel)* | Tearing/Flackern bei mehrkanaligen Moves/Farben |
| C8 | `midi_mapper.py:437` → `app_state._emit` → Views | MIDI-Thread schreibt `programmer` (ohne Lock) + ruft UI-Callbacks direkt *(plausibel)* | Sporadische Crashes/inkonsistente Anzeige bei MIDI-Fadern |

### 🟡 MITTEL

- **Serialisierungs-Lücken (Datenverlust beim Laden):** EFX `x_phase`/`y_phase` (`efx.py:165`),
  RGB-Matrix `direction` (geladen+ungenutzt, `rgb_matrix.py:163`), Executor-Page/Slot-Bindung wird nicht
  persistiert (`show_file.py:138`), Chaser-Editor „Notiz" nie zurückgeschrieben (`chaser_editor.py:218`).
- **Collection-Tick** (`collection.py:54`): doppeltes `dt` + Child-`_running` nie zurückgesetzt.
- **Grand-Master** (`output_manager.py:110`): `int(b*gm)` (Truncation, Bias) + wird auf **alle** Kanäle
  angewandt (auch Pan/Tilt/Gobo).
- **ArtNet-Broadcast** Default `2.255.255.255` (`output_manager.py:64`) scheitert in 192.168.-Netzen still.
- **UI-Thread liest Engine-Interna ohne Lock:** `live_view.py:239` iteriert `fm._running_ids`.
- **Editor-Churn:** `function_manager_view.py` baut Editor bei jedem Refresh neu → Eingabeverlust.
- **MIDI:** `_rx_loop` iteriert `_callbacks` ohne Kopie (`midi_manager.py:319`); `exclude_note`-API in
  `apc_mini_feedback` toter Code, inkonsistent zu mk2; VCColor wendet Farbe bei **jeder** CC>63 erneut an
  (keine Flankenlogik, `vc_color.py:110`).
- **VCColor nicht in VC-Toolbar** (`virtual_console_view.py:266`) — nur via Kontextmenü erreichbar.
- **Snapshots global statt pro Show** (`snapshots_view.py:26`) → fid-Referenzen passen nach Show-Wechsel nicht.
- **scene_editor-Preview** wird vom 44-Hz-Loop sofort überschrieben (`scene_editor.py:181`).

### 🟢 NIEDRIG
- Verbreitetes `except Exception: pass`/nur `print(...)` verschluckt Fehler (u.a. `app_state._emit`,
  VCColor/VCSpeedDial `_apply`, OutputManager-Tick) → stille Fehlfunktion, schwer zu diagnostizieren.
- Doppel-Refresh (Legacy + Sync-Bus) in mehreren Views; `UniverseBar` zeigt fest nur Universe 1.
- `matches_midi` byte-genau dupliziert in VCButton/VCColor (Drift-Risiko) → Mixin sinnvoll.
- VCXYPad ohne MIDI-Bindung (Inkonsistenz vs. Slider/Button/Color).
- BeatDetector/MTC kleinere Lock-/Modulo-Ungenauigkeiten.

---

## 3. Empfohlene Reihenfolge

1. **Quick-Win-Korrektheit (klein, risikoarm):** C1, C2, C3, C4 + VCColor-Toolbar + VCColor-CC-Flanke +
   EFX/RGB-Matrix-Serialisierung + `_rx_loop`-Listenkopie + Grand-Master-Rundung.
2. **Output-Architektur (mittel, sorgfältig):** C6/C7 zusammen lösen — zentraler Per-Frame-Render mit
   Clear + HTP-Merge in genau einem Thread.
3. **sACN (C5)** spec-konform neu aufbauen (idealerweise `sacn`-Lib) — braucht Hardware-/Wireshark-Test.
4. **Thread-Disziplin (C8)** — Legacy-`_emit` in den UI-Thread marshallen oder `programmer` mit Lock.
5. **Rest MITTEL/NIEDRIG** nach Bedarf.

---

## 4. Layering-/Überschreib-Audit (2026-06-07)

Fokus: falsch überschriebene Werte, doppelte Wertquellen, Kombinierbarkeit von
Effekt-Ebenen (Matrix Dimmer + Matrix Color, Snap + Matrix), VC-Aktivierung.

### ✅ Behoben
- **LAYER-01 — nicht-deterministische LTP-Reihenfolge [behoben].**
  `FunctionManager.tick()` iterierte über das **ungeordnete** `_running_ids`-Set
  statt über `_start_order`. Schrieben zwei laufende Funktionen denselben Kanal
  (z. B. eine Matrix mit `drive_intensity=True` + eine Dimmer-Matrix, oder zwei
  Effekte auf denselben Dimmer), gewann ein **zufälliger** Writer (Hash-Reihenfolge)
  statt der zuletzt gestarteten Funktion. Fix: Tick läuft jetzt in `_start_order`
  (zuletzt gestartet = schreibt zuletzt = gewinnt); `_start_order` wird mit
  selbst-beendeten Funktionen synchron gehalten. Regressionstest:
  `tests/test_function_layer_order.py`.

### ✅ Verifiziert in Ordnung (kein Bug)
- **Kein Doppel-Schreibpfad:** `PlaybackEngine._loop`/`_flush_to_dmx` ist Legacy
  und wird nicht mehr aus einem Thread getrieben (`start()` setzt nur ein Flag).
  Einziger Render-Pfad ist `AppState._render_frame`.
- **Matrix speichert nur Matrix-Parameter** (`to_dict`), keinen DMX-Snapshot →
  „Matrix pur" lässt alle Nicht-Matrix-Kanäle leer. Die Style-Kanalmaske in
  `RgbMatrixInstance.write` schreibt je Style nur Farbe **oder** Dimmer **oder**
  Shutter, andere Kanäle bleiben unangetastet → Ebenen kombinierbar.
- **Szene/Snap speichert nur ausgewählte Attribute** (`ChannelSelectDialog` +
  `programmer_to_scene_values`) → Farbe- und Dimmer-Ebenen stapelbar.
- **VC-Drag/Drop bindet korrekt:** Function-/Snap-/Snapshot-MIME-Typen stimmen
  zwischen allen Drag-Quellen (FunctionManager, Library-Panel) und dem VC-Canvas
  überein; ein gedroppter Effekt wird zu `FUNCTION_TOGGLE` (aktivierbar).
- **Keine globale MIDI-Doppelbelegung mehr:** `data/midi_mappings.json` enthält
  nur die 8 `page_select`-Notes (82–89), kein CC-Konflikt mit Fadern.

### 🟠 Offen / Design-Entscheidung nötig
- **VC-EFFEKT-01 — Fader aktivieren keinen Effekt.** `EFFECT_PARAM` /
  `EFFECT_INTENSITY` / `EFFECT_SPEED`-Fader (`vc_slider.py`) **regeln** einen
  Effekt, **starten** ihn aber nicht. Ist der Effekt nicht aktiv, bewirkt der
  Fader nichts Sichtbares → Eindruck „ich kann nur Werte anpassen, nicht
  aktivieren". Mögliche Behebung: Fader > 0 startet die Funktion, Fader = 0
  stoppt sie (wie eine Playback-Fader-Cue).
- **VC-EFFEKT-02 — Intensity-Fader wirkungslos bei reiner Farb-Matrix.** Bei
  Fixtures **mit** Dimmer-Kanal skaliert die Per-Effekt-Intensität nur den
  Dimmer. Eine Farb-Matrix (`drive_intensity=False`) schreibt den aber nicht →
  Intensity-Fader bleibt ohne Wirkung; Helligkeit kommt aus der separaten
  Dimmer-Ebene/`base_levels`. Konsistent mit dem Ebenen-Modell, aber als UX
  überraschend.
