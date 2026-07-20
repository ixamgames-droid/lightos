# APC‑mini Test‑Show — Komplettes Hands‑on‑Handbuch

Diese Anleitung gehört zur Show **`shows/APC_Test_Komplett.lshow`** und ist auf
**deine reale Hardware** zugeschnitten:

- **4× Generic „Stage Light ZQ01424"** im **8‑Kanal‑RGBW‑Mode**
  (Universe 1, Adressen **1 / 9 / 17 / 25**)
- **Akai APC mini** (Original) als Hardware‑Controller der Virtual Console

Ziel der Show: **jeden Programmier‑Stil einmal anfassbar machen** und zeigen, wie
man sie **mischt** — Farben, Dimmer‑Effekte, RGB‑Matrix, fertige Looks, manuelles
RGBW‑Mischen per Fader und die fixture‑eigenen Auto‑Programme. Aufgeteilt auf
**5 umschaltbare Seiten**.

> Tiefer einsteigen?
> Oberfläche → [ANLEITUNG.md](ANLEITUNG.md) · Effekte/Speed → [EFFEKTE.md](EFFEKTE.md) ·
> Matrix live → [MATRIX_LIVE.md](MATRIX_LIVE.md) · Show‑Dateiformat →
> [SHOW_FILE_FORMAT.md](SHOW_FILE_FORMAT.md) · Praxis‑Workflows → [WORKFLOWS.md](WORKFLOWS.md).

---

## 1. Der Strahler: Kanal‑Belegung (8‑Kanal‑RGBW)

| Kanal (relativ) | Name        | Attribut    | Hinweis |
|-----------------|-------------|-------------|---------|
| 1 | Master Dimmer | `intensity` | 0 = aus, 255 = voll |
| 2 | Rot           | `color_r`   | |
| 3 | Grün          | `color_g`   | |
| 4 | Blau          | `color_b`   | |
| 5 | Weiß          | `color_w`   | |
| 6 | Strobe        | `shutter`   | **0 = Dauerlicht**, höhere Werte = Blitzen |
| 7 | Funktion      | `macro`     | eingebaute Auto‑/Sound‑Programme des Geräts |
| 8 | Funk.Speed    | `speed`     | Geschwindigkeit des Auto‑Programms |

**DMX‑Adressen der 4 PARs** (Universe 1):

| Fixture | Label | Start‑Adresse | Kanäle |
|---------|-------|---------------|--------|
| FID 1 | PAR 1 | 1  | 1–8   |
| FID 2 | PAR 2 | 9  | 9–16  |
| FID 3 | PAR 3 | 17 | 17–24 |
| FID 4 | PAR 4 | 25 | 25–32 |

Stelle an den Geräten denselben DMX‑Mode (8 Kanäle) und die Adressen 1/9/17/25 ein,
dann passt die Show 1:1.

---

## 2. Show laden & (neu) erzeugen

### Laden
1. **Playback → Show Manager** (oder Menü „Show öffnen") → `APC_Test_Komplett.lshow`.
2. **Eingabe/Ausgabe → MIDI**: APC mini als Eingang aktiv (Backend WinMM).
3. **Virtual Console**: oben **„APC LEDs"** einschalten → die Pads leuchten.
4. **Ausgabe → Konfiguration**: dein DMX‑Interface (Enttec/Art‑Net/sACN) auf Universe 1.

### Neu erzeugen (Generator)
Die Show wird vollständig aus einem Skript gebaut — reproduzierbar und in sich sauber:

```cmd
venv\Scripts\python tools\build_apc_test_show.py
```

Der Generator ruft zuerst `reset_show()` (komplett leere Basis), patcht dann die
4 PARs, baut alle Funktionen, die Bibliothek und die 5 VC‑Seiten und **verifiziert
am Ende durch erneutes Laden**. Du kannst dort Farben, Effekte und das Layout
anpassen und neu bauen.

---

## 3. Das Layering‑Prinzip (wichtig!)

Damit du verstehst, **warum sich Sachen mischen lassen**:

- **Grundhelligkeit (base_levels):** Die 4 PARs haben den **Dimmer fest auf 255**.
  Dadurch ist eine **reine Farbe sofort sichtbar** — du musst die Helligkeit nicht
  jedes Mal mitsetzen.
- **Farb‑Ebene (nur Farbe):** Die Farb‑Kacheln setzen **nur** Rot/Grün/Blau/Weiß,
  **nicht** die Helligkeit. → Farbe wählen, Effekt läuft in dieser Farbe weiter.
- **Dimmer‑Effekte (überschreiben):** Lauflicht/Pulse/Wave/Strobe setzen den
  **Dimmer pro Schritt selbst** (an = 255 / aus = 0) und **überschreiben** die
  Grundhelligkeit → **echtes Dunkelwerden**, sauberes Lauflicht.
- **Matrix‑Effekte (eigene Farbe):** RGB‑Matrix bringt ihre Farben selbst mit.
  → vor einem Matrix‑Effekt **„Clear"** drücken, sonst überschreibt die Farb‑Ebene.

Daraus folgt die Misch‑Logik:

| Kombination | Ergebnis |
|---|---|
| Farbe + Dimmer‑Effekt | farbiges Lauflicht / Pulsen / Strobe |
| Matrix (Clear) + Dimmer‑Effekt | bewegtes Farbmuster **mit** Helligkeits‑Chase |
| Farbe + Fader „Dimmer" (F6) | Farbe stufenlos bis 0 dimmen |
| RGBW‑Fader (Seite 5) | Farbe von Hand mischen |

---

## 4. Die APC mini als Controller

```
 Scene‑Tasten (rechts)  =  SEITE 1 … 8   (page_select)
 ┌───────────────────────────────────────────┐  ┌────┐
 │  8 × 8  Pad‑Grid   (Notes 0 … 63)          │  │ S1 │ → Seite 1  FARBEN
 │  Note 0  = unten links                     │  │ S2 │ → Seite 2  DIMMER
 │  Note 56 = oben  links                     │  │ S3 │ → Seite 3  MATRIX
 │  Reihe = note//8 , Spalte = note%8         │  │ S4 │ → Seite 4  MIX
 │                                            │  │ S5 │ → Seite 5  RGBW
 │                                            │  │ S6 │ → Seite 6  COLOR‑CHASE
 └───────────────────────────────────────────┘  └────┘
 ┌───────────────────────────────────────────┐
 │ Track‑Tasten (unten)                       │  Clear · Stop All
 └───────────────────────────────────────────┘  Blackout · Tap
   F1   F2   F3   F4   F5   F6   F7   F8   F9
  CC48 CC49 CC50 CC51 CC52 CC53 CC54 CC55 CC56   (9 Fader)
```

Im VC ist das Layout **maßstäblich wie der APC mini** aufgebaut (gleiches 8×8‑Raster,
Fader darunter) und beschriftet: oben steht die Controller‑Map, rechts neben dem
Grid eine **Scene‑Legende** (welche Scene‑Taste welche Seite öffnet). So siehst du
am Bildschirm direkt, welche Hardware‑Taste was tut.

**Notennummern je Modell** (Grid 0–63 und Fader CC48–56 sind bei beiden gleich):

| | Track‑Tasten (unten) | Scene‑Tasten (rechts) |
|---|---|---|
| **APC mini (Original, „APCmini")** | Notes 64–71 | Notes 82–89 |
| **APC mini mk2** | Notes 100–107 | Notes 112–119 |

Die mitgelieferte Show ist auf **mk2** eingestellt (Generator‑Konstante
`DEVICE = "mk2"` → Track‑Tasten 100–107). Für ein **Original** auf `"original"`
stellen und neu bauen. Die Seitenumschaltung (`page_select`) steckt global in
`data/midi_mappings.json` und ist auf die **mk2‑Scene‑Tasten 112–119** gemappt.

**Seitenwechsel (bidirektional):** Die **Scene‑Tasten rechts (Notes 112–119)**
schalten Seite 1–8 — und zwar **gleichzeitig auf der Hardware und im VC**:
- Drückst du am APC eine Scene‑Taste → der VC springt auf die passende Bank, und
  die **LED der aktiven Scene‑Taste leuchtet** (die anderen aus).
- Wechselst du im VC mit den **◀ ▶**‑Knöpfen → die APC‑LED zieht automatisch nach.

So navigierst du live ohne Hinsehen. (Verifiziert: Note 112→Seite 1 … 117→Seite 6.)

**Immer aktiv (auf jeder Seite):**

| Element | MIDI (mk2) | Funktion |
|---|---|---|
| Track 1 | Note 100 | **Clear** (Programmer/Farbe freigeben) |
| Track 2 | Note 101 | **Stop All** (alle Effekte stoppen) |
| Track 3 | Note 102 | **Blackout** |
| Track 4 | Note 103 | **Tap** (Tempo tippen) |
| Fader **F6** | CC53 | **Dimmer** (Grundhelligkeit aller PARs, bis 0) |
| Fader **F7** | CC54 | **Speed global** (Tempo aller laufenden Effekte) |
| Fader **F9** | CC56 | **Grand Master** |

(Original: Track‑Tasten = Notes 64–67. Faders identisch.)

---

## 5. Die 6 Seiten im Detail

Pad‑Reihen von **oben (Reihe 7) nach unten (Reihe 0)**.

### Seite 1 — FARBEN & LOOKS  (Scene‑Taste 1)

| Reihe | Notes | Inhalt |
|---|---|---|
| 7 | 56–63 | **Farben:** Rot · Grün · Blau · Weiß · Amber · Cyan · Magenta · Warmweiß |
| 6 | 48–55 | **Farben:** Orange · Pink · Türkis · Violett · Hellblau · Limette · Rosa · Gelb |
| 5 | 40–47 | **Looks (Szenen):** Warm Wash · Cold Wash · Sonnenuntergang · Ozean · Wald · Party · Kerzenlicht · Vollweiß |
| 4 | 32–37 | **Looks aus der Bibliothek** (Library‑Snaps, dieselben 6 Looks) |
| 0 | 0–1 | **Farb‑Chaser:** Color‑Chase · Police |

> Die Farb‑Kacheln setzen **nur** Farbe → sofort sichtbar dank Grundhelligkeit.
> Tipp: hier Farbe wählen, dann auf Seite 2 einen Dimmer‑Effekt starten.

### Seite 2 — DIMMER‑EFFEKTE  (Scene‑Taste 2)

| Reihe | Notes | Inhalt |
|---|---|---|
| 7 | 56–61 | 6 Farb‑Kacheln (zum direkten Einfärben des Effekts) |
| 1 | 8–9   | Ping‑Pong · 2er‑Chase |
| 0 | 0–7   | Lauflicht ▶ · Lauflicht ◀ · Pulse · Wave · Strobe · Build‑Up · Random · Full |

**Fader:** F1 = Speed Lauflicht · F2 = Speed Pulse · F3 = Speed Wave ·
F4 = Speed Strobe · **F5 = FX‑Level** (Helligkeit **aller** Dimmer‑Effekte).

> Diese Effekte **überschreiben** die Grundhelligkeit → echtes Lauflicht.
> Farbe oben wählen → der Effekt läuft in dieser Farbe.

### Seite 3 — MATRIX (eigene Farben)  (Scene‑Taste 3)

| Reihe | Notes | Inhalt |
|---|---|---|
| 1 | 8–12 | Atmen · Color‑Fade · Plasma · Windrad · Strobe |
| 0 | 0–7  | Regenbogen · Lauflicht · Wipe · Gradient · Radar · Feuer · Regen · Sparkle |

**Fader:** **F8 = Matrix‑Master** (Helligkeit aller Matrix‑Effekte), F7 = Speed global.

> Matrix bringt die Farbe selbst mit → **vorher „Clear" (Track 1) drücken**,
> sonst überschreibt eine aktive Farb‑Ebene das Muster.

### Seite 4 — MIX & KOMBINATIONEN  (Scene‑Taste 4)

| Reihe | Notes | Inhalt |
|---|---|---|
| 7 | 56–61 | 6 Farb‑Kacheln |
| 2 | 16–19 | Matrix: Regenbogen · Lauflicht · Feuer · Radar |
| 1 | 8–11  | Looks: Warm Wash · Cold Wash · Sonnenuntergang · Ozean |
| 0 | 0–3   | Dimmer: Lauflicht · Pulse · Wave · Strobe |

**Fader:** F1 = Speed Lauflicht · F5 = FX‑Level · F8 = Matrix‑Master.

> **Die „Spiel"‑Seite:** Farbe (oben) **+** Dimmer‑Effekt (unten) = farbiges
> Lauflicht. Matrix (Clear) **+** Dimmer‑Effekt = bewegtes Farbmuster mit
> Helligkeits‑Chase. Probiere alle Kombinationen aus.
>
> **Musst du zum Mischen die Seite wechseln?** Nein. Laufende Effekte **bleiben
> aktiv, wenn du die Seite wechselst** — der Seitenwechsel ändert nur, welche Pads
> gerade leuchten/reagieren, nicht was läuft. Du kannst also auf Seite 2 ein
> Lauflicht starten, auf Seite 3 wechseln und eine Matrix dazuschalten — beides
> läuft übereinander. Seite 4 bündelt die wichtigsten Mischpartner nur bequem auf
> **einer** Seite.

### Seite 5 — RGBW VON HAND + FIXTURE‑PROGRAMME  (Scene‑Taste 5)

| Reihe | Notes | Inhalt |
|---|---|---|
| 7 | 56–63 | 8 Farb‑Kacheln (Schnellwahl) |
| 0 | 0–2   | **Fixt‑Strobe** (Shutter‑Kanal) · **Auto‑Programm** (Makro‑Kanal) · Full |

**Fader:** F1 = Rot · F2 = Grün · F3 = Blau · F4 = Weiß · **F5 = Intensität**
(Programmer, wirkt auf alle PARs).

> Hier mischst du Farbe **stufenlos von Hand**. Pad 1 testet das **fixture‑eigene
> Strobe**, Pad 2 das **eingebaute Auto‑Programm** des Geräts — die genauen
> Wertebereiche sind geräteabhängig, also ruhig mit den Werten experimentieren.

### Seite 6 — LIVE COLOR‑CHASE  (Scene‑Taste 6)

Hier baust du **live** einen Farb‑Chase: du wählst Farben an, der Effekt läuft
dann durch **genau diese** Farben.

| Reihe | Notes | Inhalt |
|---|---|---|
| 7 | 56–63 | **Farb‑Pads** (Rot · Orange · Gelb · Grün · Cyan · Blau · Violett · Magenta) |
| 6 | 48–52 | **Farb‑Pads** (Pink · Türkis · Limette · Warmweiß · Weiß) |
| 0 | 0–3 | **Start/Stop** · **Clear Chase** · **Farbe −** · **Farbe +** |

**Fader:** **F1 = Speed** (wie schnell die Farben wechseln) · **F2 = Übergang**
(0 = weiches Faden, hoch = Farbe hält und wechselt dann schnell).

**So programmierst du live:**
1. **Clear Chase** (Pad 2) drücken → Farbliste ist leer.
2. Oben die gewünschten **Farben der Reihe nach antippen** → jede landet hinten in
   der Liste (z. B. Rot, dann Blau, dann Weiß = 3‑Farben‑Chase).
3. **Start** (Pad 1) → der Chase läuft durch genau diese Farben.
4. **F1/F2** justieren Tempo und Härte des Übergangs. **Farbe +/−** springt manuell
   eine Farbe weiter/zurück.

> Technik: Das ist eine RGB‑Matrix vom Typ **Color‑Fade**, deren Farbliste
> („Color‑Sequence") live wächst. Die Farb‑Pads stehen im Modus
> **„Effekt (Farbe hinzufügen)"** und sind auf die Funktion *Live Color‑Chase*
> gebunden. So kannst du dir **eigene** Color‑Chase‑Bereiche bauen (s. §6b).

---

## 6. Programmier‑Stile — was die Show alles zeigt

| Stil | Wo | Technik in LightOS |
|---|---|---|
| **Statische Farbe** | Seite 1/5, Farb‑Kacheln | VCColor (nur Farb‑Ebene) |
| **Fertiger Look** | Seite 1, Reihe 5 | Scene (Farbe + Dimmer) |
| **Bibliothek/Snaps** | Seite 1, Reihe 4 | Library‑Snaps (Ordner *Farben* / *Looks*) |
| **Dimmer‑Chase** | Seite 2 | Chaser aus Dimmer‑Szenen |
| **Dimmer‑Modulation** | Seite 2 | Carousel (Pulse/Wave) |
| **Strobe** | Seite 2 | schneller 2‑Schritt‑Chaser |
| **Farb‑Chase** | Seite 1 | Chaser aus Farb‑Szenen |
| **RGB‑Matrix** (13 Algorithmen) | Seite 3 | RGB‑Matrix über die 4er‑Gruppe |
| **Mischen** | Seite 4 | Layer kombinieren (Farbe/Matrix + Dimmer) |
| **Manuelles RGBW** | Seite 5 | VCSlider im Programmer‑Modus |
| **Geräte‑Makro/Strobe** | Seite 5 | Szene auf Kanal 6/7/8 |
| **Live‑Color‑Chase** | Seite 6 | Color‑Fade‑Matrix mit live gebauter Farbliste |

**Enthaltene Funktionen (54):**
9 Chaser, 2 Carousel (EFX), 14 RGB‑Matrix (inkl. *Live Color‑Chase*), 29 Szenen.
**Bibliothek:** 12 Farb‑Snaps + 6 Look‑Snaps.

---

## 6b. Eigenen Color‑Chase‑Bereich bauen (für jede Show)

Du kannst dir das Live‑Bauen überall selbst einrichten — ein „Baukasten" aus
Farb‑Pads + Fadern, gebunden an eine Color‑Fade‑Funktion:

1. **Funktion anlegen:** *Geräte & Funktionen → RGB Matrix → Neu*, Algorithmus
   **„Color Fade"**, deine Strahler als Grid. Merke dir die Funktions‑ID.
2. **Farb‑Pads:** In der Virtual Console Farb‑Kacheln anlegen → Rechtsklick →
   *Einstellungen* → **Ziel = „Effekt (Farbe hinzufügen)"** und **Effekt‑ID** =
   die Funktions‑ID. Jeder Druck hängt die Farbe an die Chase‑Liste an.
3. **Steuer‑Tasten:** Ein Button mit *Aktion = EffectAction* und
   **effect_action_key = `clear_colors`** leert die Liste; `next_color` /
   `prev_color` springen manuell. Ein **Funktions‑Toggle** auf dieselbe ID
   startet/stoppt den Chase.
4. **Fader:** Ein Slider im Modus **EffectSpeed** (Tempo) und einer im Modus
   **EffectParam** mit **param_key = `hold`** (Übergang) auf die Funktions‑ID.
5. **MIDI:** Allen Elementen per Rechtsklick → *MIDI lernen* eine APC‑Taste/‑Fader
   zuweisen. Auf eine eigene **Bank** legen = eine eigene APC‑Seite.

> Genau so ist **Seite 6** der mitgelieferten Show aufgebaut.
>
> ⚠ **Stand 2026‑07:** Die früher hier empfohlenen Editor‑Baukasten‑Knöpfe (🎨 Color‑Chase /
> ⌗ Controller / 🟦 Chase‑Bereich) gibt es in der VC **nicht mehr**. Den Chase baust du wie oben
> Schritt für Schritt oder über die aktuelle Widget‑/Effekt‑Erstellung — siehe
> [anleitung_vc/ANLEITUNG_VC.md](anleitung_vc/ANLEITUNG_VC.md).

---

## 7. Schnellstart‑Rezepte

1. **Einfarbiges Standlicht:** Seite 1 → Farbe drücken. Fertig (Helligkeit über F6).
2. **Farbiges Lauflicht:** Seite 1 → z. B. *Blau* → Seite 2 → *Lauflicht ▶* →
   Speed mit F1 regeln.
3. **Bewegtes Regenbogen‑Muster:** Seite 3 → *Clear* (Track 1) → *Regenbogen* →
   Tempo mit F7, Helligkeit mit F8.
4. **Regenbogen + Pulsieren:** Seite 4 → *Clear* → Matrix *Regenbogen* (Reihe 2) →
   Dimmer *Pulse* (Reihe 0). Beides läuft übereinander.
5. **Hand‑Mix:** Seite 5 → F1–F4 für R/G/B/W schieben, F5 = Helligkeit.
6. **Live‑Color‑Chase:** Seite 6 → *Clear Chase* → z. B. *Rot*, *Blau*, *Weiß*
   antippen → *Start* → mit F1 (Speed) und F2 (Übergang) formen.
7. **Panik:** *Blackout* (Track 3) oder *Stop All* (Track 2).

---

## 8. „Neue Show" — keine Artefakte mehr

Beim Anlegen einer **neuen Show** (Menü „Neue Show" / `reset_show()`) wird jetzt
**alles** der alten Show entfernt: Patch, Fixture‑Gruppen, Programmer,
Grundhelligkeit, Paletten, Kurven, **alle Funktionen**, die Snap‑Bibliothek, EFX,
RGB‑Matrix, Virtual Console, Snapshots und Visualizer‑Positionen.

> **Fix in dieser Runde:** Zusätzlich werden jetzt **alle DMX‑Universe‑Puffer
> genullt**. Vorher konnte es passieren, dass nach „Neue Show" der Output‑Thread
> weiter die **alten** Kanalwerte sendete (z. B. blieb der Dimmer der Strahler auf
> 255), weil ein leerer Patch keinen Default‑Frame mehr hat. Jetzt ist nach
> „Neue Show" garantiert alles dunkel und sauber. (Datei `src/core/show/show_file.py`,
> Funktion `reset_show`; abgesichert über `tests/test_show_file.py`.)

---

## 9. Troubleshooting

| Problem | Ursache / Lösung |
|---|---|
| Pads leuchten nicht | VC → **„APC LEDs"** einschalten; APC mini als MIDI‑Eingang aktiv |
| Weiße/Warmweiß‑Kachel bleibt dunkel | mit aktuellem Build behoben — der **Weiß‑Kanal** wird jetzt in die LED‑Farbe eingerechnet (vorher zeigte eine reine W‑Kachel „aus") |
| Fader unten abgeschnitten | mit aktuellem Build behoben — kompaktes Layout, alle 9 Fader liegen im sichtbaren Bereich (< 800 px); ggf. Show neu laden |
| Pad/Taste reagiert nicht | falsches Modell? Track/Scene‑Notennummern prüfen (Original vs. mk2, s. §4) oder per **„MIDI lernen"** neu zuweisen |
| Farbe nicht sichtbar | Dimmer (F6) oder Grand Master (F9) hoch; ggf. *Clear* |
| Matrix zeigt falsche Farbe | vorher **Clear** drücken (aktive Farb‑Ebene überschreibt Matrix) |
| Color‑Chase zeigt nur 1 Farbe | *Clear Chase* drücken, dann mehrere Farb‑Pads nacheinander antippen |
| Effekt zu schnell/langsam | Speed‑Fader (F1–F4 pro Effekt, F7 global) |
| Strobe blitzt dauerhaft | Strobe‑Effekt mit *Stop All* beenden; Kanal 6 (Shutter) zurück auf 0 |
| Strahler bleibt nach „Neue Show" an | mit aktuellem Build behoben (siehe §8) — App neu starten, Show neu bauen |
| Seitenwechsel reagiert nicht | Scene‑Tasten prüfen (Original 82–89 / mk2 112–119); alternativ ◀ ▶ in der VC‑Toolbar |
| Effekte mischen ohne Seitenwechsel | nutze **Seite 4 (MIX)** — dort liegen Farben, Dimmer‑ und Matrix‑Effekte gemeinsam, du musst die Seite nicht wechseln |

---

## 10. Datei‑Überblick

| Datei | Zweck |
|---|---|
| `shows/APC_Test_Komplett.lshow` | die fertige Show |
| `tools/build_apc_test_show.py` | Generator (reproduzierbar, anpassbar) |
| `tools/render_apc_pages.py` | rendert jede Seite als PNG (für die Übersicht) |
| `docs/APC_TEST_SHOW.md` | dieses Handbuch (Referenz) |
| `docs/APC_SCHRITT_FUER_SCHRITT.md` | Schritt‑für‑Schritt‑Tutorial |
| `docs/APC_SEITEN_UEBERSICHT.md` | Seiten‑Bilder + „welche Taste tut was" |
| `docs/images/apc_page_*.png` | gerenderte Seiten‑Screenshots |
| `src/ui/virtualconsole/controller_templates.py` | Editor‑Bausteine (Controller‑Vorlage, Color‑Chase‑Kit) |
| `data/midi_mappings.json` | globale MIDI‑Bindungen (Seitenwechsel) |

*Stand: 2026‑06‑08*
