# backlog.d — BACKLOG-Fragmente (PROC-20)

Hier liegt **je Item eine Datei** `<ID>.md`. `BACKLOG.md` selbst wird im
normalen PR **nicht** angefasst — so koennen zwei parallele PRs dort nicht mehr
kollidieren, und ein gemergtes Item bleibt nicht auf `review` stehen.

**Dateiname:** `<ID>.md`, z. B. `PROC-20.md`. Die ID vorher mit
`tools/backlog_ids.py --gruppe <GRUPPE>` holen (das Werkzeug sieht auch die
Fragmente aller offenen PR-Zweige).

**Inhalt:** Kopfzeilen `Name: Wert`, eine Leerzeile, dann Freitext.

Ein **neues** Item:

```
ID: UI-99
Prioritaet: P2
Status: review
Titel: Kurzer Titel des Items

Was fehlt, woran man es merkt, wann es erledigt ist. Mehrere Zeilen werden
beim Sammeln zu einer Tabellenzelle.
```

Ein **vorhandenes** Item (nur der Status aendert sich):

```
ID: FM-62
Status: teils
Status-Notiz: Punkt 1 geliefert, Punkt 2 offen
```

| Kopfzeile | Bedeutung |
|---|---|
| `ID` | Pflicht, gleich dem Dateinamen |
| `Status` | Pflicht: `todo`, `review`, `done`, `teils` oder `blocked` |
| `Prioritaet` | `P1`, `P2` oder `P3` — Pflicht fuer ein neues Item |
| `Titel` | Pflicht fuer ein neues Item |
| `Status-Notiz` | optional, eine Zeile; steht spaeter hinter dem Status |
| `Nach` | optional: ID der Zeile, hinter der ein neues Item stehen soll. Ohne Angabe landet es hinter der hoechsten Nummer derselben Gruppe; fuer eine ganz neue Gruppe ist `Nach` Pflicht |

Ein senkrechter Strich ist im Fragment nicht erlaubt (er wuerde die
Tabellenzeile zerschneiden). Relative Links so schreiben, als stuende der Text
schon in `BACKLOG.md` (`docs/...`, nicht `../docs/...`).

**Welcher Status im PR?** Wer ein Item umsetzt, schreibt `review` — beim
Sammeln nach dem Merge wird daraus von selbst `done (<Datum>, PR #N)`. Wer nur
einen Befund ablegt, schreibt `todo`. Arbeitet ein PR an einem Item, dessen
Fragment noch in `backlog.d/` liegt, aendert er diese Datei (statt eine zweite
anzulegen).

**Sammeln** (leitende Sitzung, regelmaessig, als kleiner eigener PR — auf einem
frischen Stand von `main`):

```
./venv/bin/python tools/backlog_sammeln.py --pruefen   # nur Form pruefen, Exit 1 bei Fehler
./venv/bin/python tools/backlog_sammeln.py --dry-run   # zeigen, was eingetragen wuerde
./venv/bin/python tools/backlog_sammeln.py             # eintragen + Fragmente loeschen
```

Danach mit dem Betreff `backlog: sammeln` committen. Ein neues Item bekommt
eine Tabellenzeile, bei einem vorhandenen wird nur die Statusspalte ersetzt.
Die PR-Nummer liest das Werkzeug aus dem Betreff des Merge-Commits (`… (#N)`);
`--pr N` setzt sie von Hand. Ein `review`-Fragment ohne PR-Nummer bleibt
liegen. Ein zweiter Lauf aendert nichts.

**Uebergang:** PRs, die `BACKLOG.md` noch direkt aendern, bleiben gueltig.
`tools/backlog_sammeln.py --waechter` und `tests/test_backlog_fragmente.py`
melden das nur als Hinweis, nie als Fehler.
