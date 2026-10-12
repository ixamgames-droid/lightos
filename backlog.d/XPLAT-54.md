ID: XPLAT-54
Prioritaet: P3
Status: review
Titel: `test_backlog_fragmente.py` ist unter Windows rot -- der Helfer schreibt BACKLOG.md mit CRLF zurueck

**Herkunft:** Sitzung D, 11.10.2026, beim ersten Gate nach PROC-20 (#1001) am Windows-Testrechner; auf einem frischen Checkout von main `7f9674ce` nachgestellt. `WaechterTest::test_sammel_commit_deckt_keine_hand_aenderung_im_selben_zweig` erwartet „(+1/-1 Zeilen)“ und bekommt „(+15/-15 Zeilen)“. **Ursache:** der Testhelfer `_hand` liest BACKLOG.md des Wegwerf-Repos und schreibt es mit `Path.write_text(...)` zurueck -- ohne `newline` uebersetzt Python unter Windows jedes Zeilenende nach CRLF, die Datei hatte LF (so schreibt sie das Sammel-Werkzeug). Aus einer geaenderten Zeile werden damit alle 15. Das Werkzeug `tools/backlog_sammeln.py` selbst ist nicht betroffen, nur der Helfer des Tests; unter Linux faellt es nicht auf. **Fix:** `newline="\n"` im Helfer. Danach 45 von 45 gruen unter Windows (vorher 44). **Warum ein eigenes Item:** der Fall faerbt seit PROC-20 jedes Voll-Gate am Windows-Rechner rot und sieht dort wie ein Befund des jeweiligen Zweigs aus.
