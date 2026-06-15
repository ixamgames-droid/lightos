# Changelog

Alle nennenswerten Aenderungen an LightOS werden hier dokumentiert.
Format: [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)

---

## [Unreleased]

### Behoben/Hinzugefuegt (2026-06-15 — EFX-Formen, Anzeige-Sync, Geräte-Solo)
- **EFX-Formen mit harten Kanten:** `SQUARE` und `DIAMOND` waren trigonometrische
  Näherungen, die die Ecken diagonal *abschnitten* (ein „Quadrat" erreichte die
  echte Ecke nie → wirkte verschliffen). Jetzt sind Quadrat/Raute/Dreieck **echte
  Polygone** mit scharfen Ecken (gemeinsamer `_polygon`-Helfer, lineare Kanten,
  jede Kante 1/n der Phase). Neue Form **`TRAPEZ`** (schmal oben, breit unten);
  erscheint automatisch im EFX-Editor-Dropdown. `TRIANGLE` bit-identisch zum
  bestehenden Test. Für freie harte Kanten gibt es zusätzlich den Custom-Path
  (Modus „linear"). `src/core/engine/efx.py`, Tests `tests/test_efx_hard_edges.py`.
- **VC-Button spiegelt Laufzustand:** ein FUNCTION_TOGGLE-Pad leuchtete nur
  während des Drucks (`_pressed`), nicht solange seine Funktion lief — es sah aus,
  als liefe nichts mehr, obwohl sich die Moving Heads noch bewegten. Jetzt grüner
  „aktiv"-Rahmen, solange der Effekt läuft (`_function_running`); die VC-View
  zeichnet funktionsgebundene Pads bei jedem Laufzustands-Wechsel neu (UI-Thread-
  Timer, thread-sicher). `vc_button.py`, `virtual_console_view.py`, Test
  `tests/test_vc_button_running_feedback.py`.
- **Geräte-Solo (gegen Bank-übergreifendes Überschreiben):** neue VC-Pad-Option
  **„Andere Effekte auf denselben Geräten stoppen"** — beim Start ersetzt der
  Effekt nur die laufenden Effekte, die DIESELBEN Strahler benutzen (auch aus
  einer anderen Bank), Effekte auf anderen Geräten laufen weiter. Chirurgischer
  als „Exklusiv" (= alles stoppen). Engine: `FunctionManager.affected_fids()`
  (alle Typen, rekursiv über Chaser/Collection/Sequence) +
  `stop_others_sharing_fixtures()`. `function_manager.py`, `vc_button.py`, Test
  `tests/test_function_solo_fixtures.py`.
- **Live-View-Info-Box zeigt EFX/Matrix:** laufende EFX-/RGB-Matrix-Effekte
  wurden nie als „aktiv" am Gerät gelistet (`hasattr(func,'_values')` traf bei
  EFX die gleichnamige *Methode* → Exception). Jetzt korrekt per isinstance-Guard
  über alle Typen (EFX `fixtures`, Matrix `fixture_grid`, Carousel/LayeredEffect
  `fixture_ids`, Scene `_values`). `src/ui/views/live_view.py`.

### Hinzugefuegt (2026-06-14 — Fixture Generator, F-23/X-4)
- **Fixture Generator** (grafisches Anlegen eigener Geraete-Profile, an QLC+ 5
  orientiert): `src/ui/widgets/fixture_generator.py` (`FixtureGeneratorDialog`),
  Start im **Patch-Tab → „Gerät erstellen…"**. Kopf (Hersteller/Modell/Typ/
  Leistung/Notizen), mehrere Modi, gefuehrter Kanal-Editor (Attribut-Combo +
  Freitext, **mehrfache gleiche Attribute** wie zwei Pan/zwei Tilt, Default/
  Highlight, Invert, **8/16-bit mit Fine-Kanal-Kopplung**), Bereichs-Editor je
  Kanal (range_from/to, Name, `kind`, „Art aus Namen", Schnellwahl-Vorschau),
  **nicht-blockierende Live-Validierung** (0–255, Ueberlappung, Luecke,
  doppelte Attribute, Dimmer↔Strobe-Plausibilitaet, fehlender open-Bereich,
  Modus-Vergleich), **echter Live-Test** (Universe + Startadresse, ein Fader pro
  Kanal schreibt direkt ins Universe des OutputManagers, „Wackeln" rampt einen
  Kanal, „Blackout" + sauberes Restore beim Stop/Schliessen), **`.qxf`-Import**
  als Startpunkt und **Markdown-Export** des Kanal-Layouts. Speichert als
  `source="user"` via `fixture_db.create_user_profile` und emittiert
  `REFRESH_ALL`. Kernlogik UI-unabhaengig/testbar
  (`build_profile_payload`/`validate_model`/`LiveTester`/`model_to_markdown`).
  Tests: `tests/test_fixture_generator.py` (18). Doku:
  `docs/FUTURE_FIXTURE_GENERATOR.md`.

### Hinzugefuegt (2026-06-11 — Details: docs/UPDATE_2026-06-11.md)
- **EFX Custom Paths:** eigene Pan/Tilt-Bewegungen im Popout-Editor aufzeichnen
  (Punkte tippen/ziehen/umsortieren, Linear oder Spline, Vorschau), Pfad-
  Bibliothek pro Show (`efx_paths`), Auswahl im EFX-Hauptfenster, Loop/One-Shot
  als EFX-Eigenschaft. Engine: `efx_path.py` (bogenlaengen-parametrisiertes
  Sampling), `EfxAlgorithm.CUSTOM`. Tests: `tests/test_efx_path.py`.
- **EFX ueber VC/MIDI:** `EfxInstance` traegt jetzt die Live-API
  (`list_params`/`set_param`/`do_action`/`list_actions`) — Speed/Groesse/Fan/
  Richtung/Loop/Pfad/Form auf Fader & Tasten mappbar, gleiche Mechanik wie
  Matrix/Chaser; Live-Editor-Dialog zeigt funktionsspezifische Aktionen.
- **Patchen → Gruppenansicht → "Bearbeiten…":** Mitglieder hinzufuegen/
  entfernen, Reihenfolge (Fan/Chase) per ▲▼, Name aendern — touch-tauglich
  ohne Drag&Drop. Tests: `tests/test_group_edit_dialog.py`.
- **Live View Touch:** Mehrfachauswahl-Modus toggelt jetzt auch die linke
  Liste per Antippen (MultiSelection), groessere zoom-unabhaengige
  Trefferflaechen, Naechster-gewinnt-Hit-Test.
- **Programmer-Ordner klappbar:** Gruppen-Ordner-Kopfzeilen antippbar (▾/▸,
  persistiert); Bibliotheks-Ordnerzustand ueberlebt Rebuilds + Neustart.
- **Controller-Datenbank:** JSON-Profil-Bibliothek (`data/controller_library/`
  + Nutzer-Importe) mit 8 Seed-Geraeten (APC mini/mk2, nanoKONTROL2, X-Touch
  Mini, Launchpad Mini MK3, Enttec DMX USB Pro, Art-Net-Node, Makro-Tastatur),
  QLC+-.qxi-Import (CLI + UI), Browser in der MIDI-Konsole. Quellen/Lizenzen:
  `data/controller_library/README.md`. Tests: `tests/test_controller_library.py`.
- **VC-Keyboard-Mapping:** Tasten/Kombinationen auf VC-Buttons lernen
  (Rechtsklick → "Taste zuweisen…"), Konfliktpruefung, Blackout-Warnung,
  Textfeld-/Modal-/AutoRepeat-Schutz, Press/Release wie MIDI-Note, Persistenz
  im VC-Layout. Doku: `docs/KEYBOARD_MAPPING.md`. Tests:
  `tests/test_keyboard_mapping.py`.
- **Demo:** `tools/build_custom_path_demo.py` → `shows/CustomPath_Demo.lshow`
  (selbst-verifizierend; MIDI- + Tastatur-Bindungen, One-Shot + Loop-Pfad).
- **Fixture-Quellen-Doku:** `docs/FIXTURE_SOURCES.md` (OFL/QLC+ legal nutzen).

### Behoben
- **Zombie-Subscriber im Event-Bus (Crash-Klasse aus crash.log, 2026-06-10).**
  Eingebettete Views (EFX-/Matrix-/Paletten-Seite, SnapFilePanel) werden bei jedem
  Programmer-Layout-Wechsel neu gebaut, blieben aber im StateSync registriert —
  der naechste Emit lief in geloeschte Qt-Objekte (RuntimeError bis Access
  Violation, siehe %APPDATA%/LightOS/crash.log). Neu: `StateSync.subscribe_widget`
  (auto-unsubscribe bei `destroyed`) fuer diese Views + Selbstheilung in
  `StateSync.emit` ("already deleted"-Subscriber werden entfernt).
  Tests: `tests/test_sync_safe_subscribe.py`.
- **EFX "Bounce" sprang am oberen Umkehrpunkt auf den Anfang.** Nach dem Klemmen
  der Phase auf 1.0 lief noch das gemeinsame `%= 1.0` -> Phase 0.0 (Saegezahn statt
  Pendel). Betroffen u. a. "MH Bounce" in `Komplett_Demo.lshow`.
  Tests: `tests/test_moving_head_efx.py::EfxBounceTest`.

### Hinzugefuegt
- **UI-Freeze-Watchdog (main.py).** Freezes ("Keine Rueckmeldung") hinterliessen
  bisher keinen crash.log-Eintrag. Ein 1-s-Herzschlag-Timer im UI-Thread + Daemon-
  Watchdog dumpt nach >10 s Stillstand die Stacks ALLER Threads nach crash.log —
  der naechste Freeze ist damit diagnostizierbar.
- **Headless-Verifier fuer die Komplett-Demo** (`tools/verify_komplett_demo.py`):
  laedt die Show ohne UI, prueft Referenz-Integritaet (Timeline/Chaser/VC), tickt
  die AUTO-SHOW >1 Loop durch den echten Renderer und assertet, dass sich die
  Moving-Head-Kanaele in den EFX-Abschnitten bewegen.
- **ZQ02001-Profil: Dimmer/Strobe waren vertauscht (2026-06-10).** Nach realen
  Gerätedaten korrigiert: Strobe liegt VOR dem Dimmer (9ch: CH5/CH6, 11ch: CH7/CH8);
  der 9-Kanal-Modus hatte fälschlich Pan/Tilt-fein statt Pan/Tilt-Speed, Gobo-FX und
  Reset. Farbrad (15 Slots inkl. 6 Split-Farben + Auto), Gobo (7 statisch + 7 Shake +
  Wechsel 128–255) und Strobe (0–9 offen / 10–249 langsam→schnell / 250–255 aus) sind
  jetzt als exakte `ChannelRange`-Bereiche mit `kind` hinterlegt. `ensure_builtins()`
  aktualisiert veraltete builtin-Profile **in-place** (Profil-ID stabil — bestehende
  Patches überleben). Der Reset-Kanal war zudem als zweiter `macro`-Kanal im
  Programmer unsichtbar (Attribut-Dedup) → neue Attribute `gobo_fx` und `reset`.
  Doku: `docs/MOVING_HEADS.md`. Tests: `tests/test_zq02001_profile.py`.
- **Test-Suite-Stabilität:** erzeugte `VCCanvas`-Instanzen blieben beim globalen
  MIDI-Manager registriert (Abmeldung nur bei Zerstörung); über viele Tests häuften sich
  tote Callbacks bis zu einem harten Crash. Neue Autouse-Fixture (`tests/conftest.py`)
  meldet nach jedem Test alle noch lebenden Canvases ab.
- **Simple Desk Roh-Bypass (ISO-03):** Die 512 Fader schrieben direkt ins Live-Universe,
  **am zentralen Renderer vorbei**. Folge: auf gepatchten Kanaelen ueberschrieb der Renderer
  den Wert Frame fuer Frame (Flackern/wirkungslos), auf freien Kanaelen blieb er als
  **unsichtbarer „Zombie"** dauerhaft stehen. Simple Desk ist jetzt eine deterministische
  **Override-Schicht** im `_render_frame` (oberste Ebene): kein Flackern, kein Zombie, und
  die Werte sind sicht- (ISO-01) und loeschbar (ISO-02). Test: `tests/test_iso_simple_desk.py`.
  **Standard = reine Anzeige (Monitor):** die Fader spiegeln die Ausgabe und wirken nicht;
  erst die Checkbox **„Manueller Override"** gibt ihnen absolute Oberhand (im Anzeige-Modus
  sind Fader + „Alles auf …"-Buttons gesperrt).
- Effekt-Layering (LAYER-01): Laufende Funktionen wurden in **ungeordneter** Reihenfolge
  (Set) getickt. Schrieben zwei Effekte denselben DMX-Kanal (z. B. Farb-Matrix mit
  `drive_intensity` + Dimmer-Matrix), gewann ein **zufaelliger** Writer statt der zuletzt
  gestarteten Funktion → Werte wurden unvorhersehbar ueberschrieben. `FunctionManager.tick()`
  laeuft jetzt in Start-Reihenfolge (LTP: zuletzt gestartet gewinnt). Test:
  `tests/test_function_layer_order.py`.
- Virtual Console: Absturz (`KeyError: 0`) beim Bewegen eines Level-Faders. Ursache war
  eine fehlerhafte Universe-Pruefung (`< len()` auf einem dict mit 1-basierten Keys).
  Der Fader legt das Ziel-Universe nun bei Bedarf an; das Universe ist im
  Fader-Eigenschaften-Dialog einstellbar (Default 1).

### Hinzugefuegt
- **Moving-Head-Bedienung im Programmer (2026-06-10):** Strobe liegt jetzt im
  **Intensity-Tab** neben dem Dimmer (Status-Kacheln „Kein Strobe/Strobe aus" +
  stufenloser Speed-Slider + DMX-Bereichslegende; Grand Master fasst den Strobe-Kanal
  weiterhin nicht an). **Color-Wheel-Direktwahl**: farbige Kacheln für alle Voll- und
  Split-Farben (zweifarbig dargestellt) + **Auto-Farbwechsel** als Hardware-Rotation
  (Tempo-Slider) und **Software-Simulation** mit wählbarem Bereich (Von/Bis, „Nur
  Split-Farben"). **Gobo-Tab**: Kacheln mit **grafischer Gobo-Vorschau** (neues
  wiederverwendbares Modul `src/ui/widgets/gobo_icons.py`, 7 QPainter-Muster),
  Shake-Kacheln mit einstellbarer Geschwindigkeit, Gobo-Wechsel-Slider (128–255) mit
  Stopp, Gobo-FX-Fader. **Reset-Button** („Weitere") mit Sicherheitsabfrage und
  automatischem Rücksetzen nach 4 s — bewusst kein Dauer-Slider. Alles generisch aus
  den `ChannelRange`-Daten (kein Raten ohne Capability-Daten). Neue Doku:
  `docs/MOVING_HEADS.md`, `docs/FIXTURE_LIBRARY.md`,
  `docs/FUTURE_FIXTURE_GENERATOR.md` (Idee, bewusst nicht gebaut) und
  `docs/OPEN_POINTS_OVERVIEW.md` (repo-weite Übersicht offener Punkte).
- **Phase-6-Feinschliff:** Matrix-**Versatz**-Parameter (`offset`) + Dimmer/Shutter-Min/Max
  und Weissanteil **live steuerbar** (MXP-02/03); **Simple-Desk-Fader nach Fixture eingefärbt**
  (SDK-01); **Fader-Reichweite „nur Auswahl/Gruppe"** im Programmer-Modus (FDR-01); VC-Toolbar
  entschlackt (UIC-02..05: „⊞ Raster", „Canvas exportieren/importieren", „Aktiver Effekt"-Zeile
  nur bei laufendem Effekt, Canvas-Kontextmenü ohne Save/Load-Dopplung). Tests:
  `test_matrix_offset_style_params.py`, `test_fader_scope.py`, `test_simple_desk_tint.py`.
- **Demo-/Bühnen-Show (DMO-01):** `tools/build_demo_zq_show.py` → `shows/Demo_ZQ_Buehne.lshow`
  mit **4× ZQ01424 (PAR)** + **2× ZQ02001 (Moving Head)**: Farben/Looks, Dimmer-Lauflicht,
  RGB-Matrix, Moving-Head-Positionen/Beam + Sweep-Chaser, **Speed-Dial (Multiplikator)**,
  zwei **VC-Frames** (PARs / Moving Heads) und ein **Multi-Action-Button** „▶ Showtime".
  (Die ursprünglich als „Horhin" bezeichneten Strahler sind ZQ01424, der Moving Head ist ZQ02001.)
- **Paletten + Kurven: Unterordner (FLD-01c):** Paletten und Fade-Kurven haben jetzt ein
  verschachtelbares `folder`-Feld (in der Show gespeichert, rückwärtskompatibel). Die
  Paletten-Ansicht gruppiert nach Ordner (Überschriften) und bietet „In Ordner verschieben…".
  Damit ist FLD-01 („Unterordner überall") abgeschlossen. Test: `tests/test_palette_curve_folders.py`.
- **Fixture-Gruppen: Unterordner (FLD-01b):** Gruppen lassen sich einem verschachtelten
  Ordner zuordnen („Ordner…"-Button, Pfad mit `/`, z. B. „Front/Wash"); die Gruppen-Auswahl
  zeigt den Ordnerpfad und sortiert danach. Neue, **idempotente DB-Migration**
  (`migrate_show_db`) ergänzt die `folder`-Spalte in bestehenden Show-DBs ohne Datenverlust.
  Test: `tests/test_fixture_group_folders.py`.
- **Funktions-Manager zeigt Ordner (FLD-01a):** die rechte Funktionsliste bildet jetzt die
  vorhandene, verschachtelte Ordner-Hierarchie der Funktionen (`folder`-Pfad, z. B.
  „Blau/Sommer") innerhalb jeder Typ-Gruppe ab — erster Schritt von „Unterordner überall".
  Test: `tests/test_function_folders.py`.
- **Snapshots: Kanäle nachträglich ignorieren (SNP-01):** pro Snapshot lassen sich
  einzelne (Fixture, Attribut)-Kanäle vom Anwenden ausschließen — der gespeicherte Wert
  bleibt erhalten, wird aber nicht in den Programmer geschrieben. Editor über „Kanäle
  ignorieren…" (Alle/Keine/Invertieren); rückwärtskompatibel. Test: `tests/test_snapshot_ignore.py`.
- **Kanal-Gruppen pro Show (SDK-02):** Channel Groups werden jetzt in der `.lshow`
  gespeichert/geladen (statt nur global in `data/channel_groups.json`). Test:
  `tests/test_channel_groups_show.py`.
- **Widgets per Drag in Frames ziehen (FRM-01):** ein vorhandenes VC-Widget lässt sich in
  einen Frame ziehen (wird dessen Kind, Position relativ) und wieder heraus auf den Canvas;
  die Zuordnung bleibt beim Speichern erhalten. Frames werden nicht verschachtelt. Test:
  `tests/test_frame_drag.py`.
- **Multi-Actions auf VC-Buttons (BTN-01):** ein Button kann beim Druck — nach seiner
  Primär-Aktion — eine Liste weiterer Aktionen der Reihe nach ausführen (Funktion
  start/stop/toggle, Effekt-Aktion, Snapshot, Bibliothek-Snap, Blackout, Stop-All,
  Programmer/Non-VC leeren, Tap), je mit optionaler Verzögerung. Editor über
  „Mehrfach-Aktionen…" im Button-Dialog; ein „+n"-Marker zeigt die Anzahl. Vollständig
  rückwärtskompatibel (ohne Liste = klassischer Ein-Aktions-Button). Test:
  `tests/test_button_multi_action.py`.
- **Speed Dial: Multiplikator-Modus, Sync, Multi-Ziele, Invertierung (SPD-01/02/03/04):**
  optionaler **Multiplikator-Modus** (Dial als Faktor 0.5/1/2/4× auf die Effekt-Speed statt
  absoluter BPM), **SYNC-Button** (gleicht die Phase aller Ziel-Effekte an), **mehrere
  Ziel-Effekte** (weitere Function-IDs) und eine **Invert-Option** (höher = langsamer).
  Persistiert, rückwärtskompatibel. Test: `tests/test_speed_dial.py`.
- **Matrix-Live-Editor in der Virtual Console (MLV-01/02):** Rechtsklick auf einen an
  einen Effekt gebundenen VC-Button/-Fader zeigt „⚡ Live-Parameter…". Der Dialog listet
  die live steuerbaren Parameter (→ Fader) und Aktionen (→ Tasten) des Effekts; die Auswahl
  wird **automatisch** als korrekt gebundene VC-Bedienelemente erzeugt (EFFECT_PARAM /
  EFFECT_ACTION, an die `function_id` des Effekts). Bearbeiten/Entfernen über die normalen
  Widget-Menüs. Test: `tests/test_matrix_live_vc.py`.
- **Fixture U King ZQ02001 (LIB-01):** Mini-Gobo Moving Head (11-Kanal + 9-Kanal) zur
  Fixture-Library hinzugefügt — `examples/add_zq02001.py`. Kanal-Layout aus dem
  Hersteller-Handbuch; feine Farb-/Gobo-Wertbereiche sind genähert und im Skript markiert.
- **Matrix-Chase „Farbwechsel-Intervall" (MXP-01):** neuer Parameter `color_interval`
  (sichtbar bei aktivem „Farbe pro Runde wechseln") — die Farbe wechselt erst alle N
  Durchläufe (1 = jeder Durchlauf wie bisher, 2/4/8 = langsamer). Live über VC/MIDI
  steuerbar, persistiert, Default 1 für Alt-Shows. Test: `tests/test_matrix_color_interval.py`.
- **Color-Sequence: Swatch-Einzelklick öffnet den Color-Picker (MXP-04):** im kompakten
  Farbstreifen (Matrix-Programmer) öffnet ein Klick auf ein Farbquadrat direkt den Picker
  für diese Farbe (live), ohne erst den Editor öffnen zu müssen.
  Test: `tests/test_color_sequence_swatch.py`.
- **Anzeige aktiver Fremdwerte (ISO-01):** Die obere Leiste zeigt jetzt ein Badge
  „● Programmer n · Simple Desk n", sobald manuelle Werte aktiv sind — damit faellt nichts
  mehr unbemerkt in die Live-Ausgabe.
- **Zentrales Clear (ISO-02):** Button „✖ Clear ▾" in der oberen Leiste mit
  *Programmer leeren · Simple Desk leeren · Alle Nicht-VC-Werte leeren*. Setzt nur aktive
  manuelle Werte zurueck — laufende Funktionen/Effekte/Cues, gespeicherte Effekte, Shows,
  Patches und Fixtures bleiben unangetastet. API: `clear_simple_desk()`, `clear_all_non_vc()`.
- Virtual Console: pro Effekt-Fader einstellbar, ob er **bei 0 den Effekt stoppt** oder
  **nur runterregelt** (Eigenschaft `effect_autostart`, Checkbox im Fader-Dialog). An:
  Wert > 0 startet den gebundenen Effekt, Wert 0 stoppt ihn (wie ein Playback-Fader);
  aus (Default): Fader regelt nur. Gilt fuer *EffectIntensity/EffectSpeed/EffectParam*.
- Visualizer-Persistenz: Fixture-Positionen und die aktive Buehne werden mit der Show
  (`.lshow`) gespeichert und beim Laden wiederhergestellt (T-VIZ-01, T-VIZ-02).
- Unit-Tests fuer Core-Engine: `tests/test_core_engine.py`
  - `Universe` (DMX-Kanalverwaltung, Thread-Safety, Boundaries)
  - `Cue` (Datenmodell, Serialisierung-Roundtrip)
  - `FadeState` / `CueStack` (Fade-Interpolation, Go/Back/Stop/Loop, Callbacks)
  - `ChannelModifier` / `ChannelModifierManager` (alle Kurventypen, apply_to_universe, Save/Load)
  - `SelectionExpr` (Fixture-Selektion, Ranges, Excludes)
  - Command-Line Parser (`parse()` fuer alle Befehle)
  - `UndoStack` (Push/Undo/Redo, MAX_SIZE-Cap, Listener)
- `README.md` um "Quick Start"-Abschnitt erweitert (5-Minuten-Guide fuer neue Nutzer)
- `.github/workflows/ci.yml` — automatisierte Test-Pipeline (Python 3.11 + 3.12)
- `CHANGELOG.md` — diese Datei (Keep-a-Changelog-Format)

### Entfernt
- **Redundanter „Snap"-Button (UIC-01)** aus der oberen Leiste. Die Schnell-Snapshot-Funktion
  bleibt vollstaendig erreichbar ueber Menue *Programmer → Snapshot aufnehmen* (`Strg+Shift+S`),
  die *Snapshots*-Ansicht und die VC-Seitenleiste.

---

## [0.1.0] — 2026-05-26

### Hinzugefuegt
- Vollstaendige DMX-Steuerungs-Engine
  - Enttec DMX USB Pro, Art-Net 4, sACN / E1.31 (bis zu 32 Universen)
  - OutputManager mit 44-Hz-Loop, Grand Master, Blackout, Submasters
  - Channel-Modifier mit 7 Kurventypen + Custom LUT
- Engine (10 Function-Typen)
  - Scene, Chaser, Collection, Show (Timeline), EFX, RGB-Matrix,
    Sequence, Audio, Script, LayeredEffect, Carousel
  - Multi-Page-Playback: 10 Pages × 20 Executors = 200 Slots
  - Cue-System mit Fade-In/Out, Delay, Auto-Follow, Loop
  - Undo/Redo (unbegrenzt, 100er-Cap)
- Programmer
  - Attribut-Gruppen: Intensity, Color, Position, Beam, Gobo, Effect
  - Color Picker (RGB/HSB/CMY, 27 Lee-Rosco Gel-Filter)
  - Position Tool (2D-Pad, 13 Presets)
  - Fan Tool (5 Kurven, Symmetric/Asymmetric)
  - Snapshots (12×4 Quick-Recall)
  - Paletten (Color / Position / Beam)
- Audio / BPM
  - WASAPI Loopback Audio-Capture
  - Beat-Detection (Bass-Energy adaptive Threshold)
  - Tap-Tempo BPM-Manager
  - OS2L Server (VirtualDJ Integration)
  - MIDI Time Code Reader
- Virtual Console
  - Button, Slider, XY-Pad, Cue-List, Speed-Dial, Frame, Label, Solo-Frame
  - Save/Load Layouts pro Show
- 3D Visualizer (Three.js / QtWebEngine)
  - 2D Top-Down + 3D Perspektive, 4 Bühnen-Presets + Custom Stage Builder
  - Echte 3D-Modelle, volumetrische Beam-Cones
- Eingaben
  - MIDI Input mit Profil-Editor (Akai APC mini Default)
  - OSC Server (Port 7770)
  - Keyboard-Hotkeys
  - Web-Remote (Flask + Socket.IO)
- Command-Line (MA-/Avolites-Style)
  - `1 thru 5 @ 80`, `all @ full`, `go 1`, `record cue 2.5`, `page 3`, `blackout`
- Installer/Uninstaller (`install.py`, `uninstall.py`)
  - ARM64/Snapdragon-Erkennung, venv-Management, Desktop-Verknuepfung
- Start-Skripte fuer CMD (`.bat`), PowerShell (`.ps1`), Bash (`.sh`)
- Fixture-Datenbank (SQLAlchemy/SQLite), GDTF-Import
- Show-File-Format `.lshow` (ZIP + JSON, Version 1.1, Legacy-1.0-Support)
- Vollstaendige Dokumentation in `docs/`

---

<!-- Verlinkung fuer die Versionen -->
[Unreleased]: https://github.com/OWNER/lightos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/lightos/releases/tag/v0.1.0
