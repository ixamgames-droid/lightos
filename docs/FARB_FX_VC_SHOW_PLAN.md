# Plan: 4-Seiten Farb-/Effekt-Virtual-Console-Show

Ziel: Eine eigene, klar strukturierte Virtual Console mit **4 Seiten (Bänke)** auf dem realen Rig
(8 PAR + 2 Moving Heads + 2 Spider), alle Effekte an einen **Master-BPM** gekoppelt mit
**eigenem Multiplikator pro Effekt**. Erst per Generator-Skript gebaut, dann auf reale
UI-Bedienbarkeit (VC-Editor + APC mini) geprüft und fehlende Features ergänzt.

Quelle der Architektur-Fakten: Multi-Agent-Codescan 2026-06-17 (RGB-Matrix, EFX, Tempo/BPM,
VC-Widgets, globale Aktionen/Masking, VC-Editor, Scenes/Chaser).

---

## 0. Rig & Gruppen

| Gerät | fids | Adresse U1 | Farbe | Bewegung | Position (Live View) |
|---|---|---|---|---|---|
| 8× PAR (ZQ01424, 8ch RGBW) | 1–8 | 1–64 | RGBW | – | Reihe Mitte |
| 2× Moving Head (ZQ02001, 11ch) | 9,10 | 65 / 76 | Farbrad (`color_wheel`) + Gobo | Pan/Tilt | hinter PAR 1 / PAR 8 |
| 2× Spider (SPIDER14, 14ch) | 11,12 | 87 / 101 | RGBW (2 Bars) | Tilt (2 Köpfe, autom. gegenphasig) | vor PAR 1 / PAR 8 |

Fixture-Gruppen: `Alle PAR`, `Moving Heads`, `Spider`, `Alle Mover`, `Alles`.

---

## 1. Tempo-Modell (zentral)

**Master = globale BPM** (`BPMManager`, der „default"-Tempo-Bus spiegelt sie). Gesetzt per
TAP / Musik-Audio-BPM / manuell. Anzeige oben rechts auf **jeder** Seite (`VCBpmDisplay`, global).

**Jeder Effekt** ist an den Master gekoppelt (`tempo_bus_id` → globaler Bus) und hat seinen
**eigenen `tempo_multiplier`** (freie Zahl, hier Raster ¼ · ½ · 1 · 2 · 3 · 4). Das ist der
„Sub-Speed pro Effekt". Anzahl unabhängiger Multiplikatoren ist **unbegrenzt** (Multiplikator
lebt pro Funktion, nicht pro Bus) — die 4 festen Buses A/B/C/D braucht es dafür nicht.

Bedienung pro Effekt: ein **`VCSpeedDial`** (Modus `TEMPO_BUS_MULT`, Faktor-Set `¼ ½ 1 2 3 4`,
zeigt die **effektive BPM** = Master × Faktor). Die Speed-Dials auf Seite 4 zeigen auf dieselben
Effekte → automatisch synchron mit Seite 1–3.

---

## 2. Masking („nur Farbe / nur Dimmer / nur Bewegung")

Echtes Kanal-Masking ist im Engine vorhanden (kein Überschreiben, sondern Kanal-Maske):

- **Farb-Seite:** `RgbMatrix` mit `style=RGB/RGBW` + `drive_intensity=False` → schreibt **nur**
  `color_r/g/b(/w)`, lässt Dimmer/Shutter unangetastet.
- **Dimmer-Seite:** `RgbMatrix` mit `style=DIMMER` → schreibt **nur** Intensity.
- **Bewegung:** `EFX` schreibt **nur** Pan/Tilt (Farbe nie); `open_beam=False` lässt sogar
  Dimmer/Shutter frei.

Dadurch lassen sich Farbe (Seite 1) + Dimmer (Seite 2) + Bewegung (Seite 3) **gleichzeitig**
auf denselben Geräten überlagern, ohne sich zu stören.

MH-Farbe hat kein RGB → läuft über `color_wheel`-Slots (Szenen/Chaser), nicht über RGB-Matrix.

---

## 3. Seiten-Layout

Single-Select „nur ein Effekt pro Gruppe" = **`edit_slot` pro Gruppe** (Start eines Effekts
stoppt den vorherigen im selben Slot). Farb-/Fade-/Speed-Widgets binden an denselben `edit_slot`
→ sie wirken automatisch auf den gerade aktiven Effekt der Gruppe.

### Seite 1 — FARBE (nur RGB/RGBW, kein Dimmer/Shutter)
Drei Blöcke nebeneinander: **PAR | Moving Heads | Spider**. Pro Block:
- 5–6 **Farb-Kacheln** (`VCColor`, single-select) → setzt die Farbe der Gruppe.
- 4 **Effekt-Tasten** (single-select via `edit_slot`): **Solid · Wechsel (Schachbrett) ·
  Lauflicht · Farbwechsel**. (PAR/Spider = RGB-Matrizen; MH = Farbrad-Szenen/Chaser.)
- **Farbwechsel** öffnet zusätzlich `VCEffectColors` → 2–4 Farben wählbar; sonst nur 1 Farbe.
- 1 **Speed-Dial** (Multiplikator + effektive BPM-Anzeige).
- 2 kleine **Fade-Fader** (Fade ein / Fade aus).

### Seite 2 — DIMMER & GOBO
- Pro Gruppe (PAR/MH/Spider): Dimmer-Effekte single-select: **Dimmer-Lauflicht · An/Aus-Blink ·
  (Aufbau/Welle)** — `style=DIMMER`. Fade-Fader + Speed-Dial (Multiplikator) je Gruppe.
- **MH-Gobo:** Auswahl-Tasten (Gobo offen/1/3/5/7, single-select) + **Gobo-Wechsel**
  (2-Gobo-Alternation, 2-Step-Chaser, BPM-gekoppelt) + Speed-Dial.

### Seite 3 — BEWEGUNG (nur Pan/Tilt)
- **MH-Form** (single-select): Kreis · Acht · **Welliger Kreis** · Dreieck · Quadrat · **Herz**.
- **XY-Feld „Bereich aufziehen"** (`VCXYPad` Modus `area`) → Rechteck zeichnen begrenzt den
  Bewegungsbereich der MH (setzt `x_offset/y_offset/width/height`). *(existiert bereits)*
- **XY-Feld „Pfad zeichnen"** (`VCXYPad` Modus `path`, NEU) → Bahn live zeichnen.
- **Spider-Bewegung** (single-select): Ineinander/Auseinander · beide links/rechts ·
  schnelles Wackeln · feste Position außen/innen · Zufall-3-Positionen.
- Alles BPM-gekoppelt (Speed-Dial-Multiplikator je Effekt).

### Seite 4 — ÜBERSICHT / STROBE / MASTER
- **Übersicht:** Speed-Dials + BPM-Anzeigen, die auf dieselben Effekte/Buses wie Seite 1–3
  zeigen → live synchron + editierbar. Oben rechts Master-BPM.
- **Strobe-Wahl** (single-select): Alle · nur PAR · nur MH · nur Spider.
- **All-White** (Moment-Override, weiß 100 %, beim Loslassen zurück) — NEU.
- **Blackout** · **Effekt-Stop** (stoppt Effekt-Funktionen) · **Pause/Clear** (Effekte aus,
  BPM/Speeds bleiben) · **Freeze** (BPM → 0, alle Effekte einfrieren) — Freeze NEU.
- **4 rechte Fader:** Grand-Master · PAR-Master · MH-Master · Spider-Master (Dimmer).

---

## 4. Zu bauende Features (Lücken aus dem Codescan)

Alle **additiv** auf dem aktuellen (dirty) Branch — kein Worktree, da uncommittete Tempo-Arbeit
in genau diesen Dateien liegt. Jedes Feature mit gezieltem Test.

| # | Feature | Datei(en) | Status heute |
|---|---|---|---|
| F1 | `RgbAlgorithm.CHECKER` (Schachbrett/Wechsel: rot-blau, rot-aus, pro Beat umschaltbar) | `rgb_matrix.py`, `rgb_matrix_meta.py` | fehlt |
| F2 | Fade-In/Out als Live-Param (`env_fade_in`/`env_fade_out` in `list_params`/`get/set_param`) → Fade-Fader via `EFFECT_PARAM` | `rgb_matrix.py`, `efx.py` | nur Felder, nicht als Param |
| F3 | `ButtonAction.ALL_WHITE`, `FREEZE`, `STOP_EFFECTS` (+ Dialog-Labels/Sichtbarkeit) | `vc_button.py` | fehlt |
| F4 | `VCXYPad` Modus `path` (Bahn live zeichnen → `EfxInstance.set_custom_path`) + Dialog | `vc_xypad.py` | nur position/area |
| F5 | Bus-Freeze-HOLD: Effekt mit zugewiesenem Bus & `bpm<=0` **hält** statt Free-Run → Freeze friert bus-gekoppelte Effekte wirklich ein | `efx.py`, `rgb_matrix.py`, `chaser.py` | Free-Run-Fallback |
| F6 | Custom-EfxPaths „Herz" + „Welliger Kreis" (nur Daten, kein Engine-Code) | Generator | fehlt |
| F7 | `'Global'`(=default-Bus) als Auswahl im Tempo-Bus-Dropdown (Effekt folgt Master-BPM) | `rgb_matrix.py`, `efx.py`, `chaser.py` | nur '' / A–D |

Bereits vorhanden (nur konfigurieren/verdrahten): Masking (RGB/Dimmer-Style), PLAIN/CHASE/COLORFADE,
Pro-Effekt-Multiplikator, XY-Box (`area`), Gobo-Wechsel-Chaser, Spider-Gegenphase, RunOrder.Random,
4 Master-Dimmer (GRANDMASTER/GROUP_DIMMER), Single-Select (edit_slot/Solo-Frame), CLEAR behält BPM,
alle 15 VC-Widget-Typen per UI anlegbar, APC-MIDI-Lernen.

---

## 5. Vorgehen

1. **Engine/Widget-Features F1–F5, F7** additiv bauen (Serena, minimale Anker), je mit Test;
   gezielte Tests headless (`LIGHTOS_NO_OUTPUT_THREAD=1`, eigene `LIGHTOS_SHOW_DB`).
2. **Generator** `tools/build_farb_fx_vc_show.py` → `shows/Farb_FX_VC_Show.lshow`, selbst-verifizierend
   (Asserts: Masking-Style, Tempo-Kopplung, 4 Bänke, Single-Select-Slots, Master-Fader, Round-Trip).
3. **Render-Harness** headless: prüft Farb-Matrix nur RGB, Dimmer nur Intensity, EFX nur Pan/Tilt,
   Freeze friert ein, Checker-Muster, Multiplikatoren wirken.
4. **UI-Bedienbarkeit** bestätigen: alle neuen Felder erscheinen im VC-Editor (ButtonAction-Dropdown,
   `env_fade_*` im Param-Combo, XY-`path`-Modus, CHECKER im Matrix-Editor); eine Seite exemplarisch
   per computer-use durchklicken + **APC mini** mappen.
5. **Doku** ergänzen (EFFEKTE.md / bebilderte Anleitung), Memory aktualisieren.

Voll-Suite + Live-Test erst bei geschlossener Live-App (COM3-Hang). Show wird frisch geladen
(nicht in-place, BUG-01).
