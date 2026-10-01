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

5. **Ohne Claim.** (PROC-14) Claim und Release waren bis dahin reine
   Modelldisziplin — COORDINATION.md verlangt den Claim, aber nichts hat ihn
   durchgesetzt, und genau so ist ENG-20 (#743/#744) entstanden: zwei
   Sitzungen am selben Item, weil eine nie auf der Tafel stand. Jetzt muss der
   Zweig des PR einen Claim auf ``origin/sessions`` haben; sonst ist der PR
   nicht bereit, und bei der **Merge-Pruefung** (PR-Nummern angegeben) endet
   das Werkzeug mit Exit 1 — **auch ohne** ``--strict``, denn ein fehlender
   Claim ist keine Frage der Geduld, sondern eine Regel. Gelesen wird ueber
   die Lesefunktionen von ``session_claim.py`` (dieselbe Tafel, derselbe
   Verfall).

   ★ **Verfallen ist nicht fehlend.** Der Claim wird erst nach dem Merge
   released; ein PR, der laenger als ``session_claim.VERFALL`` (4 h) auf CI
   oder Merge wartet, hat dann einen verfallenen Claim. Fuer die
   Merge-Pruefung reicht „es gibt einen Claim fuer diesen Zweig" — ein
   verfallener laeuft mit Warnung durch (``refresh`` empfohlen), kein Exit 1.

   ★ **Der Bericht ueber alle offenen PRs** (ohne Nummern) zeigt fehlende
   Claims an, endet deswegen aber nur mit ``--strict`` mit Exit 1 — dort
   stehen auch alte PRs und PRs anderer Sitzungen. Entwuerfe zaehlen nie als
   „Claim fehlt": sie sind ohnehin nicht bereit.
   Bewusst uebersteuern (z. B. ein alter PR von vor der Regel):
   ``--ohne-claim "Begruendung"`` — nur zusammen mit PR-Nummern und nur mit
   Begruendung, damit daraus keine Pauschalabschaltung wird.

Das Werkzeug beantwortet die andere Frage: **sind Checks tatsaechlich GELAUFEN,
und gilt ihr Ergebnis noch?**

Aufruf::

    ./venv/bin/python tools/pr_bereit.py            # Bericht ueber alle offenen PRs
    ./venv/bin/python tools/pr_bereit.py 663 664    # nur diese (Exit 1 ohne Claim)
    ./venv/bin/python tools/pr_bereit.py --strict   # Exit 1, wenn einer nicht bereit ist
    ./venv/bin/python tools/pr_bereit.py 612 --ohne-claim "PR von vor PROC-14"
      (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Braucht ``gh`` mit angemeldetem Konto — deshalb ein Werkzeug und kein CI-Test
(dieselbe Begruendung wie bei ``backlog_status_drift.py``).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# PROC-14: dieselben Lesefunktionen wie `session_claim.py list` — eine eigene
# Nachbildung des Tafelformats oder des Verfalls wuerde frueher oder spaeter
# etwas anderes fuer "aktiv" halten als das Werkzeug, das den Claim schreibt.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_claim  # noqa: E402
# XPLAT-41: die Liste der nur beobachtenden Checks — dieselbe wie in pr_ci_status.
import _ci_beobachtend  # noqa: E402

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
OHNE_CLAIM = "ohne Claim"


def urteil(anzahl_checks: int, schluesse: list[str], zurueck: int,
           mergeable: str | None, kopf_alter_s: float | None = None,
           entwurf: bool = False,
           beobachtet: list[tuple[str, str]] | None = None) -> tuple[str, str]:
    """``(Urteil, Begruendung)`` — die ganze Entscheidungsregel an einer Stelle.

    ``anzahl_checks``/``schluesse`` sind nur die BLOCKIERENDEN Checks.
    ``beobachtet`` (XPLAT-41) sind ``(Name, Zustand)`` der Checks aus
    ``_ci_beobachtend.BEOBACHTEND`` — sie gehen nicht ins Urteil ein, ihr
    Zustand wird an die Begruendung angehaengt. Die Trennung macht
    :func:`teile_checks`, weil hier die Namen schon fehlen.

    Bewusst ohne Netz und ohne ``gh``: so misst der Test diese Funktion und
    nicht seine eigene Nachbildung des Aufrufs.

    Die Reihenfolge ist die Rangfolge. „Nie geprueft" steht ganz oben, weil es
    der einzige Zustand ist, den man am PR nicht sieht — rot, laufend und
    Konflikt zeigt die Oberflaeche von selbst.
    """
    u, grund = _urteil(anzahl_checks, schluesse, zurueck, mergeable,
                       kopf_alter_s, entwurf)
    zusatz = _ci_beobachtend.hinweis(beobachtet or [])
    return u, (f"{grund}; {zusatz}" if zusatz else grund)


def teile_checks(check_runs: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    """XPLAT-41: ``(blockierende Check-Runs, [(Name, Zustand) der beobachtenden])``.

    Hier und nicht in :func:`urteil`, weil nur die Check-Runs-Liste die Namen
    traegt — ``schluesse`` ist schon die nackte Ergebnisliste.
    """
    pflicht, beobachtet = [], []
    for c in check_runs:
        name = c.get("name") or ""
        if _ci_beobachtend.ist_beobachtend(name):
            beobachtet.append((name, _ci_beobachtend.zustand(
                c.get("status"), c.get("conclusion"))))
        else:
            pflicht.append(c)
    return pflicht, beobachtet


def _urteil(anzahl_checks: int, schluesse: list[str], zurueck: int,
            mergeable: str | None, kopf_alter_s: float | None,
            entwurf: bool) -> tuple[str, str]:
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


def _zweig_norm(name: str) -> str:
    """Zweigname ohne ``refs/heads/``- bzw. ``origin/``-Vorsatz.

    Auf der Tafel steht, was beim ``claim --branch`` eingetippt wurde — mal mit,
    mal ohne Vorsatz. Gross-/Kleinschreibung bleibt: Git-Zweige unterscheiden sie.
    """
    name = (name or "").strip()
    for vorsatz in ("refs/heads/", "origin/"):
        if name.startswith(vorsatz):
            name = name[len(vorsatz):]
    return name


def claim_pruefung(tafel: dict, zweig: str, t) -> tuple[bool, str]:
    """PROC-14: ``(Claim vorhanden?, Begruendung)`` fuer einen PR-Zweig.

    Rein und ohne Git — die Tafel kommt fertig gelesen herein, ``t`` ist die
    Uhrzeit, gegen die der Verfall gemessen wird. Ein Claim zaehlt, wenn sein
    Zweig dem PR-Zweig entspricht. Ein aktiver wird bevorzugt genannt; ist
    nur ein verfallener da (``session_claim.ist_verfallen``), zaehlt er
    trotzdem — der Release kommt erst nach dem Merge, und ein PR, der laenger
    als ``VERFALL`` auf CI wartet, darf daran nicht scheitern. Die Begruendung
    beginnt dann mit „Warnung" und nennt den ``refresh``-Befehl.
    """
    ziel = _zweig_norm(zweig)
    if not ziel:
        return False, "der PR nennt keinen Zweig — Claim nicht pruefbar"
    passend = [c for c in tafel.get("claims", [])
               if _zweig_norm(c.get("branch", "")) == ziel]
    if not passend:
        return False, (f"kein Claim auf der Tafel fuer Zweig {ziel} — erst "
                       f"`session_claim.py claim <ITEM> --branch {ziel}`, "
                       "oder bewusst `--ohne-claim \"Begruendung\"`")
    aktiv = [c for c in passend if not session_claim.ist_verfallen(c, t)]
    if not aktiv:
        c = passend[0]
        return True, (f"Warnung: Claim {c['item']} ({c['sitzung']}) fuer Zweig "
                      f"{ziel} ist verfallen (seit {c['seit']}) — fuer den Merge "
                      "genuegt er, aber besser `session_claim.py refresh "
                      f"{c['item']} --session {c['sitzung']}`")
    c = aktiv[0]
    return True, f"Claim {c['item']} ({c['sitzung']}) seit {c['seit']}"


def mit_claim(u: str, grund: str, claim_ok: bool, claim_grund: str,
              uebersteuert: str | None = None,
              entwurf: bool = False) -> tuple[str, str, bool]:
    """``(Urteil, Begruendung, Claim fehlt?)`` — Checks und Claim zusammengefuehrt.

    Ein echtes Check-Problem (rot, Konflikt, …) behaelt seinen Namen; der
    fehlende Claim wird angehaengt, nicht verschluckt. Ist sonst alles gruen,
    heisst das Urteil „ohne Claim". Der dritte Wert entscheidet bei der
    Merge-Pruefung ueber Exit 1 — unabhaengig von ``--strict``. Ein Entwurf
    zaehlt nie als „Claim fehlt" (er ist ohnehin nicht bereit); der Hinweis
    steht trotzdem in der Begruendung. Ein verfallener Claim kommt als
    ``claim_ok`` mit „Warnung" herein und wird angehaengt, nicht verschluckt.
    """
    if claim_ok:
        if claim_grund.startswith("Warnung"):
            return u, f"{grund}; {claim_grund}", False
        return u, grund, False
    if uebersteuert:
        return u, f"{grund}; Claim-Pruefung uebersteuert: {uebersteuert}", False
    if entwurf:
        return u, f"{grund}; ausserdem {claim_grund}", False
    if u == BEREIT:
        return OHNE_CLAIM, f"{grund}, aber {claim_grund}", True
    return u, f"{grund}; ausserdem {claim_grund}", True


def _lade_tafel() -> dict:
    """Tafel von ``origin/sessions`` — Werkzeug-Wurzel ist das Repo."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tafel, _spitze = session_claim.lade_tafel(repo)
    return tafel


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
    ap.add_argument("--ohne-claim", metavar="BEGRUENDUNG",
                    help="PROC-14: fehlenden Claim bewusst hinnehmen (nur mit "
                         "PR-Nummern, Begruendung Pflicht)")
    args = ap.parse_args(argv)
    if args.ohne_claim is not None:
        if not args.ohne_claim.strip():
            ap.error("--ohne-claim braucht eine Begruendung")
        if not args.pr:
            ap.error("--ohne-claim nur zusammen mit PR-Nummern — "
                     "keine Pauschalabschaltung fuer alle offenen PRs")

    if args.pr:
        nummern = [int(n) for n in args.pr]
    else:
        nummern = [p["number"] for p in _gh_json(
            "pr", "list", "--state", "open", "--limit", "50", "--json", "number")]
    if not nummern:
        print("keine offenen PRs.")
        return 0

    # PROC-14: die Tafel EINMAL lesen, nicht je PR. Ist sie nicht lesbar, faellt
    # die Claim-Pruefung durch (im Zweifel rot) — mit Grund statt Absturz.
    try:
        tafel, tafel_fehler = _lade_tafel(), None
    except Exception as e:  # noqa: BLE001 — git fehlt, kein Netz, …
        tafel, tafel_fehler = {"claims": []}, f"Tafel nicht lesbar ({e})"
    t = session_claim.jetzt()

    zeilen, nicht_bereit, ohne_claim, verfallen = [], 0, 0, 0
    for nr in sorted(nummern):
        info = _gh_json("pr", "view", str(nr), "--json",
                        "headRefOid,headRefName,title,mergeable,isDraft")
        runs = _gh_json("api", f"repos/:owner/:repo/commits/{info['headRefOid']}/check-runs")
        # XPLAT-41: beobachtende Legs (continue-on-error) zaehlen nicht mit —
        # ihr Check-Run waere sonst rot bzw. "laeuft noch" bis zum Timeout.
        liste, beobachtet = teile_checks(runs.get("check_runs") or [])
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
                          bool(info.get("isDraft")), beobachtet)
        if tafel_fehler:
            claim_ok, claim_grund = False, tafel_fehler
        else:
            claim_ok, claim_grund = claim_pruefung(
                tafel, info.get("headRefName") or "", t)
        verfallen += claim_ok and claim_grund.startswith("Warnung")
        u, grund, fehlt = mit_claim(u, grund, claim_ok, claim_grund,
                                    args.ohne_claim,
                                    bool(info.get("isDraft")))
        ohne_claim += fehlt
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
    if verfallen:
        print(f"{verfallen} PR(s) mit verfallenem Claim — kein Hindernis, "
              "aber besser `session_claim.py refresh` (PROC-14).")
    if ohne_claim:
        # Exit 1 nur bei der Merge-Pruefung (PR-Nummern) oder mit --strict:
        # der Bericht ueber alle offenen PRs enthaelt auch alte PRs und die
        # anderer Sitzungen — dort ist der fehlende Claim Auskunft, kein Halt.
        if args.pr or args.strict:
            print(f"{ohne_claim} PR(s) ohne Claim — Exit 1 (PROC-14).")
            return 1
        print(f"{ohne_claim} PR(s) ohne Claim (nur Bericht — Exit 1 erst mit "
              "PR-Nummern oder --strict, PROC-14).")
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
