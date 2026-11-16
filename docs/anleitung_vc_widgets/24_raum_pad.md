# Raum-Pad (`VCRaumPad`)

> Du tippst in einer Draufsicht der Bühne (oder im aufgeklappten Raum mit Boden und Wänden) auf einen Punkt im Raum. Alle zugeordneten Moving Heads zielen auf genau diesen Punkt. Du schiebst also nicht Pan und Tilt, sondern zeigst auf den Raum.

## Wozu & was es steuert

Das XY-Pad arbeitet mit Pan und Tilt. „Die Ecke vorne rechts“ bedeutet dort nichts, weil jeder Kopf woanders hängt. Das Raum-Pad rechnet für **jeden Kopf einzeln** aus, wie er stehen muss, damit sein Strahl den angetippten Punkt trifft. Dafür nutzt es den Standort und die Montage aus dem 3D-Visualizer. Es ist dieselbe Rechnung wie beim Werkzeug **„Zielen“** im Visualizer, einschließlich Einmess-Versatz und Feinkanal (16 Bit).

Die Werte landen im **Programmer** (`pan`, `tilt` und, wenn das Gerät sie hat, `pan_fine`/`tilt_fine`). Das ist derselbe Weg wie beim XY-Pad. Andere Programmer-Werte, zum Beispiel Dimmer oder Farbe, fasst das Pad nicht an.

## So sieht es aus & Bedienung im Betrieb

- **Mitte: die Draufsicht.** Die Raumgröße kommt aus den platzierten Geräten (wie die Raum-Hülle im Visualizer: Rig plus 4 m Rand, mindestens 12 × 12 m). Oben steht **Rückwand**, unten **Publikum**. Das Raster hat 1 m Abstand, links unten steht die Raumgröße.
- **Blaue Punkte mit Nummer:** die zugeordneten Moving Heads an ihrem Standort (Nummer = Geräte-ID).
- **Gelb gestrichelte Kreise oben links:** zugeordnete Köpfe **ohne Position** im Visualizer. Sie fahren **nicht** mit. Dabei steht „ohne Position – fährt nicht mit“, der Tooltip nennt die Geräte. Abhilfe: das Gerät im 3D-Visualizer platzieren („Im Raum platzieren“) oder einmessen.
- **Antippen oder Ziehen** in der Draufsicht setzt das Ziel. Das Pad schaltet dabei auf **AN**. Rosa Zielmarke, dünne Linien von jedem Kopf zum Ziel, rechts unten die Koordinaten (`x … m · z … m · H … m`).
- **Unten: Zielhöhe.** Der Regler reicht von 0 m (Boden) bis zur Raumhöhe. Ändern, während das Pad AN ist, führt die Köpfe sofort nach.

### Ansicht „Aufgeklappt“: auch auf Wände zielen

In den Einstellungen (Inspector oder Doppelklick) lässt sich die **Ansicht** von „Draufsicht“ auf **„Aufgeklappt“** stellen. Dann zeigt das Pad den Raum wie einen auseinandergefalteten Würfel ohne Decke, maßstabsgetreu aus Raumbreite, -tiefe und -höhe:

- **Mitte:** der **Boden** (wie die Draufsicht),
- **oben:** die **Rückwand**, **links/rechts:** die **Seitenwände**, **unten:** die **Wand vorn** (Publikumsseite). Jede Wand ist an ihrer Kante zum Boden „heruntergeklappt“, jede Fläche ist beschriftet — ist ein Pad klein, steht nur „links“/„rechts“ oder gar kein Name, abgeschnitten wird nichts.

| Tipp auf … | Ziel |
| --- | --- |
| **Boden** | wie in der Draufsicht: Punkt in der eingestellten **Zielhöhe**. |
| **Wand** | ein Punkt **auf der Wand**. Die Höhe ist der Abstand zur Klappkante (an der Kante 0 m, am äußeren Rand die Raumhöhe), die andere Richtung läuft mit dem Boden mit. Der Zielhöhen-Regler ist dann **ausgegraut** und zeigt „Wand … m“; die Koordinaten nennen die Fläche (z. B. `Rückwand · x … · H …`). |

- **Ziehen über eine Klappkante** wechselt stetig auf die Nachbarfläche: an der Kante ist der Punkt auf Boden und Wand derselbe, die Köpfe springen nicht. Das gilt genau bei Zielhöhe 0 m (Vorgabe). Steht die Zielhöhe höher, liegt der Boden-Punkt an der Kante auf der Wand in dieser Höhe; beim Überqueren rutscht das Ziel dann einmal um die Zielhöhe an der Wand nach unten. Eine gestrichelte Linie auf den Wänden zeigt diese Höhe.
- **Außerhalb aller Flächen** (z. B. in den leeren Ecken oder beim Ziehen über den Rand) wird auf die nächste Fläche begrenzt. Ein Tipp in eine leere Ecke setzt kein Ziel.
- **Köpfe** stehen auf dem Boden an ihrem Standort; hängende Köpfe tragen ihre Hängehöhe (z. B. „4,5 m“). Hängen mehrere Köpfe gleich hoch in einer Reihe, steht die Höhe nur **einmal** daran (z. B. „10× 4,5 m“). Wo der Platz nicht reicht, werden die Kreise kleiner, Nummern und Höhen fallen weg, statt sich zu überdecken; der Tooltip nennt die Höhen aller hängenden Köpfe immer („Höhen: 4,5 m: 1, 2, …“).
- **Welche Wände** gezeigt werden, ist abwählbar (der Boden bleibt immer). Eine abgewählte Wand verschwindet aus der Abwicklung und ist nicht antippbar.

Position Lock und AN/AUS gelten in beiden Ansichten gleich.

### Köpfe, die das Ziel nicht erreichen

Liegt ein Ziel außerhalb des Bewegungsbereichs eines Kopfes (typisch: ein Punkt hoch oben an der Wand über dem Kopf bei einem Gerät mit kleinem Tilt-Bereich), bekommt der Kopf einen **roten Ring mit „!“**, der Tooltip nennt ihn („Ziel außerhalb des Bewegungsbereichs“). Der Wert selbst ist derselbe wie beim Visualizer-Zielen: auf den Anschlag begrenzt, der Strahl zeigt dann daneben. Grundlage ist der Pan-/Tilt-Bereich des Geräts.

### Schalter

| Schalter | Wirkung |
| --- | --- |
| **AN / AUS** | AN: Die Köpfe zielen auf den Punkt. **AUS** gibt Pan/Tilt/Fein dieser Köpfe wieder frei: Jeder Wert bekommt zurück, was vor dem Raum-Pad im Programmer stand. Stand dort nichts, wird er entfernt, und die Köpfe gehen zurück in das, was darunter läuft (Cue, Effekt, Grundstellung). Die Ausgabe ist danach dieselbe wie vorher. Hat inzwischen jemand anderes einen dieser Werte geändert, bleibt seine Änderung stehen. |
| **Lock AN / Lock AUS** (Position Lock, Vorgabe AN) | **Lock AN:** Das Ziel bleibt nach dem Loslassen stehen. **Lock AUS:** Das Ziel gilt nur, solange der Finger oder die Maustaste gedrückt ist. Beim Loslassen wird freigegeben wie bei AUS. Mit Lock AUS wirkt auch der AN-Knopf nur, solange er gedrückt ist, wie eine Flash-Taste. Schaltet man den Lock bei stehendem Ziel aus, wird sofort freigegeben. |

> Der AN-Zustand wird **nicht** gespeichert. Eine geladene Show schreibt nichts von selbst in den Programmer. Gespeichert werden Zuordnung, letzter Zielpunkt (mit Fläche und Wandhöhe), Zielhöhe, Position Lock, Ansicht und gezeigte Wände. Shows aus der Zeit vor der aufgeklappten Ansicht öffnen in der Draufsicht.

Ein nur **gehaltenes** Ziel (Lock AUS) bleibt nie hängen: Es wird auch freigegeben, wenn die Bank wechselt, das Fenster den Fokus verliert, das System die Berührung abbricht oder während des Haltens die Touch-Sperre angeht. Wird das Pad gelöscht (auch in einem gelöschten Rahmen), per Rückgängig/Wiederholen ersetzt oder eine Show neu geladen, gibt es seine Pan/Tilt-Werte ebenfalls frei, auch bei Lock AN. Nur der Bankwechsel behält ein eingerastetes Ziel (Lock AN). Mit **Touch-Lock** ist das Pad gesperrt. Im **Bearbeiten-Modus** verschiebt und skaliert Ziehen das Widget, es zielt nichts.

**Am Finger:** Das Pad ist ein Bedienelement wie ein Fader. Wischen auf dem Pad scrollt die Konsole nicht, es zieht das Ziel. Im Touch-Modus sind AN/AUS, Lock und der Höhenregler mindestens 44 px hoch.

## Einstellungen

Doppelklick auf das Pad (im Bearbeiten-Modus) öffnet „Raum-Pad Einstellungen“. Ansicht und Wände lassen sich auch direkt im **Inspector** umstellen (wirkt sofort), dort öffnet „Moving Heads zuordnen…“ die Zuordnung.

| Einstellung | Bedeutung |
| --- | --- |
| **Beschriftung** | Titel oben rechts im Pad. |
| **Ansicht** | „Draufsicht“ (Vorgabe) oder „Aufgeklappt“ (Boden und Wände). |
| **Flächen** | Boden (immer) und die Haken Rückwand, Wand links, Wand rechts, Wand vorn — nur bei „Aufgeklappt“ wirksam. |
| **Moving Heads** | Haken an den Geräten, die zielen sollen. Die Liste zeigt nur Geräte mit Pan **und** Tilt. Ein PAR lässt sich also gar nicht zuordnen. Spider, die nur kippen, gelten nicht als Moving Head. Mover-Bars zielen mit jedem Kopf. |
| **Aktuelle Auswahl übernehmen** | Setzt die Haken auf die gerade gewählten Geräte. |
| **Gruppen** | Haken an Gruppen. Es fahren deren Moving Heads, auch wenn die Gruppe später andere Geräte bekommt. |

Ohne Zuordnung zeigt das Pad „Keine Moving Heads zugeordnet“ und tut nichts. Anders als das XY-Pad greift es dann **nicht** auf die Auswahl oder auf alle Geräte zurück.

## Tipps & Fallen

- **Standort zuerst:** Das Pad ist nur so genau wie die Positionen im Visualizer. Für echte Treffer am Rig die Köpfe einmessen.
- **Ziele über Kopfhöhe:** Ob ein Kopf über seine Waagerechte hinaus zielen kann, hängt vom Tilt-Bereich des Geräts ab (z. B. 270° ja, 180° nein). Kann er es nicht, ist er rot markiert, siehe oben.
- **Mehrere Pads auf dieselben Köpfe:** Das zuletzt bediente Pad gewinnt. Ein AUS gibt nur Werte frei, die noch vom eigenen Pad stammen.
- **Noch nicht am Handy:** Die Handy-Konsole kann Flächen-Widgets wie das Raum-Pad noch nicht bedienen.
