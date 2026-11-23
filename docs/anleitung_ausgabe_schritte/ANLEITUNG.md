# Universen, WLED (DDP) und LED-Matrix verteilen — Schritt für Schritt

> Nach diesen drei kurzen Anleitungen kannst du im Fenster **Ausgabe → Konfigurieren…** ein
> Universum für ein WLED-Gerät anlegen, eine große LED-Matrix auf einmal auf ein WLED verteilen
> und mit **WLED suchen** Geräte im Netz finden. Jede Anleitung beginnt mit einem GIF vom ganzen
> Ablauf, danach kommt ein Bild je Schritt (rote Rahmen = hier klicken bzw. hier hinschauen).

Die Bilder stammen aus einer Übungs-Show im Probelauf. Darum steht oben „Probenmodus — es wird
kein DMX gesendet“: Diesen Hinweis zeigt LightOS immer, solange kein Ausgang aktiv ist. Als
WLED-Adresse steht in den Bildern `127.0.0.1`; bei dir ist es die Adresse deines Geräts, z. B.
`192.0.2.50`. Alle Ausgänge (ENTTEC, uDMX, Art-Net, sACN):
[Ausgabe einrichten](../anleitung_ausgabe_einrichten/ANLEITUNG.md).

---

## Anleitung 1: Ein Universum für ein WLED-Gerät anlegen

![Ablauf: Universum für WLED](img/a1_ablauf.gif)

1. Öffne oben das Menü **Ausgabe** und klick auf **Konfigurieren…**.
   ![Menü Ausgabe, Konfigurieren](img/a1_schritt01.png)
2. Wechsle in den Reiter **Universen**. Hier siehst du alle Universen mit ihrem Ausgang.
   ![Reiter Universen](img/a1_schritt02.png)
3. Klick auf **+ Universum hinzufügen**. Unten erscheint eine neue Zeile mit Ausgang „Aus“.
   ![Neue Zeile](img/a1_schritt03.png)
4. Doppelklick auf den Namen und gib einen sprechenden Namen ein, z. B. „LED-Streifen Wand“.
   Lange Namen werden mit „…“ gekürzt angezeigt.
   ![Name eingeben](img/a1_schritt04.png)
5. Klick in der Spalte **Ausgang** auf die Auswahl und wähle **DDP (WLED)**.
   ![Ausgang DDP (WLED)](img/a1_schritt05.png)
6. Doppelklick in **Patch (Port/IP)** und tippe die IP-Adresse deines WLED-Geräts ein. Mit Enter
   bestätigen.
   ![IP-Adresse eintragen](img/a1_schritt06.png)
7. Klick auf **Speichern**. Erst jetzt gilt die Einstellung. Unten rechts in der Statusleiste
   steht dann z. B. „U2 DDP“.
   ![Speichern](img/a1_schritt07.png)

**Wichtig:** Klick **Speichern**, bevor du das Fenster schließt. Erst dann gelten deine
Änderungen.

---

## Anleitung 2: Eine LED-Matrix auf ein WLED verteilen

Eine große Matrix braucht mehrere Universen. **Matrix verteilen…** trägt alle Teile auf einmal
ein, jeweils mit dem richtigen Versatz (Offset) für das WLED-Gerät.

![Ablauf: Matrix verteilen](img/a2_ablauf.gif)

1. Geh in den Reiter **Patch** und klick auf **LED-Matrix…**.
   ![Knopf LED-Matrix](img/a2_schritt01.png)
2. Stell Breite, Höhe und Kanalformat ein. Gib im Feld **Modell** einen Namen ein, z. B.
   „Wandmatrix“. Rechts siehst du die Vorschau; jede Farbe ist ein Universum.
   ![Matrix-Assistent](img/a2_schritt02.png)
3. Lass **Gleich patchen ab Universum** angehakt und klick auf **In Bibliothek speichern**.
   ![In Bibliothek speichern](img/a2_schritt03.png)
4. Im Patch stehen jetzt alle Teile (T1, T2, …), jedes in seinem eigenen Universum. Unten links
   steht „… Gerät(e) gepatcht“.
   ![Teile im Patch](img/a2_schritt04.png)
5. Öffne **Ausgabe → Konfigurieren…**, Reiter **Universen**, und klick auf **Matrix verteilen…**.
   ![Matrix verteilen](img/a2_schritt05.png)
6. Wähl oben die Matrix und tippe die **WLED-IP** ein. Darunter siehst du sofort, welches
   Universum welchen Offset bekommt.
   ![Matrix und WLED-IP](img/a2_schritt06.png)
7. Passt alles? Klick auf **Eintragen**.
   ![Eintragen](img/a2_schritt07.png)
8. Die Tabelle zeigt jetzt alle Teile mit **DDP (WLED)**, der IP und dem Offset (0, 480, 960 …).
   ![Eingetragene Teile](img/a2_schritt08.png)
9. Klick auf **Speichern**. In der Statusleiste stehen dann „U2 DDP · U3 DDP …“.
   ![Speichern](img/a2_schritt09.png)

---

## Anleitung 3: WLED suchen

![Ablauf: WLED suchen](img/a3_ablauf.gif)

1. Achte oben auf die Leiste: Steht dort **„Probenmodus — es wird kein DMX gesendet“**, gibt
   LightOS gerade nichts aus.
   ![Hinweis Probenmodus](img/a3_schritt01.png)
2. Wenn du die IP schon kennst: Markier die Zeile mit der IP. Die Suche fragt diese IP dann
   direkt ab.
   ![Zeile markieren](img/a3_schritt02.png)
3. Klick auf **WLED suchen**. Der Knopf wird grau, daneben steht „Suche WLED-Geräte …“. Du kannst
   das Fenster weiter bedienen.
   ![WLED suchen](img/a3_schritt03.png)
   ![Suche läuft](img/a3_suche_laeuft.gif)
4. Wird kein Gerät gefunden, kommt nach ein paar Sekunden die Meldung **„Kein WLED gefunden
   (Multicast gesperrt?)“**. Dann trag die IP von Hand in „Patch“ ein. Spätestens nach
   10 Sekunden ist die Suche beendet.
   ![Kein WLED gefunden](img/a3_schritt04.png)

Wird ein WLED gefunden, öffnet sich eine Liste mit Name, IP und LED-Zahl. Du wählst eins aus,
und die IP landet in der markierten Zeile (ohne Markierung in einer neuen Zeile).
