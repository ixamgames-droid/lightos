# LightOS – Umbau-Roadmap: Matrix-System, Patcher-Gruppen, Live View

> Stand: 2026-06-02 · Autor: Analyse vor Umsetzung (Opus)
> Geltungsbereich: Teile 1–9 der Anforderung „Gesamtänderung Matrix/Patcher/Live View".
> **Leitprinzip:** schrittweise, je Phase ein abgeschlossener + getesteter Block;
> bestehende Funktionen erhalten, gezielt erweitern statt Komplett-Umbau.

---

## 0. Leitplanken (für alle Phasen)

- **Eine Phase = ein in sich testbarer Block.** Nach jeder Phase Smoke-Test
  (`docs/SMOKE_TEST.md`) + gezielter Funktionstest.
- **Datenmodelle rückwärtskompatibel halten:** neue Felder mit Default; `from_dict`
  liest Alt-Shows weiter (Muster wie `matrix_speed` ↔ alt `speed`).
- **Gruppen-SSOT ist die DB-Tabelle `FixtureGroup`** – Patcher, Programmer und Live
  View schreiben/lesen dieselbe Tabelle. Keine zweite Gruppen-Quelle einführen.
- **Matrix-Parameter als Daten, nicht als Code** – damit später VC-Slider/Encoder
  sie steuern können (wie `matrix_speed`/`intensity` heute schon).
- **Coding-Delegation:** schwere/umfangreiche Schritte an Sonnet, mechanische an
  Haiku; Architektur/Reviews im Hauptthread (Opus).

---

## 1. Analyse (Phase 1) – Ist-Zustand

### 1.1 Projektstruktur & relevante Dateien

Echter Root verschachtelt: `…/lightos-main/lightos-main/`, PySide6-Code unter `src/`.

| Teil | Thema | Kerndateien |
|------|-------|-------------|
| 1+2 | Matrix-System & Algorithmen | `src/core/engine/rgb_matrix.py` (Engine, 312), `src/ui/views/rgb_matrix_view.py` (View, 448) |
| 3 | Patcher-Gruppen | `src/ui/views/fixture_group_view.py` (412), `src/ui/views/patch_view.py` |
| 4+5 | 3D-Viz / Live View | `src/ui/visualizer/visualizer_window.py` (1368, ablösen), `src/ui/views/live_view.py` (607, ausbauen) |
| 6+7 | Gruppen in Live View | `live_view.py` + `FixtureGroup`-Modell |
| 8 | Zusammenspiel | `programmer_view.py` (Gruppen-Konsum), `app_state.py`, `show_file.py` |
| 9 | Navigation | `src/ui/main_window.py` (Section-Bar + `_SubTabs`) |

### 1.2 Datenmodelle (geprüft)

- **`FixtureGroup`** (`core/database/models.py`): `id, name, cols, rows, positions_json`.
  `positions_json` = `{"<col>,<row>": fid}`. **Reihenfolge** wird row-major abgeleitet
  (`programmer_view._group_fids`: sortiert nach `(row, col)`) → relevant für
  Chase/Matrix. Es gibt **keine** separate Order-Liste; Order = Rasterplatzierung.
- **`PatchedFixture`**: `fid, label, universe, address, channel_count, fixture_type, …`.
- **Kanal-Attribut-Vokabular** (für Style-Kanalmasken, aus `fixture_db.py`/`qxf_import.py`):
  - Intensität: `intensity`, `dimmer`, `master`  (`_DIM_INTENSITY_ATTRS`)
  - RGB: `color_r`, `color_g`, `color_b`
  - Weiß/Amber/UV: `color_w`, `color_a`, `color_uv`
  - Shutter/Strobe: `shutter` (Strobe wird auf `shutter` gemappt)
  - Position/Beam: `pan`, `tilt`, `zoom`, `focus`, `color_wheel`
- **Matrix = echte Funktion**: `RgbMatrixInstance(Function, FunctionType.RGBMatrix)`.
  Felder: `algorithm, color1/2/3, matrix_speed, direction, drive_intensity,
  fixture_grid, cols, rows`. `to_dict/from_dict` persistiert über `functions`-Block.
- **Live-View-Positionen** liegen heute in `AppState.visualizer_positions`
  (3D-x/y/z), **werden in der Show gespeichert** (`show_file.py:170/347`). Die Live
  View liest daraus bzw. macht Auto-Layout – **keine eigene 2D-Persistenz**.

### 1.3 Matrix-System – Ist

- View hat: Name, **Algorithmus**, Spalten, Reihen, **Geschwindigkeit**,
  **Checkbox „Helligkeit/Dimmer mitsteuern"** (`drive_intensity`), **Farben C1–C3**,
  Fixture-Grid (aus Auswahl / Auto).
- Engine `write()` schreibt **nur** `color_r/g/b` und (optional) Intensität/Dimmer auf
  voll. → Style-Erweiterung = **Kanalmaske** umstellen, Grundgerüst passt bereits.
- `matrix_speed` ist bereits ein eigener Parameter (getrennt vom `Function.speed`-
  Master, der als VC-Multiplikator dient) → Speed-auf-Slider ist schon machbar.

### 1.4 Radar-Algorithmus – Ursachenanalyse (Teil 2)

Code: `rgb_matrix.py:245–257` + Phasen-Akkumulator `:138/:163`.

**Befund – warum es stockt/springt:**
1. **Phase an Rastergröße gekoppelt:** `self._step = (… ) % max(cols, rows, 1)`.
   Radar nutzt `beam = (step*0.1) % 1.0`. Bei z. B. `cols=8` läuft `step∈[0,8)` →
   `beam∈[0,0.8)`, erreicht **nie** `[0.8,1.0)`; beim Wrap `8→0` springt `beam` von
   ~0.79 **rückwärts** auf 0 → sichtbarer „Hüpfer", und die Naht **360°→0°** wird nie
   sauber überstrichen. → **Hauptursache der Hänger.**
2. **Zwei Quellen treiben dieselbe Phase:** `tick()` (Vorschau-QTimer 50 ms) **und**
   `write()` (FunctionManager-dt) erhöhen beide `self._step`. Sind Vorschau + Funktion
   gleichzeitig aktiv, wird die Phase doppelt/ungleichmäßig fortgeschrieben → Jitter,
   framerate-abhängiges Tempo.
3. **Degeneriert auf 1×N:** typische Gruppe ist `rows=1` (`_assign_from_selection`).
   Dann `cy=0.5`, alle Pixel `row=0` → `atan2` nur in einer Halbebene → keine echte
   Rotation über den Strip.
4. **Harter Abfall ohne Wrap-Glättung:** `brightness=max(0,1-diff*8)` – kein
   einstellbarer Strahl-Breiten-/Fade-Parameter, kein Schweif.

**Fix-Richtung:**
- Kontinuierliche, **unbeschränkte Zeitphase** (in Umdrehungen/rad), **eine** Quelle
  treibt (Engine), Vorschau liest nur. Wrap **nur** in der Winkelmathematik (mod 2π),
  damit 360→0 nahtlos ist.
- Kürzeste Winkeldistanz mit Wrap: `d = abs(((α−β+π) mod 2π) − π)` → keine Naht.
- Phasen-Modulo **vom Raster entkoppeln**: separater `_phase` (Sekunden·Speed); Chase
  interpretiert `int(phase)%cols`, Radar `phase·U/s`.
- Neue Parameter: `beam_width`, `fade_tail/fade_time`, `direction` (cw/ccw), `invert`,
  `center`. Alles `dt`-basiert → framerate-unabhängig.

### 1.5 Patcher-Gruppen – Ist

`fixture_group_view.py`: links (fix 260 px) Gruppen-Combo, +Neu/Löschen/Speichern,
**Gruppen-Dimmer** (Slider), **Rastergröße** (Cols/Rows-Spin), **flache** Fixture-Liste
(Drag), Reload. Rechts: Raster-Widget (`FixtureGridWidget`).

**Lücken vs. Anforderung:**
- Drag startet **nur aus der Liste** (`FixtureListWithDrag`). Im Raster: nur Drop +
  Rechtsklick-Entfernen, **kein Drag-innerhalb** → „kann nicht verschoben/umsortiert
  werden" (Teil 3). → Drag-from-cell ergänzen.
- **Kein Highlight** der Gruppenmitglieder in der linken Liste.
- Liste ist **flach** → soll Universe-Ordner (auf-/zuklappbar) werden.
- **Gruppen-Dimmer** (`dim_box`, `set_group_dimmer`) → entfernen.
- **Rastergröße** → in rechtes, ein-/ausklappbares + verschiebbares Panel.

### 1.6 Live View + 3D-Visualizer – Ist

- `live_view.py`: `StageCanvas` zeichnet alle gepatchten Fixtures top-down; Positionen
  **in-memory** (`_positions`), geseedet aus `visualizer_positions` oder Auto-Layout.
  Vorhanden: Shift-Klick-Mehrfachauswahl, Einzel-Drag. **Fehlt alles** aus Teil 5–7:
  2D-Persistenz, linke Liste, Drag-aus-Liste, Snap-Grid, rechtes Editor-Panel,
  Minimap, Gruppe-aus-Auswahl, Gruppen-Reiter/Highlight/Detail.
- `visualizer_window.py` (1368, Three.js/QWebEngine): über Menü „Visualizer" geöffnet
  (`main_window:338–341, 1003–1034`); hält Positionen in `visualizer_positions`.
  **Abhängigkeit:** Live View seedet daraus → vor dem Abschalten Positions-Storage
  in die Live View verlagern.

### 1.7 Navigation (Teil 9)

`main_window._build_section_programmer`: Section-Button **„Programmer"** → `_SubTabs`
mit Tab **„Programmer"** (+ „Snapshots"). → Doppelte Benennung „Programmer › Programmer".
Vorschläge siehe §4 (nur Vorschlag, kein blinder Umbau).

---

## 2. Technische Soll-Konzepte

### 2.1 Matrix-Style = Kanalmaske + Wert-Generator
- Neues Feld `style: MatrixStyle` (`RGB|RGBW|DIMMER|SHUTTER`, erweiterbar via Enum).
- Engine `_generate()` liefert je Pixel **entweder** RGB-Tupel (RGB/RGBW) **oder**
  Skalar 0–255 (Dimmer/Shutter). `write()` mappt **nur** die zum Style gehörenden
  Attribute; **alle anderen Kanäle bleiben unangetastet** → Styles/Effekte
  überlagern sich, ohne sich zu überschreiben.
  - RGB → `color_r/g/b`
  - RGBW → `color_r/g/b` (+ `color_w` **nur wenn vorhanden**; sonst sauber nur RGB).
    Weiß-Anteil als Parameter (z. B. `white_amount` oder min(r,g,b)-Extraktion).
  - Dimmer → `intensity|dimmer|master`; Vorschau weiß; Min/Max-Helligkeit.
  - Shutter → `shutter`; Wert/Bereich (+ optional Strobe-Range).
- **Checkbox „Helligkeit" entfällt**; Helligkeit kommt aus Dimmer-Style bzw.
  `base_levels` (bestehendes Schichtenmodell). → Verhaltensänderung, siehe §5.

### 2.2 Parameter-Modell der Algorithmen
- `params: dict` pro Matrix (JSON-persistiert), je Algorithmus eigene Keys:
  `direction, invert, fade, fade_time, runner_count, runner_width, gap, tail,
  beam_width, center, frequency, intensity_min, intensity_max …`.
- View baut die Zusatzfelder **dynamisch je Algorithmus** (QStackedWidget/Form).
- Alle Werte gespeichert (`to_dict`) und damit später VC-bindbar.

### 2.3 Gruppen-Reihenfolge
- Bleibt row-major aus `positions_json`. Drag-Reorder (Patcher) und „Gruppe aus
  Auswahl" (Live View) schreiben dieselbe Struktur. Für 1×N-Gruppen aus Live-View-
  Auswahl: Reihenfolge = Auswahl-/Klick-Reihenfolge.

### 2.4 Live-View-Positionen
- Neuer 2D-Store `AppState.live_view_positions: {fid:(x,y)}`, in Show persistiert.
- Migration: beim Laden aus `visualizer_positions` übernehmen, wenn 2D leer.
- Snap-Grid, Weltgröße, Rasterweite ebenfalls in der Show/`ui_prefs.json` ablegen.

---

## 3. Roadmap (Phasen 2–8)

> Reihenfolge folgt deinem Vorschlag mit **einer Sicherheits-Anpassung**: Der finale
> Abbau des 3D-Visualizers (Teil 4) erfolgt **erst nach** P6/P7, weil die Live View
> heute noch aus `visualizer_positions` seedet. In P5 nur **entkoppeln**, nicht löschen.

### Phase 2 – Patcher-Gruppen aufräumen ✅ ERLEDIGT (2026-06-02) *(niedriges Risiko, guter Start)*
> Umgesetzt in `fixture_group_view.py`: Gruppen-Dimmer entfernt; Rastergröße in
> schwebendes `_FloatingGridPanel` (klappbar/verschiebbar); Universe-Baum
> (`FixtureTreeWithDrag`, klappbar); Highlight der Gruppenmitglieder; Drag im Raster
> (Move/Swap via `positions_changed`-Signal). Verifiziert: 4 group/fixture-Tests grün,
> Offscreen-Konstruktion + Move/Swap-Logik grün. Teil 9: innerer Tab „Programmer" →
> „Attribute" umbenannt (`main_window.py`).

**Datei:** `fixture_group_view.py` (+ ggf. neues Panel-Widget)
1. Gruppen-Dimmer entfernen (`dim_box`, `_on_group_dimmer`); `set_group_dimmer`
   im State bleibt vorerst (von anderen genutzt? prüfen).
2. Rastergröße in rechtes, ein-/ausklappbares + verschiebbares Panel
   (`QDockWidget`-artig bzw. floatendes Collapsible) → links Platz schaffen.
3. Linke Liste → `QTreeWidget` mit **Universe-Ordnern** (auf-/zuklappbar).
4. **Highlight** der Mitglieder der aktuell gewählten Gruppe in der Liste.
5. **Drag-innerhalb-Raster** (Zelle→Zelle) im `FixtureGridWidget` (Move + Swap),
   Reihenfolge bleibt erhalten/aktualisiert.
**Test:** Gruppe anlegen, Fixtures platzieren, im Raster umsortieren, Universe-Ordner
auf/zu, Highlight stimmt, Speichern/Laden, Programmer-Reihenfolge korrekt.

### Phase 3 – Matrix-Styles ✅ ERLEDIGT (2026-06-02)
> `MatrixStyle`-Enum (RGB/RGBW/Dimmer/Shutter) + style-abhängige Kanalmaske in `write()`
> (verifiziert: RGB→nur color_r/g/b, RGBW→+color_w, Dimmer→nur intensity, Shutter→nur
> shutter; Fremdkanäle unangetastet → überlagerbar). `preview_pixels()` (Dimmer/Shutter
> weiß). Style-Dropdown + style-spezifische UI (Weiß-Anteil/Min-Max), Helligkeits-Checkbox
> entfernt. „RGB Matrix"→„Matrix" (Kategorie-Label). R1: Alt-Shows → style=RGB,
> drive_intensity=True (bleiben hell); neue Matrizen drive_intensity=False (reine Farbe).
> Verifiziert: 16 Tests grün + unabhängiger Kanalmasken-Test.
**Dateien:** `rgb_matrix.py`, `rgb_matrix_view.py`
1. „RGB Matrix" → „Matrix" umbenennen (Tab/Labels; Klassen-/Enum-Namen können bleiben).
2. `MatrixStyle`-Enum + Feld + `to_dict/from_dict` (Default `RGB`).
3. Style-Dropdown unter Algorithmus.
4. `write()`/`_generate()` auf style-abhängige Kanalmaske umstellen (RGB/RGBW/
   Dimmer/Shutter), RGBW-Weiß-Erkennung pro Fixture.
5. Style-spezifische Settings (QStackedWidget) unter Geschwindigkeit;
   **Helligkeits-Checkbox entfernen**.
**Test:** je Style nur passende Kanäle ändern (DMX-Monitor!), RGBW mit/ohne Weiß,
Dimmer-Vorschau weiß, zwei Styles gleichzeitig ohne Überschreiben, Alt-Show lädt.

### Phase 4 – Algorithmen + Radar-Fix ✅ ERLEDIGT (2026-06-02)
> **Radar-Fix:** Phasen-Akkumulator vom Raster-Modulo entkoppelt (unbeschränkt, in
> `tick()`+`write()`); `_render(phase)` als reine Funktion; Radar neu mit wrap-sicherer
> kürzester Winkeldistanz `((ang-beam+π) mod 2π)-π` → KEIN Sprung an 360→0
> (gemessen: max. Helligkeits-Delta 4/255 über volle Rotation, Naht 2/255), framerate-/
> rastergrößen-unabhängig. **Parameter:** `params`-Dict (persistiert); `direction` jetzt
> wirksam; `invert` (Chase+Radar); `beam_width`/`fade` (Radar); `runner_count`/
> `runner_width` (Chase H/V). Dynamische Param-UI je Algorithmus. Mini-Preview-Pfad
> (`tick()`+`_generate()`) intakt. Verifiziert: 16 Tests + unabhängiger Stetigkeits-/
> Parameter-Test grün. *(Offen für später: neue Algorithmen „Wave"/„Pulse".)*
**Datei:** `rgb_matrix.py` (+ View für Parameterfelder)
1. Phasen-Akkumulator vom Raster-Modulo entkoppeln, **eine** Treiberquelle.
2. **Radar** neu: kontinuierliche Zeitphase, Wrap-sichere Winkeldistanz, Parameter
   (Drehrichtung, Strahlbreite, Fade-Schweif/-Zeit, Invert, Mittelpunkt).
3. Parameter-Modell `params` für Chase/Wave/Pulse (Richtung, Läuferanzahl/-breite,
   Abstand, Fade, Frequenz, Min/Max-Intensität, Invert).
4. Dynamische Parameter-UI je Algorithmus.
**Test:** Radar läuft dauerhaft flüssig (versch. Matrixgrößen, lange Laufzeit, keine
Hänger an 360→0); Parameter wirken & speichern; Speed über Function-Master skaliert.

### Phase 5 – 3D-Visualizer entkoppeln ✅ ERLEDIGT (2026-06-02) *(nicht löschen)*
> Neuer 2D-Store `AppState.live_view_positions` ({fid:(x,y)}), persistiert in der Show
> (`show_file.py` save/load als `"live_view"`). Live View lädt daraus, migriert aus
> `visualizer_positions` (3D x,z) falls leer, Auto-Layout-Fallback; Drag schreibt zurück;
> Neu-Laden bei SHOW_LOADED/REFRESH_ALL. 3D-Viz bleibt im Menü, ist aber entkoppelt.
> Verifiziert: Migration + Save/Load-Round-Trip + 9 Tests grün.

1. `live_view_positions` (2D) einführen + Show-Persistenz + Migration aus
   `visualizer_positions`.
2. Live View nutzt nur noch den 2D-Store. 3D-Viz-Menü bleibt, wird aber nicht mehr
   weiterentwickelt; Live View ist führend.
**Test:** Positionen laden/speichern unabhängig vom 3D-Fenster.

### Phase 6 – Live View zur Arbeitsfläche ✅ KERN ERLEDIGT (6a, 2026-06-02)
> **6a:** 3-Spalten-Layout (Geräteliste links | scrollbarer Welt-Canvas Mitte | Editor
> rechts). `LiveFixtureList` (Drag, mime `application/x-fid`). Canvas mit fester Welt-
> größe in `QScrollArea`, `place_fixture()` (snap + persist), Drop aus Liste, Intra-Drag
> snappt. Editor: Weltbreite/-höhe, Rastergröße, Snap an/aus, Raster zeigen — persistiert
> in `ui_prefs.json` (Key `live_view`). Verifiziert: Snap (137→150), Weltgröße,
> Prefs-Persistenz, **volle Suite 169 grün**, Phase-5-Persistenz intakt. Platzhalter
> für Phase-7-Reiter/Detail vorbereitet.
> **6b:** ✅ ERLEDIGT — Zoom (`set_zoom`/`_to_world`, painter.scale, geklemmt [0.25,4.0])
> + Zoom-Regler im Editor; **Minimap/Navigator** unten rechts (Welt + Fixture-Punkte +
> Viewport-Rechteck, Klick/Ziehen navigiert). Alle Maus-/Drop-Handler über `_to_world`
> zoom-fähig. Verifiziert: Zoom-Geometrie, Koordinaten-Kohärenz, Minimap, 169 Tests.
**Datei:** `live_view.py`
1. **Linke Fixture-Liste** (alle gepatchten Geräte).
2. **Drag-aus-Liste** in den Canvas → Position setzen + persistieren.
3. **Snap-on-Grid** (ein/aus, Rasterweite).
4. **Rechtes Editor-Panel**: Weltgröße, Rasterweite, Snap, Zoom/Ansicht.
5. **Minimap/Navigator** unten rechts (sichtbarer Ausschnitt, optional klick/zieh).
**Test:** Drag platziert + speichert, Snap rastet, Weltgröße/Zoom wirken, Minimap navigiert.

### Phase 7 – Gruppen in der Live View ✅ KERN ERLEDIGT (7a, 2026-06-02)
> **7a:** Linke Reiter „Fixtures" / „Gruppen" (`_left_tabs`). „Gruppe aus Auswahl…" →
> `create_group_from_selection()` schreibt `FixtureGroup` (1×N in Auswahl-Reihenfolge) →
> `emit(PATCH_CHANGED)` → erscheint automatisch im Programmer **und** Patcher (gleiche
> Tabelle, gleiche row-major-Reihenfolge — verifiziert mit der Programmer-Query). Gruppen-
> Highlight im Canvas (cyan Ring, `set_highlight`). Rechtes Detail-Panel (Name, Mitglieder
> in Reihenfolge, Fixture entfernen, Gruppe löschen). Verifiziert: Erstellen+Reihenfolge,
> Auswahl→Detail/Highlight, Mitglied entfernen (Reihenfolge erhalten+renummeriert),
> **volle Suite 169 grün**; Phase 5/6a intakt.
> **7b:** ✅ ERLEDIGT — Rubber-Band-Auswahlrahmen (Ziehen auf leerer Fläche, `_select_in_rect`,
> Shift = additiv) + mehrere ausgewählte Fixtures gemeinsam verschieben (Multi-Drag, snappt +
> persistiert alle). `selection_changed`-Signal → `state.selected_fids` synchronisiert.
> Verifiziert: `_fixture_at`/`_select_in_rect`, Signal-Sync, 169 Tests.
**Dateien:** `live_view.py`, schreibt `FixtureGroup`
1. **Mehrfachauswahl** erweitern: Klick/Shift-Klick **+ Auswahlrahmen (Rubber-Band)**,
   mehrere gemeinsam verschieben.
2. **„Gruppe aus Auswahl"** → Name abfragen → `FixtureGroup` schreiben (Reihenfolge =
   Auswahl) → erscheint **automatisch im Programmer** (gleiche Tabelle).
3. **Linke Reiter** „Fixtures" / „Gruppen".
4. **Gruppen-Highlight** im Canvas bei gewählter Gruppe.
5. **Rechtes Gruppen-Detail**: Name, Mitglieder, Reihenfolge, entfernen/bearbeiten.
**Test:** Auswahlrahmen, Gruppe erstellen→im Programmer sichtbar→gemeinsam
programmierbar, Highlight, Detail-Bearbeitung, Speichern/Laden.

### Phase 8 – Tests & Feinschliff ✅ LAUFEND/ERLEDIGT (automatisiert)
> Je Phase: unabhängiger Offscreen-Smoke-Test + volle `pytest`-Suite (durchgehend
> **169 grün**, keine Regressionen). Abschluss-End-to-End-Test der Live View (Zoom +
> Rubber-Band + Snap/Persistenz + Gruppe→Programmer-Reihenfolge + Minimap) grün.
> **Noch offen = manuelle App-Tests durch den Nutzer** (GUI-Interaktion, Alt-Show-
> Kompatibilität R1, DMX-Output je Style) — siehe Testpunkte unten.

Gesamter Smoke-Test + die in P2–P7 genannten gezielten Tests; Alt-Show-Kompatibilität;
Navigation (Teil 9) je nach Entscheidung in §4.

---

## 4. Offene Entscheidungen (vor/ während Umsetzung)

1. **Teil 9 – Navigation:** ✅ **ENTSCHIEDEN (A):** innerer Tab „Programmer" → „Attribute"
   umbenannt. (Erledigt in Phase 2.)
2. **RGB-Style & Helligkeit:** ✅ **ENTSCHIEDEN:** RGB-Style = **reine Farbe** (Helligkeit
   via Dimmer-Style/`base_levels`). Fließt in Phase 3 ein; Verhaltensänderung ggü. alter
   „Dimmer mitsteuern"-Checkbox → siehe R1 in §5 (Alt-Show-Test).

---

## 5. Risiken & Rückfallebenen

- **R1 – Alt-Shows wirken dunkel:** Wegfall von `drive_intensity` (RGB-only) kann
  Matrizen ohne Dimmer-Ebene dunkel zeigen. *Mitigation:* `drive_intensity` im
  Datenmodell behalten (nur UI weg), Default je Style sinnvoll setzen; Migration/
  `base_levels` prüfen; im Test gezielt mit Alt-Show gegenchecken.
- **R2 – Live-View/3D-Positions-Kopplung:** Reihenfolge P5 vor P6/P7 strikt einhalten,
  sonst Positionsverlust.
- **R3 – Drag&Drop uneinheitlich:** ein gemeinsames Mime-Format (`application/x-fid`,
  bereits genutzt) und ein Helper für alle Drag-Quellen.
- **R4 – Thread-Disziplin (sACN/Output):** Matrix-Änderungen nur im Render/Write-Pfad;
  keine UI-Objekte aus Engine-Threads anfassen (vgl. `PROJECT_AUDIT.md`).
- **Rückfall:** „Old versions"-Backups + Git (lokaler Stand = Source of Truth).

---

# Initiative 2 – New-Show-Reset, echtes Matrix-Layout, Algorithmen, Programmer-/Live-View-Politur

> Eingespielt: 2026-06-02 (Nutzer-Prompt). **Status: ✅ CODE/TESTS ABGESCHLOSSEN (2026-06-03)
> — I2.1–I2.9 alle umgesetzt + verifiziert (Suite 169 → 232 grün). Offen nur noch manuelle
> GUI-/Hardware-Tests durch den Nutzer (Alt-Show-Kompatibilität, DMX-Output je Style, GUI-Interaktion).**
> Leitprinzip wie Initiative 1: erst Analyse, dann je Punkt ein in sich testbarer
> Block; bestehende Funktionen + Speicherformate erhalten, rückwärtskompatibel
> migrieren. **Hinweis:** Dies ist eine Desktop-App (PySide6/Python), KEIN Web-Frontend
> → „LocalStorage/IndexedDB" aus dem Prompt = bei uns `data/*.json`, `ui_prefs.json`,
> SQLite-DB (`FixtureGroup`) und der globale `AppState`.

## I2.0 Erst-Analyse (vor Umsetzung auszufüllen)
Pro Punkt vor dem Coden klären und hier eintragen:
- betroffene Dateien/Komponenten,
- verwendete Stores/States/Datenmodelle,
- wo der „alte Gruppen bleiben"-Fehler entsteht (Verdacht: `New Show` leert die
  SQLite-`FixtureGroup`-Tabelle und `AppState`-Showfelder nicht vollständig —
  Gruppen-SSOT ist die DB, nicht die `.lshow`),
- wie Matrix-Layout heute gespeichert wird (`RgbMatrixInstance.fixture_grid/cols/rows`,
  Reihenfolge row-major aus `FixtureGroup.positions_json`),
- Aufbau der Matrix-Algorithmen (`src/core/engine/rgb_matrix.py`, `_generate`/`_render`,
  `params`-Dict seit Phase 4),
- wo Auto-Save/Sofort-Anwenden passiert (Matrix-View schreibt direkt auf die Instance?),
- wo die Effekt-Vorschau im Programmer eingebunden ist (`EffectMiniPreview`,
  5-Zonen-Layout, vgl. Memory „Programmer 5-Zonen-Layout").

## I2.1 — New Show = wirklich leer (Punkt 1) ✅ ERLEDIGT (2026-06-03)
> Lücke gefunden+geschlossen: `reset_show()` leerte alles außer der SQLite-Tabelle
> `FixtureGroup` (Gruppen-SSOT) → alte Gruppen blieben nach „Neue Show". Fix: in
> `reset_show()` (`show_file.py`) nach dem Patch-Leeren `delete(FixtureGroup)` via
> `state._session()`. Audit: kein weiterer show-bezogener State übersehen (MIDI-Mappings/
> App-Settings bewusst app-global). Regressionstest `test_reset_show_clears_fixture_groups`
> (legt Gruppe an → reset → Tabelle leer). Verifiziert: **170 passed**.
**Ziel/Akzeptanz (AK1, AK2):** „New Show" setzt den kompletten **show­bezogenen** State
zurück; keine alten Gruppen/Matrizen/Fixtures/Programmer-Zustände bleiben — weder
sichtbar noch intern. Globale App-Settings bleiben unangetastet (klare Trennung).
**Verdachtsherd:** `FixtureGroup`-DB-Tabelle + evtl. `data/*.json`-Live-Puffer
(`snapshots.json`, `midi_mappings.json`) und `AppState`-Felder werden bei New Show
nicht geleert. **To-Do:** zentrale `reset_show_state()`-Funktion, die DB-Gruppen,
Patch, Matrizen/Functions, Programmer, `live_view_positions`, `visualizer_positions`,
`base_levels` leert; Audit „welche States sind show- vs. app-global".

## I2.2 — Matrix übernimmt echtes Grid-Layout inkl. Lücken (Punkte 2 + Teile von 5) ✅ ERLEDIGT (2026-06-03)
> **2a (Engine):** `fixture_grid` darf jetzt `None`-Lücken enthalten (dichte Liste der
> Länge cols*rows mit None-Löchern statt Dict — semantisch = `{(col,row):fid}`, aber
> minimal-invasiv + nativ JSON-fähig). `write()`/`tick()` überspringen `None` (kein DMX/
> Vorschau für Lücken); `_render` liefert weiter das volle cols*rows-Raster (Lücken räumlich
> vorhanden, nicht angesteuert). Alte dichte Listen laden unverändert (Migration).
> **2b (View/State):** neue reine Hilfsfunktion `grid_from_positions(positions,cols,rows)`;
> `AppState.selected_group_id` (+get/set); Programmer setzt die aktive Gruppen-ID beim
> Gruppen-Klick (vor dem Publish), löscht sie bei Einzel-/Add-Auswahl; Matrix
> `_assign_from_selection` übernimmt bei aktiver Gruppe das **exakte 2D-Grid (group.cols×rows
> inkl. Lücken)**, sonst Fallback 1×N. Grid-Label zählt Fixtures + Lücken.
> Verifiziert: **187 passed** (+17 Tests: Lücken-Engine, Persistenz/Migration, grid_from_positions, State).
**Ziel/Akzeptanz (AK3, AK4, AK5):** Matrix übernimmt die **exakten Grid-Koordinaten**
(row/col) aus der Programmer-Anordnung, **inkl. absichtlicher Lücken** — kein
Auto-Komprimieren/Sortieren/Auffüllen. Leere Felder bleiben leer und werden räumlich
berücksichtigt, aber nicht angesteuert. **Heute:** `positions_json` kennt Lücken
bereits, aber die Engine leitet Reihenfolge row-major als dichte Liste ab → Lücken
gehen verloren. **To-Do:** Engine + `fixture_grid` auf echtes `{(col,row):fid}`-Raster
mit `None`-Löchern umstellen; alle Algorithmen auf Koordinaten statt Index.
(Migration: alte dichte Grids weiter lesbar.)

## I2.3 — Algorithmen: Start aus der Mitte / mehrdirektional (Punkt 3) ✅ ERLEDIGT (2026-06-03)
> Gemeinsam mit I2.5 umgesetzt. Mittelpunkt = geometrisch `((cols-1)/2,(rows-1)/2)` aus dem
> echten Matrix-Raum (lücken-/formrobust). `CENTER_OUT` (Mitte→außen, auf 1×N beidseitig) +
> `OUTER_IN` (außen→Mitte) decken die mehrdirektionalen/Mitte-Anforderungen ab; alle neuen
> Algorithmen sind koordinatenbasiert + robust für 1×1/1×N/N×1/2D. Verifiziert: **197 passed**.
**Ziel/Akzeptanz (AK6):** Chase/Lauflicht zusätzlich: Mitte→außen, außen→Mitte, Mitte
in beide Richtungen, formabhängig in alle Richtungen. Mittelpunkt aus dem **echten
Matrix-Raum** (nicht aus der Fixture-Liste), robust bei ungleichmäßigen/nicht-
rechteckigen/lückenhaften Layouts. Baut auf I2.2 (Koordinaten) auf.

## I2.4 — Nur relevante Parameter je Algorithmus (Punkt 4) ✅ ERLEDIGT (2026-06-03)
> Metadaten-Modul `src/core/engine/rgb_matrix_meta.py` (`ParamSpec`/`AlgoMeta`/`ALGO_META`):
> je Algorithmus Beschreibung, Richtungs-Flag und relevante Parameter (Key/Label/Typ/Default/
> Min-Max-Step/Tooltip) — Keys exakt die, die `_render` liest. View baut die Param-Felder jetzt
> **dynamisch** (`_rebuild_param_fields`/`_load_params_into_widgets`), `_param_change` schreibt
> generisch über `_param_widgets`; hartcodierte `_apply_algo_param_visibility` + feste Widgets
> entfernt (0 Altreferenzen). Logik/Metadaten von UI getrennt. Die neuen Algorithmen (I2.5)
> zeigen so ihre Param-Felder (Ringbreite/Windungen/Armbreite …). Verifiziert: **216 passed** (+19).
**Ziel/Akzeptanz (AK7):** UI zeigt dynamisch nur die für den gewählten Algorithmus
sinnvollen Controls. **Struktur:** Algorithmus-**Metadaten** (Name, Beschreibung,
Pflicht-/Optional-Parameter, Defaults, UI-Control-Typen, unterstützte Richtungen,
Flags für Farben/Speed/Fade/Phase/Mittelpunkt). View baut Felder aus den Metadaten
(erweitert das in Phase 4 begonnene dynamische Param-UI). Logik/Layout/UI getrennt halten.

## I2.5 — ≥6 neue Matrix-Algorithmen (Punkt 5) ✅ ERLEDIGT (2026-06-03)
> 6 neue, deterministische, koordinatenbasierte Algorithmen in `rgb_matrix.py` (`_render`):
> `Center→Außen`, `Außen→Center`, `Bounce H`, `Bounce V`, `Diagonal Welle`, `Spirale`.
> Alle edge-robust (kein /0, kein IndexError; 1×1/1×N/N×1/2D getestet), nutzen `params`-Defaults
> (runner_width/turns/beam_width) → laufen ohne UI-Felder; erscheinen automatisch im Dropdown.
> Param-UI-Feinschliff folgt in I2.4. Verifiziert: **197 passed** (+10 Algorithmus-Tests).
**Ziel/Akzeptanz (AK8):** Mindestens: (1) außen→innen, (2) innen→außen, (3) Bounce H,
(4) Bounce V, (5) Diagonal Chase, (6) Spiral Chase. Optional weitere: Ring-Welle,
Random Sparkle, Checkerboard, Wave H/V, Radar Sweep (Radar existiert schon),
Fill/Unfill, Snake, Center Pulse, Corners→Center, Center→Corners. Alle auf echten
Koordinaten (I2.2), Lücken räumlich berücksichtigt aber nicht angesteuert, je
Algorithmus Param-Metadaten (I2.4), robust für klein/groß/quadratisch/lückenhaft.

## I2.6 — Matrix-Edit erst auf „Speichern" anwenden (Punkt 6) ✅ ERLEDIGT (2026-06-03)
> Entscheidung: gilt für BEIDE Matrix-Ansichten; Geräte-/Grid-Auswahl + Name bleiben live.
> Draft-Modell: `_saved` = echte Instanz (FunctionManager), `_current` = Arbeitskopie (Editor
> bearbeitet nur den Draft, Vorschau zeigt Draft). Engine: `from_dict`→`apply_dict`-Refactor
> (DRY), `_save_edit` kopiert Draft→Saved in-place (id/Laufzustand bleiben). Buttons „💾 Speichern"/
> „↩ Zurücksetzen" + Dirty-Label („● ungespeicherte Änderungen"), `_update_dirty` vergleicht
> `to_dict()`. Param-Edits → nur Draft (deferred=dirty); Grid-Follow + Name → in beide (live, kein
> dirty). Vorschau treibt Phase selbst (Draft läuft nicht im Manager). Verifiziert: **223 passed** (+7).
**Ziel/Akzeptanz (AK9, AK10):** Änderungen laufen zuerst nur im **Bearbeitungszustand**;
aktive Matrix ändert sich erst bei bewusstem **Speichern**-Klick. Plus „Abbrechen/
Zurücksetzen" und **Dirty-State**-Erkennung. Preview/Edit ↔ gespeicherte aktive Matrix
klar trennen. **Zusatz-Audit:** weitere Programmer-Stellen mit Sofort-Save/Auto-Apply
suchen und benennen/verbessern.

## I2.7 — Effekt-Vorschau rechts im Programmer entfernen (Punkt 7) ✅ ERLEDIGT (2026-06-03)
> `EffectMiniPreview` aus dem 5-Zonen-Layout entfernt: rechte Spalte = jetzt nur noch Snap-Browser
> (`right = self._make_snap_panel()`), kein leeres Panel. Init `_effect_preview`, die `itemClicked`-
> Verbindung und die Methode `_on_effect_item` entfernt (0 Restreferenzen). Widget-Datei
> `effect_mini_preview.py` bleibt erhalten (mögliche Wiederverwendung im Effekt-Assistenten) und
> ist weiter eigenständig getestet. Zonen-Test auf Snap-Panel umgestellt. Verifiziert: **223 passed**.
**Ziel/Akzeptanz (AK11, AK15):** `EffectMiniPreview` aus dem Programmer-Layout
entfernen, frei werdenden Platz sinnvoll nutzen (keine leeren Panels/Abstände).
Übrig bleibende State-Logik/Props/Komponente prüfen; falls Komponente woanders
gebraucht → nur Verwendung im Programmer lösen. (Achtung: kollidiert mit Memory
„Programmer 5-Zonen-Layout" → Zonen-Layout anpassen.)

## I2.8 — Live View: Fixture-Liste als Universe-Baum (Punkt 8) ✅ ERLEDIGT (2026-06-03)
> Flache `LiveFixtureList` (entfernt) → `FixtureTreeWithDrag` aus Phase 2 wiederverwendet:
> einklappbare Universe-Ordner (analog Patcher), Kinder draggbar via `application/x-fid`
> (Canvas-Drop unverändert). Neues Suchfeld (`_fixture_search`) + `_apply_fixture_filter`
> (blendet nicht-passende Kinder + leere Ordner aus, case-insensitiv). `_refresh_fixture_list`
> baut den Baum. Test `tests/test_live_view_tree.py` ruft die ECHTEN LiveView-Methoden via
> Stub (kein QWidget-Init). Verifiziert: **229 passed** (+6).
**Ziel/Akzeptanz (AK12):** Linke `LiveFixtureList` analog zum Patcher-„Gruppen"-Tab
als `QTreeWidget` mit einklappbaren **Universe-Ordnern** (Wiederverwendung von
`FixtureTreeWithDrag` aus Phase 2). Auswahl-Highlight, optional Suchfilter, einheitliches
Styling, Auf/Zu-Zustand sinnvoll merken.

## I2.9 — Live View: Skalierungs-Regler verbessern (Punkt 9) ✅ ERLEDIGT (2026-06-03)
> Dünner Editor-Zoom-Slider → schwebendes **Zoom-Overlay** unten rechts über der Minimap
> (`_zoom_overlay` am Viewport, `_position_zoom_overlay` aus `_position_minimap` gerufen):
> klare „Zoom"-Beschriftung, breiter Slider (8px Groove, 22px Handle), große −/+ Buttons
> (30×30, touch-tauglich), %-Anzeige. `_zoom_slider`/`_lbl_zoom`/`_on_zoom_changed` + Persistenz
> unverändert (nur verlagert). Verifiziert: **232 passed** (+3 Zoom-Tests).
**Ziel/Akzeptanz (AK13):** Zoom-Slider größer/sichtbarer, unten in die Nähe der Minimap
(Phase 6b), klar beschriftet („Zoom"/„Skalierung"), desktop- und touch-tauglich.

## I2.10 — Querschnitt / Regression
**Akzeptanz (AK14, AK15):** Alt-Shows weiter ladbar (Migrationen rückwärtskompatibel),
keine leeren UI-Flächen/kaputten Layouts. Nach jedem Block: State/UI/Save/Load prüfen,
volle `pytest`-Suite grün, Offscreen-Smoke je Punkt.

**Empfohlene Reihenfolge:** I2.1 (Reset, isoliert + hohe Wirkung) → I2.2 (Koordinaten-
Fundament) → I2.3/I2.5 (Algorithmen darauf) → I2.4 (Param-Metadaten/UI) → I2.6 (Dirty/
Save) → I2.7/I2.8/I2.9 (UI-Politur).
