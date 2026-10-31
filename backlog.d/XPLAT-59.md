ID: XPLAT-59
Prioritaet: P3
Status: review
Titel: Startskripte unter Windows - Warnung lesbar machen und Prozess-Arch im Rueckfall

Nebenbefunde von Sitzung B zu XPLAT-57 (#1163) und Gegenpruefung von A. (1) Die Warnung vor nativem ARM64-Python (XPLAT-51) war in start.ps1 blassgelb (-ForegroundColor Yellow) und in start.bat gar nicht hervorgehoben, im Windows Terminal (Campbell) kaum von normalem Text zu unterscheiden. Jetzt Schwarz auf Gelb: start.ps1 per -ForegroundColor Black -BackgroundColor Yellow, start.bat per ANSI-Folge (ESC entsteht zur Laufzeit ueber prompt $E, nur im ARM-Zweig, also Windows 10 1709 oder neuer mit ANSI-faehiger Konsole). Beide Skripte bleiben reines ASCII. (2) start.ps1: griff der Rueckfall ueber PROCESSOR_IDENTIFIER, blieb $procArch leer und die Kopfzeile zeigte eine leere Prozess-Arch; jetzt Rueckfall auf $env:PROCESSOR_ARCHITECTURE. Waechter: tests/test_xplat59_startwarnung_lesbar.py. **Offen:** Sichtpruefung auf dem Windows-ARM-Rig (Farbe in Windows Terminal und conhost).
