ID: LIZ-4
Prioritaet: P2
Status: todo
Titel: Windows-Bundle: neueste Microsoft-Laufzeit (VCRUNTIME140/_1) nach _internal legen — Qt ist mit 14.44 gebaut, geladen wird 14.42

**Herkunft:** Sitzung D, Bundle-Probe von #1101 (19.10.2026); Entscheidung des Projektinhabers 20.10.2026: neueste Fassung nach oben.
**Befund:** Im Bundle liegen 12 Laufzeit-DLLs in drei Fassungen: `_internal\VCRUNTIME140(_1).dll` 14.42.34438 (aus Python 3.12.10), unter `PySide6\`/`shiboken6\` MSVCP140/_1/_2 und VCRUNTIME140/_1 in 14.44.35211, `numpy.libs\msvcp140-<hash>.dll` 14.40 (private Kopie). Beim `--selbsttest` geladen: VCRUNTIME140/_1 in 14.42, MSVCP140* in 14.44. Qt/PySide6 ist mit 14.44 gebaut und läuft gegen vcruntime 14.42 — widerspricht Microsofts Regel (Laufzeit mindestens so neu wie das neueste Build-Werkzeug). Lief bisher, ein PC ohne installiertes VC++-Redistributable ist ungeprüft.
**Fertig, wenn:** der Bau (`packaging/windows/LightOS.spec` bzw. `qt_umfang.py`) die neueste im Bundle gefundene VCRUNTIME140/_1 nach `_internal\` legt; ein Wächter prüft, dass die Fassung dort ≥ jeder anderen im Bundle ist; Pipeline-Lauf grün; einmal an einem Windows-PC OHNE VC++-Redistributable gestartet (`--selbsttest` „ok“ und App-Start). UCRT bleibt ausgeschlossen (gehört zu Windows 10/11). Zuständig: Sitzung D.
