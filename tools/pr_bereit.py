#!/usr/bin/env python3
"""PROC-03 — ist ein offener PR wirklich pruefbar gruen, oder sieht er nur so aus?

Vor dem Merge wird ueblicherweise gefragt: „ist irgendein Check rot?" Diese Frage
uebersieht drei Zustaende, die alle wie gruen aussehen und alle schon vorgekommen
sind:

1. **Nie geprueft.** Am 24.08.2026 bekamen zwei PRs (#653, #659) fuer keinen
   ihrer Commits einen einzigen Check-Run — ``total_count`` = 0, Run-Liste leer.

   ★ **Frisch gepusht sieht genauso aus.** GitHub legt die Check-Runs erst ein
   paar Sekunden nach dem Push an; am 25.08. an #661 und #665 beobachtet, beide
   erholten sich von selbst. Deshalb wird ein Kopf-Commit, der juenger als
   ``FRISCH_SEKUNDEN`` ist, NICHT als "nie geprueft" gemeldet, sondern als
   "gerade gepusht". Ohne diese Unterscheidung meldet das Werkzeug bei jedem
   Push Fehlalarm — und ein Waechter, der das tut, wird umgangen.
   Kein Draft, Basis ``main``, Trigger passend, Nachbar-PRs derselben Stunde
   liefen normal. Die Merge-Schaltflaeche unterscheidet diesen Zustand nicht von
   „alles gruen", und ``gh pr merge`` fuehrt ihn kommentarlos aus.
   ★ **Close/Reopen hilft nicht** — an #659 gemessen, das ``reopened``-Ereignis
   erzeugte ebenfalls keinen Run. Was hilft, ist ein neuer Commit auf dem Zweig
   (ein Merge von ``origin/main`` genuegt).

2. **Gruen auf altem Stand.** Die Checks liefen, aber ``main`` ist seither
   weitergezogen. Das Ergebnis gilt fuer einen Stand, den es nicht mehr gibt —
   und genau so ist am 24.08. ein PR gruen gemeldet und Minuten spaeter
   ``CONFLICTING`` geworden.

   ★★ **Gemessen wird ueber die ABSTAMMUNG, nicht ueber die Uhr** (CDX-57, von
   Codex gefunden). Die erste Fassung verglich Zeiten: „ist der letzte
   ``main``-Commit juenger als der letzte Check?". Das hat ein Loch, und zwar
   genau dort, wo es weh tut: die drei Legs (Linux + zwei Windows) enden zu
   verschiedenen Zeiten. Zieht ``main`` weiter, WAEHREND sie laufen, endet die
   letzte Leg NACH dem neuen ``main``-Commit — die Zeitprobe sagt dann „aktuell",
   obwohl der gepruefte Stand diesen ``main``-Commit nie enthalten hat. Das
   Werkzeug haette also ausgerechnet den Zustand durchgewunken, gegen den es
   gebaut ist. Jetzt zaehlt ``behind_by`` aus
   ``repos/:owner/:repo/compare/main...<head>`` — eine Aussage ueber Commits,
   die keine Uhr braucht.

3. **Entwurf.** Ein Draft mit gruenen Checks ist nicht bereit, egal wie gruen er
   ist. Bis CDX-57 trug ``isDraft`` nur ein ``[DRAFT]`` an die Anzeige und ging
   nicht ins Urteil ein — ``--strict`` gab fuer einen Draft eine 0 zurueck.

4. **Teilweise geprueft.** Ein Teil der Legs hat abgeschlossen, der Rest nicht.
   ``gh pr checks`` zeigt das, aber „kein Fehlschlag" liest sich auch hier gruen.

Das Werkzeug beantwortet die andere Frage: **sind Checks tatsaechlich GELAUFEN,
und gilt ihr Ergebnis noch?**

Aufruf::

    ./venv/bin/python tools/pr_bereit.py            # Bericht ueber alle offenen PRs
    ./venv/bin/python tools/pr_bereit.py 663 664    # nur diese
    ./venv/bin/python tools/pr_bereit.py --strict   # Exit 1, wenn einer nicht bereit ist
      (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Braucht ``gh`` mit angemeldetem Konto — deshalb ein Werkzeug und kein CI-Test
(dieselbe Begruendung wie bei ``backlog_status_drift.py``).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

BEREIT = "bereit"
NIE_GEPRUEFT = "nie geprueft"
FRISCH = "gerade gepusht"
# Wie lange nach einem Push "noch keine Check-Runs" normal ist. Grosszuegig
# gewaehlt: ein Fehlalarm kostet Vertrauen, ein paar Minuten Geduld nichts.
FRISCH_SEKUNDEN = 180
ROT = "rot"
UNFERTIG = "laeuft noch"
ALT = "gruen auf altem Stand"
KONFLIKT = "Konflikt"
ENTWURF = "Entwurf"


def urteil(anzahl_checks: int, schluesse: list[str], zurueck: int,
           mergeable: str | None, kopf_alter_s: float | None = None,
           entwurf: bool = False) -> tuple[str, str]:
    """``(Urteil, Begruendung)`` — die ganze Entscheidungsregel an einer Stelle.

    Bewusst ohne Netz und ohne ``gh``: so misst der Test diese Funktion und
    nicht seine eigene Nachbildung des Aufrufs.

    Die Reihenfolge ist die Rangfolge. „Nie geprueft" steht ganz oben, weil es
    der einzige Zustand ist, den man am PR nicht sieht — rot, laufend und
    Konflikt zeigt die Oberflaeche von selbst.
    """
    if anzahl_checks == 0:
        if kopf_alter_s is not None and kopf_alter_s < FRISCH_SEKUNDEN:
            return FRISCH, (f"Kopf-Commit ist {int(kopf_alter_s)} s alt — GitHub legt "
                            "die Check-Runs erst kurz nach dem Push an. Gleich nochmal sehen.")
        return NIE_GEPRUEFT, ("kein einziger Check-Run auf dem Kopf-Commit — "
                              "das sieht aus wie gruen und ist es nicht")
    offen = [s for s in schluesse if s in (None, "", "pending", "queued", "in_progress")]
    fehl = [s for s in schluesse if s in ("failure", "cancelled", "timed_out", "action_required")]
    if fehl:
        return ROT, f"{len(fehl)} von {len(schluesse)} Checks nicht bestanden"
    if offen:
        return UNFERTIG, f"{len(offen)} von {len(schluesse)} Checks noch ohne Ergebnis"
    if mergeable == "CONFLICTING":
        return KONFLIKT, "Checks gruen, aber der Zweig kollidiert mit der Basis"
    if zurueck > 0:
        return ALT, (f"alle Checks gruen, aber der gepruefte Stand liegt {zurueck} "
                     "Commit(s) hinter main — das Urteil gilt fuer einen Stand, "
                     "den es nicht mehr gibt")
    if entwurf:
        # Zuletzt, weil die Zustaende darueber ECHTE Probleme sind: ein roter
        # Draft soll „rot" heissen, nicht „Entwurf".
        return ENTWURF, "Checks gruen und aktuell, aber der PR ist ein Entwurf"
    return BEREIT, f"{len(schluesse)} Checks gruen, Stand aktuell"


# ── Alles ab hier redet mit gh ───────────────────────────────────────────────

def _gh(*args: str) -> str:
    p = subprocess.run(("gh",) + args, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"gh fehlgeschlagen: {' '.join(args)}\n{p.stderr.strip()}")
    return p.stdout.strip()


def _gh_json(*args: str):
    # ★ NICHT mit `-q` aufrufen: `gh` gibt einen gefilterten Skalar dann als
    # ROHTEXT aus (`2026-08-24T22:03:48Z`, ohne Anfuehrungszeichen), und
    # json.loads bricht daran ab. Filtern wird hier in Python gemacht.
    return json.loads(_gh(*args) or "null")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pr", nargs="*", help="PR-Nummern (Vorgabe: alle offenen)")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1, wenn ein PR nicht bereit ist")
    args = ap.parse_args(argv)

    if args.pr:
        nummern = [int(n) for n in args.pr]
    else:
        nummern = [p["number"] for p in _gh_json(
            "pr", "list", "--state", "open", "--limit", "50", "--json", "number")]
    if not nummern:
        print("keine offenen PRs.")
        return 0

    zeilen, nicht_bereit = [], 0
    for nr in sorted(nummern):
        info = _gh_json("pr", "view", str(nr), "--json",
                        "headRefOid,title,mergeable,isDraft")
        runs = _gh_json("api", f"repos/:owner/:repo/commits/{info['headRefOid']}/check-runs")
        liste = runs.get("check_runs") or []
        schluesse = [c.get("conclusion") for c in liste]
        # ★ CDX-57: wie weit haengt der GEPRUEFTE Stand hinter main? Eine Aussage
        # ueber Commits — im Gegensatz zur frueheren Zeitprobe unabhaengig davon,
        # wann welche Leg fertig wurde.
        vgl = _gh_json("api", f"repos/:owner/:repo/compare/main...{info['headRefOid']}")
        zurueck = int(vgl.get("behind_by") or 0)
        kopf = _gh_json("api", f"repos/:owner/:repo/commits/{info['headRefOid']}")
        kopf_zeit = kopf.get("commit", {}).get("committer", {}).get("date")
        alter = None
        if kopf_zeit:
            from datetime import datetime, timezone
            alter = (datetime.now(timezone.utc)
                     - datetime.fromisoformat(kopf_zeit.replace("Z", "+00:00"))).total_seconds()
        u, grund = urteil(len(liste), schluesse, zurueck,
                          info.get("mergeable"), alter,
                          bool(info.get("isDraft")))
        if u != BEREIT:
            nicht_bereit += 1
        zeilen.append((nr, u, grund, info["title"], info.get("isDraft")))

    breite = max(len(z[1]) for z in zeilen)
    for nr, u, grund, titel, draft in zeilen:
        zeichen = "✓" if u == BEREIT else "⚠"
        print(f"{zeichen} #{nr:<4d} {u:<{breite}s}  {titel[:58]}")
        print(f"{'':>8}{'':<{breite}s}  {grund}" + ("   [DRAFT]" if draft else ""))

    print()
    print(f"{len(zeilen) - nicht_bereit} von {len(zeilen)} bereit.")
    return 1 if (nicht_bereit and args.strict) else 0


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    sys.exit(main())
