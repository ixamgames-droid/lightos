# LightOS – Feature-Map / Funktions-Inventar (AUDIT-01)

> Stand: 2026-06-01 · Bezug: `TODO.md` Abschnitt 12, **AUDIT-01**
> Ziel: Vollständiger Überblick „was ist wo?" + Markierung der Doppelungen als
> Grundlage für die Konsolidierung (AUDIT-02).

**Methodik:** statisch aus dem Quellcode erhoben (`src/ui/**`, 44 Module). Die
Sektions-/Tab-Struktur stammt direkt aus `main_window.py`, die Beschreibungen aus
den Modul-/Klassen-Docstrings. LOC = Zeilenzahl (grobe Größe). Kein Laufzeittest –
beschreibt die **Soll-Struktur laut Code**.

Die App ist eine **PySide6/Qt**-Anwendung. Einstieg: `MainWindow`
(`src/ui/main_window.py`, 1465 LOC). Oben eine **Sektions-Leiste mit 7 Schaltern**
(QStackedWidget), darunter der Inhalt; viele Sektionen haben **Sub-Tabs**
(`_SubTabs`). Dazu eine Menüleiste, eine Command-Line am unteren Rand und der
Visualizer als separates Fenster.

---

## 1. Sektionen (Haupt-Navigation, 7 Schalter)

| # | Sektion (Schalter) | Sub-Tabs | Inhalt / Zweck |
|---|--------------------|----------|----------------|
| 0 | **Live View** | – | 2D-Top-Down-Ansicht aller gepatchten Fixtures aus der Vogelperspektive (`live_view.py`, 607) |
| 1 | **Patchen** | Patch · Gruppen | Geräte patchen + Fixture-Gruppen (EFX/RGB Matrix/Funktionen nach P-01 in den Programmer umgezogen) |
| 2 | **Programmer** | Programmer · Funktionen · EFX · RGB Matrix · Paletten · Snapshots | Fixture-Attribute live setzen, Funktions-/Effekt-Editoren, Paletten, Snapshots |
| 3 | **Virtual Console** | – | Frei konfigurierbare Konsole: Toolbar + Canvas + Snapshot-Seitenleiste (`virtual_console_view.py`, 619) |
| 4 | **Simple Desk** | Simple Desk · Channel Groups | 512 direkte DMX-Fader + Kanal-Gruppen-Submaster |
| 5 | **Playback** | Playback · Show Manager | Executor-Fader/Cuelisten + Timeline-Show-Editor |
| 6 | **Eingabe / Ausgabe** | Output · DMX Monitor · MIDI · Audio Input | DMX-Ausgabe, Monitor, MIDI, Audio in einem Bereich |

### Sub-Tabs im Detail

| Sektion | Sub-Tab | Modul | Beschreibung |
|---------|---------|-------|--------------|
| 1 | Patch | `views/patch_view.py` (350) | Geräte patchen/verwalten, DMX-Adressen, Universe-Belegung |
| 1 | Gruppen | `views/fixture_group_view.py` (375) | **Fixture**-Gruppen auf 2D-Grid (Drag&Drop) |
| 2 | Programmer | `views/programmer_view.py` (707) | Live-Bearbeitung von Fixture-Attributen (Slider, Farbe, Tools) |
| 2 | Funktionen | `views/function_manager_view.py` (604) | Zentraler Funktions-Browser (Szenen/Chaser/… anlegen, bearbeiten, MIDI-Learn) |
| 2 | EFX | `views/efx_view.py` (336) | 2D-Bewegungsfiguren (Pan/Tilt) für Moving Heads + Live-Preview |
| 2 | RGB Matrix | `views/rgb_matrix_view.py` (307) | LED-Grid-Effekte + Matrix-Preview |
| 2 | Paletten | `views/palette_view.py` (180) | Color/Position/Beam/Effect-Paletten (QLC+-Stil) |
| 2 | Snapshots | `views/snapshots_view.py` (367) | Quick-Save-Buttons für Programmer-States (48 Slots) |
| 4 | Simple Desk | `views/simple_desk.py` (200) | 512 vertikale DMX-Fader pro Universe |
| 4 | Channel Groups | `views/channel_groups_view.py` (241) | **Kanal**-Gruppen mit gemeinsamem Slider (Submaster) |
| 5 | Playback | `views/playback_view.py` (506) | Cuelisten, Executor-Fader, GO/BACK |
| 5 | Show Manager | `views/show_manager_view.py` (550) | Timeline-Editor: Tracks + ShowFunctions als Blöcke |
| 6 | Output | `views/output_view.py` (118) | DMX-Kanalwerte in Echtzeit (Zellen) |
| 6 | DMX Monitor | `views/dmx_monitor_view.py` (204) | Alle 512 DMX-Kanäle als 32×16-Grid |
| 6 | MIDI | `views/midi_view.py` (599) | MIDI-Monitoring, Konfiguration, Mapping, virtueller Port |
| 6 | Audio Input | `views/audio_input_view.py` (359) | WASAPI-Loopback-Aufnahme + Beat/BPM-Anzeige |

---

## 2. Sektions-Leiste (globale Bedienelemente, immer sichtbar)

| Element | Funktion |
|---------|----------|
| Grand Master (Slider) | Globaler Master-Dimmer 0–100 % |
| TAP | Tap-Tempo (BPM) |
| Validation-Banner | Zeigt Show-Probleme, Klick öffnet `ValidationDialog` |
| Snap | Aktuellen Programmer in nächsten freien Snapshot-Slot speichern |
| ◀ Page N ▶ | Multi-Page-Playback umschalten |
| BPM-Label + Indikator | BPM-Anzeige (klickbar zum Setzen) + Beat-Blink |
| STOP ALL | Alle Executors stoppen |
| BLACKOUT | Globaler Blackout (Toggle) |
| Command-Line (unten) | MA-/Avolites-Befehlszeile (`widgets/command_line.py`) |

---

## 3. Menüleiste

| Menü | Einträge (Kurz) |
|------|-----------------|
| **Datei** | Neue Show · Öffnen · Speichern · Speichern unter · Zuletzt verwendet · XML-Workspace (.qxw) importieren · Show prüfen & reparieren · Beenden |
| **Bearbeiten** | Rückgängig · Wiederherstellen · Verlauf löschen (`core/undo.py`) |
| **Ansicht** | Alle Views aktualisieren (F5) |
| **Show** | Cue aufnehmen (R) · Nächste/Vorherige Page |
| **Programmer** | Highlight (H) · Lowlight (Shift+H) · Programmer leeren (Esc) · Kopieren/Einfügen · Snapshot aufnehmen |
| **Datenbank** | Fixtures importieren (XML) · Neues Fixture-Profil |
| **Ausgabe** | Konfigurieren · Channel-Modifier · Mock Mode · Web-Interface (:5000) · OSC (:7770) · OS2L (:1234) · Input-Profile |
| **Visualizer** | 3D-Visualizer öffnen/schließen |
| **Command** | Command-Line fokussieren (`:` / F12) |
| **Hilfe** | Über LightOS |

---

## 4. Funktions-Editoren (modal, aus *Funktionen*/*Show Manager* geöffnet)

| Editor | Modul | Beschreibung |
|--------|-------|--------------|
| Szene | `views/scene_editor.py` (227) | Kanal-Snapshot einer Szene bearbeiten |
| Chaser | `views/chaser_editor.py` (304) | Schritt-Sequenz aus Funktionen + Timing |
| Sequence | `views/sequence_editor.py` (371) | Step-Tabelle pro Fixture |
| Collection | `views/collection_editor.py` (136) | Mehrere Funktionen parallel starten |
| Carousel | `views/carousel_editor.py` (182) | Beat-synchronisierte Pattern (Layered) |
| Effect-Layer | `views/effect_layer_editor.py` (244) | Layer eines `LayeredEffect` (Matrix) editieren |
| Script | `views/script_editor.py` (170) | Skript-Funktion mit Syntax-Highlighting |
| Audio | `views/audio_editor.py` (175) | `AudioFunction` bearbeiten |

## 5. Werkzeuge & Dialoge

| Werkzeug | Modul | Beschreibung |
|----------|-------|--------------|
| Effekt-Assistent | `widgets/effect_wizard.py` (298) | Wizard (Typ·Fixtures·Farben·Optionen) → erzeugt fertigen Chaser |
| Fixture-Editor | `widgets/fixture_editor.py` (409) | Eigene Fixture-Profile (Modes/Channels) anlegen |
| Fixture-Browser | `widgets/fixture_browser.py` (199) | Gerät aus DB wählen & patchen |
| QXF-Import | `widgets/qxf_import_dialog.py` (151) | QLC+-Fixtures bulk-importieren |
| Input-Profil-Editor | `widgets/input_profile_editor.py` (327) | MIDI/OSC-Mappings verwalten + lernen |
| MIDI-Teach | `widgets/midi_teach_dialog.py` (296) | APC-mini-Tasten/Fader visuell an VC-Widget binden |
| Output-Konfig | `widgets/output_config.py` (400) | Enttec · Art-Net · sACN · DMX-Input · Universen |
| Channel-Modifier | `widgets/channel_modifier_dialog.py` (129) | Pro Kanal eine Kurve zuweisen |
| Channel-Range-Lock | `widgets/channel_range_lock_dialog.py` (155) | Kanal auf Sub-Range sperren |
| Color-Picker | `widgets/color_picker.py` (596) | Farbrad + Basic/Full/Filter-Tabs |
| Curve-Editor | `widgets/curve_editor.py` (336) | Fade-Kurven grafisch bearbeiten |
| Fan-Tool | `widgets/fan_tool.py` (290) | Werte über Selektion fächern |
| Position-Tool | `widgets/position_tool.py` (350) | Pan/Tilt-2D-Pad für Moving Heads |
| Validation | `widgets/validation_dialog.py` (58) | Probleme beim Show-Laden anzeigen |
| Touch-Tastatur | `touch_keyboard.py` (267) | On-Screen-Keyboard für Tablet-Betrieb |

## 6. Virtual-Console-Widgets (`virtualconsole/`)

| Widget | Modul | Beschreibung |
|--------|-------|--------------|
| Basis | `vc_widget.py` (272) | Abstrakte Basisklasse aller VC-Widgets |
| Canvas | `vc_canvas.py` (406) | Freie Layout-Fläche (Edit/Live) |
| Button | `vc_button.py` (469) | Flash/Toggle/Blackout/StopAll/Snapshot |
| Slider | `vc_slider.py` (332) | Fader: Level/Playback/Submaster |
| XY-Pad | `vc_xypad.py` (187) | Pan/Tilt-2D-Pad |
| Color | `vc_color.py` (308) | Farb-Kachel |
| CueList | `vc_cuelist.py` (154) | CueStack mit GO/BACK/STOP |
| Frame | `vc_frame.py` (246) | Container mit Multi-Page |
| Speed-Dial | `vc_speedial.py` (264) | Tempo-Dial + Tap-Tempo |
| Label | `vc_label.py` (55) | Statischer Text |

## 7. Separates Fenster

| Fenster | Modul | Sub-Tabs | Beschreibung |
|---------|-------|----------|--------------|
| Visualizer | `visualizer/visualizer_window.py` (1368) | Fixtures · Bühne · Einstellungen | 3D/2D-Bühne via Three.js (QWebEngineView) |

---

## 8. ⚠️ Doppelungen & Redundanzen (Kernergebnis)

| # | Thema | Wo / Befund | Bewertung |
|---|-------|-------------|-----------|
| **D-1** | **Snapshots 3-fach** | (a) Sektion 2 Sub-Tab „Snapshots" (`snapshots_view`), (b) Snapshot-Seitenleiste in der Virtual Console (`SnapshotSidebar`), (c) Snap-Datei-Panel (`snap_file_panel.py`) | Mehrere Snapshot-UIs nebeneinander → vereinheitlichen |
| **D-2** | **Effekt-Erstellung fragmentiert** | `effect_wizard` (Generator), `rgb_matrix_view`, `effect_layer_editor`, `efx_view`, `carousel_editor` | Viele getrennte Wege/Datenmodelle → deckt sich mit TODO **ARC-05/ARC-06** |
| ~~**D-3**~~ | ~~**RGB-Matrix / Effekt im Patch-Bereich**~~ | ✅ **ERLEDIGT (P-01, 2026-06-01):** „EFX", „RGB Matrix", „Funktionen" in den *Programmer* verschoben; *Patchen* = nur noch Patch · Gruppen | behoben |
| **D-4** | **Gruppen-Begriff doppelt & verstreut** | *Fixture*-Gruppen (Sektion 1) vs. *Kanal*-Gruppen (Sektion 4) | Fachlich verschieden, aber gleicher Name „Gruppen"/„Groups" in zwei Sektionen → Verwechslungsgefahr |
| **D-5** | **DMX-Werte-Anzeige doppelt** | *Output* (`output_view`) und *DMX Monitor* (`dmx_monitor_view`) – beide in Sektion 6, beide zeigen Live-Kanalwerte | Überschneidung → zusammenlegen oder klar abgrenzen |
| **D-6** | **MIDI-Mapping/Lernen mehrfach** | `midi_view`, `midi_teach_dialog`, `input_profile_editor` | Drei Wege, eine Bindung anzulegen |
| **D-7** | **Farbauswahl mehrfach** | `widgets/color_picker`, `vc_color`, QColorDialog (rgb_matrix/visualizer), `palette_view` (Color) | Mehrere Farbwähler-Implementierungen |
| **D-8** | **Funktions-Verwaltung vs. Show-Manager** | `function_manager_view` (Liste) und `show_manager_view` (Timeline) verwalten beide Funktionen | Teilüberschneidung – ggf. klar trennen (Bibliothek vs. Timeline) |
| **D-9** | **Snap-Datei-Panel doppelt eingebettet** | `snap_file_panel.py` (710 LOC, `SnapFilePanel`) wird **sowohl** in `programmer_view.py` **als auch** in `snapshots_view.py` instanziiert | Eine Einbindung genügt → siehe D-1 |

> *Kein* echtes Duplikat (Workflow, gehört zusammen): `patch_view` + `fixture_browser`
> + `fixture_editor` + `qxf_import` (Patch-Workflow); `output_view`/`output_config`
> (Anzeige + Konfig-Dialog).

---

## 9. Konsolidierungs-Empfehlung (Input für AUDIT-02)

**Zusammenlegen**
- **C-1 (Snapshots, D-1/D-9):** Eine zentrale Snapshot-Verwaltung; VC-Seitenleiste,
  Quick-Snap und das Snap-Datei-Panel greifen auf **eine** Liste/Komponente zu
  (statt `SnapFilePanel` doppelt in Programmer und Snapshots zu instanziieren).
- **C-2 (Effekte, D-2):** Generator und manuelle Editoren mittelfristig auf **ein**
  Programm-/Effekt-Datenmodell führen (TODO ARC-05/ARC-06).
- **C-3 (DMX-Anzeige, D-5):** *Output* und *DMX Monitor* zu einer Ansicht mit
  Umschalter (Zellen ↔ Grid) zusammenfassen.
- **C-4 (MIDI-Lernen, D-6):** Ein gemeinsamer Teach-/Learn-Flow, von allen Stellen
  aufrufbar.
- **C-5 (Farbwähler, D-7):** `widgets/color_picker` als einzige Komponente
  überall wiederverwenden.

**Verschieben / besser organisieren**
- **C-6 (D-3): ✅ ERLEDIGT (P-01, 2026-06-01)** — „EFX", „RGB Matrix", „Funktionen"
  aus *Geräte & Funktionen* in den *Programmer* verschoben. *Patchen* ist jetzt reiner
  Patch-Bereich (Patch · Gruppen), passend zu PA-01 „Umbenennung in Patchen".
- **C-7 (Gruppen, D-4):** Fixture- und Kanal-Gruppen in **einem** Bereich mit klarer
  Beschriftung („Fixture-Gruppen" vs. „Submaster/Kanal-Gruppen").
- **C-8 (Funktionen vs. Show, D-8):** Rollen schärfen: *Funktionen* = Bibliothek/CRUD,
  *Show Manager* = zeitliche Anordnung. Keine doppelte Bearbeitungslogik.

**Aufräumen**
- **C-9 (D-9):** `SnapFilePanel` nur an **einer** Stelle einbetten (gemeinsame
  Instanz/Komponente), statt parallel in Programmer und Snapshots.

> Vorgehen laut **AUDIT-02**: schrittweise (ein Bereich pro PR), nach jeder Änderung
> Smoke-Test (`docs/SMOKE_TEST.md`) – jede Funktion muss erreichbar bleiben.
