ID: LAS-42
Prioritaet: P2
Status: todo
Status-Notiz: braucht eine Messung am echten EL-400 mit dem Projektinhaber
Titel: EL-400: Achsen-Umkehr und Laser-Reiter rechnen die X/Y-Kanäle nach zwei verschiedenen Modellen

**Herkunft:** großer Bedientest QA-96 (Befund QA96-12, Gegenprüfung „unklar“, nur am Gerät zu entscheiden), 11./12.10.2026, Sitzung A; nachgetragen beim Abgleich verlorener IDs am 20.10.2026 (der Befund hatte keine eigene Zeile, LAS-30 führt nur „am echten EL-400 nachmessen“).
**Befund:** Die Achsen-Umkehr (LAS-30, `src/core/laser/achsen.py`) behandelt X/Y als zwei Richtungsbereiche (11–127 und 128–255), der Laser-Reiter/die Lage-Anzeige (`src/core/laser/profilangaben.py`) als einen durchgehenden Weg 11–255. Beispiel: Laser-Reiter „100 % rechts“ (DMX 11) mit „X-Achse umkehren“ im Patch — gesendet wird 128, das liest der Laser-Reiter als „4 % rechts“. Die vorhandenen Messpunkte (80 = rechts, 200 = links) passen zu beiden Modellen.
**Fertig, wenn:** am Gerät gemessen ist, wo das Bild bei X = 20, 120, 135 und 250 steht; das falsche Modell ist an das richtige angeglichen; ein Test hält die gemessenen Punkte fest und ist ohne die Änderung rot.
