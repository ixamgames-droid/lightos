# Show-Autobau & Live-Aufnahme — Arbeitsanweisung

> Kanonische Anleitung, wie LightOS-Shows **voll automatisch gebaut, live vorgeführt und
> als Einzelanleitungen aufgenommen** werden. Geschrieben 2026-06-15 während des Baus der
> `Testshow_2026`. Verwandt: [`SHOW_FILE_FORMAT.md`](SHOW_FILE_FORMAT.md),
> [`MATRIX_LIVE.md`](MATRIX_LIVE.md), [`EFFEKTE.md`](EFFEKTE.md),
> [`ANLEITUNGEN_WALKTHROUGH_PLAN.md`](ANLEITUNGEN_WALKTHROUGH_PLAN.md),
> [`SHOW_2026_BUGLOG.md`](SHOW_2026_BUGLOG.md).

## 0. Mandat (David, 2026-06-15)
- **Voller Zugang, voll automatisch.** Künftige Shows komplett selbst bauen — Patch, Gruppen,
  Farb-/Dimmer-Matrizen, EFX, Szenen/Cues, **Virtual Console + APC-Mapping**, Musik-Sync.
- **Fehler SOFORT selbst fixen**, ohne auf Freigabe zu warten. Build → bei Crash/Fehler Ursache
  finden → fixen → weiter. Nicht für jeden Schritt rückfragen; durchbauen.
- **Live bauen UND dabei aufnehmen**: wie man anpasst, wie man die VC patcht/mappt, wie man
  Effekte programmiert, Musik-Sync — alles als Screenshots/GIFs → Einzelanleitungen.

## 1. Davids reales Rig (Test-Aufbau, alles auf dem Boden)
```
            [ MH Links ]   PAR1 PAR2 PAR3 PAR4 PAR5 PAR6 PAR7 PAR8   [ MH Rechts ]
                                  Spider1        Spider2            (vorne, am Boden)
```
- **8 PAR** (ZQ01424, 8ch RGBW) — nebeneinander in einer Reihe (die „paar Lichter").
- **2 Moving Heads** (ZQ02001, 11ch) — **je einer links und rechts** der PAR-Reihe.
- **2 Spider** (SPIDER14, 14ch, RGBW + Pan/Tilt) — **vor** der PAR-Reihe, am Boden.
- Aktuell alles am Boden (Testaufbau). → Für 3D-/Live-View-Positionen, EFX-Offsets und
  räumliche Looks danach ausrichten: PAR-Reihe Mitte, MH außen L/R, Spider vorne tief.
- **Adressierung** (Universe 1, sequenziell): PAR 1–8 @ DMX **1–64**; MH Links @ **65**,
  MH Rechts @ **76** (je 11ch); Spider 1 @ **87**, Spider 2 @ **101** (je 14ch) — 114 Kanäle.
  ⚠ Bei „MH/Spider reagieren nicht": **zuerst physische Geräteadresse/-Modus gegen diese Werte prüfen.**

## 2. Methode: Generator-Skript statt UI-Massenklick
Schnelle UI-Massenautomatik crasht die App nativ. Daher: Show **strukturell per Generator** bauen,
dann in der App nur **laden + vorführen/filmen**.
- Vorlage: [`tools/build_testshow_2026.py`](../tools/build_testshow_2026.py)
  (API-Vorbild: `tools/build_musik_show_2026.py`, `tools/build_apc_test_show.py`).
- Headless ausführen:
  `venv\Scripts\python.exe tools\build_testshow_2026.py`  (setzt `QT_QPA_PLATFORM=offscreen`).
- Das Skript endet mit **Selbst-Asserts** (Patch=12, Bänke, Farb-/Dimmer-Matrizen, Auto-Show,
  Beat-Sync, Playlist, keine VC-Overlaps). Schlägt ein Assert fehl → Bug, sofort fixen.

### Engine-API-Spickzettel
- `reset_show()`, `get_state()`, `get_function_manager()`
- `profile_id(short)` über `FixtureProfile.short_name` (`ZQ01424`, `ZQ02001`, `SPIDER14`)
- `state.add_fixture(PatchedFixture(...), undoable=False)`; danach `state._rebuild_render_plan()`
- `get_channels_for_patched(fx)` → Kanäle. **Spider:** `color_r/g/b/w` existieren **doppelt**
  (Bank 1+2). Szenen mit Multimap-Helfer (ALLE Kanalnummern eines Attributs setzen), sonst leuchtet
  nur eine Bank. Die **RGB-Matrix** schreibt pro Kanal → bedient beide Bänke automatisch korrekt.
- Gruppen: `with state._session()` → `FixtureGroup(name, cols, rows, positions_json)`
- `fm.new_scene/new_chaser/new_rgb_matrix/new_efx`
- **Matrix:** `m.colors = ColorSequence([...])`; `m.style = MatrixStyle.RGB|DIMMER`;
  `m.drive_intensity=False`; `m.intensity_min/max`; `m.fixture_grid`; `m.cols/rows`; `m.params`;
  `m.matrix_speed`; `m.priority`.
  - **Farb-Matrix** (Farbebene): `RGB`, `drive_intensity=False` → schreibt nur Farbkanäle.
  - **Dimmer-Matrix** (drüberlegen): `DIMMER` → schreibt nur Dimmer → disjunkt → sauberes Layering.
  - Schemata: grün/weiß=`WAVE`, blau/weiß & grün/blau=`GRADIENT` (beide Farben fließend; **kein** CHASE,
    der wirkt als Lauflicht statt „beide Farben").
- **EFX:** `e.fixtures=[EfxFixture(fid=…)]`; `e.algorithm=EfxAlgorithm.*`;
  `e.phase_mode` `sync|fan|offset`; `spread/counter_rotate/mirror`; `open_beam=True`
  (Intensität 255 + Shutter offen); `bit16`; `speed_hz`; `x_offset/y_offset`; `width/height`.
- **Cues:** `state.new_cue_stack(name)`; `.mode`; `.beat_sync`; `.beats_per_cue`; `.add_cue(Cue(...))`.
- **Musik:** `state.playlist` (Ordner `C:/Users/David/Desktop/Musik/BP Party`, Bounce ~150 BPM);
  `state.music_autoshow = {enabled, function_ids, bank, slots}` → `MusicShowDirector` startet die
  Funktionen beim ▶ im Musik-Player. Beat-Sync: `CueStack.beat_sync` + `audio_triggered` Chaser.
- **VC:** `VCButton/VCColor/VCSlider/VCCueList/VCSongInfo/…`; `state._vc_layout = {"widgets":[…]}`;
  `save_show(path)` / `load_show(path)`.

## 3. APC mini mk2 — Konventionen
- Pads **Note 0–63** (Note 0 unten-links), Fader **CC 48–56**, Track-Tasten mk2 **100–107**,
  Scene-Tasten **112–119**.
- **Bank N ↔ Playback-Seite N**. Globale Widgets `bank=-1` (auf allen Seiten sichtbar).
- **LED-Feedback** muss EINMAL in der VC-Leiste **„APC LEDs"** aktiviert werden
  (siehe `SHOW_2026_BUGLOG.md` HINWEIS-02 — Kandidat: bei erkanntem APC default an).
- Beispiel-Bankaufteilung (Testshow): 1 Farbschemata · 2 Dimmer-Effekte · 3 EFX & Mover ·
  4 Räumliche Looks · 5 RGBW-Programmer · 6 Live-Chase; global: Clear/StopAll/Blackout/Tap/Media + F6/F7/F9.

## 4. Live-Steuerung & Aufnahme (PowerShell-Win32 + GDI)
`computer-use` sieht das Qt-Fenster nicht → alles per GDI/Win32.
- **Treiber:** [`docs/_walkthrough/lo.ps1`](_walkthrough/lo.ps1)
  `fg|rect|untop|move|click|dclick|rclick|drag|type|key|scroll|shot Path [W]|crop Path X Y W H [W]`.
  - **Vor JEDER Aufnahme `lo.ps1 fg`** (setzt TOPMOST; sonst zieht das Chat-/Claude-Fenster den
    Vordergrund und Crops zeigen das falsche Fenster). Am Ende `lo.ps1 untop`.
- **GIFs:** [`docs/tutorial_matrix/_capseries.ps1`](tutorial_matrix/_capseries.ps1) (N Frames im
  Intervall) + [`_makegif.py`](tutorial_matrix/_makegif.py) (PIL). Frames vor dem Bauen kurz prüfen.
- **App-Start:** `venv\Scripts\pythonw.exe main.py --touch` (WorkingDir = inneres Projekt;
  APC beim Start angeschlossen → Auto-Connect). Start-Dialog „Auto-Save Wiederherstellung" → **Nein**.
- **Show laden:** `Ctrl+O` (StandardKey.Open) → im Datei-Dialog den **Pfad per Clipboard `^v` +
  `{ENTER}`** (raw `SendKeys`, da der Dialog nicht „LightOS" heißt → `lo.ps1 type` würde das
  Hauptfenster fokussieren). ⚠ **NICHT in-place neu laden** (BUG-01 Crash) — Generator-Änderung →
  **App neu starten** → frisch laden (aus funktions-freiem Zustand ist Laden sicher).
- **Bank/Seite wechseln (zuverlässig):** `lo.ps1 key "^{PGDN}"` / `"^{PGUP}"` — die VC-Bank folgt
  der Playback-Seite. (Direkter Tab-Klick auf „Bank N" ist unzuverlässig.)
- **Sektion wechseln:** Sektionsleiste ~y≈128 phys.: Live View · Patchen · Programmer ·
  Virtual Console · Simple Desk · Playback · Eingabe/Ausgabe.
- **VC-Pad-Koordinatenmodell** (Fenster maximiert, Bildschirm **2880×1920**):
  `pad(row,col) ≈ ( 98 + 133·col , 437 + 132·row )` Bildschirm-Pixel; col 0–7, row 0–4.
  **Bei anderer Auflösung neu kalibrieren** über einen Vollauflösungs-Crop eines bekannten Pads.
- **Sichtbarkeit der Wirkung:** 2D-Live-View zeigt **Farben/Helligkeit** sauber (GDI-fähig), aber
  **keine Pan/Tilt-Bewegung** (Mover nur als Richtungsstrich) und Mover-Intensität nur eingeschränkt.
  Bewegung über **EFX-Editor-Vorschau** oder echte Mover filmen. 3D-Visualizer ist per GDI **schwarz**.
- **Diagnose statt Raten:** Verhalten headless reproduzieren (Show laden, `fm.start`, `fm.tick`,
  DMX der Kanäle auslesen) trennt Engine- von GUI-/Output-/Adress-Problemen sauber.

## 5. Einzelanleitungen (Aufnahme-Output)
- Struktur: `docs/anleitung_<thema>/{img,web,gif,seq}` + Master-`.md`.
  Vorbild/Format: [`docs/tutorial_matrix/TUTORIAL_LICHTSHOW.md`](tutorial_matrix/TUTORIAL_LICHTSHOW.md).
- Themen: `patch_gruppen`, `farbmatrix`, `dimmermatrix`, `efx`, `apc_mapping`, `musik_sync`.
- Jede Anleitung steht allein, hat 1 Lernziel, nennt die zu ladende `.lshow`, zeigt Schritt-Screenshots
  + GIFs der laufenden Effekte und die APC-Belegung.

## 6. Fehler-Handling (autonom)
- Bug-Log: [`docs/SHOW_2026_BUGLOG.md`](SHOW_2026_BUGLOG.md).
- **Blockierende** Fehler sofort fixen; nicht-blockierende loggen und nach Fertigstellung der
  Reihe nach beheben + betroffene Anleitungen aktualisieren. Nach Engine-Änderungen `pytest`.

## 7. Stand der Testshow 2026 (Pause-Punkt 2026-06-15)
- `shows/Testshow_2026.lshow` + `tools/build_testshow_2026.py` **fertig** (32 Funktionen,
  130 VC-Widgets, 6 Bänke, Auto-Show an Musik gekoppelt, 2 Beat-Sync-Cuelisten).
- **Live verifiziert (David):** 3 Farbschemata (grün/weiß, blau/weiß, grün/blau), Dimmer-Layering,
  APC Bank-Wechsel + LED-Feedback + Master/Dimmer-Fader.
- **Gefilmt:** Layout Bank 1/2/3, Live-Stills grün/weiß · blau/weiß · grün/blau,
  Layering-GIF (`docs/anleitung_dimmermatrix/gif/layering_gruenweiss_atmen.gif`).
- **Noch offen:** EFX live an echten Movern, räumliche Looks, Szenen/Cues/Beat-Sync live,
  Musik-Play-Test, restliche Anleitungen + Screenshots, Bugfixes.
- **Offene Befunde:**
  - **BUG-01 🔴** Reload-Crash (`load_show → add_fixture → programmer_view._refresh_effects_list`).
  - **MH-EFX live** 🟠 (wiederkehrend): Engine/Render erzeugen korrekte Bewegung+Beam (headless
    verifiziert: pan/tilt ändern sich, intensity=255, shutter offen), aber an Davids echten MH bewegte
    sich nichts. **Beim Fortsetzen zuerst:** Live-DMX-Ausgabe (Simple Desk) der Kanäle 65–86 prüfen
    UND physische MH-Geräteadresse/-Modus (soll 65/76, 11-Kanal) abgleichen.
  - **HINWEIS-02** APC-LEDs manuell aktivieren.
