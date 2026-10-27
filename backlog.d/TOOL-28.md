ID: TOOL-28
Prioritaet: P2
Status: review
Titel: Backlog-Sammeln uebernimmt den Freitext auch bei vorhandener Zeile
Nach: TOOL-27

**Befund:** `tools/backlog_sammeln.py` setzte bei einem Fragment, dessen ID schon als Zeile in BACKLOG.md stand, nur den Status und meldete „der Freitext des Fragments wird NICHT uebernommen“. Dadurch gingen Liefertexte verloren (20.10.2026 u. a. LAS-39, LIZ-2, QA-97, QA-98, LAS-40, VCB-42; 27.10.2026 bei 8 von 12 Fragmenten, von Hand nachgetragen). **Ergebnis:** Der Freitext wird an „**Wort:**“-Marken und Leerzeilen in Absaetze geteilt; jeder Absatz, der (Leerraum zusammengezogen, senkrechter Strich escaped) noch nicht in der Zeile steht, kommt als EIN „**Nachtrag aus Fragment (eingesammelt <Datum>):** …“ ans Ende der letzten Zelle. Spaltenzahl bleibt, ein zweiter Lauf haengt nichts an, `--pruefen`/`--dry-run` zeigen den Nachtrag ohne zu schreiben. Status-Logik (review -> done mit PR), Status-Notiz und Einfuegen neuer Zeilen unveraendert. README in `backlog.d/` nachgezogen. **Tests:** `tests/test_tool28_sammeln_freitext.py` (9 Faelle, 7 davon ohne Fix rot), `tests/test_backlog_fragmente.py` an das neue Verhalten angepasst. **Grenze:** Abgleich ist reiner Textvergleich je Absatz — ein in der Zeile umformulierter Absatz gilt als fehlend und wird erneut angehaengt.
