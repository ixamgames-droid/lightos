ID: PRIV-06
Prioritaet: P2
Status: blocked
Status-Notiz: wartet auf Entscheidung des Projektinhabers (aendert PRIV-03 „nur vorwaerts“ fuer die Backlog-Dateien)
Titel: Klarname im Backlog-Bestand pseudonymisieren und das Gate auf BACKLOG.md/backlog.d ausdehnen

**Herkunft:** Befund der Verwalter-Sitzung (Laptop) auf der Tafel, 25.10.2026: `BACKLOG.md` auf main enthaelt den Klarnamen des Rig-Inhabers rund 50-mal (Altbestand seit Juli). Kein neuer Verstoss — PRIV-03 hat am 26.08.2026 entschieden, den Bestand stehen zu lassen, weil die Ersetzung jeden offenen Zweig in Konflikte gezwungen haette.
**Was sich seitdem geaendert hat:** Seit PROC-20 (10.10.2026) aendert kaum ein Zweig `BACKLOG.md` noch direkt (Fragmente in `backlog.d/`). Fuer die Backlog-Dateien ist die Ersetzung damit ohne Konfliktwelle moeglich. Die Git-Historie behaelt den Namen weiter (Rewrite bleibt eine Menschenentscheidung, PRIV-01).
**Vorschlag:** `tools/pseudonymisieren.py` nur auf `BACKLOG.md`, `BACKLOG_ARCHIVE.md` und `backlog.d/` anwenden (normaler Commit, Historie unveraendert); `tests/test_keine_privaten_dateien.py` bzw. `pruefe_oeffentlich()` mit der lokalen Namensliste auf diese Dateien ausdehnen, damit neue Eintraege den Namen nicht wieder hineintragen. Uebrige Dateien (Doku, Code-Kommentare) bleiben nach PRIV-03 unberuehrt, bis der Projektinhaber anders entscheidet.
**Fertig, wenn:** entschieden; bei „ja“ Backlog-Dateien ohne Klarnamen, Gate rot bei einem neu eingetragenen Klarnamen (Gegenprobe), keine offenen PRs mit BACKLOG.md-Aenderung im Konflikt.
