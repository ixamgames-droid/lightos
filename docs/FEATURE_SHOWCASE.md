# Feature‑Showcase — die „alles drin"‑Test‑Show

Diese Anleitung gehört zur Show **`shows/Feature_Showcase.lshow`**. Sie ist die
große Schwester der [APC‑Test‑Show](APC_TEST_SHOW.md): wo jene auf den reinen
Live‑Einsatz mit 4 PARs zugeschnitten ist, will **diese Show jedes
programmierbare Feature von LightOS einmal anfassbar machen** — und der
Generator beweist beim Bauen, dass sich auch wirklich **alles** aufbauen,
speichern und wieder laden lässt.

> **Selbst‑verifizierend:** `tools/build_feature_showcase.py` prüft am Ende, dass
> *jeder* Enum‑Wert (alle Button‑Aktionen, Slider‑Modi, Color‑Targets,
> Carousel‑Pattern und Matrix‑Algorithmen) mindestens einmal vorkommt. Fehlt
> etwas, schlägt der Build mit einem Fehler fehl. Aktueller Stand: **alles grün**
> (Button 11/11 · Slider 10/10 · Color 4/4 · Carousel 5/5 · Matrix 17/17).

---

## 1. Das Rig (Universe 1)

| FID | Label | Gerät | Mode | Adresse | Kanäle |
|-----|-------|-------|------|---------|--------|
| 1–4 | PAR 1–4 | Generic **Stage Light ZQ01424** | 8‑Kanal RGBW | 1 / 9 / 17 / 25 | 1–32 |
| 5–6 | Mover 1–2 | Generic **Moving Head Wash RGB 7ch** | 7‑Kanal | 33 / 40 | 33–46 |

**PAR (8‑Kanal RGBW):** 1 Dimmer · 2 Rot · 3 Grün · 4 Blau · 5 Weiß · 6 Strobe ·
7 Makro · 8 Funk.Speed.
**Mover (7‑Kanal):** 1 Pan · 2 Tilt · 3 Dimmer · 4 Rot · 5 Grün · 6 Blau · 7 Strobe.

> **Die 2 Moving Heads sind optional.** Sie bringen Pan/Tilt, Positionen und die
> Carousel‑Pattern *Kreis*/*Sweep* ins Spiel. Hast du keine Mover, ignoriere
> einfach die Mover‑Seite — der Patch sendet dann nur ins Leere, stört aber nichts.

**Grundprinzip (Layering):** Alle PARs **und** Mover haben den Dimmer per
`base_levels` fest auf 255 → eine Farbe ist sofort sichtbar. Dimmer‑Effekte
überschreiben die Helligkeit (echtes Lauflicht). Farb‑Kacheln setzen nur Farbe.
Matrix‑Effekte bringen ihre Farbe selbst mit — die Matrix‑Buttons dieser Show
haben deshalb `clear_programmer` aktiv und geben die Farb‑Ebene **automatisch**
frei (kein manuelles „Clear" mehr nötig).

---

## 2. Show laden & neu erzeugen

### Laden
1. **Playback → Show Manager** → `Feature_Showcase.lshow`.
2. **Eingabe/Ausgabe → MIDI**: APC mini als Eingang (Backend WinMM), VC → **„APC LEDs"** an.
3. **Ausgabe → Konfiguration**: dein Interface auf Universe 1.

### Neu erzeugen (Generator)
```cmd
venv\Scripts\python tools\build_feature_showcase.py
```
Der Generator ruft `reset_show()` (leere Basis), patcht das Rig, baut alle
Funktionen/Paletten/Bibliothek/8 VC‑Seiten, **lädt am Ende erneut** und gibt eine
**Feature‑Coverage‑Tabelle** aus.

---

## 3. Die APC mini als Controller

```
 Scene‑Tasten (rechts) = SEITE 1 … 8   (page_select, global)
 ┌──────────────────────────────────────┐ ┌────┐
 │ 8 × 8 Pad‑Grid  (Notes 0 … 63)        │ │ S1 │ Farben
 │ Note 0 = unten links, 56 = oben links │ │ S2 │ Dimmer
 │                                       │ │ S3 │ Matrix A
 │                                       │ │ S4 │ Matrix B
 │                                       │ │ S5 │ Mover
 │                                       │ │ S6 │ Hand
 └──────────────────────────────────────┘ │ S7 │ Mix
 ┌──────────────────────────────────────┐ │ S8 │ Chase
 │ Track‑Tasten (unten)                  │ └────┘
 └──────────────────────────────────────┘
   F1 … F9  =  CC 48 … 56   (9 Fader)
```

**Immer aktiv (auf jeder Seite):**

| Element | MIDI (mk2) | Funktion |
|---|---|---|
| Track 1 | Note 100 | **Clear** (Programmer freigeben) |
| Track 2 | Note 101 | **Stop All** |
| Track 3 | Note 102 | **Blackout** |
| Track 4 | Note 103 | **Tap** (Tempo tippen) |
| Track 5 | Note 104 | **Snapshot** (Look festhalten/abrufen) |
| Fader **F6** | CC53 | **Dimmer** (Submaster, Grundhelligkeit) |
| Fader **F7** | CC54 | **Speed global** (alle laufenden Effekte) |
| Fader **F9** | CC56 | **Grand Master** |

Die Show ist auf **APC mini mk2** eingestellt (`DEVICE = "mk2"` → Track 100–107,
Scene 112–119). Für ein **Original** auf `"original"` stellen und neu bauen
(Track 64–71, Scene 82–89). Reagiert eine Taste nicht → in der App per
**„MIDI lernen"** neu zuweisen.

---

## 4. Die 8 Seiten

### Seite 1 — FARBEN & LOOKS
Obere zwei Reihen 16 Farb‑Kacheln (`ColorTarget=Alle`, nur Farbe), darunter 8
Look‑Szenen und 6 Bibliotheks‑Snaps. Unten: Farb‑Chaser *Color‑Chase* / *Police*
und eine Kachel **„In Programmer"** (`ColorTarget=Programmer`, mit Intensität).

### Seite 2 — DIMMER‑EFFEKTE & CAROUSELS
Chaser (Lauflicht ▶◀, Ping‑Pong, 2er, Strobe, Build‑Up, Random) **plus**
Carousels *Pulse* / *Wave* / *EFX‑Chase*. Pad 12 = **FUNCTION_FLASH** auf *Strobe*
(blitzt nur, solange gehalten). Oben 6 Farb‑Kacheln.
**Fader:** F1–F4 Effekt‑Speed, F5 FX‑Level (Helligkeits‑Master aller Dimmer‑Effekte).

### Seite 3 — MATRIX A
10 Matrix‑Algorithmen: *Plain · Regenbogen · Lauflicht · Wipe · Welle · Gradient ·
Fill · Sparkle · Color‑Fade · Strobe* (1‑zeilig über alle 6 Geräte). Buttons mit
`clear_programmer` → Farb‑Ebene wird automatisch frei.
**Fader:** F8 Matrix‑Master, F7 **EFFECT_PARAM** (Sättigung des Regenbogens).

### Seite 4 — MATRIX B (2D) + EFFEKT‑AKTIONEN
7 Textur‑Algorithmen im **2×2‑Grid** (PARs): *Radar · Spirale · Plasma · Windrad ·
Atmen · Feuer · Regen*. Reihe 2 = **EffectAction**‑Buttons: *Bounce · Reverse ·
Freeze · Live‑Reset · Commit Live* und eine Kachel **„Aktive Farbe"**
(`ColorTarget=Effekt`, setzt live die aktive Farbe der gebundenen Matrix).

### Seite 5 — MOVER
5 Positions‑Szenen (Center, Publikum, Boden, Links, Rechts), Carousels
**Kreis** (CIRCLE) / **Sweep** (SWEEP) und ein Pos‑Chase.
**Fader:** F1 Pan, F2 Tilt (`Programmer`), F3 Kreis‑Speed, F4 **BPM**.

### Seite 6 — HAND (RGBW von Hand)
8 Farb‑Kacheln + Fixt‑Strobe (Shutter) / Auto‑Programm (Makro) / Full.
**Fader:** F1–F4 = Rot/Grün/Blau/Weiß (`Programmer`), F5 = **Level**.

### Seite 7 — MIX & PLAYBACK
Farbe + Dimmer‑/Matrix‑Effekt frei kombinieren (alles bleibt beim Seitenwechsel
aktiv). Reihe 3: **Exec Go** (`TOGGLE`) / **Exec Flash** (`FLASH`) auf
Playback‑Slot 0 + **Snapshot 1**.
**Fader:** F1 Speed Lauflicht, F4 **Playback** (Slot 0), F5 FX‑Level, F8 Matrix‑Master.

### Seite 8 — LIVE COLOR‑CHASE
Live einen Farb‑Chase bauen: 1) **Clear Chase** leert die Liste, 2) oben Farben
antippen (`ColorTarget=Effekt‑Hinzufügen`), 3) Pad 1 = Start. *Farbe −/+* springt
manuell, *Letzte weg* = `remove_color`.
**Fader:** F1 Speed, F2 Übergang (`EFFECT_PARAM`, param `hold`).

---

## 5. Feature‑Abdeckung (Verifikation)

Jeder programmierbare Enum‑Wert ist in dieser Show belegt — hier die Zuordnung
„Feature → wo in der Show":

### Button‑Aktionen (`ButtonAction`, 11/11)

| Wert | Wo |
|---|---|
| `Toggle` | Seite 7 *Exec Go* |
| `Flash` | Seite 7 *Exec Flash* |
| `FunctionToggle` | überall (Effekt/Szene starten) |
| `FunctionFlash` | Seite 2 Pad 12 |
| `Blackout` | Track 3 |
| `StopAll` | Track 2 |
| `Snapshot` | Track 5 + Seite 7 |
| `LibrarySnap` | Seite 1 (Look‑Snaps) |
| `Clear` | Track 1 |
| `Tap` | Track 4 |
| `EffectAction` | Seite 4 + Seite 8 |

### Slider‑Modi (`SliderMode`, 10/10)

| Wert | Wo |
|---|---|
| `Level` | Seite 6 F5 |
| `Playback` | Seite 7 F4 (Slot 0) |
| `Submaster` | F6 (Dimmer) |
| `GrandMaster` | F9 (Master) |
| `Programmer` | Seite 5/6 (Pan/Tilt, RGBW) |
| `BPM` | Seite 5 F4 |
| `Speed` | F7 (global) |
| `EffectIntensity` | FX‑Level / Matrix‑Master |
| `EffectSpeed` | Seite 2/4/5/8 |
| `EffectParam` | Seite 3 (Sättigung), Seite 8 (hold) |

### Color‑Targets (`ColorTarget`, 4/4)

| Wert | Wo |
|---|---|
| `Alle Fixtures` | Seite 1/2/6/7 Farb‑Kacheln |
| `Programmer/Selektion` | Seite 1 *In Programmer* |
| `Effekt (aktive Farbe)` | Seite 4 *Aktive Farbe* |
| `Effekt (Farbe hinzufügen)` | Seite 8 (Live‑Chase) |

### Carousel‑Pattern (`CarouselPattern`, 5/5)
`Pulse` · `Wave` · `Chase` (PARs, Seite 2) · `Circle` · `Sweep` (Mover, Seite 5).

### Matrix‑Algorithmen (`RgbAlgorithm`, 17/17)
`Plain · Chase · Wipe · Wave · Gradient · Rainbow · Fill · Random · Color Fade ·
Strobe` (Seite 3) und `Radar · Spirale · Sine Plasma · Windrad · Atmen · Feuer ·
Regen` (Seite 4, 2D). *Live Color‑Chase* (Seite 8) ist eine 18. Matrix‑Instanz
(Color‑Fade mit live wachsender Farbliste).

### Weitere Features
- **Funktions‑Typen:** Scene (34), Chaser (10), EFX/Carousel (5), RGBMatrix (18).
- **Paletten:** 4 Farb‑ + 5 Positions‑ + 2 Beam‑Paletten (Paletten‑Panel).
- **Bibliothek:** 12 Farb‑, 6 Look‑, 3 Positions‑Snaps in 3 Ordnern.
- **Effekt‑Aktionen:** `toggle_bounce`, `reverse_direction`, `toggle_freeze`,
  `clear_live_override`, `commit_live`, `clear_colors`, `next/prev_color`,
  `remove_color`, `add_color` (via Color‑Hinzufügen‑Kacheln).
- **Live View:** 2D‑Positionen für alle 6 Geräte sind vorbelegt.

---

## 6. Schnellstart‑Rezepte

1. **Farbiges Lauflicht:** Seite 1 *Blau* → Seite 2 *Lauflicht ▶* → F1 Speed.
2. **Regenbogen‑Matrix:** Seite 3 *Regenbogen* (clear_programmer regelt das Clear).
3. **2D‑Plasma + Pulsieren:** Seite 4 *Plasma* → Seite 2 *Pulse* (läuft übereinander).
4. **Mover‑Kreis:** Seite 5 *Kreis* → F3 Speed; oder Position antippen.
5. **Live‑Color‑Chase:** Seite 8 *Clear Chase* → Farben antippen → *Start*.
6. **Panik:** *Blackout* (Track 3) oder *Stop All* (Track 2).

---

## 7. Datei‑Überblick

| Datei | Zweck |
|---|---|
| `shows/Feature_Showcase.lshow` | die fertige Show |
| `tools/build_feature_showcase.py` | Generator (reproduzierbar, selbst‑verifizierend) |
| `docs/FEATURE_SHOWCASE.md` | dieses Handbuch |
| `docs/APC_TEST_SHOW.md` | kompakte Live‑Show für reine PAR‑Rigs |

*Stand: 2026‑06‑08*
