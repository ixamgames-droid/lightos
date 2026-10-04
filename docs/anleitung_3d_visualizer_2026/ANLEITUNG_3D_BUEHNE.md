# 3D-Visualizer: Bühne bauen & Fixtures hängen

Diese Anleitung zeigt **Schritt für Schritt**, wie im LightOS-3D-Visualizer eine Bühne
gebaut wird (Traversen, Stützen, Plattform, Rückwand), wie Geräte daran gehängt werden,
wie du die Kamera führst und wie du die Darstellung der Lichtstrahlen einstellst.

Die Bilder zeigen die Doku-Demo des Bild-Werkzeugs: acht PARs an einer Front-Traverse,
zwei Wash- und zwei Spot-Moving-Heads an einer Back-Traverse, eine LED-Leiste vorn auf
der Bühnenkante. Die Schritte gelten für jede Show mit gepatchten Geräten. Die Bilder
entstehen aus dem Code am echten Bildschirm
(`tools/anleitungsbilder/szenen_3d_buehne.py`, siehe
[Anleitungsbilder](../ANLEITUNGSBILDER.md)).

![3D-Visualizer mit Doku-Bühne: Traversen, Stützen, PARs und Moving Heads im Nebel](img/01_uebersicht.png)

1. **Ansicht** — „3D Perspective" oder „2D Top-Down" (Taste `V`).
2. **Modus** — „Ansehen" oder „Bauen" (Taste `E`).
3. **Bühne** — welche gespeicherte Bühne geladen ist; daneben **Speichern**, **Neu**,
   **Löschen**.
4. **Reiter** — **Fixtures** (Geräte), **Bühne** (Bühnen-Elemente), **Einstellungen**
   (Darstellung). Im Bild ist PAR 1 gewählt (oben in der Ansicht „Selektion: FIXTURE
   x1“); darunter zeigt **Position & Ausrichtung** seine Werte: Er hängt mit `Y=5.6`
   an der Front-Traverse.

## Vorbereitung

1. Show mit gepatchten Geräten öffnen.
2. Menü **Visualizer → 3D Visualizer öffnen**. Das Fenster öffnet sich neben dem
   Hauptfenster; beim ersten Öffnen dauert es einige Sekunden, bis die 3D-Szene steht.
   Alle gepatchten Geräte stehen im Reiter **Fixtures** in der Liste, z. B.
   `[X] [001] PAR 1 (par)`. Geräte, die in der 2D-Bühne (Sektion **Bühne**) schon
   eine Lage haben, erscheinen sofort im Raum. Die Statuszeile unten zählt mit:
   „13 Fixture(s) in Szene | 8 Bühnen-Elemente".

## Ansehen und Bauen

Der Visualizer hat **zwei Modi**:

- **Ansehen** — nichts ist anfassbar; Ziehen mit der Maus dreht die Kamera. Rechts
  oben in der 3D-Ansicht steht „ANSEHEN".
- **Bauen** — erst jetzt lassen sich Geräte und Bühnen-Elemente anfassen. *Welche*,
  entscheidet der Reiter rechts: **Fixtures** oder **Bühne**. Der orange Rahmen um die
  Ansicht zeigt beides an: „BAUEN · Fixtures" bzw. „BAUEN · Bühne".

Ein Klick auf einen Reiter schaltet den Modus **nicht** um. Wer im Ansehen-Modus nur
die Liste ansehen will, macht damit nichts versehentlich anfassbar. Im Bauen-Modus
hellt **Auto-Helligkeit** die Szene auf (siehe [Teil D](#teil-d--darstellung-reiter-einstellungen)).

## Teil A — Bühne bauen (Reiter „Bühne")

![Modus Bauen, Reiter Bühne: die Front-Traverse ist gewählt und gelb hervorgehoben](img/02_buehne_bauen.png)

1. **Modus → Bauen** stellen.
2. Reiter **Bühne** wählen (Taste `S`). Oben in der Ansicht erscheint das gelbe Banner
   „BÜHNE BEARBEITEN – Tippen=Auswählen | Ziehen=Verschieben | ↻ / 🗑 unten rechts";
   die runden Knöpfe unten rechts drehen bzw. löschen das gewählte Element.
3. **Element hinzufügen:** Boden / Floor · Plattform · Truss (horizontal) ·
   Truss/Stütze (vertikal) · Wand / Backdrop · LED-Wand · Lautsprecher ·
   Publikumsfläche · DJ-Booth. Ein neues Element erscheint sofort in der Szene und in
   der Liste „Bühnen-Elemente" darüber und ist gleich gewählt.
4. **Eigenschaften (Selektion):** Name, Position `X`/`Y`/`Z` (Mittelpunkt des
   Elements, in Metern), Größe `Breite (W)`/`Höhe (H)`/`Tiefe (D)`, Rotation und Farbe.
   Das gewählte Element leuchtet in der Szene gelb, oben steht z. B.
   „Selektion: TRASSE (horizontal) - Front-Traverse".

So entsteht die Bühne im Bild:

1. **Plattform (Bühnenboden):** „**+ Plattform**" legt eine Fläche von 6 × 0,4 × 4 m an.
   Im Bild: `Breite=11`, `Höhe=1`, `Tiefe=7`, `Y=0.5` (Mittelpunkt auf halber Höhe —
   die Oberkante liegt damit bei 1 m).
2. **Traverse:** „**+ Truss (horizontal)**" legt eine 4 m lange Traverse auf 8 m Höhe
   an. Im Bild die Front-Traverse: `X=0`, `Y=6`, `Z=2.5`, `Breite=12`; die
   Back-Traverse genauso mit `Z=-2.5`. Positiv `Z` ist vorn (zum Publikum).
3. **Werte eingeben:** Feld anklicken → `Strg+A` → Wert tippen. Der Wert gilt **schon
   beim Tippen**, das Element wandert sofort mit; ENTER oder TAB sind nicht nötig.
   Punkt und Komma gehen beide („5.7" und „5,7").
4. **Verschieben per Maus:** Element in der Szene anfassen und ziehen — es bewegt sich
   in der Bodenebene (`X`/`Z` ändern sich, die Felder ziehen mit). Die Höhe (`Y`)
   stellst du über das Feld ein.
5. **Stützen:** „**+ Truss/Stütze (vertikal)**" (4 m hoch). Über `X`/`Z` an die Enden
   der Traversen setzen — im Bild `X=±6`, `Z=±2.5`, `Höhe=6`, `Y=3` — ergibt zwei
   „Goalposts".
6. **Rückwand:** „**+ Wand / Backdrop**" hinter die Back-Traverse (`Z=-3.6`).

> **„Größe anpassen"** schaltet nur die Ziehgriffe am Element in der Szene ein (der Knopf
> wird gelb); die Größen-Felder bleiben dabei frei. **Element LÖSCHEN** entfernt das
> gewählte Element.

## Teil B — Geräte platzieren und hängen (Reiter „Fixtures")

![Modus Bauen, Reiter Fixtures: Spot 1 ist gewählt, Andocken ist an](img/03_geraet_platzieren.png)

1. **Gerät wählen** — in der Liste (`[X]` = im Raum, `[ ]` = noch nicht platziert) oder
   in der Szene antippen. Mehrere Geräte wählst du in der Liste mit `Strg`/`Umschalt`
   oder in der Szene mit einem Rahmen.
2. **Im Raum platzieren** setzt das gewählte Gerät in die Szene; **Entfernen** nimmt
   es wieder heraus. Schneller geht es per **Ziehen**: Gerät aus der Liste in die
   3D-Ansicht ziehen. Ein halbtransparenter Geist zeigt, wo es landet; färbt er sich
   **grün**, dockt es beim Loslassen an die Traverse darunter an. Ziehen wirkt nur im
   Bauen-Modus — im Ansehen-Modus zeigt der Mauszeiger, dass hier nichts abgelegt werden
   kann.
3. **Andocken** (Taste `D`): an, rasten Geräte beim Platzieren und Ziehen an Traversen
   ein (sie hängen darunter) bzw. stehen oben auf Plattform, Boden, Lautsprecher,
   Publikumsfläche oder DJ-Booth — und wandern mit, wenn du das Element verschiebst.
   Aus, platzierst du frei auf fester Höhe. Die Statuszeile meldet den Zustand.
4. **Position & Ausrichtung** — die Felder des gewählten Geräts:
   - **Unten an die Traverse:** `Y` = Unterkante der Traverse minus 0,25 m. Im Bild hängt
     Spot 1 an der Back-Traverse (`Y=6`, 0,3 m hoch): `Y=5.6`, `Z=-2.5`, `X` entlang
     der Traverse verteilen. Genau diese Höhe setzt auch das Andocken.
   - **Oben auf die Traverse:** `Y` knapp über die Traverse (z. B. `Y=6.5`).
   - **Seitlich:** an eine Stütze setzen (deren `X`/`Z`, mittlere `Y`) und mit **Drehen
     (Hochachse Y)** zur Seite ausrichten.
   - **Ausrichten:** **Drehen (Hochachse Y)**, **Kippen (auf/ab X)**, **Roll (seitlich
     Z)**. Moving Heads folgen zusätzlich live ihren Pan/Tilt-Werten.

Ist ein Gerät gewählt, zeigt die Szene oben die Werkzeugleiste **Bewegen · Zielen ·
Nachfahren** und am Gerät ein Gizmo: am Boden ziehen verschiebt in `X`/`Z`, die Pfeile
verschieben je Achse bzw. in der Höhe, die Ringe drehen (mit `Strg` frei, ohne Raster).
**Zielen** richtet gewählte Strahler auf einen angetippten Punkt aus — wie du das an den
echten Aufbau angleichst, steht in [Moving Heads einmessen](../anleitung_einmessen/ANLEITUNG_EINMESSEN.md).
Mehrere gewählte Geräte lassen sich über **⬄ Ausrichten** auf eine Linie legen,
gleichmäßig verteilen oder als Reihe, Raster oder Kreis anordnen.

## Teil C — Kamera

![Kamera-Menü geöffnet, Ansicht von vorn](img/04_kamera.png)

Das Menü **⌖ Kamera** hält alles zur Kamera an einer Stelle:

- **Presets:** Top (von oben) · Front · Seite · Perspektive · Frei. Das Bild zeigt die
  Bühne nach **Front**.
- **Fit (alle)** rückt alle Geräte ins Bild, **Fit Auswahl (F)** nur die gewählten
  (`F` wirkt so, wenn die 3D-Ansicht den Fokus hat; sonst springt `F` auf den Reiter
  Fixtures).
- **Zurücksetzen** — Startansicht (auch: Doppel-Tipp in die Ansicht).
- **Kamera speichern…** fragt nach einem Namen. Gespeicherte Kameras gehören zur Show
  und stehen danach unten im Menü (`↦ Name`) zum Abruf.

Mit der Maus: Ziehen dreht, Mausrad zoomt; am Touchscreen drehst du mit einem Finger
und schwenkst/zoomst mit zwei.

## Teil D — Darstellung (Reiter „Einstellungen")

![Reiter Einstellungen: Render-Qualität, Szenen-Helligkeit und Strahl-Optionen](img/05_einstellungen.png)

1. **Render-Qualität — Stufe:** „Automatisch (empfohlen)" prüft beim Start die
   Grafikkarte und wählt passend; „Hoch (Desktop-GPU)" bzw. „Niedrig (schwache/mobile
   GPU)" überschreiben das. Niedrig rechnet ohne Kantenglättung, mit weniger Auflösung,
   Schatten und Kegeldetail — flüssiger auf schwachen Chips. Die Wahl gilt für diesen
   Rechner, nicht für die Show; die Szene lädt danach neu.
2. **Szenen-Helligkeit:** Grundlicht der Szene. Niedrig = dunkel, Strahlen gut sichtbar;
   hoch = Bühne gut sichtbar zum Bauen. Schnellwahl Konzert (10 %) · Standard (20 %) ·
   Probe (50 %) · Bearbeiten (75 %) · Vollhell (100 %). **Auto-Helligkeit im
   Bauen-Modus** springt beim Wechsel auf Bauen auf 65 % und zurück auf 20 % im
   Ansehen-Modus. Der ☀-Regler in der Werkzeugleiste ist derselbe Regler.
3. **Strahlen:**
   - **Beam Opacity** — wie deckend die Lichtkegel sind (im Bild 35 %).
   - **Max. Strahllänge** — deckelt die sichtbare Länge der Kegel (0 = aus). Hilft bei
     waagerecht oder nach oben zeigenden Köpfen, deren Strahl nie auf den Boden trifft.
     Ändert nichts an der DMX-Ausgabe.
   - **Lichtkegel**, **Bodenpunkte** und **Nebel/Haze** einzeln ein- und ausschalten.
     Einzelne Geräte nimmst du über das Rechtsklick-Menü der Fixture-Liste aus der
     Kegel-Anzeige.

Darunter: **Fixture-Namen (Labels)** an den Geräten, **Snap to Grid** mit
**Grid-Schritt**, **Raum-Hülle** (eine neutrale Wand-/Deckenfläche als
Größen-Orientierung, aus in der 2D-Draufsicht) und **FPS anzeigen** zur Fehlersuche.

Die Szene zeigt live, was die Ausgabe sendet — Farbe, Dimmer, Pan/Tilt, Farbrad:

![GIF: Moving Heads fahren auseinander und kreuzen sich, PARs und Washes wechseln die Farbe](img/07_moving_heads.gif)

## Teil E — Draufsicht (2D Top-Down)

![Ansicht 2D Top-Down: Traversen, Geräte als Kreise, Lichtflecken am Boden](img/06_top_down.png)

**Ansicht → 2D Top-Down** (Taste `V` schaltet hin und zurück) zeigt den Plan von oben:
Traversen und Bühnen-Elemente als Umrisse, Geräte als farbige Kreise, die Lichtflecken am
Boden. Im Plan zoomt das Mausrad, ein Doppel-Tipp setzt die Ansicht zurück; im
Ansehen-Modus schwenkt Ziehen den Plan, im Bauen-Modus verschiebt es Geräte. Das Feld
`Y (Höhe)` ist hier ausgeblendet — von oben gibt es keine Höhe. Ist das Bild zu klein,
hilft **Kamera → Fit (alle)**.

## Teil F — Speichern

- **Bühne** (Elemente aus Teil A) über **💾 Speichern** in der Visualizer-Werkzeugleiste
  unter einem Namen. Sie steht danach in der Auswahl **Bühne:**; beim Schließen mit
  ungespeicherten Änderungen fragt der Visualizer nach. **✚ Neu** beginnt eine leere
  Bühne, **🗑 Löschen** entfernt die gewählte.
- **Show** (Geräte, Positionen, gespeicherte Kameras, Gruppen, Effekte, VC) im
  Hauptfenster über **Datei → Speichern** bzw. **Speichern unter…**.

Rückgängig/Wiederholen (`Strg+Z`/`Strg+Y`) wirkt auch im Visualizer-Fenster.

## Was bei großen Rigs anders aussieht

Ab dem **9. Gerät im Raum** wirft nicht mehr jeder Scheinwerfer einen eigenen
Schlagschatten. Die Ansicht vergibt höchstens **8 Schlagschatten**, und zwar an
die Geräte mit den niedrigsten Fixture-Nummern; alle übrigen leuchten normal
weiter, werfen aber keinen Schatten auf Boden und Bühnenelemente. Wird ein Gerät
entfernt, rückt das nächste nach.

**Warum das so ist:** jeder Schlagschatten kostet die Grafikkarte nicht nur eine
Textur, sondern auch Platz im Beleuchtungs-Programm. Ohne diese Grenze scheiterte
auf Rechnern mit stärkerer Grafik ab 26 Schatten das Übersetzen dieses Programms —
die Ansicht stürzte ohne Meldung ab, und kurz davor stand das Bild sekundenlang
still. Zudem zeichnet jeder schattenwerfende Scheinwerfer die ganze Szene noch
einmal aus seiner Sicht — mit 16 Schatten war das der größte Einzelposten pro
Bild und ließ die Ansicht bei großen Rigs ruckeln. Acht Schatten reichen für den
Raumeindruck. Die Obergrenze von 8 gilt überall gleich; nur auf sehr schwachen
Grafikchips (weniger als 14 Textur-Einheiten) werfen noch weniger Geräte Schatten. Neu berechnet werden die Schatten nur, wenn sich etwas bewegt
(Pan/Tilt, verschobene Geräte oder Bühnenteile) — Kamerafahrten und reine Farb- oder
Dimmerwechsel kosten keinen Schattendurchlauf.

**Wenn Schatten für eine bestimmte Stelle wichtig sind:** die Vergabe folgt der
Fixture-Nummer. Ein Gerät, dessen Schatten man sehen will, sollte also eine
niedrige Nummer haben — oder man nimmt für die Aufnahme die übrigen kurz aus dem
Patch.

Wie lange die Ansicht je Bild braucht, lässt sich messen:
`./venv/bin/python tools/viz_render_benchmark.py 12 32 48` (echtes Fenster
nötig, misst auf der echten Grafikkarte).

## Tastenkürzel im Visualizer

| Taste | Wirkung |
|---|---|
| `V` | 3D ↔ 2D Top-Down |
| `E` | Ansehen ↔ Bauen |
| `F` | Fokus in der 3D-Ansicht: Fit Auswahl; sonst Reiter Fixtures |
| `S` | Reiter Bühne |
| `D` | Andocken an/aus |
| `Strg+Z` / `Strg+Y` | Rückgängig / Wiederholen |

## Früher bekannte Macken (alle erledigt)

Ältere Fassungen dieser Anleitung nannten hier offene Punkte. Sie sind behoben bzw. ließen
sich nicht mehr nachstellen (Details im BACKLOG-Archiv):
- **3D-Bearbeiten reagierte nicht** (bis 2026-07-07): Hinzufügen, Verschieben, Drehen und
  Kamera-Reset blieben ohne Wirkung, Geräte erschienen erst nach einem Neustart. Die
  3D-Seite holt sich Zustand und Ereignisse seither selbst ab.
- **VIZ-TRUSS-ADD:** „+ Truss (horizontal)" legt die Traverse auch bei geladenen Geräten
  zuverlässig an.
- **VIZ-STAGE-PANEL:** Felder übernehmen den Wert beim Tippen, „Größe anpassen" sperrt
  keine Felder, Auswahl in Tabelle und Szene bleibt gleich.
- **VIZ-FIX-DECIMAL:** Positionsfelder nehmen Punkt und Komma.
- **VC-WIDGET-DRAG:** VC-Widgets lassen sich im Bearbeiten-Modus per Ziehen umplatzieren.

Die Grundschritte davor (Patch, Gruppen, Effekte, Virtuelle Konsole) zeigen
[Erste Schritte](../anleitung_erste_schritte/ANLEITUNG.md) und
[Programmer-Grundlagen](../anleitung_programmer_grundlagen/ANLEITUNG.md).
