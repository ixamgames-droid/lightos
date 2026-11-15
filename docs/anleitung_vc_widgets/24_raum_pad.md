# Raum-Pad (`VCRaumPad`)

> Du tippst in einer Draufsicht der Bühne auf einen Punkt im Raum. Alle zugeordneten Moving Heads zielen auf genau diesen Punkt. Du schiebst also nicht Pan und Tilt, sondern zeigst auf den Raum.

## Wozu & was es steuert

Das XY-Pad arbeitet mit Pan und Tilt. „Die Ecke vorne rechts“ bedeutet dort nichts, weil jeder Kopf woanders hängt. Das Raum-Pad rechnet für **jeden Kopf einzeln** aus, wie er stehen muss, damit sein Strahl den angetippten Punkt trifft. Dafür nutzt es den Standort und die Montage aus dem 3D-Visualizer. Es ist dieselbe Rechnung wie beim Werkzeug **„Zielen“** im Visualizer, einschließlich Einmess-Versatz und Feinkanal (16 Bit).

Die Werte landen im **Programmer** (`pan`, `tilt` und, wenn das Gerät sie hat, `pan_fine`/`tilt_fine`). Das ist derselbe Weg wie beim XY-Pad. Andere Programmer-Werte, zum Beispiel Dimmer oder Farbe, fasst das Pad nicht an.

## So sieht es aus & Bedienung im Betrieb

- **Mitte: die Draufsicht.** Die Raumgröße kommt aus den platzierten Geräten (wie die Raum-Hülle im Visualizer: Rig plus 4 m Rand, mindestens 12 × 12 m). Oben steht **Rückwand**, unten **Publikum**. Das Raster hat 1 m Abstand, links unten steht die Raumgröße.
- **Blaue Punkte mit Nummer:** die zugeordneten Moving Heads an ihrem Standort (Nummer = Geräte-ID).
- **Gelb gestrichelte Kreise oben links:** zugeordnete Köpfe **ohne Position** im Visualizer. Sie fahren **nicht** mit. Dabei steht „ohne Position – fährt nicht mit“, der Tooltip nennt die Geräte. Abhilfe: das Gerät im 3D-Visualizer platzieren („Im Raum platzieren“) oder einmessen.
- **Antippen oder Ziehen** in der Draufsicht setzt das Ziel. Das Pad schaltet dabei auf **AN**. Rosa Zielmarke, dünne Linien von jedem Kopf zum Ziel, rechts unten die Koordinaten (`x … m · z … m · H … m`).
- **Unten: Zielhöhe.** Der Regler reicht von 0 m (Boden) bis zur Raumhöhe. Ändern, während das Pad AN ist, führt die Köpfe sofort nach.

### Schalter

| Schalter | Wirkung |
| --- | --- |
| **AN / AUS** | AN: Die Köpfe zielen auf den Punkt. **AUS** gibt Pan/Tilt/Fein dieser Köpfe wieder frei: Jeder Wert bekommt zurück, was vor dem Raum-Pad im Programmer stand. Stand dort nichts, wird er entfernt, und die Köpfe gehen zurück in das, was darunter läuft (Cue, Effekt, Grundstellung). Die Ausgabe ist danach dieselbe wie vorher. Hat inzwischen jemand anderes einen dieser Werte geändert, bleibt seine Änderung stehen. |
| **Lock AN / Lock AUS** (Position Lock, Vorgabe AN) | **Lock AN:** Das Ziel bleibt nach dem Loslassen stehen. **Lock AUS:** Das Ziel gilt nur, solange der Finger oder die Maustaste gedrückt ist. Beim Loslassen wird freigegeben wie bei AUS. Mit Lock AUS wirkt auch der AN-Knopf nur, solange er gedrückt ist, wie eine Flash-Taste. |

> Der AN-Zustand wird **nicht** gespeichert. Eine geladene Show schreibt nichts von selbst in den Programmer. Gespeichert werden Zuordnung, letzter Zielpunkt, Zielhöhe und Position Lock.

Ein Bankwechsel gibt ein nur **gehaltenes** Ziel (Lock AUS) frei. Mit **Touch-Lock** ist das Pad gesperrt. Im **Bearbeiten-Modus** verschiebt und skaliert Ziehen das Widget, es zielt nichts.

**Am Finger:** Das Pad ist ein Bedienelement wie ein Fader. Wischen auf dem Pad scrollt die Konsole nicht, es zieht das Ziel. Im Touch-Modus sind AN/AUS, Lock und der Höhenregler mindestens 44 px hoch.

## Einstellungen

Doppelklick auf das Pad (im Bearbeiten-Modus) öffnet „Raum-Pad Einstellungen“.

| Einstellung | Bedeutung |
| --- | --- |
| **Beschriftung** | Titel oben rechts im Pad. |
| **Moving Heads** | Haken an den Geräten, die zielen sollen. Die Liste zeigt nur Geräte mit Pan **und** Tilt. Ein PAR lässt sich also gar nicht zuordnen. Spider, die nur kippen, gelten nicht als Moving Head. Mover-Bars zielen mit jedem Kopf. |
| **Aktuelle Auswahl übernehmen** | Setzt die Haken auf die gerade gewählten Geräte. |
| **Gruppen** | Haken an Gruppen. Es fahren deren Moving Heads, auch wenn die Gruppe später andere Geräte bekommt. |

Ohne Zuordnung zeigt das Pad „Keine Moving Heads zugeordnet“ und tut nichts. Anders als das XY-Pad greift es dann **nicht** auf die Auswahl oder auf alle Geräte zurück.

## Tipps & Fallen

- **Standort zuerst:** Das Pad ist nur so genau wie die Positionen im Visualizer. Für echte Treffer am Rig die Köpfe einmessen.
- **Ziele über Kopfhöhe:** Liegt das Ziel höher als der Kopf, rechnet das Modell wie beim Visualizer-Zielen bis zur Waagerechten.
- **Mehrere Pads auf dieselben Köpfe:** Das zuletzt bediente Pad gewinnt. Ein AUS gibt nur Werte frei, die noch vom eigenen Pad stammen.
- **Geplant (Teil B):** eine zweite Ansicht mit aufgeklapptem Raum (Boden und Wände), um auch auf Wände zu zielen.
