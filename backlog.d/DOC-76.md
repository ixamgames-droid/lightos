ID: DOC-76
Prioritaet: P2
Status: review
Titel: Bilder/GIFs: OSC, Fernsteuerung per Art-Net/sACN, Interface-Assistent

Herkunft: Restliste aus DOC-74 (Texte stehen seit #1169 auf main, Bilder fehlten) und Auftrag des Projektinhabers vom 29.10.: alle neuen Anleitungen bebildert und mit GIFs fuer Ablaeufe.

**Geliefert** (alle offscreen in der Sandbox von `tools/anleitungsbilder.py`, nichts geht ins Netz):

- `docs/anleitung_osc/img/` (neue Szenen-Datei `szenen_osc.py`): `01_menue_osc.png` (Menue Ausgabe: OSC-Server und OSC-Zuordnungen), `02_eingang.png` (Reiter Eingang mit vier Beispiel-Zuordnungen, Muster `{n}`, Funktion, Lernen markiert), `03_rueckmeldung.png` (Reiter Rueckmeldung, Ziel 192.0.2.20:9000, Vorlage LightOS), `04_lernen.gif` (Lernen -> wartet -> `/Page1/Fader{n}` mit Versatz -200 eingetragen; die Nachricht kommt ueber die Lern-API `OscZuordnung.empfange`, der OSC-Server bleibt aus).
- `docs/anleitung_externe_pulte/img/01_fernsteuerung.png` (neue Szenen-Datei `szenen_externe_pulte.py`): Kasten „Fernsteuerung (Pult steuert LightOS)“ im Reiter DMX-Eingang mit drei Beispielzeilen; Spalten Executor/Schwelle %, „+ Zuordnung“, „Entfernen“, „Fernsteuerung aktiv“, Uebernehmen markiert. Uebernehmen wird nie gedrueckt, Art-Net-/sACN-Empfaenger werden vorher und nachher als „aus“ geprueft.
- `docs/anleitung_ausgabe_einrichten/img/` (Szenen-Datei erweitert): `12_assistent_nichts_gefunden.png` (Assistent ohne Geraet, `befunde=[]`, es wird nicht gesucht) und `13_testsignal_ablauf.gif` (Testsignal senden -> Rueckfrage mit Vorgabe Abbrechen, per Abbrechen geschlossen -> laeuft mit Stopp -> gestoppt; Laser-Ausgang durchgehend gesperrt). Die Ausgaenge sind Attrappen, der Ausgabe-Thread ist aus (Sicherheitsnetz bricht sonst ab).
- Eingebunden in `docs/anleitung_osc/ANLEITUNG.md`, `docs/anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md` und `docs/anleitung_ausgabe_einrichten/ANLEITUNG.md` + `.en.md`.

Nicht dabei: 3D-Bilder (offscreen schwarz, nicht Teil dieses Punkts).
