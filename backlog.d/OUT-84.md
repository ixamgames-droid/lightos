ID: OUT-84
Prioritaet: P1
Status: review
Titel: Neues Universum nach Löschen bekommt doppelte Nummer, Speichern überschreibt dann still den DDP-Ausgang

**Herkunft:** Live-Klicktest 23.11.2026 (echte App im abgeschotteten Fenster-Server, Probelauf), Bereich Ausgabe-Dialog.

**Neues Universum nach Löschen bekommt doppelte Nummer, Speichern überschreibt dann still den DDP-Ausgang** (hoch). Nachstellen: Ausgabe > Konfigurieren > Universen. Es gibt U1 und U2 (U2 = DDP 127.0.0.1). U1 markieren > Löschen. Danach '+ Universum hinzufügen': die neue Zeile bekommt # 2 (_univ_add nimmt rowCount+1). Speichern: universes.json enthält num 2 zweimal, die Zeile 'Aus' überschreibt DDP. In der Statusleiste verschwindet 'U2 DDP'. _univ_save prüft nicht auf doppelte Nummern. Zweimal nachgestellt. Erwartet: Die nächste freie Nummer (1 oder 3) oder eine Ablehnung doppelter Nummern beim Speichern Gesehen: # 2 doppelt, beide Zeilen gespeichert, der WLED-Ausgang ist weg, ohne Meldung

**Geliefert:** '+ Universum hinzufügen' vergibt die kleinste freie Nummer (nach Löschen von U1 wieder die 1). 'Speichern' lehnt doppelte Nummern ab (auch solche, die erst durch das Klemmen auf 1–32 entstehen) und meldet 'Doppelte Universumsnummer — nicht gespeichert' mit den Zeilen; die Datei bleibt unverändert. Anleitung 'Ausgabe einrichten' (de/en) nachgezogen. Test: tests/test_out84_universen_dialog.py.
