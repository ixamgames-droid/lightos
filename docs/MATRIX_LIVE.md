# LightOS – RGB-Matrix-Engine & Live-Programming

Referenz zur überarbeiteten Matrix-Engine (Initiative 2026-06, Phasen 1–6) und
zur **Live-Steuerung von Effekten über die virtuelle Konsole / MIDI**.
Bedien-Grundlagen stehen in [ANLEITUNG.md](ANLEITUNG.md), das Effekt-Kochbuch in
[EFFEKTE.md](EFFEKTE.md).

> **Schnellster Einstieg:** die fertige Demo-Show
> `shows/Live_Programming_Demo.lshow` laden (Generator:
> `tools/build_live_demo_show.py`). Sie zeigt alle neuen Algorithmen und die
> komplette Live-Bedienung auf einem APC-mini-Layout. Siehe Abschnitt 7.

---

## 1. Grundidee

Eine **RGB-Matrix** ist eine eigenständige Funktion (`FunctionType.RGBMatrix`).
Sie rendert pro Frame ein vollständiges Pixelbild (`cols × rows`) und schreibt
es auf die zugewiesenen Fixtures.

- **`fixture_grid`** – Liste der Länge `cols·rows` in **Zeilen-Reihenfolge**
  (Index `= row·cols + col`). Jeder Eintrag ist eine Fixture-ID **oder `None`**.
- **`None` = Lücke**: räumlich vorhanden, aber kein Gerät. Lücken werden
  - in der Vorschau **sichtbar leer** gezeichnet (gestrichelter Rahmen),
  - bei der Ausgabe **übersprungen** (kein DMX),
  - von **Fill/Random** nie ausgewählt (zählen nur „echte" Fixtures).
- **`drive_intensity`** – treibt die Matrix auch den Dimmer-/Intensitäts-Kanal?
  - `True`: Farbe **und** Helligkeit kommen aus dem Pixel → sofort sichtbar.
  - `False` (Default für neue Matrizen): **nur Farbe**; die Helligkeit bleibt
    frei für eine separate Dimmer-Ebene (Fader / Dimmer-Effekt). So lässt sich
    eine Matrix als reine Farb-Ebene mit einem Dimmer-Effekt kombinieren.
- **`intensity`** (Function-Master, 0..1) skaliert die gesamte Ausgabe und ist
  an einen VC-Fader bindbar (Modus *EffectIntensity*).

`_render(phase)` ist eine **reine Funktion**: gleiche Phase → gleiches Bild
(auch Random ist pro Phase deterministisch). Dadurch ist die Vorschau exakt das,
was ausgegeben wird.

---

## 2. Algorithmen-Katalog (17)

Bewusst konservativ konsolidiert: reine Richtungs-/Bewegungs-Varianten sind
**Parameter** eines Grundalgorithmus; eigenständige Texturen bleiben getrennt.

### Grundalgorithmen (parametrisch)

| Algorithmus | Beschreibung | wichtigste Parameter | Farben |
|---|---|---|---|
| **Plain** | Volle Fläche in Farbe 1 | – | 1 |
| **Chase** | Lauflicht | `axis` (H/V/Diag), `movement` (normal/bounce/center_out/outside_in), `runner_count`, `runner_width`, `fade` (Schweif), `color_cycle`, `invert` | 1 |
| **Wipe** | Wisch über die Matrix | `axis` (H/V), `movement`, `edge_fade` | 2 |
| **Wave** | Welle mit wählbarem Ursprung | `origin` (left/right/top/bottom/center/radial/diag), `density`, `spread` | 2 |
| **Gradient** | scrollender Farbverlauf über die Sequence | `axis` (H/V), `blend` (smooth/steps) | 2+ |
| **Rainbow** | Regenbogen (eigene HSV-Farben) | `movement` (linear/radial/center_out/outside_in), `spread`, `saturation`, `value` | 0 |
| **Fill** | füllt die Matrix anteilig | `level` (0–100 %, **live**), `fill_dir`, `edge` (hard/fade) | 2 |
| **Random** | Zufalls-Effekt (nur echte Fixtures) | `mode` (color/dimmer/strobe/flash/sparkle/pulse), `count`, `rate`, `scope` (all/row/col), `no_repeat`, `strobe_rate` | 3 |
| **ColorFade** | Crossfade durch die Sequence (deaktivierte Farben übersprungen) | `hold`, `pingpong` | 3 |
| **Strobe** | ganzes Feld blitzt | – | 1 |

### Texturen (eigenständig)

| Algorithmus | Beschreibung | Parameter | Farben |
|---|---|---|---|
| **Radar** | rotierender Radarstrahl | `beam_width`, `fade`, `invert` | 1 |
| **Spiral** | rotierender Spiralarm | `turns`, `beam_width`, `invert` | 1 |
| **SinePlasma** | Sinus-Plasma C1↔C2 | – | 2 |
| **Pinwheel** | rotierende Segmente | `runner_count` (Segment-Paare), `invert` | 2 |
| **Breathe** | Feld pulsiert | – | 1 |
| **Fire** | flackernder Flammen-Look | – | 2 |
| **Rain** | fallende Tropfen je Spalte | `fade` | 1 |

> Die Spalte **Farben** sagt, wie viele Farbfelder der Algorithmus auswertet
> (`AlgoMeta.colors`). Der Programmer zeigt nur so viele Farben an, wie wirklich
> wirken — z. B. keine Farbe bei Rainbow.

---

## 3. Parameter-UI (Programmer → RGB Matrix)

Die Parameter-Felder werden **dynamisch** aus den Metadaten (`rgb_matrix_meta.py`,
`ALGO_META`) gebaut — pro Algorithmus erscheinen nur die sinnvollen Parameter.

- Jeder Parameter hat Typ (`int`/`float`/`bool`/`select`), Default, Min/Max/Step
  und Tooltip. `select` → Dropdown, `bool` → Checkbox, Zahlen → Spinbox.
- **Pop-out**: Bei vielen Parametern (z. B. Chase) wird der Parameter-Bereich
  eng. Über **„⤢ Eigenes Fenster"** lassen sich die Parameter in ein eigenes,
  nicht-modales Fenster auslagern (zurück über denselben Knopf / Fenster
  schließen).

---

## 4. Farben: die ColorSequence

Das kanonische Farbmodell ist eine **ColorSequence** beliebiger Länge — kein
festes C1/C2/C3 mehr.

- Jeder Eintrag ist `[(r,g,b), aktiv]`; einzelne Farben lassen sich
  **deaktivieren** (ColorFade/Gradient überspringen sie).
- `active_index` = die aktuell „ausgewählte" Farbe (Ziel von Live-Farb-Pickern
  und `next/prev_color`).
- `color1/2/3` existieren weiter als **Kompatibilitäts-Properties** auf die
  ersten drei Einträge (für alte Shows, Tests, Show-Builder).

**ColorSequence-Editor** (Programmer, ab 2 Farben sichtbar): Liste + Toolbar
`＋ / ✕ / ✎ / ⊘ / ◀ / ▶` zum Hinzufügen, Löschen, Bearbeiten, Aktiv-Schalten und
Umsortieren.

---

## 5. Live-Programming über die virtuelle Konsole (Phase 6)

Der Kern ist **ein** gemeinsamer Dispatcher: `src/core/engine/effect_live.py`.
VC und MIDI greifen ausschließlich über ihn in laufende Effekte ein. Das Wissen,
*welche* Parameter ein Effekt hat und *wie* man sie setzt, liegt nur im Effekt
(`list_params` / `get_param` / `set_param` / `do_action`) — die Bedienelemente
kennen nur einen **Parameter-Key** bzw. einen **Aktions-Namen**.

**Ziel-Auflösung:** jedes Live-Bedienelement zielt entweder auf einen
**fest gebundenen Effekt** (`function_id`) **oder**, wenn leer, auf den
**aktiven Effekt** (zuletzt gestartet). So steuert ein Fader/Button automatisch
das, was gerade läuft.

### 5.1 Fader – Effekt-Parameter (Modus *EffectParam*)

- Eigenschaft `param_key` = der zu steuernde Parameter (z. B. `level`, `speed`,
  `count`, `rate`, `density`, `spread`, `hold`, `runner_count`).
- Der Fader (0–100 %) wird auf den **Wertebereich der ParamSpec** abgebildet:
  - `bool` → an/aus ab 50 %
  - `select` → gleichmäßig auf die Optionen
  - `int`/`float` → linear in `[min, max]`
- Mehrere IDs (kommagetrennt) = **Gruppen-Submaster** (steuert alle gleichzeitig).

> **„bei 0 wirklich stoppen" (Eigenschaft `effect_autostart`, alle EFFECT-Modi).**
> Standardmäßig **aus**: der Fader **regelt nur** — den Effekt separat per Taste
> (Modus *FunctionToggle*) starten; bei 0 läuft der Effekt mit Wert 0 weiter.
> Ist die Option **an**, **steuert der Fader auch An/Aus**: Wert > 0 startet den/die
> gebundenen Effekt(e) (falls noch nicht laufend), Wert 0 stoppt sie wirklich
> (wie ein Playback-Fader). Einstellbar pro Fader im Dialog *„Fader Einstellungen"*;
> braucht eine feste `function_id`/`function_ids` (bei „aktiver Effekt" wird nichts
> erzwungen). Gilt für *EffectIntensity*, *EffectSpeed* und *EffectParam*.

### 5.2 Buttons – Effekt-Aktionen (Aktion *EffectAction*)

`effect_action_key` ist einer von:

| Key | Wirkung |
|---|---|
| `add_color` | aktuelle/übergebene Farbe an die Sequence anhängen |
| `remove_color` | ausgewählte Farbe entfernen |
| `toggle_color` | ausgewählte Farbe aktiv/inaktiv |
| `next_color` / `prev_color` | Auswahl in der Sequence weiter/zurück |
| `reverse_direction` | Laufrichtung umkehren |
| `toggle_bounce` | Bewegung normal ↔ bounce |
| `freeze` / `unfreeze` / `toggle_freeze` | Animation einfrieren / fortsetzen |
| `clear_live_override` | Live-Änderungen verwerfen → Preset |
| `commit_live` | Live-Werte als neuen Preset übernehmen |
| `tap` | Tap-Tempo (globale BPM) |

### 5.3 Farb-Kachel – Live einfärben (Ziel *Effekt*)

Eine VCColor mit Ziel **„Effekt (aktive Farbe)"** setzt live die aktuell
ausgewählte Sequence-Farbe (oder legt die erste an) — Farbe wechseln, während
der Effekt weiterläuft.

### 5.4 Encoder – relative Feinsteuerung (*VCEncoder*)

Während der Fader **absolut** setzt, verstellt der Encoder einen numerischen
Parameter **relativ** (Drehen ohne Sprung) — ideal zum Feinjustieren des
**aktiven Effekts**, ohne dass ein voreingestellter Fader-Wert „springt".

- Eigenschaften: `param_key` (numerisch, z. B. `speed`, `count`, `density`),
  `function_id` (leer = aktiver Effekt), `step` (Schrittweite als Anteil des
  Wertebereichs).
- Bedienung: Maus-Drag hoch/runter oder Mausrad; intern
  `effect_live.adjust_param(key, ticks·step, fid)` (geklemmt).
- Anzeige: der Encoder zeigt stets den **aktuellen** Wert des Zielparameters.
- MIDI: zwei Modi — **Relativ** (Hardware-Encoder; CC 1..63 = +, 65..127 = −)
  oder **Absolut** (Poti/Fader; CC 0..127 → Wertebereich).

### 5.5 Live-Overrides vs. Preset (#17)

Live-Änderungen wirken **sofort**, verändern aber nur den laufenden Zustand:

- **`clear_live_override`** stellt den gespeicherten Preset wieder her
  (Animation läuft ohne Sprung weiter).
- **`commit_live`** übernimmt die Live-Werte bewusst als neuen Preset.
- In die Show gespeichert wird weiterhin nur beim bewussten **Speichern**.
- **`toggle_freeze`** friert die Animation ein (Ausgabe bleibt, Phase steht).

Sofort-Wirkung ohne Neustart, weil `_render` seine Parameter **jeden Frame
frisch** aus dem Parameter-State liest.

---

## 6. MIDI-Parität

Dieselben zwei Ziele stehen im MIDI-Mapper zur Verfügung (über denselben
Dispatcher), optional mit fester Effekt-ID via `@`:

| Ziel | Beispiel | Button-Modus |
|---|---|---|
| `effect_param:<key>[@<id>]` | `effect_param:level@6` | continuous (CC → 0..1 → Range) |
| `effect_action:<key>[@<id>]` | `effect_action:next_color` | flash (1× pro Druck) |

Ohne `@<id>` wirkt das Mapping auf den **aktiven Effekt**. Das löst auch die
früher fehlende „Tempo/Speed per MIDI"-Steuerung: `effect_param:speed` auf einen
CC legen.

---

## 7. Demo-Show (`Live_Programming_Demo.lshow`)

Bauen/aktualisieren: `venv/Scripts/python.exe tools/build_live_demo_show.py`.

**Aufbau:** 14 RGBW-PARs als **8×2-Matrix mit 2 bewussten Lücken**. APC-mini-Layout:

- **Untere Pad-Reihe (Notes 0–7):** die 8 Grund-/Neu-Algorithmen (Chase, Wipe,
  Wave, Gradient, Rainbow, Fill, Random, ColorFade) — **exklusiv** als
  FunctionToggle → wird der „aktive Effekt".
- **2. Reihe (Notes 8–13):** eigenständige Texturen (Radar, Fire, Rain, Spiral,
  Pinwheel, Breathe).
- **3. Reihe (Notes 16–23):** Live-Aktionen (Farbe +/−, + Farbe, Umkehren,
  Freeze, Reset Live, Commit, Tap) auf dem aktiven Effekt.
- **Obere Reihe (Notes 48–55):** Live-Farben → färben die aktive Sequence-Farbe.
- **Fader (CC 48–56):** Speed (aktiver Effekt), Fill-Level → Fill, Count/Rate →
  Random, Density → Wave, Spread → Rainbow, Hold → ColorFade, FX-Speed (global),
  Master.
- **Encoder (rechts):** Speed (aktiver Effekt) und Count → Random — relativ
  feinjustieren (Maus-Drag / Rad).

**So testen:** Effekt-Pad unten drücken → Fader/Buttons/Farben bewegen → wirkt
sofort live. Die zwei Matrix-Lücken bleiben in Vorschau und Ausgabe leer.

---

## 8. Rückwärtskompatibilität / Migration

Alte Shows mit den früheren ~29 Algorithmus-Namen werden beim Laden transparent
auf die neuen (Algorithmus, Parameter) abgebildet (`_LEGACY_ALGO_MAP` in
`apply_dict`, **vor** der Enum-Bildung — sonst `ValueError`). Beispiele:

| Alt | Neu |
|---|---|
| `Chase Horizontal/Vertical/Diagonal` | `Chase` + `axis` H/V/Diag |
| `Bounce H/V` | `Chase` + `movement: bounce` |
| `Center→Außen` / `Außen→Center` | `Chase` + `movement: center_out/outside_in` |
| `Komet Horizontal` | `Chase` + `fade` (Schweif) |
| `Chase Multicolor` | `Chase` + `color_cycle: true` |
| `Wipe Horizontal/Vertical` | `Wipe` + `axis` |
| `Welle Horizontal` / `Diagonal Welle` / `Ripple (Ringe)` | `Wave` + `origin` left/diag/radial |
| `Gradient Horizontal/Vertikal` | `Gradient` + `axis` |
| `Color Scroll` | `Gradient` + `blend: steps` |
| `Sparkle` | `Random` + `mode: sparkle` |

`drive_intensity` fehlt in Alt-Shows → wird als `True` geladen (bleibt hell).

---

### Siehe auch
- [EFFEKTE.md](EFFEKTE.md) – Effekte bauen & mit Geschwindigkeit steuern
- [ANLEITUNG.md](ANLEITUNG.md) – Oberfläche, Patchen, Gruppen, Programmer, MIDI
- [UMBAU_ROADMAP.md](UMBAU_ROADMAP.md) – größere Umbau-Initiative (Kontext)
