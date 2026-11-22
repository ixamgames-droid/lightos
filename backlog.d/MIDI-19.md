ID: MIDI-19
Prioritaet: P2
Status: todo
Titel: APC mini mk2: LED-Rueckmeldung startet nicht von selbst, Seitentaste leuchtet nicht, „APC LEDs“ schaltet einmal hin und her

**Herkunft:** Probe des Projektinhabers am 22.11.2026 (Linux, echte App, APC mini mk2 per USB, Show mit leerer Virtual Console). Die Seitentasten rechts wechseln die Seite richtig. Aber: (1) Beim Start oeffnet LightOS keinen MIDI-Ausgang zum APC (Log: „MIDI Ausgang: -“, obwohl beide APC-Eingaenge automatisch verbunden werden) — die LEDs bleiben dunkel. (2) Ein Druck auf „APC LEDs“ startet das LED-Feedback, schliesst es nach ~0,1 s wieder und startet es ~0,6 s spaeter erneut (Log [ApcMk2]: geoeffnet/gestartet/geschlossen/geoeffnet/gestartet); am Geraet leuchten die Tasten nur kurz auf. (3) Danach leuchtet auch die Taste der aktiven Seite nicht (beim APC mini mk1 ist die aktive Seite gelb, `apc_mini_feedback.py`).

**Erledigt, wenn:** ein erkanntes APC mini mk2 beim Start automatisch LED-Rueckmeldung bekommt (Ausgang passend zum Eingang oeffnen), ein Druck auf „APC LEDs“ genau einmal umschaltet, die Seitentaste der aktiven Seite leuchtet und aktive VC-Tasten ihre Pads leuchten lassen; Test mit einem Schein-MIDI-Ausgang (gesendete Noten/Farben pruefen), Gegenprobe am Geraet.
