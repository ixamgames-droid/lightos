# Anleitungen-Audit & Neufassungs-Plan — 2026-06-19

> **Auslöser:** Nach dem **VC-Smart-Build-Umbau** (2026-06-19) und weiteren UI-Änderungen
> wurden **alle 23 Endnutzer-Anleitungen** automatisiert gegen den **aktuellen Quellcode**
> geprüft (3 Ground-Truth-Agenten aus `main_window.py` / `virtualconsole/*` /
> `programmer_view.py`+Editoren, dann je 1 Agent pro Anleitung, der jede UI-Aussage
> gegen Code mit file:line abgeglichen hat).
> **Ergebnis:** 0 komplett obsolet · **6 MAJOR** (Ablauf/Struktur geändert) · **14 MINOR**
> (nur Label-Drift) · **3 OK**.

---

## 1. Verdikt-Übersicht

| Verdikt | Anzahl | Anleitungen |
|---|---|---|
| 🟥 **MAJOR** | 6 | `ANLEITUNGEN.md` · `ANLEITUNG.md` · `EFFEKTE.md` · `anleitung_dimmermatrix` · `anleitung_vc` · `tutorial_matrix/TUTORIAL_LICHTSHOW` |
| 🟨 **MINOR** | 14 | `ANLEITUNGEN_EVENT_DEMO` · `anleitung_patch_gruppen` · `anleitung_farbmatrix` · `anleitung_farbchase` · `anleitung_efx` · `anleitung_apc_mapping` · `anleitung_musik_sync` · `anleitung_speed` · `anleitung_vc_workflow` · `anleitung_vc_elemente` · `anleitung_spider` · `anleitung_speed_bpm` · `anleitung_matrix_effekte` · `anleitung_ablaeufe` |
| 🟩 **OK** | 3 | `anleitung_vc_smartbuild` · `anleitung_moving_heads` · `anleitung_programmer` |

---

## Umsetzungs-Stand (fortlaufend)

- ✅ **Phase 0 — Archiv + Show-Rebuild** — Snapshot unter `Old versions/anleitungen-pre-audit-20260619/`;
  `build_event_demo_2026.py` + `build_hardstyle_vc.py` umlaut-korrigiert (Fächer/Größe/Grün/Weiß/
  Gegenläufig/…) + GO-Tasten entkürzt, beide Shows neu gebaut (Event-Demo-Selbsttest grün, Struktur
  unverändert 70/201; Hardstyle 16/54).
- ✅ **Phase 1 — Texte** — alle 23 Anleitungen korrigiert/neu geschrieben (Runde 1) + unabhängig gegen
  Code verifiziert + Runde 2 mit allen echten Nachbesserungen. Bildverweise auf noch fehlende Screenshots
  sind **bewusste Platzhalter** für Phase 2 (siehe Shot-Liste unten).
- 🔄 **Phase 2 — alle Screenshots frisch** — in Arbeit (interaktiv, App + GDI/`lo.ps1`).
  - ✅ **anleitung_vc komplett (15/15)** — 01/02 (leer/Bearbeiten), 03/04/10/11/12/13 (Bänke 1–3 + Edit),
    05 (aktiver Button), **15/16/17 (Drop-Karte/Galerie/Konflikt-Karte — frisch live aus dem Smart-Build)**,
    18/19 (Bank 4 BEAT-BLINK + Bank 5 MH/Spider). Nur 14_apc_midi_teach = vorhandenes (valides) Bild behalten.
  - ✅ Smart-Build-Dialoge wiederverwendet in: tutorial_matrix/17_drop_karte, vc_workflow/17+18,
    vc_elemente/04+05+06, speed/04_konflikt_karte (alle Dead-Links aufgelöst).
  - ⏳ **Offen:** Event-Demo-Bänke (moving_heads, spider, speed_bpm, matrix_effekte, programmer, ablaeufe),
    tutorial_matrix (web/+img/), Kern-Docs (ANLEITUNG patch/group/color/helper, EFFEKTE chaser),
    Themen (patch_gruppen, farbmatrix, farbchase, dimmermatrix, efx, apc_mapping, musik_sync, speed-rest, farb_fx_vc).
  - **Methode (zum Fortsetzen):** App läuft via venv-`python.exe main.py --touch`; Steuerung/Capture per
    `docs/_walkthrough/lo.ps1` (immer `fg` vor `shot`/`crop`; Klick-Koords NUR aus Voll-Crops mit bekanntem
    Maßstab ableiten — Augenmaß im verkleinerten Vollbild ist ~2× daneben). VC-Bänke: Strg+Bild↓/↑.
    Shows via Strg+O → Pfad eintippen. Rechtsklick-Kontextmenüs sind flakig (Fokus-Aussetzer).

### Neue Screenshots, die Phase 2 erzeugen muss (Platzhalter in den Texten)
`ANLEITUNG.md`: tutorial_matrix/web/programmer_helper.png · `anleitung_dimmermatrix`: img/02_vc_tempo_bus.png ·
`anleitung_vc`: img/15_drop_karte, 16_widget_galerie, 17_konflikt_karte, 18_bank4_beat_blink, 19_bank5_mh_spider ·
`tutorial_matrix`: img/17_drop_karte.png · `anleitung_musik_sync`: img/03_autoshow_fuer_lied.png ·
`anleitung_speed`: img/04_konflikt_karte.png · `anleitung_vc_workflow`: img/17_drop_karte, 18_widget_galerie ·
`anleitung_vc_elemente`: img/04_drop_karte, 05_widget_galerie, 06_konflikt_karte.
Dazu (Nutzer-Wunsch): **alle vorhandenen** Screenshots ebenfalls frisch neu aufnehmen.

---

## 2. Übergreifende Befunde (betreffen mehrere Anleitungen)

1. **VC-Smart-Build-Umbau (2026-06-19)** — der zentrale Bruch. Ein Effekt/Funktion aus der
   Bibliothek auf das leere Canvas ziehen erzeugt **nicht mehr** sofort einen Toggle-Button,
   sondern öffnet die **Drop-Karte „Effekt einrichten"** (Häkchen je Aspekt, TOGGLE
   vorausgewählt) + **grafische Widget-Galerie „Widget wählen"**; Drop auf einen belegten
   Regler zeigt die **Konflikt-Karte „Regler ist schon belegt"** (Ersetzen / Dazu koppeln /
   Neues Widget daneben). Betrifft: `anleitung_vc` (MAJOR), `tutorial_matrix`, `anleitung_speed`,
   `anleitung_vc_workflow`, `anleitung_vc_elemente`, `anleitung_dimmermatrix` (Tempo-Bus-Kopplung).
   → Die **bereits korrekten Screenshots** dazu liegen in `docs/anleitung_vc_smartbuild/`
   (`04_drop_card_simple_crop.png`, `05_drop_card_subforms_crop.png`, `06_widget_gallery_crop.png`,
   `02_conflict_card.png`) und können **wiederverwendet** werden.

2. **`FunctionManagerView` ist nicht (mehr) eingehängt** — in `main_window.py` nur importiert,
   nie instanziiert. Damit existieren die in `ANLEITUNG.md §5` und `EFFEKTE.md §5` beschriebenen
   Buttons (`+ Sequence/+ Collection/+ Show/+ Audio/+ Script/+ Layered Effekt/+ Carousel`,
   „✨ Effekt-Assistent", „🎹 MIDI lernen", „Run", fett-im-Baum) **im erreichbaren UI nicht**.
   Der echte **Programmer → Helper**-Tab hat nur: `Effekt-Assistent…` · `+ Szene` · `+ Chaser`
   · `Programmer → Szene` + Liste mit `Start`/`Stop` (laufend = Pfeil-Präfix). **MIDI-Teach**
   läuft über die **VC** („MIDI Lernen") bzw. **Eingabe/Ausgabe → MIDI**.
   *(Während der Ausführung kurz gegenprüfen, ob FunctionManagerView absichtlich raus ist.)*

3. **8 Sektionen, Strg+1…8** — `ANLEITUNG.md §1`-Fließtext sagt noch „7 Hauptbereiche /
   Strg+1…7" (Tabelle darunter ist korrekt).

4. **Show-Dateien teils mit ASCII-Pad-Labels** (vor dem Umlaut-Sweep gebaut): z. B.
   „Faecher/Groesse/Gegenlaeufig" statt „Fächer/Größe/Gegenläufig" in `Event_Demo_2026.lshow`;
   „GO Aufwaer/GO Drop-Se" (auf 7 Zeichen gekürzt). → **Generatoren neu bauen**, dann erscheinen
   die Pad-Texte korrekt und die Screenshots stimmen. Betrifft `anleitung_moving_heads`,
   `anleitung_spider`, `anleitung_ablaeufe`, `anleitung_programmer`.

5. **Hardstyle_Show.lshow auf 5 Bänke erweitert** (16.06.), aber `ANLEITUNGEN.md` + `anleitung_vc`
   dokumentieren nur 3. Neu: Bank 4 „BEAT-BLINK / Effekt-Farben", Bank 5 „MH-Gobos / Spider /
   Bewegung". → Index korrigieren, VC-Anleitung um Bank 4/5 ergänzen (Screenshots fehlen).

6. **RGB-Matrix-Editor: „Dimmer treiben"-Schalter entfernt** (`drive_intensity` nicht mehr aus
   UI). Farbe/Dimmer-Trennung läuft nur noch über den **Style** (RGB vs. Dimmer). Betrifft
   `tutorial_matrix` (durchgängig falsch erklärt).

7. **Matrix-Algorithmen: 18** (nicht 17). „Comet/Komet" und „Ripple" sind **keine** eigenen
   Algorithmen mehr (→ Chase mit „After Fade %" bzw. Wave radial; nur Legacy-Migrationsnamen).
   UI zeigt deutsche Namen: „Atmen (Puls)/Feuer/Regen/Windrad". Betrifft `EFFEKTE.md`, `anleitung_farbmatrix`.

---

## 3. Markierte Liste je Anleitung (was ist falsch → was tun)

### 🟥 MAJOR

- **`ANLEITUNGEN.md`** (Index Hardstyle-Kit) — „**3 Bänke**" → **5 Bänke** (Z. 18 & 34);
  Schichten-Modell um Beat-Farb-Chase + MH-Farbe/Gobo + Spider ergänzen; Links zu
  `anleitung_moving_heads` + `anleitung_spider` aufnehmen. *Kein Reshoot (reine Link-Seite).*
- **`ANLEITUNG.md`** (8-Sektionen-Komplettanleitung) — §1 „7/Strg+1…7" → **8/Strg+1…8**;
  §5 **neu schreiben** (echter Helper-Tab statt FunctionManagerView; MIDI-Teach via VC/MIDI-Tab);
  §4.2 Strobe-Kacheln „Kein Strobe/Strobe aus" → **„Auf/Zu" + „Strobe langsam/mittel/schnell"**;
  Position-Tab „einbetten"-Toggle → fester Aufklappbereich **„Position-Tool (XY-Pad)"**.
  *Reshoot: Helper-Tab (neu), `m1_color_editor.png` prüfen.*
- **`EFFEKTE.md`** — §5 FunctionManagerView-Buttons entfernen/klarstellen; **Run/Stop → Start/Stop**;
  „MIDI lernen" aus Helper raus (→ VC/MIDI-Tab); „✨ Effekt-Assistent" → **„Effekt-Assistent…"**;
  EFX-Felder „X/Y-Offset" → **„Zentrum Pan/Zentrum Tilt"**; **17 → 18** Algorithmen;
  „fett im Baum" → Pfeil-Präfix in Liste. *Reshoot: `06_chaser_editor.png` (Start/Stop sichtbar).*
- **`anleitung_dimmermatrix`** — **§3 „relative Geschwindigkeit" neu schreiben**: Tempo-Bus /
  „Tempo ×" / Sync gibt es **nicht im Matrix-Editor**, sondern in der **VC (Smart-Drop / SpeedDial /
  BusSelector)** bzw. **BPM-Sektion**. Bus-Optionen sind fix `(frei)/Global/A/B/C/D` (kein freier
  „hardstyle"-Bus; „Global" = Master-BPM). §2: „Schweif/fade" → **„After Fade (%)"**;
  „Dimmer min/max" → **„Dimmer-Bereich (Min/Max)"** in Gruppe „Farben".
  *Reshoot: neue Bilder vom KORREKTEN Bedienort (VC/BPM) — fehlen komplett.*
- **`anleitung_vc`** (VC bauen) — **§2 neu schreiben** auf Smart-Build-Flow (Drop-Karte + Galerie +
  Konflikt-Karte + „↔ Widget ändern"); §1 Werkzeugleisten-Liste an echte Quick-Add-Buttons anpassen
  („⌗ Controller", „🎨 Color-Chase", 15 Buttons). Bank 4/5 ergänzen.
  *Reshoot: `03_funktionen_ziehen` (kritisch), `02`/`13` (Toolbar); Drop-Karte/Galerie/Konflikt
  aus `anleitung_vc_smartbuild/` wiederverwenden.*
- **`tutorial_matrix/TUTORIAL_LICHTSHOW`** — §4 Layering: **„Dimmer treiben"-Schalter raus** → über
  **Style** erklären; §7a VC-Drag: jetzt **Drop-Karte** statt Sofort-Pad; Klein-Labels
  („N Fixtures" statt „Selection:", „＋ Gruppe aus Auswahl", englische EFX-Algonamen).
  *Reshoot: `m1`/`m2` Matrix-Editor, `09`/`10`/`11` VC.*

### 🟨 MINOR (überwiegend Label-Patches, meist ohne Reshoot)

- **`ANLEITUNGEN_EVENT_DEMO`** — Smart-Build-Link (`anleitung_vc_smartbuild`) ergänzen,
  `anleitung_vc_workflow` als „klassisch" kennzeichnen. *Kein Reshoot.*
- **`anleitung_patch_gruppen`** — „Start-Adresse" → **„DMX-Adresse"**; „RasterGröße" →
  **„Rastergröße"**; Universe-Leiste „Belegte DMX-Kanäle — Universe:"; **„Speichern"-Schritt
  ergänzen** (Raster wird nicht auto-persistiert) + „Bearbeiten…"-Alternativweg. *Kein Reshoot.*
- **`anleitung_farbmatrix`** — „Comet/Ripple" nicht mehr als eigene Algos; „Schweif (fade)" →
  **„After Fade (%)"**; deutsche Algonamen. *Kein Reshoot.*
- **`anleitung_farbchase`** — Button **„🎨 Bearbeiten…"**; Sequence-Editor sind Icon-Buttons
  (`＋ ✎ ✕ ⊘ ◀ ▶`); Hinweis: Matrix folgt Auswahl (Spalten/Reihen aus Gruppe). *Kein Reshoot.*
- **`anleitung_efx`** — Pan/Tilt-Hub **0–255** (nicht %); §3 nach echten Bedienelementen gliedern
  (Combo „Verhältnis:" sync/fan/offset vs. Checkboxen „Gegenläufig/Spiegeln" vs. Spins); open_beam
  = **„Dimmer/Shutter mit öffnen"**; Gruppe „Verhältnis der Geräte zueinander". *Kein Reshoot.*
- **`anleitung_apc_mapping`** — **„MIDI Lernen" bindet nur Buttons/Pads**, nicht Fader (Fader → Weg B
  MIDI-Teach/CC); Toolbar-Label „🎚 Pickup". *Kein Reshoot.*
- **`anleitung_musik_sync`** — Auto-Show: globaler EIN/AUS-Schalter **+ Pro-Lied**-Zuweisung
  („Auto-Show für Lied…"), keine globale Funktions-IDs-UI; Quelle **„PC-Audio (Player/Spotify)"**;
  **OS2L (VirtualDJ)** als präzise Taktquelle ergänzen; Navi-Pfad „Eingabe/Ausgabe → Musik (Strg+7)".
  *Optional: Bild „Auto-Show für Lied…".*
- **`anleitung_speed`** — Kontextmenü **„Einstellungen…"** (kein „⚙"); §4 Kopplung: erster Effekt =
  direkte Bindung, weiterer = **Konflikt-Karte** (Ersetzen/Dazu koppeln/Neues Widget). *Reshoot:
  Konflikt-Karte (aus `anleitung_vc_smartbuild/02_conflict_card.png` wiederverwendbar).*
- **`anleitung_vc_workflow`** — Toolbar-Weg bleibt gültig; **MIDI-Lernen-Stolperstein** korrigieren
  (bewaffnet Button, kein Teach-Dialog; nur Buttons; Klick ins Leere bricht ab); kurzen Smart-Build-
  Abschnitt ergänzen. *Optional: `04_bearbeiten_toolbar` prüfen; Smart-Build-Bilder wiederverwenden.*
- **`anleitung_vc_elemente`** — Smart-Build-Weg ergänzen; XY-Pad **3. Modus „Pfad"**; SpeedDial
  **5. Ziel „Effekt ×½/×2 (Multiplier)"**; Rechtsklick „↔ Widget ändern…". *Kein Reshoot.*
- **`anleitung_spider`** — nur Umlaut „Fächer" (Show neu bauen). *Reshoot nur bei sichtbarem ASCII.*
- **`anleitung_speed_bpm`** — §5: **F6/F7/F9 gibt es nicht** (streichen); „Dauer-Leiste unten" →
  **„Alle-Banks-Frame" der VC**; „(¼…×4)" beim Speed-Fader entfernen (stufenlos). *Kein Reshoot.*
- **`anleitung_matrix_effekte`** — „Speed-Fader (F7)" → BPM-Sektion/Top-Bar; „Stop All" →
  **„STOP ALL"**. *Kein Reshoot.*
- **`anleitung_ablaeufe`** — GO-Tasten-Labels sind gekürzt („GO Aufwaer/…"); Mix-Tasten volle Namen.
  *Besser: GO-Captions im Generator entkürzen + Show neu bauen. Kein zwingender Reshoot.*

### 🟩 OK (höchstens Mini-Labels)

- **`anleitung_vc_smartbuild`** — akkurat & aktuell. Optional: „↔ Widget ändern" → „… ändern…".
- **`anleitung_moving_heads`** — akkurat. Nur Screenshots prüfen (echte Umlaute nach Show-Neubau).
- **`anleitung_programmer`** — akkurat. **`01_bank8_uebersicht.png` neu aufnehmen**; „Clear" →
  „✖ Clear ▾".

---

## 4. Neufassungs-Plan (Phasen)

**Phase 0 — Vorbereitung (kein App-Bedarf)**
- Snapshot aller Anleitungs-Dateien nach „Old versions" archivieren (Workspace-Policy).
- Show-Generatoren mit Umlaut-/Label-Korrekturen neu bauen: `tools/build_event_demo_2026.py`
  (GO-Captions entkürzen), Hardstyle-Show-Generator prüfen → korrekte Pad-Labels.

**Phase 1 — Text-Korrekturen (kein App-Bedarf, autonom)**
- Alle 23 Anleitungen gemäß Liste oben patchen/neu schreiben (Labels, §5/§3-Rewrites,
  Smart-Build-Abschnitte, Index-Links). Danach adversariale Verifikation gegen Code.

**Phase 2 — Screenshot-Neuaufnahme (App + computer-use / `lo.ps1`)**
- Reihenfolge nach Bug-Fund-Wert: VC-Familie → Kern (`ANLEITUNG`/`EFFEKTE`/`tutorial_matrix`)
  → Rest. Vorhandene `anleitung_vc_smartbuild/`-Bilder wiederverwenden.
- Neu nötig: VC-Toolbar (aktuell), Helper-Tab, Chaser-Editor (Start/Stop), Matrix-Editor ohne
  „Dimmer treiben", Tempo-Bus-Bedienung aus der VC, Programmer-Bank 8, Hardstyle-Bank 4/5,
  ggf. MH/Spider-Banken mit echten Umlauten.

**Phase 3 — Abschluss**
- Übersichten (`ANLEITUNGEN.md`, `ANLEITUNGEN_EVENT_DEMO.md`) + `ANLEITUNGEN_WALKTHROUGH_PLAN.md`
  aktualisieren; Memory-Notiz `project_user_docs` nachziehen.

---

*Quelle: Multi-Agent-Verifikation 2026-06-19 (26 Agenten). Voller Befund-Datensatz im
Session-Transcript des Workflows `verify-anleitungen`.*
