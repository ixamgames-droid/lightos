ID: XPLAT-55
Prioritaet: P2
Status: todo
Status-Notiz: ungeprüft, ob nach den Gate-Umbauten seit dem 11.10. noch zutreffend
Nach: XPLAT-54
Titel: Zeitbomben-Wächter läuft unter Windows ins 300-s-Limit und wird still nicht ausgewertet

**Herkunft:** Befund von Sitzung D (Windows x64) am 11.10.2026 auf der Tafel, mit dem Vorschlag „nächste freie Nummer XPLAT-55“; die Rückfrage blieb offen, eine Zeile wurde nie angelegt — nachgetragen am 20.10.2026.
**Befund:** `tests/test_zeitbomben_gate.py` lief seit dem main-Stand vom Abend des 11.10. an diesem Rechner in jedem Voll-Gate ins 300-s-Limit (zweimal nach 29 von 36 Fällen abgebrochen); am Nachmittag brauchte die Datei noch 142–182 s. Einzeln 36/36 grün in 386 s, davon 311 s allein `RepoTest::test_kein_test_im_repo_ist_eine_zeitbombe`. Der Runner toleriert das Zeitlimit — der Wächter wird unter Windows also nicht mehr ausgewertet. Vermutung (ungeprüft): die Kandidatenliste ist mit den am 11.10. gemergten Tests gewachsen.
**Fertig, wenn:** der Repo-Lauf wie in XPLAT-34 auf mehrere Tests/Dateien verteilt oder parallelisiert ist und unter Windows im Gate sicher unter dem Limit bleibt (gemessen), oder belegt ist, dass das Problem nicht mehr besteht.
