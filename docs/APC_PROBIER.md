# APC Probier-Show — Testfeld & Offene Punkte

> **Show:** `shows/APC_Probier.lshow` · **Generator:** `tools/build_apc_probier_show.py`
> **Stand:** 2026-06-11 · **Hardware:** Akai APC mini (mk2) + 4× PAR (ZQ01424, 8ch RGBW) + 2× Moving Head (ZQ02001, 11ch)
>
> Zweck: ausprobieren, ob sich die Befehle so auf dem APC bauen lassen, wie wir
> uns das mit der UI vorstellen — und festhalten, wo es noch hakt. Bewusst nur
> **4 Banks**, jede mit EINEM klaren Test-Schwerpunkt. APC-SCENE-Tasten rechts =
> Seite 1–4.

## Banks im Überblick

| Scene | Bank | Schwerpunkt |
|-------|------|-------------|
| 1 | **Alle Effekte** | Jeder Effekt einzeln als Pad — Überblick „geht alles per Pad?" |
| 2 | **Effekte + Fader** | Wenige Effekte, dafür PARs live per Fader formen (R/G/B/W + Dim + FX-Level) |
| 3 | **Chase Builder** | Farb-Chase live bauen: Farben antippen → Liste, Clear/Farbe±/Richtung/Bounce/Freeze/Commit |
| 4 | **Matrix Builder** | EINE Matrix; „Form ±" blättert durch ALLE Algorithmen + Live-Recolor (color1/2/3 + Sequence) + Speed/Master/Param |

Universell auf **jeder** Seite:
- **Track-Tasten unten:** Clear · Stop All · Blackout · Tap · Musik-BPM
- **Fader F6** Dimmer (Submaster) · **F7** Speed global · **F9** Grand Master

## Pad-Belegung je Bank

### Bank 1 — Alle Effekte
- **Reihe 1 (oben):** 8 Farb-Kacheln (nur Farbe, sofort sichtbar) — erst Farbe wählen, dann Effekt darunter.
- **Darunter, der Reihe nach:** Dimmer-FX (Lauflicht ›/‹, Ping-Pong, 2er-Chase, Strobe, Build-Up, Pulse, Wave) → Farb-Chaser (Color-Chase, Police) → 12× Matrix → 4× MH-EFX → 5× MH-Szenen.

### Bank 2 — Effekte + PAR-Fader
- **Pads:** 8 Farben + 8 ausgewählte Effekte (Lauflicht, Ping-Pong, 2er, Strobe, Build, Pulse, Color-Chase, Regenbogen).
- **Fader:** F1–F4 = **R/G/B/W der PARs** (treffen nur PARs), F5 = **PAR-Dim*** (nur Auswahl, s. u.), F8 = **FX-Level** des laufenden Dimmer-Effekts.
- Ablauf: Effekt starten → PARs live einfärben/abdimmen.

### Bank 3 — Chase Builder
1. Pad unten links = **Start**.
2. Oben **Farben antippen** → hängen der Reihe nach an die Chase-Liste an.
3. Untere Reihe: Start/Stop · **Clear** · Farbe − · Farbe + · Richtung · Bounce · Freeze · **Commit** (Live als Preset übernehmen).
4. Fader: F1 Speed, F2 Übergang (`hold`: 0 = weich faden … hoch = hart halten).
5. **Chase-Builder-Widget** rechts neben dem Grid (To-Do #1): EIN Touch-Element mit Farb-Palette, gebauter Liste (Feedback #6), Aktions-Buttons und Speed/Hold — die kompakte Alternative zu den verstreuten Pads links.

### Bank 4 — Matrix Builder *(2026-06-12 umgebaut, nutzt To-Do #3 + #5)*
- **EINE** Builder-Matrix statt 12 Algorithmus-Pads.
- **Untere Reihe:** Start/Stop · **Form −** · **Form +** (blättern durch ALLE Algorithmen) · Richtung · Bounce · Freeze · Reset Live · Commit.
- **Recolor oben:** Reihe 1 = `color1` (Rot/Grün/Blau/Weiß) + rechts die aktive **Sequence**-Farbe; Reihe 2 = `color2`; Reihe 3 = `color3`. Die `color1/2/3`-Kacheln greifen bei Feuer/Plasma/Windrad/Lauflicht, die Sequence-Kachel bei Color-Fade.
- Fader: F1 Matrix-Speed, F2 Matrix-Master, F3 Parameter (`white_amount`) — alle fest auf den Builder gebunden.

---

## ✅ Was sich sauber auf den Pads bauen lässt

- **Jeder Effekt einzeln** als Toggle/Flash-Pad: Dimmer-Chaser, Carousels (Pulse/Wave), Farb-Chaser, RGB-Matrix, MH-EFX, MH-Szenen.
- **Farb-Ebene** (Farb-Kachel, `ColorTarget.ALL`, ohne Helligkeit) unter laufenden Dimmer-Effekten → farbiges Lauflicht.
- **PARs live per Fader** formen: RGBW im `PROGRAMMER`-Modus (trifft durch die Kanäle nur die PARs).
- **Effekt-Master per Fader:** Speed und Level eines Effekts ODER einer Effekt-Gruppe (`EFFECT_SPEED` / `EFFECT_INTENSITY`).
- **Globale Fader:** Submaster-Dimmer, Speed-global, Grand Master.
- **Live-Farb-Chase bauen:** Farben anhängen (`EFFECT_ADD`) + Aktionen Clear/Farbe±/Richtung/Bounce/Freeze/Commit (`EFFECT_ACTION`) + Speed-/Hold-Fader.
- **Matrix exklusiv** umschalten und live einfrieren/umdrehen.

---

## 🔧 Hardware-Test 2026-06-11 (David) — Ergebnisse & Fixes

### Gefixt
- **Pulse & Wave waren immer weiß**, egal welche Farbe gewählt war. *Ursache:* Das Carousel schrieb bei jedem Pattern seine Eigenfarbe (Default 255/255/255 = weiß) und „besaß" damit die Farbkanäle → die Programmer-Farbe wurde blockiert. *Fix:* Farb-Ausgabe ist jetzt opt-in (`paint_color`, Default aus) in `src/core/engine/carousel.py` — Pulse/Wave modulieren nur noch die Helligkeit, die Farbe kommt aus der Ebene darunter. Regressionstest: `tests/test_carousel_color.py`.
- **Police machte Lila statt reinem Blau / Color-Chase „passte nicht" zu einer vorher live gewählten Farbe** (nach Clear/Stop All war alles korrekt). *Ursache:* Der blaue Step setzt `color_r=0` — und weil `0 == Default`, gilt der Kanal als *nicht* effektgetrieben, also überschreibt ihn die im Programmer hängende Farbe (LTP). Rot + Blau = Lila. *Fix (Show):* Farb-**produzierende** Effekte (Color-Chase, Police, alle Matrix) haben jetzt `clear_programmer` → sie räumen beim Start die alte Programmer-Farbe weg. Dimmer-/Intensitäts-Effekte (Lauflicht, Pulse, Wave …) bleiben bewusst kombinierbar (Farbe + Dimmer-FX = farbiges Lauflicht).
- **MH Kreis tat „nichts".** Die CIRCLE-Mathematik ist korrekt; auffällig war nur `spread=0.5` (Fan, beide Köpfe phasenversetzt). *Fix (Show):* `spread=0.0` → beide Köpfe fahren synchron einen klaren Kreis (wie „Acht", die sauber lief). **Bitte auf der Hardware nochmal gegenchecken.**

### Bestätigt OK
- MH Acht, Position Center/Publikum, MH Rot/Blau, Gobo-Wechsel ✓
- **Chase Builder (Bank 3) läuft „richtig gut, richtig cool"** — keine Änderung nötig.
- Matrix-Effekte laufen als Effekte (Farbe live ändern geht nur bei Color-Fade — bekannt, s. u.).

### Noch zu beobachten (Hardware)
- MH **Sweep gespiegelt** kreiste statt sauber zu sweepen, MH **Bounce** drehte „auf der Stelle" (~180°). LINE-Param/Offset evtl. nachjustieren — beim nächsten Test gezielt anschauen.

---

## ⚠️ Offene Punkte / To-Do (UI-Grenzen beim Bauen gefunden)

1. ~~**Kein dediziertes „Builder"-Widget.**~~ ✅ **erledigt 2026-06-12.** Neues
   VC-Widget **`VCChaseBuilder`** („Chase Builder") bündelt ALLES in EINEM Element:
   12er-Farb-Palette (antippen = anhängen), die gebaute Liste (Feedback, aktive
   Farbe gelb), Aktions-Buttons (▶/■ Start · Clear · C− · C+ · ⇄ · ❄ · ✓) und
   Speed/Hold-Slider — gebunden an einen Ziel-Effekt über `effect_live`. Aus der
   VC-Toolbar ziehbar; in der Show auf Bank 3 (rechts). Tests:
   `tests/test_vc_chase_builder.py`. *(Die verstreuten Pads links bleiben für die
   reine APC-Hardware-Bedienung; das Widget ist die kompakte Touch-Variante.)*

2. ~~**Chaser lässt sich NICHT live bauen.**~~ ✅ **erledigt 2026-06-12.** `Chaser`
   hat jetzt `add_step` / `capture_step` (nimmt den aktuellen Programmer als neue
   Scene auf und hängt sie an) + `do_action`/`list_actions` (Schritt aufnehmen,
   letzten/alle löschen, Richtung, Ping-Pong, Neustart, Tap) + `list_params/
   set_param` (Tempo/Richtung/Modus). Ein echter Szenen-Chaser ist damit vom APC
   aus zusammensteckbar. Tests: `tests/test_chaser_live_build.py`. *(Bank 3 bleibt
   vorerst der bewährte COLORFADE-Farb-Fade — „läuft richtig gut" — kann aber jetzt
   wahlweise als echter Szenen-Chaser gebaut werden.)*

3. ~~**Matrix-Algorithmus nicht live umschaltbar.**~~ ✅ **erledigt 2026-06-12.**
   `RgbMatrix` hat jetzt `next_algorithm`/`prev_algorithm` (do_action, rotiert
   durch alle `RgbAlgorithm`) + `list_actions`-Einträge „Form +/−" und
   `set_param("algorithm", …)`/`get_param` (analog EFX; behebt nebenbei einen
   stillen Bug, dass `set_param("algorithm")` nur in `params` landete). Damit
   reicht im „Matrix Builder" EINE Matrix + ein „Form +/−"-Pad statt 12 Pads.
   Tests: `tests/test_matrix_algo_cycle.py`.

4. ~~**PROGRAMMER-Fader nicht fest an eine Fixture-Gruppe bindbar.**~~ ✅ **erledigt
   2026-06-12.** `VCSlider` hat im PROGRAMMER-Modus jetzt die Reichweite **„Feste
   Gruppe"** (`programmer_scope="group"` + `programmer_group`): der Fader wirkt
   unabhängig von der Live-Auswahl genau auf die Geräte einer Gruppe. In der Show
   ist „PAR-Dim" damit fest auf die **PAR-Reihe** gebunden (keine Vorauswahl mehr).
   Tests: `tests/test_vc_slider_group_scope.py`.

5. ~~**Live-Recolor der Matrix nur bei Color-Fade/Sequence-Algos.**~~ ✅ **erledigt
   2026-06-12.** Neue Farb-Kachel-Ziele `ColorTarget.EFFECT_C1/C2/C3` („Effekt
   Farbe 1/2/3") setzen gezielt `color1/2/3` des Ziel-Effekts (über
   `effect_live.set_param`). Damit lassen sich Feuer/Plasma/Windrad live umfärben,
   wo die Sequence-Variante (`ColorTarget.EFFECT`) nichts bewirkt. RAINBOW bleibt
   farblos (generiert den Hue selbst — hat keine festen Farbslots). Tests:
   `tests/test_vc_effect_live.py::*effect_slots`.

6. ~~**Reihenfolge-Falle + fehlendes Builder-Feedback.**~~ ✅ **erledigt 2026-06-12
   (Feedback-Fenster).** Neues VC-Anzeige-Widget **„Chase-Liste" (`VCColorList`)**
   spiegelt live die Color-Sequence eines Ziel-Effekts: Farben in Reihenfolge,
   **aktive Farbe gelb umrandet**, deaktivierte durchgestrichen, Status
   „● läuft / ○ gestoppt / leer". In der Show auf Bank 3 (rechts, gebunden an den
   Chase-Builder) und Bank 4 (Matrix-Farben). Drag-bar aus der VC-Toolbar
   („Chase-Liste"). Tests: `tests/test_vc_color_list.py`.
   *(Rest-Gap: LED-Spiegelung der gebauten Liste auf eigene APC-Pads — hängt am
   Pad-Layout/#1. Die Farb-Paletten-Pads zeigen ihre Farbe via mk2-LED bereits.)*

### Aus dem Hardware-Test neu dazugekommen

7. ~~**Relative Moving-Head-Bewegungen.**~~ ✅ **erledigt 2026-06-12 (Grundlage).**
   `EfxInstance.relative` (Param „Relativ (additiv)" + `toggle_relative`-Aktion):
   beim Start wird die aktuelle Pan/Tilt-Position jedes Geräts aus dem Programmer
   geschnappt und die Bewegung läuft additiv um diesen Punkt statt um 128/128.
   Tests: `tests/test_efx_relative.py`. *(Offen für später: Zentrum auch aus einer
   Positions-**Szene**/DMX statt nur Programmer — siehe #8 XY-Bereich.)*

8. ~~**XY-Steuerpad-Widget für die VC + Live-Positions-Programmierung.**~~ ✅
   **erledigt 2026-06-12.** `VCXYPad` fährt Pan/Tilt schon lange live (Punkt-Modus);
   NEU der **„Feld"-Modus** (`mode="area"` + `efx_function_id`): ein Rechteck
   aufziehen → setzt Zentrum (x_offset/y_offset) **und** Größe (width/height) eines
   Ziel-EFX → „in diesem Feld fährst du jetzt deine Acht/deinen Kreis". Tests:
   `tests/test_vc_xypad_area.py`. In der Feature-Test-Show auf Seite 3.

9. ~~**Selbst-färbende Effekte sperren die Farb-Kacheln (Info/Disable).**~~ ✅
   **erledigt 2026-06-12.** `effect_live.color_is_effect_driven()` erkennt eine
   laufende RGB-/RGBW-Matrix; `VCColor` graut Programmer/Alle-Kacheln dann aus
   und zeigt ein 🔒-Symbol (Effekt-Ziele bleiben unberührt). Die VC-View aktualisiert
   das live (400-ms-Tick, nur bei Zustandswechsel neu gezeichnet). Tests:
   `tests/test_color_context_lock.py`. *(Color-Chaser-Erkennung bewusst noch nicht —
   der eindeutige Fall ist die Matrix.)*

10. **Echtes „Matrix Builder"-Konzept.** 🟡 **weitgehend adressiert 2026-06-12:**
   Bank 4 ist umgebaut — EINE Matrix, „Form ±" blättert live durch alle
   Algorithmen (#3), Live-Recolor `color1/2/3` + Sequence (#5), Speed/Master/Param
   fest gebunden. Damit *baut* man eine Matrix jetzt schrittweise statt aus 12
   Pads. Rest-Gap = bewusst offen: ein **dediziertes Builder-Widget** (#1) und
   das **Feedback-Fenster** (#6) wären die UI-Krönung.

11. ~~**Nächste Demo: sektioniertes APC-Layout („Profi-Modus").**~~ ✅ **erledigt
   2026-06-12.** `shows/Profi_Modus.lshow` (Generator `tools/build_profi_show.py`,
   Doku [PROFI_MODUS.md](PROFI_MODUS.md)): 4×4 Farben (Programmer) · 4×4 Effekte
   (**exklusiv**, nur einer) · 4×4 Attribute des **aktiven** Effekts · 4×4 Sonstiges.
   Die Fader F1–F3 (FX-Speed/Master/Param) sind **nicht** fest gebunden → wirken
   automatisch auf den zuletzt gestarteten Effekt (kontext-adaptiv). Self-verifizierend.

---

*Stand nach Hardware-Test 2026-06-11. Punkte 1–6 = beim Bauen gefunden, 7–11 = aus Davids Feedback. Fixes (Pulse/Wave, Police/Color-Chase, MH-Kreis) sind eingebaut; Show neu gebaut.*
*Update 2026-06-12: Großrunde abgearbeitet — #2 (Chaser live baubar), #3 (RgbMatrix
Live-Algo-Wechsel), #4 (PROGRAMMER-Fader feste Gruppe), #5 (Live-Recolor color1/2/3),
#7 (relative MH-Bewegung), #9 (Farb-Kachel-Lock bei Effekt-Farbe). Bank 2 (PAR-Dim →
feste Gruppe) + Bank 4 (Matrix Builder: eine Matrix + Form ±/Recolor) neu gebaut.
Danach auch #6 (Chase-Feedback-Fenster `VCColorList`), #8 (XY-Pad „Feld"-Modus),
#11 (Quadranten-Demo `shows/Profi_Modus.lshow`) und **#1 (dediziertes
`VCChaseBuilder`-Widget)**. Damit sind **alle 11 To-Dos erledigt** — offen nur noch
die LED-Pad-Spiegelung der gebauten Liste (hängt am Pad-Layout). Neue Test-Shows:
`Feature_Test.lshow` ([FEATURE_TEST.md](FEATURE_TEST.md)) + `Profi_Modus.lshow`
([PROFI_MODUS.md](PROFI_MODUS.md)). Gesamtsuite 708 Tests grün.*
