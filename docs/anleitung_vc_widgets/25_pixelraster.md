# Pixelraster (`VCPixelraster`)

> Du malst mit dem Finger oder der Maus direkt auf eine LED-Matrix bzw. eine Kopf-Gruppe. Jede Rasterzelle ist ein Kopf (oder ein ganzes Gerät), die gemalte Farbe liegt mit eigenem Pegel über dem, was gerade läuft, auch über laufenden Matrix-Effekten.

## Wozu & was es steuert

Das Raster kommt aus einer **Fixture-Gruppe**: Kopf-Zellen (z. B. die 4 Köpfe einer LED-Leiste) und ganze Geräte, Untergruppen-Blöcke (Gruppe in Gruppe) werden aufgelöst. Eine Gruppe aus einem Panel mit 20 × 40 Köpfen ergibt ein Raster mit 20 × 40 Zellen.

Die Zeichnung ist eine **eigene Ausgabe-Ebene**, nicht der Programmer:

- Sie liegt **über** Effekten, Cuelisten, Programmer und Modify-Effekten: `Ergebnis = darunter + (gemalt − darunter) × Pegel`.
- **Masters, Blackout, Grand Master und Laser-NOT-AUS** liegen weiter darüber und behalten das letzte Wort.
- Sie schreibt **nur Rot, Grün und Blau**, nie einen Dimmer. Ein Gerät mit eigenem Dimmer auf 0 bleibt dunkel, die Farbe zieht den Dimmer nicht mit.
- Nicht gemalte Zellen lassen das Darunterliegende unverändert.
- Gemalte Pixel landen nicht in Cues oder Snaps, sie gehören dem Element.

## So sieht es aus & Bedienung im Betrieb

- **Oben die Knopfleiste:** **Pinsel**, **Radierer**, **Füllen** (das aktive Werkzeug ist blau), **Farbe** (Farbfeld, öffnet den Farbwähler wie bei der Farb-Kachel und schaltet auf Pinsel), **Auflösung** (`1×1` → `2×2` → `4×4`), **Löschen**, **Merken**, **Abruf**.
- **Mitte das Raster:** belegte Zellen grau, gemalte in ihrer Farbe. Leere Plätze der Gruppe bleiben schwarz.
- **Rechts der Pegel-Regler** (gelb, Zahl in Prozent): wie stark die Zeichnung über dem Rest liegt. 0 = Zeichnung unsichtbar, nichts geht verloren.

| Werkzeug | Wirkung |
| --- | --- |
| **Pinsel** | Antippen oder Ziehen färbt die Zellen in der gewählten Farbe. |
| **Radierer** | Macht Zellen wieder durchsichtig; dort gilt wieder, was darunter läuft. |
| **Füllen** | Färbt die zusammenhängende Fläche gleicher Farbe (auch eine leere Fläche). |
| **Auflösung** | Fasst 2 × 2 bzw. 4 × 4 Zellen zu einem Malpunkt zusammen (Hilfslinien zeigen die Blöcke). Die Zeichnung bleibt in voller Auflösung erhalten, Umschalten verliert nichts. |
| **Löschen** | Erster Tipp macht den Knopf rot („Sicher?“), ein zweiter Tipp innerhalb von 3 Sekunden löscht die ganze Zeichnung. |
| **Merken / Abruf** | Merken legt die aktuelle Zeichnung als Bild beim Element ab (bis zu 12, das älteste fällt heraus). Abruf lädt die gemerkten Bilder der Reihe nach („Abruf 2/3“). |

Mit **Touch-Lock** ist das Element gesperrt. Im **Bearbeiten-Modus** verschiebt und skaliert Ziehen das Element, es malt nichts. **Am Finger** ist das Raster ein Bedienelement wie ein Fader: Wischen malt, die Konsole scrollt nicht. Im Touch-Modus sind alle Knöpfe und der Pegel-Regler mindestens 44 px groß; ist das Element schmal, bricht die Knopfleiste in eine zweite Zeile um.

## Einstellungen

Doppelklick im Bearbeiten-Modus öffnet „Pixelraster Einstellungen“ (nicht im Kiosk): **Beschriftung** und **Raster aus** — entweder eine **Gruppe** oder ein **Matrix-Gerät**. Als Matrix-Gerät steht jedes Gerät mit mehreren Farbköpfen in der Liste (Panel mit Rasterform, LED-Leiste); sein Raster ist seine Kopf-Matrix, eine Gruppe braucht es dafür nicht. Eine Matrix aus dem Matrix-Assistenten, die über mehrere Universen läuft, steht als Ganzes über ihre Gesamtgruppe („… · Matrix (ganze Matrix)“); ihre Teile einzeln ebenfalls. Im **Inspector** öffnet „Raster zuordnen…“ denselben Dialog, „Raster neu lesen“ übernimmt spätere Änderungen an der Gruppe. Ein Wechsel der Bindung verwirft die Zeichnung nicht; Zellen außerhalb des neuen Rasters geben nur nichts aus.

Die Gruppe wird über ihre feste Kennung gemerkt: **Umbenennen löst die Bindung nicht**, das Element zeigt danach den neuen Namen. Eine gelöschte und unter demselben Namen neu angelegte Gruppe ist eine andere Gruppe — das Element meldet dann „Gruppe … fehlt“. Ältere Shows, deren Pixelraster nur den Gruppennamen kennen, laden weiter; die Kennung wird beim Laden nachgetragen.

## Speichern

Gespeichert werden beim Element: Gruppe (Name und Kennung) bzw. Matrix-Gerät, Zeichnung, gemerkte Bilder, Pegel, Farbe, Werkzeug und Auflösung. Malen gilt als Änderung an der Show (Rückfrage beim Schließen); Werkzeug, Farbe, Auflösung, Pegel und Abruf sind Bedienung. **Achtung:** Eine Show mit Zeichnung und Pegel über 0 gibt die Zeichnung nach dem Laden sofort aus, wie ein Fader seinen gespeicherten Wert. Shows ohne Pixelraster laden unverändert.

Noch nicht: Bedienung in der Handy-Konsole, Mischart neben „Überblenden“.
