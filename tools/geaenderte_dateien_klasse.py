#!/usr/bin/env python3
"""PROC-19 — aendert ein Zweig NUR Doku-/Verwaltungsdateien? Gibt ``doku`` oder ``voll`` aus.

Die CI faehrt fuer jeden PR die volle segmentierte Suite (~28 min Linux, dazu
die Windows-Legs) — auch wenn nur Markdown geaendert wurde. Weil die
Merge-Warteschlange einen PR nach dem anderen auf aktuellem ``main`` gruen
sehen will (``tools/pr_bereit.py``), staut jeder Backlog- oder Anleitungs-PR
alle anderen. Dieses Werkzeug entscheidet, ob ein PR den kurzen Weg nehmen
darf: dieselben Jobs, dieselben Job-NAMEN, aber statt der Suite nur die
Doku-/Backlog-/Privatsphaere-Gates aus ``tools/doku_gates.txt``.

Was als Doku zaehlt (alles andere ist ``voll``):

* ``*.md`` direkt im Repo-Wurzelverzeichnis (README, BACKLOG*, WORKFLOW ...),
* ``changelog.d/*.md`` und ``backlog.d/*.md`` (Fragmente, PROC-09/PROC-20),
* unter ``docs/``: Markdown und Bilder (``.md .png .jpg .jpeg .gif .webp .svg``).

Bewusst NICHT Doku: jede ``.md`` ausserhalb davon (``tools/README.md`` ist
erzeugt und wird gegen den Code geprueft, ``fixtures/bibliothek/SCHEMA.md``
gehoert zur Bibliothek), Skripte und JSON unter ``docs/`` (z. B.
``bilder.json``, ``capability_manifest.json`` — die pruefen Tests gegen den
Code), ``tools/``, ``tests/``, ``.github/``.

Sicherheitsnetz — im Zweifel ``voll``:

* unbekannte Datei, leere Liste, merkwuerdiger Pfad (``..``, absolut,
  Backslash) -> ``voll``;
* jeder Git-Fehler -> ``voll``;
* gerechnet wird gegen den MERGE-BASE mit der Basis, nicht gegen den letzten
  Commit — sonst rutschte Code durch, sobald der letzte Commit nur Doku
  aendert. Umbenennungen zaehlen mit ALTEM und NEUEM Pfad (``--no-renames``);
* ``--ci``: alles ausser einem Pull-Request ist ``voll`` (Push nach ``main``
  faehrt immer die volle Suite). Im Pull-Request steht der Checkout auf dem
  Test-Merge von GitHub (``refs/pull/N/merge``): Elter 1 ist die Basis, Elter 2
  der PR-Kopf. Das wird GEPRUEFT (zwei Eltern, Elter 2 == ``PR_KOPF_SHA``),
  bevor gegen Elter 1 verglichen wird. Stimmt es nicht, gilt ``voll``.

Aufruf (aus dem Repo-Root):
    python tools/geaenderte_dateien_klasse.py                 # gegen origin/main
    python tools/geaenderte_dateien_klasse.py --basis REF
    python tools/geaenderte_dateien_klasse.py --gates         # Liste der Doku-Gates
    python tools/geaenderte_dateien_klasse.py --ci            # in der CI (schreibt GITHUB_OUTPUT)

Ausgabe auf stdout ist genau ``doku`` oder ``voll`` (bzw. bei ``--gates`` je
Zeile eine Testdatei); die Begruendung geht nach stderr.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys

DOKU = "doku"
VOLL = "voll"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES_DATEI = os.path.join(REPO, "tools", "doku_gates.txt")

#: Was unter ``docs/`` als Doku gilt. Skripte und JSON bewusst nicht.
DOCS_ENDUNGEN = frozenset({".md", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})

#: Fragment-Ordner: nur ``<ordner>/<datei>.md``, keine Unterordner. ``backlog.d``
#: (PROC-20) steht hier, damit ein reiner Backlog-PR — ein neues Fragment oder
#: der Sammel-PR, der Fragmente loescht und BACKLOG.md schreibt — den kurzen
#: Weg nimmt. Seine Gates (``test_backlog_*``, ``test_doc_links``) laufen dort.
FRAGMENT_ORDNER = frozenset({"changelog.d", "backlog.d"})


def ist_doku(pfad: str) -> bool:
    """``True`` nur fuer einen sauberen, repo-relativen Doku-Pfad."""
    if not isinstance(pfad, str) or not pfad or pfad != pfad.strip():
        return False
    if "\\" in pfad or pfad.startswith("/") or any(ord(c) < 32 for c in pfad):
        return False
    teile = pfad.split("/")
    if any(t in ("", ".", "..") for t in teile):
        return False
    endung = os.path.splitext(teile[-1])[1].lower()
    if len(teile) == 1:
        return endung == ".md"
    if teile[0] in FRAGMENT_ORDNER:
        return len(teile) == 2 and endung == ".md"
    if teile[0] == "docs":
        return endung in DOCS_ENDUNGEN
    return False


def nicht_doku(pfade) -> list[str]:
    """Die Pfade, die den kurzen Weg verhindern (fuer die Begruendung)."""
    return [p for p in pfade if not ist_doku(p)]


def klasse(pfade) -> str:
    """``doku`` nur, wenn es Aenderungen gibt und ALLE Doku sind."""
    pfade = list(pfade)
    if not pfade:
        return VOLL
    return VOLL if nicht_doku(pfade) else DOKU


def _git(repo: str, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True,
        text=True, encoding="utf-8").stdout


def geaenderte_dateien(basis: str, repo: str = REPO) -> list[str] | None:
    """Alle Pfade, die ``HEAD`` gegenueber dem Merge-Base mit ``basis`` aendert.

    ``None`` bei jedem Git-Fehler (Aufrufer -> ``voll``).
    """
    try:
        mb = _git(repo, "merge-base", basis, "HEAD").strip()
        if not mb:
            return None
        roh = _git(repo, "diff", "--name-only", "--no-renames", "-z", mb, "HEAD")
    except (subprocess.CalledProcessError, OSError, UnicodeError):
        return None
    return [p for p in roh.split("\0") if p]


def klasse_gegen(basis: str, repo: str = REPO) -> tuple[str, str]:
    """``(Klasse, Begruendung)`` fuer ``HEAD`` gegen den Merge-Base mit ``basis``."""
    pfade = geaenderte_dateien(basis, repo)
    if pfade is None:
        return VOLL, f"Git-Vergleich gegen {basis} fehlgeschlagen — im Zweifel voll"
    if not pfade:
        return VOLL, f"keine Aenderung gegen {basis} — im Zweifel voll"
    stoerer = nicht_doku(pfade)
    if stoerer:
        zeige = ", ".join(stoerer[:5]) + (" ..." if len(stoerer) > 5 else "")
        return VOLL, f"{len(stoerer)} von {len(pfade)} Dateien sind keine Doku: {zeige}"
    return DOKU, f"alle {len(pfade)} geaenderten Dateien sind Doku"


def ci_klasse(env, repo: str = REPO) -> tuple[str, str]:
    """Klasse fuer einen CI-Lauf; ``env`` ist ``os.environ`` (oder ein dict)."""
    ereignis = env.get("GITHUB_EVENT_NAME", "")
    if ereignis != "pull_request":
        return VOLL, f"Ereignis '{ereignis or '?'}' ist kein Pull-Request — volle Suite"
    kopf = (env.get("PR_KOPF_SHA") or "").strip()
    if not kopf:
        return VOLL, "PR_KOPF_SHA fehlt — im Zweifel voll"
    try:
        eltern = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()[1:]
    except (subprocess.CalledProcessError, OSError, UnicodeError):
        return VOLL, "HEAD nicht lesbar — im Zweifel voll"
    if len(eltern) != 2 or eltern[1] != kopf:
        return VOLL, "HEAD ist nicht der Test-Merge dieses PR-Kopfes — im Zweifel voll"
    return klasse_gegen(eltern[0], repo)


def _muster(gates_datei: str = GATES_DATEI) -> tuple[list[str], list[str]]:
    """``(Gate-Muster, bewusst ausgenommene Muster)`` aus ``doku_gates.txt``."""
    gates, ausgenommen = [], []
    with open(gates_datei, encoding="utf-8") as fh:
        for zeile in fh:
            z = zeile.split("#", 1)[0].strip()
            if not z:
                continue
            if z.startswith("!"):
                ausgenommen.append(z[1:].strip())
            else:
                gates.append(z)
    return gates, ausgenommen


def doku_gates(repo: str = REPO, gates_datei: str | None = None) -> list[str]:
    """Die Testdateien des kurzen Wegs, als ``tests/test_x.py`` (sortiert)."""
    gates, _ = _muster(gates_datei or os.path.join(repo, "tools", "doku_gates.txt"))
    tests = os.path.join(repo, "tests")
    namen = sorted(n for n in os.listdir(tests)
                   if n.startswith("test_") and n.endswith(".py"))
    return ["tests/" + n for n in namen
            if any(fnmatch.fnmatchcase(n, m) for m in gates)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--basis", default="origin/main",
                    help="Vergleichsbasis (gerechnet wird gegen den Merge-Base)")
    ap.add_argument("--ci", action="store_true",
                    help="CI-Modus: liest GITHUB_EVENT_NAME/PR_KOPF_SHA, schreibt GITHUB_OUTPUT")
    ap.add_argument("--gates", action="store_true",
                    help="die Testdateien des kurzen Wegs ausgeben")
    args = ap.parse_args(argv)

    if args.gates:
        dateien = doku_gates()
        if not dateien:
            print("[klasse] FEHLER: tools/doku_gates.txt trifft keine Testdatei",
                  file=sys.stderr)
            return 1
        print("\n".join(dateien))
        return 0

    if args.ci:
        # Der CI-Modus scheitert NIE an sich selbst: jede Ausnahme heisst voll.
        try:
            k, grund = ci_klasse(os.environ)
        except Exception as e:  # noqa: BLE001 — Sicherheitsnetz
            k, grund = VOLL, f"unerwarteter Fehler ({type(e).__name__}) — im Zweifel voll"
        ausgabe = os.environ.get("GITHUB_OUTPUT")
        if ausgabe:
            with open(ausgabe, "a", encoding="utf-8") as fh:
                fh.write(f"klasse={k}\n")
    else:
        k, grund = klasse_gegen(args.basis)
    print(f"[klasse] {k}: {grund}", file=sys.stderr)
    print(k)
    return 0


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
