ID: TOOL-29
Prioritaet: P2
Status: review
Titel: Namenspruefung startet je Backlog-Zeile ein git — Privatsphaere-Gate auf Windows-ARM zu langsam

**Herkunft:** Befund von Sitzung B (Windows-ARM, 29.10.2026): `test_keine_privaten_dateien::test_kein_klarname_in_den_backlog_dateien` brauchte dort 182 s und lief im Gate ins Zeitlimit, weil `pruefe_oeffentlich` je Backlog-Zeile ueber `_klarnamen()` → `_git_klarnamen_datei()` ein `git rev-parse --git-common-dir` startete (rund 2450 Prozesse). **Fix:** der Ort `<git-common-dir>/klarnamen.txt` wird einmal je Prozess ermittelt; die Liste selbst wird weiter jedes Mal frisch gelesen. Test `tests/test_tool29_klarnamen_ein_git.py`.
