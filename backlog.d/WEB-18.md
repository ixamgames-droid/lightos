ID: WEB-18
Prioritaet: P2
Status: todo
Titel: Klicktest-Befunde Web-Fernbedienung (2 Punkte, davon 1 mittel)

**Herkunft:** Live-Klicktest 23.11.2026 (echte App im abgeschotteten Fenster-Server, Probelauf), Bereich Web-Fernbedienung. Fotos/Protokoll lokal unter berichte/klicktest_2026_11_23/.

1. **Nach STOP über die Web-Fernbedienung bleibt im Playback-Reiter „Aktive Cue“ stehen** (mittel). Nachstellen: 1. Testshow „Hochzeit Komplett 2026“ (Probelauf) öffnen, Ausgabe → Web-Interface einschalten, im Dialog unter Erweitert die „Feste Fernbedienung“ einschalten und den Schlüssel notieren. 2. Reiter Playback öffnen, Cueliste „Aufwärmen (Follow)“ ist gewählt. 3. Mit einer Sitzung, die /?k=<fester Schlüssel> geöffnet hat, POST /api/go senden: Cue 1.0 „Amber“ wird aktiv (Zeile grün, „Aktive Cue: ▶ Cue 1.0 — Amber“). 4. POST /api/stop senden (Antwort 200 ok). Erwartet: Gleiches Bild wie beim STOP-Knopf in der App: „Aktive Cue: —“, „Nächste: —“. Gesehen: Die grüne Markierung der Zeile verschwindet, aber „Aktive Cue: ▶ Cue 1.0 — Amber / Nächste: 2.0 — Rosa“ bleibt stehen, auch nach einem Wechsel zum Reiter Bühne und zurück. GO+STOP mit den Knöpfen in der App zeigt dagegen korrekt „—“. Zweimal nachgestellt. Vermutung: Der Web-Pfad (_transport_info → cueliste_ziel.bediene_cueliste → stack.stop()) läuft am Signal vorbei, mit dem die Playback-Ansicht ihr Feld „Aktive Cue“ aktualisiert.
2. **Handy-Leiste: Knöpfe unten im Bearbeiten-Modus abgeschnitten** (gering). Nachstellen: App auf 1600x900 maximieren, VC → Handy-Konsole → Bearbeiten einschalten. Erwartet: „Automatisch füllen / Entfernen / Alles leeren“ sind sichtbar. Gesehen: Die Knopfzeile ist nur als Rand am unteren Ende zu sehen. Man muss in der Leiste scrollen.

**Erledigt, wenn:** jeder Punkt behoben (mit Test) oder begruendet verworfen ist.
