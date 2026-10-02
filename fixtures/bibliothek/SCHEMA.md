# LightOS-Profil — Format der eigenen Geräte-Bibliothek (FM-56)

> **Herkunft und Lizenz — zuerst lesen.**
> LightOS liefert eine **eigene** Geräte-Bibliothek mit. Ein Profil darf aus genau
> drei Quellen entstehen, und **jede Datei sagt im Pflichtfeld `herkunft`, woher sie
> stammt**:
>
> 1. **Selbst geschrieben aus Herstellerangaben** (Bedienungsanleitung, DMX-Tabelle,
>    Datenblatt) oder aus dem LightOS-Bestand — `herkunft.art` = `hersteller-handbuch`
>    bzw. `lightos`, `lizenz` = `eigen`. Aus dem Handbuch werden nur **Fakten**
>    übernommen (Kanalbelegung, Wertebereiche), keine Texte oder Bilder.
> 2. **Aus einer QLC+-Gerätedefinition (`.qxf`) umgebaut** — QLC+ steht unter der
>    Apache License 2.0. `art` = `qlcplus`, `lizenz` = `Apache-2.0`.
> 3. **Aus einem Profil der Open Fixture Library umgebaut** — OFL steht unter der
>    MIT-Lizenz. `art` = `ofl`, `lizenz` = `MIT`.
>
> Bei 2. und 3. sind `urheber`, `original` (Pfad/URL der Originaldatei) und
> `geaendert` (was LightOS umgebaut hat) **Pflicht** — Apache-2.0 §4(b) verlangt,
> geänderte Dateien zu kennzeichnen, §4(c) und MIT verlangen die Urhebernennung.
> Die Lizenztexte liegen unter [`licenses/`](../../licenses/), der Abschnitt
> „Geräte-Bibliothek“ in [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)
> verweist darauf. **Inhalte aus anderen Quellen (z. B. GDTF-Share, Hersteller-
> Profildateien mit eigener Lizenz) nur nach ausdrücklicher Klärung.** Eine Datei
> ohne Lizenzangabe besteht den Wächter nicht.

## Ablage

- Eine Datei je Gerät: `fixtures/bibliothek/<hersteller>/<modell>.json`.
- Dateinamen: ASCII, klein, Bindestriche — Umlaute werden umschrieben (`ß` → `ss`,
  `ä` → `ae`), `+` → `-plus-`, alles andere außer `a-z0-9` → `-`. Den Pfad liefert
  `python tools/bibliothek_profil.py pfad --hersteller "…" --modell "…"`.
- Hersteller + Modell kommen in der Bibliothek **genau einmal** vor.
- Ordner mit `_` am Anfang gehören nicht zur ausgelieferten Bibliothek:
  `_beispiele/` enthält drei Muster, die aus eingebauten Profilen konvertiert sind.
- Kodierung UTF-8. Schreibweise wie `tools/bibliothek_profil.py` sie erzeugt
  (eingerückt, einfache Objekte auf einer Zeile); das ist Konvention, keine Pflicht.

## Prüfen

```bash
./venv/bin/python tools/bibliothek_profil.py pruefen              # ganze Bibliothek
./venv/bin/python tools/bibliothek_profil.py pruefen datei.json   # einzelne Dateien
./tools/verify_loop.sh tests/test_fm56_bibliothek_waechter.py      # Wächter-Test
```

Jeder Befund nennt Datei und Feld, z. B.
`u-king/x.json: modi[0] ('9-Kanal').kanaele[3] (Kanal 4).attribut: unbekannt 'red'`.
Unbekannte Felder sind ein Fehler (Tippfehler fallen so auf).

## Felder

### Kopf

| Feld | Pflicht | Inhalt |
|---|---|---|
| `format_version` | ja | `1` |
| `hersteller` | ja | Herstellername wie auf dem Gerät (`"Stairville"`) |
| `hersteller_kurz` | nein | Kürzel ≤ 20 Zeichen (`"STAIR"`); fehlt es, wird es abgeleitet |
| `modell` | ja | Modellname (≤ 120 Zeichen) |
| `kurzname` | ja | Kurzname ≤ 40 Zeichen, Großbuchstaben üblich (`"LEDPAR56"`) |
| `typ` | ja | Gerätetyp, siehe Liste unten |
| `leistung_w` | nein | Leistungsaufnahme in Watt (ganze Zahl, Default 0) |
| `notizen` | nein | freier Text (Annahmen, Besonderheiten) |
| `viz_model` | nein | 3D-Modell-Override (leer = Automatik) |
| `quelle` | ja | `{"titel", "version"?, "datum"?, "url"?}` — Handbuch-Titel, Version, Datum, URL des Herstellers. Nur Herkunftsangabe; `titel` ist Pflicht |
| `herkunft` | ja | `{"art", "lizenz", "urheber"?, "original"?, "geaendert"?}` — siehe Kasten oben. `art`: `lightos` · `hersteller-handbuch` · `qlcplus` · `ofl`; `lizenz`: `eigen` (lightos/handbuch) · `Apache-2.0` (qlcplus) · `MIT` (ofl) |
| `autor` | ja | wer die Datei geschrieben hat (`"LightOS"`) |
| `geprueft` | ja | `{"ok": true/false, "wie": "…"}` — `ok` nur, wenn am echten Gerät oder gegen das Handbuch Kanal für Kanal geprüft; `wie` sagt, wie |
| `modi` | ja | Liste der DMX-Modi (mindestens einer) |

### Modus (`modi[]`)

| Feld | Pflicht | Inhalt |
|---|---|---|
| `name` | ja | Modusname, eindeutig im Profil (`"9-Kanal"`, ≤ 80 Zeichen). Patches hängen am Namen — später nicht leichtfertig umbenennen |
| `beschreibung` | nein | Text |
| `raster` | nein | `{"rows", "cols"}` — physische Rasterform der Pixel/Zonen (VIZ-50a), z. B. 4×12. Fehlt es, rät der Renderer |
| `weiss` | nein | `{"rows", "cols"}` — Form der **eigenen** Weiß-Leiste neben dem Farbraster (CDX-52). Nur angeben, was die Kanäle nicht sagen: eine Reihe quer = `{"rows": 1, "cols": 0}`, die Zahl kommt aus den `color_w`-Kanälen |
| `kanaele` | ja | Kanäle **in DMX-Reihenfolge** (Kanal 1 zuerst); die Kanalzahl ist die Länge der Liste |

### Kanal (`kanaele[]`)

| Feld | Pflicht | Inhalt |
|---|---|---|
| `name` | ja | Anzeigename (≤ 80 Zeichen) |
| `attribut` | ja | genau ein Name aus der Attribut-Liste unten |
| `default` | ja | Grundwert 0..255 (Pan/Tilt 128, Dimmer/Strobe 0, Shutter auf „offen“) |
| `highlight` | ja | Wert beim Highlight 0..255 (Dimmer/Farbe 255, Shutter 0 oder offen) |
| `invert` | nein | `true`, wenn der Kanal umgekehrt läuft |
| `aufloesung` | nein | `"8bit"` (Default) oder `"16bit"` |
| `segment` | nein | nur an Dimmer-Kanälen (`intensity`/`dimmer`/`master`): welches eigene Weiß-Segment dieser Dimmer dimmt, **0-basiert** = Index unter den `color_w`-Kanälen des Modus (FM-46). Nur setzen, wenn das Handbuch es sagt |
| `bereiche` | nein | Wertebereiche, siehe unten |

### Bereich (`bereiche[]`)

| Feld | Pflicht | Inhalt |
|---|---|---|
| `von`, `bis` | ja | 0 ≤ von ≤ bis ≤ 255 |
| `name` | ja | Beschriftung (`"Gobo 3 (Spirale)"`) |
| `art` | nein | Art des Bereichs, siehe Liste. Fehlt sie, wird sie aus dem Namen abgeleitet (wie bei den eingebauten Profilen); besser ausdrücklich angeben |

Erst Bereiche mit `art` erzeugen in der Bedienung Farb-/Gobo-/Strobe-/Offen-Kacheln.

## Listen

### Gerätetypen (`typ`)

| Wert | Bedeutung |
|---|---|
| `dimmer` | reiner Dimmer / Dimmerpack |
| `par` | PAR / Wash ohne Bewegung (LED-PAR, Flood, Blinder mit einer Zelle) |
| `led_bar` | Leiste mit mehreren Segmenten (LED-Bar, Pixel-Bar) |
| `moving_head` | Moving Head (Spot, Beam, Wash), auch Mehrkopf-Mover |
| `scanner` | Scanner (Spiegel) |
| `strobe` | Stroboskop |
| `laser` | Laser |
| `matrix` | Pixel-Panel / Matrix (Rasterform im Modus angeben) |
| `smoke` | Nebelmaschine |
| `hazer` | Hazer / Dunst |
| `other` | alles andere |

### Attribute (`attribut`)

Exakt diese Namen — andere kennt LightOS nicht (Programmer-Tabs, Farbmischung,
Renderer hängen daran). Gibt es kein passendes, `raw`.

| Attribut | Bedeutung |
|---|---|
| `intensity` | Dimmer / Helligkeit (Master des Geraets oder eines Kopfes) |
| `dimmer` | Dimmer (gleichwertig zu intensity; bevorzugt intensity) |
| `master` | Master-Dimmer (gleichwertig zu intensity) |
| `shutter` | Shutter/Strobe-Kanal mit Offen-/Zu-/Strobe-Bereichen |
| `strobe` | reine Strobe-Geschwindigkeit (ohne Shutter-Funktion) |
| `duration` | Blitzdauer (Stroboskope) |
| `color_r` | Rot |
| `color_g` | Gruen |
| `color_b` | Blau |
| `color_w` | Weiss (auch Warm-/Kaltweiss; eigene Weiss-Achse siehe weiss) |
| `color_a` | Amber |
| `color_uv` | UV |
| `cmy_c` | CMY Cyan |
| `cmy_m` | CMY Magenta |
| `cmy_y` | CMY Gelb |
| `color_wheel` | Farbrad (Bereiche mit art color/open/rotate) |
| `pan` | Pan grob |
| `pan_fine` | Pan fein (16 bit) |
| `tilt` | Tilt grob |
| `tilt_fine` | Tilt fein (16 bit) |
| `zoom` | Zoom |
| `focus` | Fokus |
| `frost` | Frost |
| `iris` | Iris |
| `prism` | Prisma ein/aus bzw. Auswahl |
| `prism_rotation` | Prisma-Rotation |
| `gobo_wheel` | Gobo-Rad (Bereiche mit art gobo/open/shake/rotate) |
| `gobo_wheel2` | zweites Gobo-Rad desselben Geraets |
| `gobo_rotation` | Gobo-Rotation / Index |
| `gobo_fx` | Gobo-Effekt (z. B. Animationsrad-Funktion) |
| `animation` | Animationsrad |
| `speed` | Bewegungs-/Funktionsgeschwindigkeit |
| `effect_speed` | Effekt-/Programmgeschwindigkeit |
| `effect` | Effekt-Auswahl |
| `macro` | Makro / Auto-Programm / Farbmakro |
| `fan` | Luefter (Nebelmaschine) |
| `reset` | Reset / Steuerkanal mit Reset-Bereich |
| `lamp` | Lampe an/aus |
| `raw` | alles, was in keine Klasse passt (nur Fader, keine Logik) |
| `laser_boundary` | Laser: Begrenzung |
| `laser_bank` | Laser: Musterbank |
| `laser_x` | Laser: X-Position |
| `laser_y` | Laser: Y-Position |
| `laser_zoom_x` | Laser: Zoom X |
| `laser_zoom_y` | Laser: Zoom Y |
| `laser_color` | Laser: Farbe |
| `laser_color_change` | Laser: Farbwechsel |
| `laser_dots` | Laser: Punkte |
| `laser_draw` | Laser: Zeichnen |
| `laser_draw_mode` | Laser: Zeichenmodus |
| `laser_twist` | Laser: Verdrehung |
| `laser_grating` | Laser: Gitter |
| `laser_scan_rate` | Laser: Scanrate |

### Bereichs-Arten (`art`)

| Wert | Bedeutung |
|---|---|
| `""` | unbekannt / nur Beschriftung |
| `open` | offen (Shutter offen, Weiss/offen auf Farb- oder Gobo-Rad) |
| `closed` | geschlossen / Blackout |
| `strobe` | Strobe |
| `color` | eine Farbe auf dem Farbrad |
| `gobo` | ein Gobo |
| `rotate` | Rotation / Durchlauf (Rad- oder Gobo-Rotation) |
| `shake` | Gobo-Shake |
| `sound` | Musiksteuerung |
| `reset` | Reset |
| `frost` | Frost |
| `prism` | Prisma |

Faustregeln (aus `docs/FIXTURE_LIBRARY.md`, Abschnitt 5): Reset-Kanäle als `reset`,
nie als zweites `macro`; zwei Gobo-Räder als `gobo_wheel` + `gobo_wheel2`; ein
Shutter-Kanal mit Offen-Bereich bekommt `art` `open`, damit „offen“ gefunden wird.

## Beispiel

```json
{
  "format_version": 1,
  "hersteller": "Testwerk",
  "modell": "Par 7",
  "kurzname": "PAR7",
  "typ": "par",
  "leistung_w": 70,
  "quelle": {"titel": "Bedienungsanleitung Par 7", "version": "1.2", "datum": "2026-01-01", "url": "https://example.invalid/par7.pdf"},
  "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
  "autor": "LightOS",
  "geprueft": {"ok": false, "wie": "nur Handbuch"},
  "modi": [
    {
      "name": "5-Kanal",
      "kanaele": [
        {"name": "Dimmer", "attribut": "intensity", "default": 0, "highlight": 255},
        {"name": "Rot", "attribut": "color_r", "default": 0, "highlight": 255},
        {"name": "Gruen", "attribut": "color_g", "default": 0, "highlight": 255},
        {"name": "Blau", "attribut": "color_b", "default": 0, "highlight": 255},
        {
          "name": "Strobe",
          "attribut": "shutter",
          "default": 0,
          "highlight": 0,
          "bereiche": [
            {"von": 0, "bis": 9, "name": "Offen", "art": "open"},
            {"von": 10, "bis": 255, "name": "Strobe langsam → schnell", "art": "strobe"}
          ]
        }
      ]
    }
  ]
}
```

Weitere Muster: `_beispiele/generic/led-par-dimmer-plus-rgb-4ch.json` (PAR),
`_beispiele/generic/moving-head-spot-16ch.json` (Moving Head mit Farb-/Gobo-Rad),
`_beispiele/u-king/zq06121-led-balken-768-stage-light.json` (Raster + eigene Weiß-Leiste).

Herkunft einer aus QLC+ umgebauten Datei (vom Konverter
`tools/bibliothek_profil.py qxf` gesetzt):

```json
"herkunft": {
  "art": "qlcplus",
  "lizenz": "Apache-2.0",
  "urheber": "QLC+-Beitragende (Heikki Junnila, Massimo Callegari u. a.); Datei: Q Light Controller Plus 4.12.0 · <Autor>",
  "original": "resources/fixtures/<Hersteller>/<Datei>.qxf",
  "geaendert": "ins LightOS-Format umgebaut (JSON statt QXF); Kanal-Attribute auf LightOS-Namen abgebildet; …"
}
```

## Was beim Start passiert

`fixture_db.ensure_builtins()` spielt alle Dateien (ohne `_beispiele/`) mit
`source = "lightos"` in die Fixture-DB — nur wenn sich eine Datei seit dem letzten
Lauf geändert hat (Stempel je Datei). Neu → anlegen; geändert → Kopf und Modi aus
der Datei neu aufbauen (Profil-ID bleibt); ungültig → gemeldet, übersprungen, der
Start läuft weiter. Gibt es Hersteller + Modell schon mit anderer Herkunft
(eingebaut, eigenes Profil, QLC+-Import), bleibt die Datei draußen — nichts wird
doppelt angelegt, nichts überschrieben. Die vollständige Herkunft steht danach auch
in der DB (`FixtureProfile.herkunft`); ein Export erfindet nie „eigen“. Code: `src/core/database/bibliothek_format.py`.
