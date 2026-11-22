ID: WEB-17
Prioritaet: P3
Status: review
Status-Notiz: Sichtprobe am echten iPhone offen
Titel: Handy-Konsole: Titel einer Handy-Gruppe wird bei einzeln umrahmten Kacheln abgeschnitten

**Herkunft:** WEB-14-Probe am echten iPhone (22.11.2026). Liegen die Kacheln einer Handy-Gruppe nicht nebeneinander, bekommt jede einen eigenen Rahmen und nur die erste den Titel — der steht dann unter einer schmalen Kachel und ist abgeschnitten („Handy-T…“ statt „Handy-Test“). Funktion ist in Ordnung, nur die Beschriftung.

**Erledigt, wenn:** der Titel vollstaendig lesbar ist (z. B. ueber die Kachelbreite hinaus laufen lassen, umbrechen oder als Hinweis-Zeile ueber der ersten Kachel), ohne fremde Kacheln zu ueberdecken; Test in test_web14_handy_gruppen.py bzw. eigener Datei mit dem HTML-Aufbau.

**Geliefert:** Der Gruppen-Titel in `src/web/templates/konsole.html` wird nicht mehr per Auslassungszeichen gekuerzt, sondern bricht innerhalb der Breite seines eigenen Rahmens um (notfalls mitten im Wort). Beim Solo-Rahmen (oben angeschlagen) waechst er nach unten, bei der Handy-Gruppe (unten angeschlagen) nach oben – jeweils nur in die eigene Kachel, nie ueber eine fremde. Gilt fuer Einzel-Kacheln und gemeinsame Rahmen gleich. Test `tests/test_web17_gruppen_titel.py` prueft den CSS-Aufbau.
