# Web-Fernbedienung und Handy-Konsole — Schritt für Schritt

> Nach diesen drei kurzen Anleitungen kannst du die Web-Fernbedienung einschalten, deine
> Handy-Konsole aus Seiten und Kacheln bauen und eine Handy-Gruppe anlegen und am Handy
> bedienen. Jede Anleitung beginnt mit einem GIF vom ganzen Ablauf, danach kommt ein Bild je
> Schritt. Rote Rahmen zeigen, wo du klickst.

**Show:** Die Bilder zeigen die Show „Hochzeit Komplett 2026“ (Generator
`build_hochzeit_komplett.py`, siehe [Übersicht](../ANLEITUNGEN.md)), aufgenommen im Probelauf
(es geht kein DMX hinaus). Die Schlüssel in den Bildern stammen aus diesem Probelauf und gelten
nirgends. Deinen eigenen Link mit Schlüssel stellst du nie öffentlich ins Netz. Ausführlich:
[Web-Remote — das Handy als Konsole](../anleitung_web_remote/ANLEITUNG.md).

---

## Anleitung 1: Web-Fernbedienung einschalten (nur dieser PC)

**Ziel:** LightOS nimmt Befehle über den Browser an. Erst nur am eigenen PC, ohne WLAN.

![Ablauf: Web-Fernbedienung einschalten](img/a1_ablauf.gif)

1. Öffne oben das Menü **Ausgabe**. Klick auf **Web-Interface (Port 5000)**.
   ![Menü Ausgabe](img/a1_01_menue.png)
2. Der Dialog **Web-Remote: Verbindung & Token** geht von selbst auf. Oben steht:
   „Web-Interface läuft — nur dieser PC (127.0.0.1:5000)“.
   ![Dialog nach dem Einschalten](img/a1_02_dialog.png)
3. Setz den Haken bei **Handy-Konsole**. Jetzt erscheint der Link mit dem Schlüssel. Mit
   **Link kopieren** holst du ihn in die Zwischenablage.
   ![Handy-Konsole einschalten](img/a1_03_konsole.png)
4. Brauchst du die feste Fernbedienung (GO, Fader, Blackout)? Klapp **Erweitert** auf.
   ![Erweitert aufklappen](img/a1_04_erweitert.png)
5. Setz den Haken bei **Feste Fernbedienung**. Sie hat einen eigenen Link mit eigenem Schlüssel.
   Roh-DMX bleibt aus.
   ![Feste Fernbedienung](img/a1_05_fest.png)
6. Unten in der Statuszeile steht jetzt **Web: :5000 OK**.
   ![Statuszeile](img/a1_06_status.png)
7. Test: Ein GO über die Fernbedienung startet die Cueliste. Im Reiter **Playback** siehst du die
   aktive Cue.
   ![GO über die Fernbedienung](img/a1_07_go.png)

**Gut zu wissen**

- Ist Port 5000 schon belegt, meldet LightOS das klar. Die App läuft weiter, der Haken im Menü
  bleibt aus.
  ![Port belegt](img/a1_08_port.png)
- **Schlüssel erneuern** macht alle alten Links und QR-Codes sofort ungültig. Vorher kommt eine
  Rückfrage.
  ![Schlüssel erneuern](img/a1_09_schluessel.png)
- Fürs echte Handy im WLAN klickst du auf **Handy verbinden**. Das schaltet „LAN-/Handy-Remote“
  mit ein und zeigt einen QR-Code.
- Einen Blackout vom Handy hebt nur dasselbe Handy wieder auf — oder du am Pult.

---

## Anleitung 2: Handy-Konsole bauen — Seiten und Kacheln

**Ziel:** Du legst fest, welche Tasten am Handy erscheinen. Das Original bleibt in der Konsole,
aufs Handy kommt nur eine Verknüpfung.

![Ablauf: Handy-Konsole bauen](img/a2_ablauf.gif)

1. Geh in den Reiter **VC**. Klick oben auf **Handy-Konsole**. Rechts geht die Seitenleiste auf.
   ![Knopf Handy-Konsole](img/a2_01_knopf.png)
2. Schalte **Bearbeiten** ein. Klick dann in der Leiste auf **+**.
   ![Bearbeiten und Plus](img/a2_02_bearbeiten.png)
3. Die erste Handy-Seite heißt „Seite 1“.
   ![Seite 1](img/a2_03_seite.png)
4. Rechtsklick auf eine Taste der Konsole, z. B. **Feuer**. Wähle **Auf Handy-Konsole legen**.
   ![Auf Handy-Konsole legen](img/a2_04_rechtsklick.png)
5. Mach das auch mit **Regen** und **Radar**. Die drei Kacheln stehen jetzt im Handy-Raster.
   ![Drei Kacheln](img/a2_05_drei.png)
6. Farbwähler gehen nicht aufs Handy. Das Menü sagt dir das direkt.
   ![Farbwähler nicht möglich](img/a2_06_farbwaehler.png)
7. Doppelklick auf einen Seiten-Reiter benennt ihn um. Höchstens 24 Zeichen. Leer lassen behält
   den alten Namen.
   ![Seite umbenennen](img/a2_07_umbenennen.png)
8. So sieht es mit zwei Seiten aus. Mit **−** löschst du die gewählte Seite.
   ![Zwei Seiten](img/a2_08_party.png)
9. Vertan? Der Rückgängig-Pfeil holt jede Änderung zurück.
   ![Rückgängig](img/a2_09_undo.png)

Speichere danach die Show. Seiten und Gruppen sind beim nächsten Laden wieder da.

---

## Anleitung 3: Handy-Gruppe anlegen und am Handy bedienen

**Ziel:** Von mehreren Tasten ist am Handy immer nur eine an. Tippst du eine an, gehen die
anderen aus.

![Ablauf: Handy-Gruppe](img/a3_ablauf.gif)

1. Rechtsklick auf eine Kachel im Handy-Raster. Wähle **Neue Handy-Gruppe mit dieser Kachel…**
   ![Neue Handy-Gruppe](img/a3_01_menue.png)
2. Hak alle Kacheln an, die zusammengehören.
   ![Kacheln wählen](img/a3_02_dialog.png)
3. Gib einen Namen ein (bis 24 Zeichen). Ohne Namen heißt sie „Gruppe 1“. Klick **OK**.
   ![Name der Gruppe](img/a3_03_name.png)
4. Die Gruppe hat jetzt einen gelb gestrichelten Rahmen.
   ![Gruppe mit Rahmen](img/a3_04_rahmen.png)
5. Öffne den Link der Handy-Konsole im Browser. Oben rechts steht **verbunden**. Am Pult steht
   „1 Handy verbunden“.
   ![Handy-Konsole im Browser](img/a3_05_browser.png)
6. Tipp am Handy auf **Feuer**. Am Pult geht Feuer an, Regen geht aus.
   ![Tipp am Handy](img/a3_06_tipp.png)
7. **BLACKOUT** unten am Handy wirkt sofort auch am Pult. Nochmal tippen hebt ihn auf.
   ![Blackout vom Handy](img/a3_07_blackout.png)
8. Ist LightOS weg (beendet oder Netz weg), sperrt das Handy die Bedienung und zeigt
   **Getrennt**.
   ![Getrennt](img/a3_08_getrennt.png)

Handy und Pult nebeneinander:

![Handy und Pult live](img/a3_handy_live.gif)
