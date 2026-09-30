# Erste Schritte mit LightOS

> Du hast LightOS gerade installiert und willst wissen, wo was ist? Diese Anleitung führt
> einmal durch das Hauptfenster, legt eine neue Show an, patcht ein Gerät, bringt es im
> Programmer zum Leuchten und speichert das Ganze als Show-Datei. Das dauert etwa zehn
> Minuten. Die roten Zahlen in den Bildern gehören zu den gleich nummerierten Punkten im Text.

## Was du brauchst

- **LightOS, installiert und startbar.** Wie das unter Windows und Linux geht, steht in
  [INSTALL.md](../../INSTALL.md). Unter Linux startest du LightOS aus dem LightOS-Ordner
  mit `venv/bin/python main.py`.
- **Keine Hardware.** Für diese Anleitung reicht der Rechner. Ob wirklich DMX
  herauskommt, richtest du danach ein:
  [Ausgabe einrichten (ENTTEC, Art-Net, sACN)](../anleitung_ausgabe_einrichten/ANLEITUNG.md).
- Als Beispielgerät dient ein eingebautes Profil, das jede Installation mitbringt:
  **Generic — LED PAR Dimmer+RGB 4ch** (4 Kanäle: Dimmer, Rot, Grün, Blau). Hast du
  ein eigenes Gerät, suchst du in Schritt 5 einfach nach dessen Namen.

---

## 1. Das Hauptfenster

Nach dem Start öffnet LightOS in der Sektion **Bühne**. Von oben nach unten:

![Hauptfenster einer leeren Show](img/01_hauptfenster.png)

1. **Menüleiste** — `Datei`, `Bearbeiten`, `Ansicht`, `Show`, `Programmer`, `Datenbank`,
   `Ausgabe`, `Visualizer`, `Command`, `Hilfe`. Hier liegen Speichern und Öffnen
   (Schritt 7) und die Ausgabe-Einstellungen.
2. **Sektionsleiste** — die acht Arbeitsbereiche von LightOS, siehe Schritt 2.
3. **GM** — der Grand Master. Er regelt die Gesamthelligkeit von 0 bis 100 %.
4. **TAP** — Tempo tippen. Laut Tooltip: einmal tippen setzt den Beat auf „jetzt",
   viermal im Takt setzt das Tempo.
5. **STOP ALL** — hält alles an, was läuft: Cue-Listen auf allen Pages und alle
   gestarteten Funktionen (Szenen, Chaser, Effekte).
6. **BLACKOUT** — schaltet alle Ausgänge auf 0. Der Knopf rastet ein; ein zweiter
   Klick hebt den Blackout wieder auf.
7. **Befehlszeile** — für Tastatur-Befehle wie `1 thru 5 @ 80`. Beispiele stehen als
   Platzhaltertext im Feld.
8. **Statusleiste** — links der Zustand des ENTTEC-Adapters (`Enttec: nicht gefunden`,
   solange keiner angeschlossen ist), der Web-Server und die Zahl der Geräte
   (`0 Gerät(e)`). Ganz rechts steht, wohin die Ausgabe geht (`Ausgabe: …`). Was die
   Meldungen dort bedeuten, erklärt
   [Ausgabe einrichten, Schritt 8](../anleitung_ausgabe_einrichten/ANLEITUNG.md#8-warnungen-in-der-statusleiste-lesen).

Rechts neben TAP erscheinen bei Bedarf weitere Anzeigen, zum Beispiel
**● Programmer** mit der Zahl der aktiven Werte, sobald im Programmer etwas steht (siehe Schritt 6).

## 2. Die acht Sektionen

Ein Klick auf einen Namen wechselt den Arbeitsbereich. Mit der Tastatur geht es über
**Strg+1** bis **Strg+8**.

![Die Sektionsleiste](img/02_sektionen.png)

1. **Bühne** — 2D-Draufsicht auf deine Geräte. Links die Liste **Fixtures** /
   **Gruppen**; Geräte ziehst du auf die Fläche. Oben rechts wechselst du zwischen
   **2D** und **3D**.
2. **Patchen** — Geräte anlegen, auf DMX-Adressen legen und zu Gruppen zusammenfassen
   (Schritt 5). Ausführlich:
   [Patchen & Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md).
3. **Programmer** — Geräte auswählen und ihre Werte von Hand setzen (Schritt 6). Was
   der Programmer je Gerät zeigt:
   [Programmer: jedes Gerät richtig bedienen](../anleitung_geraete_bedienen/ANLEITUNG_GERAETE_BEDIENEN.md).
4. **Virtual Console** — deine eigene Bedienoberfläche aus Knöpfen, Fadern und
   Anzeigen. Einstieg: [Virtuelle Konsole bauen](../anleitung_vc/ANLEITUNG_VC.md),
   Nachschlagen: [VC-Bau-Elemente](../anleitung_vc_widgets/README.md).
5. **Simple Desk** — jeder der 512 DMX-Kanäle eines Universums als eigener Fader,
   direkt und ohne Geräte-Logik.
6. **Playback** — Cue-Listen abspielen.
7. **E/A** — Eingabe und Ausgabe: Monitore für die DMX-Werte, die LightOS rechnet,
   dazu MIDI und Musik. Die Monitore zeigt
   [Ausgabe einrichten](../anleitung_ausgabe_einrichten/ANLEITUNG.md#6-kontrolle-der-output-monitor).
8. **BPM** — Tempo-Erkennung aus Musik. Ausführlich:
   [BPM-Manager](../anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md).

Welche Reiter eine Sektion hat, siehst du oben links unter der Sektionsleiste, sobald
du sie öffnest — bei **Patchen** zum Beispiel **Patch** und **Fixture-Gruppen**
(Bild in Schritt 5).

## 3. Eine neue Show anlegen

Öffne das Menü **Datei** und wähle **Neue Show** (1). Die Tastenkombination ist
**Strg+N**.

![Menü Datei, Neue Show](img/03_datei_neu.png)

## 4. Die Rückfrage bestätigen

LightOS fragt nach, bevor es die aktuelle Show verwirft:

![Rückfrage Neue Show](img/04_rueckfrage.png)

Mit **Yes** (1) werden gepatchte Geräte, Virtual Console, Funktionen, Paletten und
Bibliothek geleert, und du beginnst mit einer leeren Show. **No** lässt alles, wie es
ist. Die Knöpfe sind englisch beschriftet, weil sie von Qt stammen.

> Die leere Show hat noch keinen Dateinamen. Den bekommt sie erst beim ersten
> Speichern (Schritt 7).

## 5. Ein Gerät patchen

Wechsle in die Sektion **Patchen**, Reiter **Patch**. Die Tabelle ist leer. Klicke auf
**+ Gerät hinzufügen** (1).

![Patch einer neuen Show](img/05_patch_leer.png)

Es öffnet sich der Dialog **Gerät hinzufügen**:

![Dialog Gerät hinzufügen](img/06_geraet_waehlen.png)

1. **Suche:** — tippe einen Teil des Namens, hier `LED PAR`. Die Liste zeigt dann alle
   passenden Profile als `Hersteller — Gerät`.
2. Wähle das Profil **Generic — LED PAR Dimmer+RGB 4ch**. Rechts erscheinen Hersteller
   und Gerät, und **Hinzufügen** wird anklickbar.
3. **Modus:** — das Kanal-Layout. Dieses Profil kennt nur `4-Kanal Dimmer+RGB (4ch)`.
   Bei anderen Geräten muss der Modus zu der Einstellung am Gerät passen.
4. **Universe:** — auf welchem DMX-Universum das Gerät liegt. Für den Anfang `1`.
5. **DMX-Adresse:** — die Startadresse. LightOS schlägt darunter den nächsten freien
   Bereich vor (`Vorschlag: Adresse 1 …`) und trägt ihn gleich ein. Stelle am echten
   Gerät dieselbe Adresse ein.
6. **Hinzufügen** — legt das Gerät an und schließt den Dialog.

Weitere Felder: **Anzahl:** legt mehrere gleiche Geräte auf einmal an, **Label:** ist der
Name in LightOS (vorbelegt mit dem Kurznamen des Profils, hier `PARD`), **Adress-Offset:**
der Abstand zwischen mehreren Geräten (`0` = direkt hintereinander).

Danach steht das Gerät in der Tabelle:

![Ein Gerät im Patch](img/07_patch_ein_geraet.png)

1. Die neue Zeile: FID `1`, Label `PARD`, Hersteller `Generic`, Modus, Universe (`Univ.`)
   `1`, Adresse `1`, `4` Kanäle. Die Zeilenfarbe steht für den Gerätetyp. Eine **rote**
   Zeile mit **⚠** vor der FID würde einen Adresskonflikt anzeigen.
2. Die Statusleiste zählt jetzt `1 Gerät(e)`.

Umbenennen, Adresse ändern: **Doppelklick** auf die Zeile öffnet *Gerät bearbeiten*.
Mehr dazu: [Patchen & Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md).

## 6. Den ersten Wert im Programmer setzen

Wechsle in die Sektion **Programmer**, Reiter **Attribute**.

![Programmer mit Dimmer auf 255](img/08_programmer.png)

1. Klicke das Gerät in der Liste **Geräte** an (`[001] PARD`). Erst dann erscheinen in
   der Mitte die Regler. (**Alle** darunter wählt alle Geräte, **Keine** hebt die Auswahl
   auf.)
2. Reiter **Intensity**.
3. Ziehe den Fader **Dimmer** ganz nach rechts auf `255` (100 %).

Oben in der Sektionsleiste erscheint jetzt **● Programmer 1**: ein Wert ist im
Programmer aktiv.

> **Warum bleibt der PAR noch dunkel?** Ein RGB-Scheinwerfer leuchtet nur, wenn auch
> eine Farbe gesetzt ist — mit Rot, Grün und Blau auf 0 ist er trotz vollem Dimmer
> schwarz. Die **Lampen-Vorschau** unten zeigt in diesem Fall trotzdem Weiß; darauf
> ist hier kein Verlass. Also noch eine Farbe:

![Programmer mit Rot auf 255](img/09_programmer_farbe.png)

1. Reiter **Color**.
2. Unter **Schnellwahl:** die Kachel **Rot** — sie setzt Rot auf 255 und Grün und Blau
   auf 0.
3. Alternativ die Fader **Rot**, **Grün** und **Blau** einzeln ziehen.
4. Die **Lampen-Vorschau** zeigt die Mischung. Oben steht jetzt **● Programmer** mit einer Zahl — sie zählt die Werte, die im Programmer stehen.

Hängt ein Gerät an einem eingerichteten Ausgang, leuchtet es jetzt rot. Prüfen kannst
du das auch ohne Gerät im DMX-Monitor der Sektion **E/A**: Kanal 1 (Dimmer) und
Kanal 2 (Rot) stehen auf 255 — siehe
[Ausgabe einrichten, Schritt 7](../anleitung_ausgabe_einrichten/ANLEITUNG.md#7-kontrolle-der-dmx-monitor).

Zurücksetzen kannst du die Programmer-Werte über **✖ Clear ▾** oben in der
Sektionsleiste.

## 7. Speichern und wieder öffnen

Alles läuft über das Menü **Datei**:

![Menü Datei, Speichern und Öffnen](img/10_datei_speichern.png)

1. **Öffnen...** (Strg+O) — eine gespeicherte Show laden (`*.lshow`).
2. **Speichern** (Strg+S) — speichert unter dem bisherigen Namen. Hat die Show noch
   keinen, fragt LightOS wie bei *Speichern unter...* nach einem.
3. **Speichern unter...** — neuer Name oder anderer Ort. Die Endung `.lshow` ergänzt
   LightOS selbst.
4. **Zuletzt verwendet** — die zehn zuletzt geöffneten oder gespeicherten Shows.

Die Datei-Dialoge starten im Ordner der aktuellen Show, sonst im Ordner `shows` im
LightOS-Datenordner (Linux: `~/.local/share/LightOS/shows`, Windows:
`%APPDATA%\LightOS\shows`). Nach dem Speichern steht der Pfad im Fenstertitel und kurz
in der Statusleiste (`Gespeichert: …`).

**Automatisch gesichert** wird zusätzlich alle 5 Minuten in die Datei `auto_save.lshow`
im LightOS-Datenordner. Das Intervall stellst du unter **Datei → Auto-Save-Intervall...**
ein (1–60 Minuten). Ist beim nächsten Start diese Sicherung neuer als deine zuletzt
gespeicherte Show — etwa nach einem Absturz —, bietet LightOS an, sie
wiederherzustellen. Beim Beenden fragt LightOS nach, wenn es ungespeicherte Änderungen
vermutet.

---

## Wie geht es weiter?

- **Licht wirklich ausgeben:** [Ausgabe einrichten (ENTTEC, Art-Net, sACN)](../anleitung_ausgabe_einrichten/ANLEITUNG.md)
- **Mehr Geräte und Gruppen:** [Patchen & Gruppen](../anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md)
- **Eigene Bedienoberfläche:** [Virtuelle Konsole bauen](../anleitung_vc/ANLEITUNG_VC.md)
- **Alle Anleitungen:** [Übersicht](../ANLEITUNGEN.md)

<!-- Bilder: venv/bin/python tools/anleitungsbilder.py erste_schritte (docs/ANLEITUNGSBILDER.md) -->
