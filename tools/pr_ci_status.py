#!/usr/bin/env python3
"""PROC-10: unterscheidet "alle Checks gruen" von "es gibt gar keine Checks".

Aufruf:  venv/Scripts/python.exe tools/pr_ci_status.py <PR-Nummer>
         (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Exit 0 = mindestens ein abgeschlossener Check UND alle erfolgreich.
Exit 1 = alles andere, samt Begruendung auf stdout.

★ **Warum es das gibt.** Am 2026-09-03 ist Sitzung B ein PR durchgerutscht,
ohne dass CI gelaufen war: ``gh pr checks --watch`` beendete sich mit **Exit 0**
— nicht weil die Checks gruen waren, sondern weil es zu dem Zeitpunkt **gar
keine** gab. Der Lauf war zehn Sekunden alt und stand in der Warteschlange, die
Checks hingen noch nicht am PR. Der Exit-Code heisst also zweierlei, "alle
gruen" und "es gibt keine", und genau diese Zweideutigkeit hebelt PROC-03 aus,
das ein Merge ohne CI verhindern soll.

Der Schaden war damals klein (eine Zeile ``BACKLOG.md``; der Lauf auf ``main``
war anschliessend gruen). Der Mechanismus ist es nicht: **an genau diesem Tag
hat GitHub dreimal** fuer einen frischen PR verzoegert oder gar keinen Lauf
angelegt — zweimal bei Sitzung A (#705, #706), einmal bei B (#688). Der Zustand
"noch keine Checks" ist hier der Normalfall, nicht die Ausnahme.

⚠️ Eine Regel im Fliesstext hat an dieser Stelle nachweislich nicht getragen —
PROC-03 stand da und wurde trotzdem verletzt, weil das WERKZEUG die
Unterscheidung nicht anbot. Deshalb ein Werkzeug und kein weiterer Absatz.

**Was NICHT gruen ist** (im Zweifel rot, wie QA-53):
  * keine Checks              -> der haeufige, gefaehrliche Fall
  * ein Check noch nicht fertig (QUEUED/IN_PROGRESS/PENDING)
  * ein Ergebnis, das nicht SUCCESS/SKIPPED/NEUTRAL ist
  * ein unbekanntes Ergebnis  -> lieber melden als raten

**Abhilfe, wenn gar kein Lauf angelegt wurde** (von Sitzung A am 03.09. zweimal
erfolgreich gefahren, ohne Force-Push): ``main`` IN den Zweig mergen. Das
erzeugt frische SHAs, laesst sich normal pushen, und GitHub legt dafuer einen
Lauf an.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

#: Ergebnisse, die einen abgeschlossenen Check nicht rot machen. SKIPPED und
#: NEUTRAL sind bewusst dabei: ein bedingt uebersprungener Job ist kein
#: Fehlschlag. Alles andere - auch Unbekanntes - zaehlt als rot.
OK_ERGEBNISSE = {"SUCCESS", "SKIPPED", "NEUTRAL"}

#: Zustaende, die "laeuft noch" bedeuten.
LAEUFT_NOCH = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED"}

KEIN_LAUF_HINWEIS = (
    "  Abhilfe ohne Force-Push: `main` IN den Zweig mergen (frische SHAs,\n"
    "  normal pushbar) - GitHub legt dafuer einen Lauf an."
)


def bewerte(checks) -> tuple[bool, str]:
    """``(gruen, Begruendung)`` fuer die Rollup-Liste eines PRs.

    Rein und ohne Netz: ``checks`` ist die Liste aus
    ``gh pr view <n> --json statusCheckRollup``. Genau deshalb ist der Fall
    "leere Liste" hier ueberhaupt pruefbar - mit einem echten PR liesse er sich
    nicht auf Bestellung herstellen.
    """
    if checks is None:
        return False, "Kein Rollup erhalten - Status unbekannt, also NICHT gruen."
    if len(checks) == 0:
        return False, ("KEINE Checks am PR. Das ist NICHT gruen, sondern "
                       "ungeprueft (PROC-10).\n" + KEIN_LAUF_HINWEIS)

    offen, rot, unbekannt = [], [], []
    for eintrag in checks:
        name = str(eintrag.get("name") or eintrag.get("context") or "<ohne Namen>")
        status = str(eintrag.get("status") or eintrag.get("state") or "").upper()
        ergebnis = str(eintrag.get("conclusion") or "").upper()
        if status in LAEUFT_NOCH or (status and status != "COMPLETED" and not ergebnis):
            offen.append(f"{name} ({status or 'ohne Status'})")
        elif ergebnis in OK_ERGEBNISSE:
            continue
        elif ergebnis:
            rot.append(f"{name} ({ergebnis})")
        else:
            unbekannt.append(f"{name} (Status {status or '?'}, ohne Ergebnis)")

    if offen:
        return False, "Noch nicht fertig: " + ", ".join(offen)
    if rot:
        return False, "Fehlgeschlagen: " + ", ".join(rot)
    if unbekannt:
        return False, ("Unklares Ergebnis, im Zweifel rot: " + ", ".join(unbekannt))
    return True, f"{len(checks)} Check(s), alle erfolgreich."


def hole_checks(pr: str, repo: str | None = None):
    """``gh`` fragen. Getrennt von :func:`bewerte`, damit die Logik testbar bleibt."""
    befehl = ["gh", "pr", "view", str(pr), "--json", "statusCheckRollup"]
    if repo:
        befehl += ["--repo", repo]
    erg = subprocess.run(befehl, capture_output=True, text=True, timeout=120)
    if erg.returncode != 0:
        raise RuntimeError(f"gh scheiterte: {erg.stderr.strip()[:400]}")
    return json.loads(erg.stdout).get("statusCheckRollup")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0] or None)
    p.add_argument("pr", help="PR-Nummer")
    p.add_argument("--repo", help="owner/repo, falls nicht das aktuelle")
    a = p.parse_args(argv)
    try:
        checks = hole_checks(a.pr, a.repo)
    except Exception as e:                      # Netz/gh/Rechte
        print(f"[ci] Status nicht ermittelbar: {e}")
        print("[ci] NICHT gruen - ohne Auskunft wird nicht gemergt.")
        return 1
    gruen, grund = bewerte(checks)
    print(f"[ci] PR #{a.pr}: {grund}")
    if not gruen:
        print("[ci] NICHT mergen (PROC-10).")
        return 1
    print("[ci] Gruen - Merge erlaubt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
