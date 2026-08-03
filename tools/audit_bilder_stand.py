#!/usr/bin/env python3
"""Welche Punkte eines Bilder-Audits sind noch offen?

Ein Bilder-Audit ist eine Momentaufnahme. Wird danach nachgearbeitet — und das
wurde es —, sagt die Datei selbst nichts darüber; wer sie abarbeitet, sucht dann
Bilder, die längst neu sind oder gar nicht mehr existieren. Genau das ist am
2026-08-03 passiert: von 50 Punkten des Audits vom 20.07. waren **3 hinfällig**
(Bild entfernt) und **47 erneuert** — offen blieb **keiner**.

Dieses Skript stellt die Frage maschinell, damit sie nicht wieder von Hand
beantwortet werden muss:

    ./venv/bin/python tools/audit_bilder_stand.py docs/BILDER_AUDIT_2026-07-20.md

Es liest die `### \\`pfad\\` (schwere)`-Überschriften, prüft je Bild, ob es noch
existiert, und vergleicht seinen letzten Git-Zeitstempel mit dem Zeitpunkt, zu
dem das Audit angelegt wurde.

**Auf die Sekunde, nicht auf den Tag** — die erste Fassung verglich tagesgenau
und meldete prompt 16 offene Punkte, darunter vier Bilder, die am Stichtag
selbst drei Stunden NACH dem Audit erneuert worden waren. Begründung in
`_audit_zeitpunkt`, Regressionstest in `tests/test_audit_bilder_stand.py`.

**Was es NICHT kann** — und das ist wichtig: Es prüft *Dateidaten*, nicht
*Inhalte*. Ein Bild, das nach dem Audit angefasst wurde, gilt hier als erneuert;
ob der beschriebene Befund wirklich behoben ist, sieht nur ein Mensch. Die Liste
ist eine **Vorsortierung**, kein Urteil — ein Werkzeug, das mehr behauptet, als
es misst, wäre schlimmer als keines.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UEBERSCHRIFT = re.compile(r"^### `([^`]+)`\s*\((high|medium|low)\)", re.M)


def _audit_zeitpunkt(pfad: str) -> str:
    """Wann wurde das Audit geschrieben? — aus dem GIT-LOG, nicht aus dem Namen.

    ⚠️ Die erste Fassung nahm das Datum aus dem Dateinamen und verglich
    tagesgenau mit `>`. Das ging schief: die Widget-Dialog-Bilder wurden am
    2026-07-20 um **22:39** erneuert — als direkte Reaktion auf das Audit, das
    am selben Tag um **19:18** entstand. Tagesgenau sind beide „2026-07-20",
    und ein striktes `>` zaehlte sie als OFFEN. Vier Bilder standen dadurch auf
    der Restliste, obwohl der Befund laengst behoben war; beim Nachaufnehmen
    waere ein besseres Bild durch ein schlechteres ersetzt worden.

    Deshalb: Zeitstempel des Commits, der das Audit HINZUGEFUEGT hat.
    """
    r = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ad", "--date=iso-strict",
         "--", pfad], cwd=_REPO, capture_output=True, text=True)
    zeilen = [z for z in r.stdout.splitlines() if z.strip()]
    if not zeilen:
        print(f"WARNUNG: kein Anlage-Commit fuer {os.path.basename(pfad)} "
              f"gefunden — ohne Stichzeit ist 'erneuert' nicht bestimmbar.",
              file=sys.stderr)
        return ""
    return zeilen[-1].strip()


def _letztes_git_datum(pfad: str) -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=iso-strict",
                        "--", pfad], cwd=_REPO, capture_output=True, text=True)
    return r.stdout.strip()


def ist_neuer(bild: str, stichzeit: str) -> bool:
    """Wurde das Bild NACH dem Audit angefasst?

    Vergleicht als Zeitpunkte, nicht als Zeichenketten. Lexikografisch ginge es
    fast immer gut — aber nur, solange beide Stempel denselben UTC-Offset
    tragen. Ueber einen Sommerzeit-Wechsel hinweg ist `…T02:30:00+02:00`
    (00:30 UTC) alphabetisch groesser als `…T02:00:00+01:00` (01:00 UTC) und
    damit falschherum. Dieselbe Sorte Ungenauigkeit wie der Tagesvergleich,
    nur seltener sichtbar — deshalb hier gleich mit erledigt.

    Leere Angaben heissen „unbekannt" und damit NICHT neuer: im Zweifel bleibt
    ein Punkt offen, statt stillschweigend als erledigt zu verschwinden. Das
    gilt auch fuer den TypeError, den ein Stempel OHNE Zeitzone ausloest
    (`--date=iso-strict` liefert immer einen Offset — aber die Regel darf nicht
    daran haengen, dass der Aufrufer das Format richtig waehlt).
    """
    if not bild or not stichzeit:
        return False
    try:
        return datetime.fromisoformat(bild) > datetime.fromisoformat(stichzeit)
    except (ValueError, TypeError):
        print(f"WARNUNG: unlesbarer Zeitstempel ({bild!r} / {stichzeit!r}) — "
              f"Punkt bleibt offen.", file=sys.stderr)
        return False


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    audit = sys.argv[1]
    if not os.path.isabs(audit):
        audit = os.path.join(_REPO, audit)
    if not os.path.exists(audit):
        print(f"FEHLER: {audit} gibt es nicht", file=sys.stderr)
        return 1

    stichtag = _audit_zeitpunkt(audit)
    punkte = _UEBERSCHRIFT.findall(open(audit, encoding="utf-8").read())
    if not punkte:
        print("FEHLER: keine `### `pfad` (schwere)`-Ueberschriften gefunden — "
              "Format geaendert?", file=sys.stderr)
        return 1

    hinfaellig, erneuert, offen = [], [], []
    for rel, schwere in punkte:
        voll = os.path.join(_REPO, rel)
        if not os.path.exists(voll):
            hinfaellig.append((rel, schwere))
            continue
        datum = _letztes_git_datum(rel)
        if ist_neuer(datum, stichtag):
            erneuert.append((rel, datum))
        else:
            offen.append((rel, schwere, datum))

    print(f"Audit: {os.path.basename(audit)}\nStichzeit (Anlage-Commit): {stichtag or '?'}")
    print(f"Punkte gesamt: {len(punkte)}")
    print(f"  hinfaellig (Bild existiert nicht mehr): {len(hinfaellig)}")
    for rel, s in hinfaellig:
        print(f"     {rel}")
    print(f"  seit dem Audit angefasst (Befund VERMUTLICH behoben — "
          f"Dateidatum, kein Inhaltsvergleich): {len(erneuert)}")
    print(f"  OFFEN: {len(offen)}")
    for ordner, n in Counter(r.split('/')[1] for r, _, _ in offen).most_common():
        print(f"     {n:>3}  {ordner}")
    print()
    for rel, s, datum in sorted(offen, key=lambda x: x[0]):
        print(f"  [{s}] {rel}\n           unveraendert seit {datum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
