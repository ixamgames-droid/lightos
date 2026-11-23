ID: OUT-85
Prioritaet: P2
Status: todo
Titel: Klicktest-Befunde Ausgabe-Dialog (5 Punkte, davon 2 mittel)

**Herkunft:** Live-Klicktest 23.11.2026 (echte App im abgeschotteten Fenster-Server, Probelauf), Bereich Ausgabe-Dialog. Fotos/Protokoll lokal unter berichte/klicktest_2026_11_23/.

1. **Art-Net übernimmt ungültige Ziel-IP und meldet 'Aktiv (gespeichert)'** (mittel). Nachstellen: Reiter Art-Net > Ziel-IP '999.1.1' oder 'abc' eintragen > 'Art-Net aktivieren' anhaken > Übernehmen. Status: 'Aktiv → abc · Universum 1 (gespeichert)'. In universes.json steht patch 'abc'. _apply_artnet prüft die IP nicht. Zweimal nachgestellt. Dasselbe in 'Matrix verteilen': 'abc' lässt 'Eintragen' aktiv. Erwartet: Ungültige IP ablehnen, mit Hinweis Gesehen: Wird angenommen, als aktiv angezeigt und gespeichert
2. **Schließen verwirft ungespeicherte Universen-Änderungen ohne Rückfrage** (mittel). Nachstellen: Universen > '+ Universum hinzufügen' (und z. B. DDP mit IP setzen) > Schließen > Dialog wieder öffnen: die Zeile ist weg, es kam keine Warnung. Zweimal nachgestellt. Erwartet: Rückfrage 'Änderungen speichern?' oder ein deutlicher Hinweis Gesehen: Still verworfen
3. **Universum mit gepatchten Geräten lässt sich ohne Warnung löschen** (gering). Nachstellen: Universen > U1 markieren (14 Geräte gepatcht) > Löschen > Speichern. Es kommt keine Rückfrage. Danach warnt nur die Statusleiste 'U1 ohne Ausgang'. Erwartet: Hinweis, dass noch Geräte auf U1 gepatcht sind Gesehen: Sofort gelöscht
4. **Probelauf-Text im uDMX-Reiter ist irreführend** (gering). Nachstellen: Probelauf starten > Ausgabe > Konfigurieren > uDMX. Dort steht 'STAB-39: echte Ausgabe nur aus der App (main.py)', obwohl die App aus main.py läuft (gesperrt ist sie wegen CLAUDECODE). Erwartet: z. B. 'Probelauf: Ausgabe gesperrt' Gesehen: Text verweist auf main.py
5. **Kosmetik im Universen-Reiter** (gering). Nachstellen: a) Neue Zeilen haben die #-Spalte linksbündig, geladene Zeilen zentriert. b) Ein zweizeiliger WLED-Status verschiebt die Knopfreihe um 2 px. c) 'Gespeichert' zeigt nur den rohen Dateipfad. d) Der Hinweis '… „Speichern“ übernimmt' bleibt nach dem Speichern stehen. e) Datenbank > LED-Matrix-Assistent > 'In Bibliothek speichern' schließt ohne jede Rückmeldung und ohne Patch-Angebot. Erwartet: Einheitlich, mit klarer Rückmeldung Gesehen: siehe Fotos

**Erledigt, wenn:** jeder Punkt behoben (mit Test) oder begruendet verworfen ist.
