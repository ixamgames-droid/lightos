ID: PROC-22
Prioritaet: P3
Status: review
Titel: Merge-Konflikte in tools/doku_gates.txt vermeiden (merge=union)

Fast jeder Zweig hängt in `tools/doku_gates.txt` eine Zeile an dieselbe Stelle. Am 2026-10-13 kollidierten deshalb mehrere PRs in der Merge-Warteschlange nur an dieser Datei und mussten von Hand aufgelöst werden.
**Umsetzung (2026-10-13):** `.gitattributes` setzt für die Datei `merge=union` — beim lokalen Zusammenführen bleiben die Zeilen beider Seiten erhalten. Die Reihenfolge der Zeilen ist ohne Bedeutung, doppelte Zeilen schaden dem Gate nicht.
**Grenze:** Das wirkt beim Mergen mit git auf dem Rechner (Warteschlange, Nachziehen von main). Die Merge-Vorschau auf GitHub wertet die Einstellung nicht aus und kann weiter „Konflikt“ anzeigen.
