# Virtual Console: Pixelraster, Bank lösen, Pop-up-Felder — Schritt für Schritt

> Nach diesen drei kurzen Anleitungen kannst du ein Pixelraster anlegen, an Lampen binden und
> darauf malen, eine Bank als eigenes Fenster lösen und ein Pop-up-Feld mit eigener Taste bauen.
> Jede Anleitung beginnt mit einem GIF vom ganzen Ablauf, danach kommt ein Bild je Schritt.

**Show:** Die Bilder zeigen die Show „Hochzeit Komplett 2026“ (Generator
`build_hochzeit_komplett.py`, siehe [Übersicht](../ANLEITUNGEN.md)), aufgenommen im Probelauf
(es geht kein DMX hinaus). Die VC von Grund auf: [Virtual Console bauen & designen](../anleitung_vc/ANLEITUNG_VC.md) ·
[VC-Widget-Referenz](../anleitung_vc_widgets/README.md).

---

## Anleitung 1: Ein Pixelraster anlegen und an Lampen binden

Mit dem Pixelraster malst du Farben direkt auf deine Lampen. Vorher sagst du dem Raster, welche
Lampen es zeigen soll.

![Ablauf: Pixelraster anlegen](img/a1_ablauf.gif)

1. **Bearbeiten einschalten.** Öffne den Reiter „Virtual Console“. Tippe oben links auf
   **Bearbeiten**. Die Werkzeugleiste mit allen Elementen erscheint.
   ![Bearbeiten einschalten](img/a1_01_bearbeiten.png)
2. **Pixelraster hinzufügen.** Tippe in der Leiste auf **Pixelraster**. Ein leeres Raster
   erscheint auf der Fläche. Darin steht „Kein Raster zugeordnet“. Zieh es an eine freie Stelle.
   ![Neues Pixelraster](img/a1_02_pixelraster_neu.png)
3. **Raster zuordnen.** Tippe das Raster einmal an. Rechts im Inspector tippst du auf
   **Raster zuordnen…**.
   ![Raster zuordnen](img/a1_03_raster_zuordnen.png)
4. **Einstellungen.** Ein kleines Fenster geht auf. Oben steht die Beschriftung. Darunter steht
   „Raster aus“.
   ![Fenster Einstellungen](img/a1_04_dialog.png)
5. **Lampen wählen.** Öffne die Liste „Raster aus“. Oben stehen die **Matrix-Geräte**, zum
   Beispiel eine LED-Bar mit 4 Köpfen. Darunter stehen die **Gruppen**. Bei einer Gruppe zählt
   jeder Kopf als eigene Zelle.
   ![Lampen wählen](img/a1_05_auswahl.png)
6. **Bestätigen.** Tippe auf **OK**. Das Raster zeigt jetzt so viele Zellen, wie die Lampen Köpfe
   haben. Im Beispiel sind das 4 Zellen für die LED-Bar.
   ![Raster mit vier Zellen](img/a1_06_ergebnis.png)

**Tipp:** Lässt du die Beschriftung leer, heißt das Element einfach „Pixelraster“. Umbenennen der
Gruppe löst die Bindung nicht.

---

## Anleitung 2: Auf dem Pixelraster malen

Malen geht nur, wenn **Bearbeiten aus** ist. Im Bearbeiten-Modus verschiebst du das Raster nur.

![Ablauf: Malen](img/a2_ablauf.gif)

1. **Pinsel und Farbe.** Tippe auf **Pinsel**. Das Farbfeld daneben zeigt die Malfarbe. Tippe
   darauf, um eine andere Farbe zu wählen.
   ![Pinsel und Farbe](img/a2_01_pinsel.png)
2. **Malen.** Tippe auf eine Zelle oder zieh den Finger über mehrere Zellen. Sie werden in deiner
   Farbe gefüllt.
   ![Malen](img/a2_02_malen.png)
3. **Radieren.** Tippe auf **Radierer** und dann auf eine Zelle. Sie wird wieder leer.
   ![Radieren](img/a2_03_radierer.png)
4. **Füllen.** Tippe auf **Füllen** und dann auf eine leere Fläche. Alle zusammenhängenden
   Zellen in derselben Farbe werden umgefärbt.
   ![Füllen](img/a2_04_fuellen.png)
5. **Auflösung.** Der Knopf **1×1** schaltet weiter auf 2×2 und 4×4. Ein Malpunkt färbt dann
   einen ganzen Block. Beim Umschalten geht nichts verloren.
   ![Auflösung](img/a2_05_aufloesung.png)
6. **Merken und Abrufen.** **Merken** speichert dein Bild am Element. **Abruf** holt die
   gemerkten Bilder der Reihe nach zurück. Auf dem Knopf steht dann zum Beispiel „Abruf 1/1“.
   ![Merken und Abrufen](img/a2_06_merken_abruf.png)
7. **Pegel.** Der senkrechte Regler rechts bestimmt, wie stark dein Bild über allem anderen
   liegt. Steht er auf **0**, siehst du auf der Bühne nichts. Zieh ihn nach oben.
   ![Pegel](img/a2_07_pegel.png)
8. **Alles löschen.** Tippe einmal auf **Löschen**. Der Knopf wird rot und zeigt **Sicher?**.
   ![Löschen, Sicher?](img/a2_08_loeschen_sicher.png)
9. **Bestätigen.** Tippe innerhalb von 3 Sekunden ein zweites Mal. Jetzt ist das Bild weg. Ein
   schneller Doppeltipp löscht absichtlich **nicht**. Der zweite Tipp muss ein eigener Tipp sein.
   ![Bild gelöscht](img/a2_09_geloescht.png)

Bei **Touch-Lock** („Gesperrt“) kannst du nicht malen und nichts löschen. So verhinderst du
versehentliche Tipps in der Show.

---

## Anleitung 3: Eine Bank lösen und ein Pop-up-Feld bauen

### Teil A: Bank als eigenes Fenster

Damit legst du eine Bank auf einen zweiten Bildschirm, zum Beispiel einen Touch-Bildschirm.

![Ablauf: Bank lösen](img/a3_ablauf_bank.gif)

1. **Bankmenü öffnen.** Bearbeiten muss aus sein. Tippe oben auf **Bank 1**. Ganz unten steht
   **Bank 1 lösen (eigenes Fenster)**.
   ![Bankmenü](img/a3_01_bankmenue.png)
2. **Gelöst.** Die Bank geht als eigenes Fenster auf. Oben steht „Bank 1 — gelöst“. Alles darin
   funktioniert wie vorher, auch das Malen. Zieh das Fenster auf den Bildschirm, den du willst.
   ![Gelöste Bank](img/a3_02_geloest.png)
3. **Andocken.** Tippe oben rechts im Fenster auf **Andocken** oder schließe das Fenster. Die
   Bank ist wieder in der Hauptfläche.
   ![Wieder angedockt](img/a3_03_angedockt.png)

**Gut zu wissen:** Schaltest du Bearbeiten ein, dockt die Bank von selbst an. Schaltest du
Bearbeiten wieder aus, löst sie sich wieder.

### Teil B: Pop-up-Feld mit eigener Taste

Ein Pop-up-Feld ist ein Rahmen, der erst aufgeht, wenn du seine Taste drückst.

![Ablauf: Pop-up-Feld](img/a3_ablauf_popup.gif)

1. **Rahmen anlegen.** Bearbeiten an. Tippe in der Leiste auf **Frame**. Ein neuer Rahmen
   erscheint. Zieh ihn an eine freie Stelle.
   ![Neuer Rahmen](img/a3_04_rahmen_neu.png)
2. **Zum Pop-up machen.** Rechts im Inspector auf **Einstellungen öffnen…**. Gib einen Namen ein,
   zum Beispiel „Extras“. Setze den Haken bei **Pop-up-Feld**. Dann **OK**. Der Rahmen hat jetzt
   einen lila Rand. Der Haken **Solo-Frame** darüber macht etwas anderes: dort ist immer nur
   eine Taste gleichzeitig aktiv. Solo-Rahmen haben einen roten Rand.
   ![Haken Pop-up-Feld](img/a3_05_popup_haken.png)
3. **Taste anlegen.** Lege eine Taste an (Leiste: **Button**). Wähle sie aus. Stelle im Inspector
   bei **Aktion** auf **Pop-up-Feld öffnen/schließen**.
   ![Aktion der Taste](img/a3_06_tastenaktion.png)
4. **Feld wählen.** Darunter bei **Pop-up-Feld** wählst du deinen Rahmen „Extras“.
   ![Pop-up-Feld wählen](img/a3_07_feld_waehlen.png)
5. **Ausprobieren.** Bearbeiten aus. Tippe die Taste. Das Feld geht auf und liegt über allem.
   Tippe noch einmal, und es geht wieder zu.
   ![Pop-up-Feld zu](img/a3_08_popup_zu.png)
   ![Pop-up-Feld offen](img/a3_09_popup_auf.png)

**Regeln:** Ein Pop-up-Feld darf keine Pop-up-Taste und kein weiteres Pop-up-Feld enthalten.
Beim Laden der Show sind alle Pop-up-Felder zu. Im Kiosk-Modus (nur Virtual Console)
funktionieren Pop-ups, Malen und Bank lösen genauso; Bearbeiten und Rechtsklick-Menüs gibt es
dort nicht.
