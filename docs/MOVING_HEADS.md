# Moving Heads in LightOS

> Stand: 2026-06-10 · Diese Datei dokumentiert die Moving-Head-Unterstuetzung in
> Fixture Library und Programmer — insbesondere das korrigierte **ZQ02001**-Profil
> (Dimmer/Strobe-Tausch), die Farbrad-/Gobo-/Strobe-Wertebereiche und die neuen
> Programmer-Bedienelemente.
> Verwandt: [FIXTURE_LIBRARY.md](FIXTURE_LIBRARY.md) ·
> [MOVING_HEAD_ROADMAP.md](MOVING_HEAD_ROADMAP.md) ·
> [MOVING_HEAD_SHOW.md](MOVING_HEAD_SHOW.md) ·
> [FUTURE_FIXTURE_GENERATOR.md](FUTURE_FIXTURE_GENERATOR.md)

---

## 1. ZQ02001 Mini Moving Head — Kanal-Layout (korrigiert 2026-06-10)

Quelle: reale Geraetedaten des Nutzers (2026-06). Das fruehere Profil hatte
**Dimmer und Strobe vertauscht** und im 9-Kanal-Modus faelschlich
Pan-fein/Tilt-fein statt Speed/Gobo-FX/Reset. Beide Modi sind jetzt korrekt:

| Funktion | 9-Kanal | 11-Kanal | Attribut |
|---|---|---|---|
| Pan | CH1 | CH1 | `pan` |
| Pan fein | — | CH2 | `pan_fine` |
| Tilt | CH2 | CH3 | `tilt` |
| Tilt fein | — | CH4 | `tilt_fine` |
| Farbrad | **CH3** | **CH5** | `color_wheel` |
| Gobo | **CH4** | **CH6** | `gobo_wheel` |
| Strobe | **CH5** | **CH7** | `shutter` |
| Master Dimmer | **CH6** | **CH8** | `intensity` |
| Pan/Tilt-Speed | CH7 | CH9 | `speed` |
| Gobo FX / Sound | **CH8** | **CH10** | `gobo_fx` |
| Reset / Rekalibrierung | **CH9** | **CH11** | `reset` |

Die Definition lebt zentral in
`src/core/database/fixture_db.py` (`_zq02001_modes_data()`).
`ensure_builtins()` aktualisiert ein veraltetes Profil **in-place** beim
naechsten Start (Profil-ID bleibt stabil, bestehende Patches funktionieren
weiter). Manuell anstossen: `venv\Scripts\python examples\add_zq02001.py`.

### Dokumentierte Annahmen

- **CH7 (9ch) / CH9 (11ch) = Pan/Tilt-Speed** — aus aelteren Notizen
  uebernommen, vom Geraet nicht explizit bestaetigt.
- **Strobe 250–255 = „Strobe aus"** wird als „offen, kein Strobe"
  interpretiert (gleiches Verhalten wie 0–9).
- **Gobo-FX-Kanal:** genaue Funktion („Effekte des Gobos, Sound usw.")
  geraeteabhaengig und nicht voll dokumentiert → bewusst neutraler Fader,
  keine Presets.
- **Reset-Haltedauer:** der Reset-Button haelt den Wert 4 Sekunden, dann wird
  der Kanal automatisch auf Default (0) zurueckgesetzt. Annahme — falls das
  Geraet laenger braucht, `ResetActionButton.HOLD_MS` anpassen.
- **Tippfehler der Original-Notizen** interpretiert:
  „3–16" → **16–23** (Gobo 2), „46–71" → **64–71** (Leerbereich).

---

## 2. Farbrad (CH3 / CH5)

| DMX | Farbe | kind |
|---|---|---|
| 0–9 | Weiß / Offen | `open` |
| 10–19 | Rot | `color` |
| 20–29 | Grün | `color` |
| 30–39 | Blau | `color` |
| 40–49 | Gelb | `color` |
| 50–59 | Orange | `color` |
| 60–69 | Hellblau | `color` |
| 70–79 | Rosa | `color` |
| 80–89 | Hellblau/Rosa (Split) | `color` |
| 90–99 | Orange/Hellblau (Split) | `color` |
| 100–109 | Gelb/Orange (Split) | `color` |
| 110–119 | Blau/Gelb (Split) | `color` |
| 120–129 | Grün/Blau (Split) | `color` |
| 130–139 | Rot/Grün (Split) | `color` |
| 140–255 | Automatischer Farbwechsel, langsam → schnell | `rotate` |

### Bedienung im Programmer (Color-Tab)

- **Dedizierte Buttons fuer alle Voll- und Split-Farben** (PresetTile-Kacheln):
  jede Kachel zeigt die echte Farbe, Split-Farben als zweifarbige Kachel
  (diagonal geteilt). Tooltip = DMX-Bereich. Der Fader bleibt erhalten.
- Die Kacheln entstehen **generisch** aus den `ChannelRange`-Daten
  (kind `color`/`open`) — jedes Fixture mit gepflegtem Farbrad-Profil bekommt
  sie automatisch (`src/ui/widgets/preset_tile.py`, `ColorQuickBar`).

### Farbrotation / Auto-Farbwechsel

Zwei Wege (`ColorWheelAutoBar` im Color-Tab):

| | Hardware | Software-Simulation |
|---|---|---|
| **Was passiert** | Rad dreht im Geraet (DMX 140–255) | LightOS schaltet das Rad per Timer durch gewaehlte Slots |
| **Bereich** | immer **alle** Farben (Geraete-Funktion) | frei waehlbar: Von/Bis-Slot oder „Nur Split-Farben" |
| **Tempo** | Slider → DMX-Wert im Bereich 140–255 | Slider → Schaltintervall ~1,5 s bis ~0,12 s |
| **Ausgabe** | ein statischer DMX-Wert | `set_programmer_value(color_wheel, …)` pro Schritt |
| **Grenzen** | kein Teilbereich moeglich | laeuft nur solange der Programmer aktiv ist; harte Wechsel (Farbraeder koennen nicht faden); wird **nicht** als Animation in Snaps/Szenen gespeichert |

Die Hardware kann keinen Teilbereich rotieren — deshalb simuliert die Software
das fuer „nur Farben 1–3", „Farbe 3 bis 6", „nur Split-Farben" usw.

---

## 3. Gobo (CH4 / CH6)

| DMX | Funktion | kind |
|---|---|---|
| 0–7 | Kein Gobo | `open` |
| 8–15 | Gobo 1: Ring, Mitte dunkel, aussen Licht mit drei Spalten | `gobo` |
| 16–23 | Gobo 2: Ovale von innen klein nach aussen gross | `gobo` |
| 24–31 | Gobo 3: Kreise, die aus vielen kleinen Kreisen bestehen | `gobo` |
| 32–39 | Gobo 4: Tetris-Muster | `gobo` |
| 40–47 | Gobo 5: unterschiedlich grosse Kreise | `gobo` |
| 48–55 | Gobo 6: Spirale | `gobo` |
| 56–63 | Gobo 7: Zebra-Muster | `gobo` |
| 64–71 | Kein Gobo (Leerbereich) | `open` |
| 72–79 … 120–127 | Gobo 1–7 **Shake** (je 8er-Block, hoeherer Wert = schnelleres Wackeln) | `shake` |
| 128–255 | Gobos wechseln nacheinander, hoeher = schneller (ohne Wackeln) | `rotate` |

### Bedienung im Programmer (Gobo-Tab)

Der **Gobo-Tab** existiert als eigener Reiter und ist nur sichtbar, wenn das
ausgewaehlte Fixture Gobo-Kanaele besitzt (`setTabVisible`, M2.1). Inhalt
(`GoboQuickBar`):

- **Direkt-Buttons** „Kein Gobo" + Gobo 1–7, jeweils **mit grafischer
  Vorschau** des Musters (siehe Abschnitt 4).
- **Shake-Buttons** fuer alle 7 Gobos (Icon mit orangem Vibrations-Marker) +
  **Shake-Geschwindigkeits-Slider** (waehlt den Wert innerhalb des 8er-Blocks;
  wirkt live auf den zuletzt gewaehlten Shake-Gobo).
- **Gobo-Wechsel-Slider** (DMX 128–255, langsam → schnell) + Stopp-Button
  (zurueck auf „Kein Gobo"). Damit ist der fruehere, falsch platzierte
  „Gobos wackeln"-Wert sauber aufgeteilt: *Shake* (72–127, wackelt) und
  *Wechsel* (128–255, schaltet durch) sind getrennte Bedienelemente.
- **Gobo FX / Sound** (CH8/CH10) erscheint als normaler Fader **im Gobo-Tab**
  (Attribut `gobo_fx` wird der Gobo-Gruppe zugeordnet) — neutral benannt, da
  die genaue Geraetefunktion nicht voll dokumentiert ist.
- Text-Legende mit allen DMX-Bereichen unter den Kacheln.

Bei **Mehrfachauswahl** mit unterschiedlichen Profilen gilt das Template-Prinzip
des Programmers: Kacheln/Bereiche kommen vom ersten ausgewaehlten Geraet; ohne
`kind`-Daten gibt es nur neutrale Kacheln bzw. Fader (es werden keine Werte
geraten).

---

## 4. Grafische Gobo-Vorschau

`src/ui/widgets/gobo_icons.py` — wiederverwendbares Modul, QPainter-gezeichnet
(keine externen Bilddateien), gecacht.

- Das Muster wird **aus dem Range-Namen** erkannt (Schluesselwoerter wie
  „Ring", „Ovale", „Tetris", „Spirale", „Zebra", „Punkte", „Kreis aus…").
  Andere Fixtures bekommen dieselben Icons, wenn ihre Gobo-Ranges entsprechend
  benannt sind.
- Unbekannte Namen → neutrales nummeriertes Icon („Gobo N"), **kein geratenes
  Muster**.
- Shake-Varianten: gleiches Muster + orange Vibrations-Boegen.
- API: `gobo_pixmap_for_name(name, size, shake)` bzw.
  `gobo_pixmap(style, size, shake, number)`; Stile: `ring_slits`, `ovals`,
  `circle_of_circles`, `tetris`, `dots`, `spiral`, `zebra`, `open`.

---

## 5. Strobe (CH5 / CH7) — und warum er im Intensity-Tab liegt

| DMX | Funktion | kind |
|---|---|---|
| 0–9 | Kein Strobe (offen) | `open` |
| 10–249 | Strobe langsam → schnell | `strobe` |
| 250–255 | Strobe aus (offen) | `open` |

Bedienung (`ShutterQuickBar`, **im Intensity-Tab direkt beim Dimmer**):

- **Status-Buttons** aus den Range-Namen: „Kein Strobe (offen)",
  „Strobe aus (offen)" (gruen) + Stufen „Strobe langsam/mittel/schnell".
- **Strobe-Geschwindigkeits-Slider** (stufenlos im Bereich 10–249,
  beschriftet langsam → schnell).
- **Text-Legende** zeigt alle DMX-Bereiche.
- Der Strobe-**Fader** liegt ebenfalls im Intensity-Tab (Attribut-Gruppe
  „Intensity" enthaelt jetzt `shutter`/`strobe`; Dimmer wird zuerst gelistet).
  Wichtig: `shutter` ist **nicht** in `INTENSITY_ATTRS` — der **Grand Master
  dimmt den Strobe-Kanal nicht** mit, und Dimmer-Effekte behandeln ihn nicht
  als Intensitaet. Dimmer und Strobe sind sauber getrennt.

---

## 6. Reset / Rekalibrierung (CH9 / CH11)

| DMX | Funktion | kind |
|---|---|---|
| 0–149 | Keine Funktion | — |
| 150–255 | Reset / Rekalibrierung | `reset` |

Bedienung (`ResetActionButton`, Tab „Weitere"):

- **Kein Dauer-Slider** — der Kanal wird im Programmer bewusst nicht als
  Fader angeboten (sonst koennte ein versehentlich stehender Wert das Geraet
  dauerhaft resetten).
- Button **„⟳ Moving Head Reset…"** mit **Sicherheitsabfrage** („faehrt in
  Home-Position — waehrend einer Show deutlich sichtbar").
- Nach Bestaetigung: Reset-Wert (Mitte des `reset`-Bereichs, 202) wird
  gesendet, der Button ist gesperrt, und nach **4 s** wird der Kanal
  automatisch auf den Default (0) zurueckgesetzt — der Reset kann nicht
  haengen bleiben.

---

## 7. Generisches Capability-Prinzip

Der Programmer reagiert auf **Faehigkeiten aus der Fixture-Definition**, nicht
auf Geraetenamen — keine Sonderlogik im UI-Code:

| Capability | Erkennung | UI |
|---|---|---|
| Dimmer | Attribut `intensity`/`dimmer`/`master` | Fader im Intensity-Tab |
| Strobe | Attribut `shutter`/`strobe` (+ Ranges `open`/`closed`/`strobe`) | Status-Kacheln + Speed-Slider + Fader im Intensity-Tab |
| Color Wheel | Attribut `color_wheel` + Ranges kind `color`/`open` | Farb-/Split-Kacheln + Fader |
| Auto-Farbwechsel | Range kind `rotate` am Farbrad | Hardware-/Software-Rotation |
| Gobos | Attribut `gobo_wheel` + Ranges kind `gobo` | Gobo-Tab + Icon-Kacheln |
| Gobo Shake | Ranges kind `shake` | Shake-Kacheln + Speed-Slider |
| Gobo-Wechsel | Range kind `rotate` am Gobo-Rad | Wechsel-Slider + Stopp |
| Gobo Effects | Attribut `gobo_fx` | Fader im Gobo-Tab |
| Reset | Attribut `reset` (+ Range kind `reset`) | Sicherer Button, kein Fader |

Modi (9ch vs. 11ch) sind regulaere `FixtureMode`-Eintraege — beim Patchen wird
der Modus gewaehlt, die Kanalnummern kommen vollstaendig aus der DB
(Details: [FIXTURE_LIBRARY.md](FIXTURE_LIBRARY.md)).

---

## 8. Auswirkungen auf bestehende Shows / Presets

- **Profil-Update ist in-place**: Profil-ID und Modusnamen bleiben erhalten,
  gepatchte ZQ02001 funktionieren weiter.
- Szenen/Snaps speichern Werte **pro Attribut** — `intensity`-/`shutter`-Werte
  landen nach der Korrektur automatisch auf den **richtigen** Kanaelen.
  (Wer vorher um den Tausch „herumprogrammiert" hat, also absichtlich Dimmer-
  Werte auf den Strobe-Fader gelegt hat, muss diese Looks einmal neu speichern.)
- Werte des alten Attributs `macro` (Auto/Sound, 11ch-CH10) werden nicht mehr
  angewendet (Kanal heisst jetzt `gobo_fx`); der alte Reset-Kanal war als
  zweiter `macro`-Kanal ohnehin **nie im Programmer sichtbar** (Attribut-Dedup).
- `tools/build_movinghead_show.py` nutzt die exakten neuen Werte; die Demo
  `shows/MovingHead_Demo.lshow` wurde neu generiert und self-verifiziert.

## 9. Manuelle Testschritte (Hardware)

1. ZQ02001 im 9-Kanal- und 11-Kanal-Modus patchen, Geraet entsprechend stellen.
2. Intensity-Tab: Dimmer hell/dunkel (CH6/CH8) — Strobe-Slider blitzt (CH5/CH7).
3. „Strobe aus (offen)"-Kachel: Licht an, kein Blitzen (DMX 250–255 prüfen).
4. Color-Tab: jede Farb-Kachel gegen die echte Radfarbe pruefen (insb. die
   Splits 80–139); Hardware-Rotation Start/Stopp + Tempo.
5. Software-Farbwechsel „Von Rot Bis Blau" und „Nur Split-Farben".
6. Gobo-Tab: Gobo 1–7 gegen die echten Muster pruefen; Shake-Speed innerhalb
   eines Blocks (z. B. 72 vs. 79) vergleichen; Gobo-Wechsel 128→255 wird schneller.
7. Reset-Button: Bestaetigung, Geraet rekalibriert, nach ~4 s normal steuerbar.
8. Pan/Tilt-Speed-Fader (CH7/CH9) veraendert die Bewegungsgeschwindigkeit
   (Annahme verifizieren!) und Gobo-FX-Fader (CH8/CH10) beobachten/dokumentieren.
