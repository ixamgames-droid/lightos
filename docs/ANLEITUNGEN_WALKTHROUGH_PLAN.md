# Anleitungen → echte Walkthroughs — Übersicht & Plan

> **Ziel:** Die vorhandenen Text-Anleitungen werden durch **verifizierte Walkthroughs** ersetzt — der Agent
> übernimmt den PC, klickt jeden Schritt **live in LightOS** durch (wie bereits beim Matrix-Tutorial gemacht),
> erfasst frische Screenshots und protokolliert dabei gefundene **UI-/Anzeige-/Bedienfehler**.
> Erstellt: 2026-06-15. Quelle der Klassifizierung: Multi-Agent-Analyse aller 58 Projekt-Markdown-Dateien.

---

## Stand 2026-06-16 — Bebilderte Themen-Anleitungen + zentrale Docs synchronisiert

**Neue, eigenständige bebilderte Schritt-für-Schritt-Anleitungen** (Screenshots/GIFs) liegen jetzt unter
`docs/anleitung_*/` — Einstieg über die Übersicht **[ANLEITUNGEN.md](ANLEITUNGEN.md)**:
`anleitung_patch_gruppen` (Patch + Gruppen) · `anleitung_vc` (Virtuelle Konsole) ·
`anleitung_apc_mapping` (APC mini) · `anleitung_efx` (EFX/Moving-Head-Bewegung) ·
`anleitung_farbmatrix` · `anleitung_farbchase` (Blau-Weiß) · `anleitung_dimmermatrix` (relative Geschwindigkeit) ·
`anleitung_musik_sync` (Auto-Show/BPM) — plus das komplette `tutorial_matrix/TUTORIAL_LICHTSHOW.md`.

**Zentrale Docs auf die aktuelle 8-Sektionen-UI gebracht** (`ANLEITUNG.md`, `EFFEKTE.md`, `README.md`):
„Geräte & Funktionen" → **„Patchen"**; **EFX / RGB Matrix / Funktionen / Paletten in den Programmer**
verschoben (Tabs in der „Attribute"-Ansicht: Intensity · Color · Position · Gobo · Weitere · Helper · EFX ·
Matrix · Paletten); **„Snap"-Button entfernt** (→ Snapshots / Strg+Shift+S); neue **Sektion „BPM"**; neue Tabs
**Musik** (E/A) und **Kurven** (Playback); Simple-Desk-Tab „Submaster/Kanal-Gruppen"; Strg+1…**8**. Dazu wurden
passende **Programm-Screenshots eingebaut** und Querverweise auf die bebilderten Anleitungen gesetzt.

→ Damit sind die **Doku-Befunde B-02, B-03, B-04, B-08, B-09, B-10, B-11** (Abschnitt 5) in der Doku
**nachgezogen** (✅ 2026-06-16). Die Code-Fixes B-01 und B-07 waren bereits erledigt.

---

## 1. Methodik (so läuft jeder Walkthrough)

1. **Start:** LightOS via `LightOS.lnk` (venv 3.14, `--touch`); Qt-Fenster wird **per Win32/PowerShell** gesteuert
   und **per GDI** abfotografiert (computer-use sieht das Qt-Fenster nicht — siehe Memory `reference_lightos_ui_automation`).
2. **Vorbereiten:** Falls die Anleitung eine `.lshow` braucht → laden (alle nötigen Shows sind vorhanden, siehe Tabelle).
   Anleitungen ohne Show (z. B. ANLEITUNG, EFFEKTE) starten auf leerer Bühne / `Leer.lshow` und bauen alles selbst auf.
3. **Durchklicken:** Jeden dokumentierten Schritt real ausführen; nach jedem sichtbaren Ergebnis ein Screenshot.
4. **Beobachten der Lichtwirkung:** Ohne echte Hardware dient der **3D-Visualizer / Live View** als „Ausgabe".
5. **Assets:** Screenshots nach `docs/<thema>/img/`, GIFs nach `docs/<thema>/gif/` — Konvention wie in `tutorial_matrix/`.
6. **Bug-Log:** Jede Abweichung (falsches Label, kein Feedback, Absturz, falsche Anzeige) unten in Abschnitt 5 eintragen.

### Hardware-Hinweis (wichtig)
Viele Anleitungen sind auf die **Akai APC mini** und teils auf **DMX-Ausgabe / Moving-Head-Hardware** bezogen.
Diese liegt nicht vor. **Gute Nachricht:** Fast alle APC-Aktionen sind 1:1 über die **On-Screen Virtual Console (VC)**
nachklickbar (Pads/Fader sind dort gespiegelt). Hardware-zwingende Schritte (Art-Net-Node, Enttec-COM-Port,
echter Audio-BPM, physischer Controller, VirtualDJ/OS2L) werden **ausgeklammert oder als „nur mit Hardware" markiert**.

---

## 2. Walkthrough-Kandidaten (priorisiert) — **15 Dateien**

Legende Status: ⬜ offen · 🟡 in Arbeit · ✅ verifiziert neu aufgenommen

### Priorität HOCH (Kern-Bedienung, höchster Bug-Fund-Wert)

| # | Datei | Titel | UI-Sektionen | Show (✓ vorhanden) | ~Schritte | HW nötig? | Status |
|---|-------|-------|--------------|--------------------|-----------|-----------|--------|
| 1 | [ANLEITUNG.md](ANLEITUNG.md) | Komplette Anleitung | Patch · Programmer · Live View · Simple Desk · Playback · VC · MIDI | — (leer/Leer.lshow) | 22 | nein | ⬜ |
| 2 | [WORKFLOWS.md](WORKFLOWS.md) | Praxis-Workflows | Patch · Programmer · Playback · VC · MIDI | — | 40 | teils (Art-Net/Enttec/Audio ausklammern) | ⬜ |
| 3 | [tutorial_matrix/TUTORIAL_LICHTSHOW.md](tutorial_matrix/TUTORIAL_LICHTSHOW.md) | Matrix · Chase · MH-EFX · VC (Vorbild!) | Patch · Live View · Programmer · VC | Tutorial_Matrix.lshow | 28 | nein | ⬜ |
| 4 | [EFFEKTE.md](EFFEKTE.md) | Effekte bauen & Tempo steuern | Programmer · VC · MIDI | — | 30 | nein | ⬜ |
| 5 | [APC_SCHRITT_FUER_SCHRITT.md](APC_SCHRITT_FUER_SCHRITT.md) | APC mini + 4× RGBW (Einsteiger) | Playback · VC · Programmer · MIDI | APC_Test_Komplett.lshow | 55 | APC → via VC | ⬜ |
| 6 | [APC_TEST_SHOW.md](APC_TEST_SHOW.md) | APC-Test-Show Hands-on | VC · MIDI · Playback · Patch | APC_Test_Komplett.lshow | 35 | APC → via VC | ⬜ |
| 7 | [FEATURE_TEST.md](FEATURE_TEST.md) | Feature-Test-Show (Neuerungen 06-12) | Programmer · VC · Playback · MIDI | Feature_Test.lshow | 24 | APC → via VC | ⬜ |

> Hinweis: #5 und #6 nutzen **dieselbe Show** (`APC_Test_Komplett.lshow`) → am besten in einer Sitzung zusammen.

### Priorität MITTEL (Demo-/Show-Bedienung, teils hardware-/show-gebunden)

| # | Datei | Titel | UI-Sektionen | Show (✓ vorhanden) | ~Schritte | HW nötig? | Status |
|---|-------|-------|--------------|--------------------|-----------|-----------|--------|
| 8 | [FEATURE_SHOWCASE.md](FEATURE_SHOWCASE.md) | „Alles drin"-Test-Show (6 Rezepte) | Playback · VC · MIDI · Live View | Feature_Showcase.lshow | 14 | APC/Mover → via VC/Viz | ⬜ |
| 9 | [KEYBOARD_MAPPING.md](KEYBOARD_MAPPING.md) | Tastatur-Tasten auf VC-Buttons | VC · MIDI | — | 5 | nein | ⬜ |
| 10 | [DEMO_SHOW_NOTES.md](DEMO_SHOW_NOTES.md) | Praxis-Demo — 6 manuelle Tests | Patch · Programmer · Live View · VC · MIDI | Praxis_Demo.lshow | 6 | teils | ⬜ |
| 11 | [MASTER_DEMO.md](MASTER_DEMO.md) | Master-Demo „alles, was die Show kann" | VC · Programmer · MIDI | Master_Demo.lshow | 18 | APC → via VC | ⬜ |
| 12 | [LIVE_EDIT.md](LIVE_EDIT.md) | Effekte live einmappen & bearbeiten | VC · MIDI · Programmer | Live_Edit.lshow | 5 | APC → via VC | ⬜ |
| 13 | [MOVING_HEAD_SHOW.md](MOVING_HEAD_SHOW.md) | Moving-Head-Demo | Patch · Programmer · VC · MIDI | MovingHead_Demo.lshow | 7 | Mover → via Viz | ⬜ |
| 14 | [PARTY_DEMO.md](PARTY_DEMO.md) | Party-Demo (BPM + Musik) | VC · Playback · MIDI · Programmer | Party_Demo_2026.lshow | 8 | APC/VirtualDJ → In-App-Player/VC | ⬜ |
| 15 | [MUSIK_SHOW_2026.md](MUSIK_SHOW_2026.md) | Auto-Lichtshow zur Musik (BPM-sync) | VC · Playback · Programmer · MIDI | Musik_Show_2026.lshow | 8 | VirtualDJ optional (Nominal-BPM-Fallback) | ⬜ |

---

## 3. Empfohlene Reihenfolge

1. **ANLEITUNG.md** — der Master-Durchlauf: berührt alle 7 Sektionen, braucht keine Hardware/Show → findet die meisten Bugs.
2. **WORKFLOWS.md** — konkrete Aufgaben-Rezepte (überlappt mit #1, deckt Cue-Stack/Executor ab).
3. **tutorial_matrix/TUTORIAL_LICHTSHOW.md** — Vorbild-Format gegenprüfen + Screenshots neu aufnehmen.
4. **EFFEKTE.md** — Effekt-Editoren im Detail (EFX/Matrix/Chaser, Tempo/BPM).
5. **APC_SCHRITT_FUER_SCHRITT.md + APC_TEST_SHOW.md** — zusammen (gleiche Show, via On-Screen-VC).
6. **FEATURE_TEST.md** → **FEATURE_SHOWCASE.md** → **KEYBOARD_MAPPING.md**.
7. Restliche Demo-Docs (10–15) als Bedien-Demos mit Visualizer-Beobachtung.

---

## 4. Nicht-Kandidaten (43 Dateien) — bleiben Referenz/Planung

### Teilweise nutzbar (niedrige Prio, nur einzelne Abschnitte UI-tauglich)
| Datei | Warum nur teilweise |
|-------|--------------------|
| [NEUE_DEMO.md](NEUE_DEMO.md) | Show-Beschreibung; nur Abschnitt „Playback-Workflow (speichern & abspielen)" wäre ein echter Walkthrough. |
| [KOMPLETT_DEMO.md](KOMPLETT_DEMO.md) | Generator-gebaut; nur als Bedien-Demo (8 APC-Seiten/Autoplay) denkbar, hardware-lastig. |
| [PROFI_MODUS.md](PROFI_MODUS.md) | Fertige APC-Belegung, keine Bau-Schritte; APC-Hardware nötig. |
| [MATRIX_LIVE.md](MATRIX_LIVE.md) | Engine-/Dispatcher-Referenz; Bedienteil besser in EFFEKTE.md verschmelzen. |
| [APC_SEITEN_UEBERSICHT.md](APC_SEITEN_UEBERSICHT.md) | Belegungs-Referenz; verweist selbst auf APC_SCHRITT_FUER_SCHRITT.md. |
| [FIXTURE_SOURCES.md](FIXTURE_SOURCES.md) | Quellen/Lizenz; nur QXF-Import-Teil wäre ein kleiner Patch-Walkthrough. |
| [README.md](../README.md) | Nur der 9-Schritt-Quick-Start; gehört als Verweis auf die echten Anleitungen. |

### Reine Referenz / Spezifikation (kein Walkthrough)
FEATURES.md · UI_DESIGN.md · ARTNET.md · DMX_PROTOCOL.md · OUTPUT_MERGE_CONTRACT.md · SHOW_FILE_FORMAT.md ·
FIXTURE_LIBRARY.md · MOVING_HEADS.md · ARCHITECTURE.md (Root)

### Planung / Audit / Roadmap (kein Walkthrough)
FEATURE_MAP.md · PROJECT_AUDIT.md · OPEN_POINTS_OVERVIEW.md · MASTERPLAN_2026-06-08.md · UMBAU_ROADMAP.md ·
UMBAU_2026-06_PLAN.md · PROGRAMMER_REBUILD.md · MOVING_HEAD_ROADMAP.md · MUSIK_PLAYER_IDEEN.md ·
FUTURE_FIXTURE_GENERATOR.md · APC_PROBIER.md · ROADMAP.md (Root)

### Dev-Meta / Changelog / Debug (kein Walkthrough)
SMOKE_TEST.md · UMBAU_2026-06_CHANGES.md · UPDATE_2026-06-11.md · CRASH_LOG_ANALYSIS_2026-06-14.md ·
INSTALL.md · CONTRIBUTING.md · WORKFLOW.md (Root) · DEVELOPMENT_NOTES.md (Root) · CHANGELOG.md (Root) ·
MIDI_CRASH_DEBUG_NOTES.md (Root)

### Archiv
_archiv/NEXT_STEPS.md · _archiv/TODO.md · _archiv/VISUALIZER_TODO.md · _archiv/SPIDER_MULTIHEAD_TODO.md · _archiv/README.md

---

## 5. Bug-/Befund-Log (wird während der Walkthroughs gefüllt)

> Format: `[Datum] [Anleitung] [Sektion] — Beobachtung (erwartet vs. tatsächlich) — Schweregrad`

### ANLEITUNG.md — Befunde 2026-06-15

**B-01 (HOCH, Crash/Freeze) — ✅ GEFIXT & VERIFIZIERT 2026-06-15** (Unit-Repro · volle Suite 1127 grün · live: 4 SlimPAR sauber gepatcht).
Fix in `app_state.py` (`next_fid()` DB-bewusst, `add_fixture()` fid-Guard, neues `clear_patch()`) + `show_file.py` (`_replace_patch_from_data` nutzt `clear_patch()`).
**Patchen schlägt mit DB-Integritätsfehler fehl und friert die UI ein.**
- **Repro:** Patchen → „+ Gerät hinzufügen" → Gerät wählen (Chauvet SlimPAR 64) → „Hinzufügen".
- **Erwartet:** Gerät erscheint in der Patch-Tabelle mit fid `[001]`.
- **Tatsächlich:** Nichts wird gepatcht; ein modaler Dialog „LightOS — Unerwarteter Fehler" erscheint,
  wird aber oft **nicht gezeichnet** (im Screenshot unsichtbar, on-screen bei 432,315) und lässt das
  **Hauptfenster `ENABLED=False`** zurück → App wirkt eingefroren, alle Klicks werden ignoriert.
  Schließen nur per Tastatur (Enter), nicht per Fenster-WM_CLOSE.
- **crash.log:** `sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: patched_fixtures.fid`
  bei `INSERT INTO patched_fixtures (fid, ...) VALUES (1, 'SLIM64 1', ...)`.
- **Ursache:** `data/current_show.db` enthält **7 verwaiste Zeilen** (PAR 1–7, fid 1–7), aber der
  In-Memory-`_patch_cache` ist leer (UI: „0 Geräte"). `AppState.next_fid()`
  ([app_state.py:485](../src/core/app_state.py)) berechnet die nächste fid aus dem **leeren Cache** → 1 →
  `add_fixture()` ([app_state.py:176](../src/core/app_state.py)) INSERTet fid 1 in die DB, die fid 1 schon hat → UNIQUE-Verletzung.
  Cache und persistente Tabelle sind desynchron; `_replace_patch_from_data()`
  ([show_file.py:89](../src/core/show/show_file.py)) entfernt beim Laden nur Fixtures, **die im Cache stehen** → verwaiste
  DB-Zeilen werden bei leerem Cache nie bereinigt.
- **Fix-Vorschläge:** (a) `next_fid()` aus `MAX(fid)` der DB statt aus dem Cache ableiten;
  (b) `add_fixture` bei Kollision robust auf nächste freie fid ausweichen; (c) `_replace_patch_from_data`
  die DB-Tabelle hart leeren (`DELETE FROM patched_fixtures`) statt cache-basiert; (d) Exception-Hook:
  Fehlerdialog erzwungen zeichnen + Hauptfenster nie disabled hinterlassen.

**B-02 (MITTEL, Doku): Sektion 2 heißt in der UI „Patchen", nicht „Geräte & Funktionen"** (wie in §1-Tabelle).

**B-03 (MITTEL, Doku): „Patchen" hat nur 2 Unter-Tabs (Patch · Fixture-Gruppen),** nicht 5
(„Patch · EFX · RGB Matrix · Funktionen · Gruppen" laut §1). EFX/RGB Matrix/Funktionen sind in die
Programmer-Sektion verschoben; „Gruppen" heißt „Fixture-Gruppen".

**B-04 (NIEDRIG, Doku): Top-Leiste — „Snap"-Button existiert nicht mehr** (per Code-Kommentar UIC-01
bewusst aus der Section-Bar entfernt; → Menü „Programmer → Snapshot aufnehmen" / Strg+Shift+S).
Anleitung nennt ihn in §1 **und** §4.4. Stattdessen gibt es einen undokumentierten **„✖ Clear ▾"**-Button.

**§3 verifiziert (✓ funktioniert):** Fixture-Gruppen → „+ Neu" (Namens-Dialog) → Rastergröße (Spalten/Zeilen) →
Fixtures per Drag&Drop aufs Raster (Reihenfolge sichtbar) → „Speichern" („Gruppe 'Front Wash' gespeichert").
- **B-07 (NIEDRIG, UI-Bug) — ✅ GEFIXT & VERIFIZIERT 2026-06-15: Die 6 Gruppen-Buttons waren unleserlich**
  (sahen aus wie kryptische Glyphen √ n e зс c ר). **Ursache:** 6 Text-Buttons in EINER HBox-Reihe im fix
  260px-schmalen, touch-grossen Panel → je ~43px → Labels zu Mittel-Fragmenten beschnitten.
  **Fix:** `fixture_group_view.py` — Buttons in `QGridLayout` 2 Spalten × 3 Reihen (Import ergänzt). Live: alle
  Labels lesbar (+ Neu · Umbenennen · Bearbeiten… · Loeschen · Speichern · Ordner…); Gruppentests grün.
- B-08 (Doku): Doc §3 sagt Tab „Gruppen", real „Fixture-Gruppen"; Button „Loeschen" (ohne ö).

**§4 verifiziert (✓ funktioniert):** Programmer → Gruppe „Front Wash" per Einfachklick gewählt (4 Geräte aktiv) →
Color-Tab → Kachel „Rot" → alle 4 Lampen rot (Lampen-Vorschau + Rot-Fader 255, Badge „● Programmer 12"). Toolbar
(Highlight/Lowlight/Clear/Copy/Paste/Undo/Redo/Color/Position/Fan Tool) vorhanden.
- **B-09 (MITTEL, Doku): Programmer-Unter-Tabs heißen „Attribute · Snapshots"**, nicht „Programmer · Paletten ·
  Snapshots" (§1-Tabelle). „Paletten" ist jetzt ein **Attribut-Tab**.
- **B-10 (MITTEL, Doku): Attribut-Tabs sind Intensity · Color · Position · Weitere · Helper · EFX · Matrix ·
  Paletten** — §4.2 nennt nur „Intensity · Color · Position · Gobo · Weitere". (Gobo nur bei Gobo-Geräten = korrekt;
  Helper/EFX/Matrix/Paletten fehlen im Doc.) Rechts zusätzlich **Bibliothek-Panel** + **„Layout: Zonen"** (undokumentiert).
- B-11 (NIEDRIG, Doku): §4.2 „Color Picker einbetten" → Button real „Color Picker (Fenster)". Intensity-Tab zeigt bei
  reinen RGB-Geräten korrekt „Keine Intensity-Kanäle gefunden" (kein Dimmer-Kanal).

---

## 6. Fortschritt

- **2026-06-16:** Themenbezogene bebilderte Anleitungen vorhanden (8 Stück + Matrix-Tutorial, Übersicht
  [ANLEITUNGEN.md](ANLEITUNGEN.md)); zentrale Docs `ANLEITUNG.md` / `EFFEKTE.md` / `README.md` auf die
  aktuelle 8-Sektionen-UI synchronisiert und mit Screenshots bebildert (Doku-Befunde B-02…B-11 nachgezogen).
- Kandidaten gesamt: **15** · verifiziert neu aufgenommen: **0** · in Arbeit: **1** (ANLEITUNG.md)
- **ANLEITUNG.md:** §1 Oberfläche ✓ · §2 Patchen ✓ (nach B-01-Fix) · §3 Gruppen ✓ · §4 Programmer ✓ —
  offen: §5 Funktionen, §6 Playback/Cues, §7 Eingabe/Ausgabe, §8 Speichern, danach Doku-Neufassung.
- Befunde bisher: B-01 (gefixt) + 10 Doku-/UI-Abweichungen (B-02…B-11). Screenshots in `%TEMP%\lo_wt\`
  (Keeper später nach `docs/anleitung/img/`).
- Letzter Stand: 2026-06-15 — Live-Durchlauf §1–§4 fertig, Patch-Fix verifiziert (Suite 1127 grün).
