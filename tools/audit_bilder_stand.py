#!/usr/bin/env python3
"""Welche Punkte eines Bilder-Audits sind noch offen?

Ein Bilder-Audit ist eine Momentaufnahme. Wird danach nachgearbeitet — und das
wurde es —, sagt die Datei selbst nichts darüber; wer sie abarbeitet, sucht dann
Bilder, die längst neu sind oder gar nicht mehr existieren. Genau das ist am
2026-08-03 passiert: von 50 Punkten des Audits vom 20.07. waren **3 hinfällig**
(Bild entfernt) und **31 erneuert**, offen blieben **16**.

Dieses Skript stellt die Frage maschinell, damit sie nicht wieder von Hand
beantwortet werden muss:

    ./venv/bin/python tools/audit_bilder_stand.py docs/BILDER_AUDIT_2026-07-20.md

Es liest die `### \\`pfad\\` (schwere)`-Überschriften, prüft je Bild, ob es noch
existiert, und vergleicht sein letztes Git-Datum mit dem Datum im Dateinamen des
Audits.

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

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UEBERSCHRIFT = re.compile(r"^### `([^`]+)`\s*\((high|medium|low)\)", re.M)
_DATUM_IM_NAMEN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _audit_datum(pfad: str) -> str:
    t = _DATUM_IM_NAMEN.search(os.path.basename(pfad))
    if not t:
        print(f"WARNUNG: kein Datum im Dateinamen {os.path.basename(pfad)} — "
              f"ohne Stichtag ist 'erneuert' nicht bestimmbar.", file=sys.stderr)
        return ""
    return "-".join(t.groups())


def _letztes_git_datum(pfad: str) -> str:
    r = subprocess.run(["git", "log", "-1", "--format=%ad", "--date=short", "--", pfad],
                       cwd=_REPO, capture_output=True, text=True)
    return r.stdout.strip()


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

    stichtag = _audit_datum(audit)
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
        if stichtag and datum > stichtag:
            erneuert.append((rel, datum))
        else:
            offen.append((rel, schwere, datum))

    print(f"Audit: {os.path.basename(audit)}   Stichtag: {stichtag or '?'}")
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
        print(f"  [{s}] {rel}   (unveraendert seit {datum})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
