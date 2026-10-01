#!/usr/bin/env python3
"""CHANGELOG-Fragmente sammeln — und direkte CHANGELOG-Aenderungen melden (PROC-09).

Warum es das gibt
-----------------
Der Kopf von ``CHANGELOG.md`` war ein **garantierter Konflikt** zwischen zwei
parallel arbeitenden Sitzungen: jeder PR schrieb seinen Eintrag an dieselbe
Stelle direkt unter ``## [Unreleased]``. Nachgemessen ueber die PRs #690–#759:
21 Zweig-Merges, 17 davon mit Konflikt (81 %), CHANGELOG.md war in 11 davon
beteiligt. GitHub startet fuer einen konfliktbehafteten PR nicht einmal die CI
— man wartet auf Pruefungen, die nie kommen. Die Aufloesung war jedes Mal
dieselbe (beide Eintraege behalten): Reibung ohne Erkenntnis.

Die Antwort ist das towncrier-Muster: **je PR eine eigene Datei** unter
``changelog.d/``. Zwei PRs legen zwei verschiedene Dateien an und koennen
deshalb nicht mehr kollidieren. Erst ein Sammel-Lauf (Release oder bewusste
Aufraeumrunde, EINE Sitzung) schreibt die Fragmente in ``CHANGELOG.md``.

Fragment-Format
---------------
Dateiname ``JJJJ-MM-TT-<ID>.md`` (z. B. ``2026-10-01-UI-64.md``; mehrere IDs
mit Bindestrich/Unterstrich verbinden). Inhalt ist der **fertige** Abschnitt,
genau so, wie er im CHANGELOG stehen soll::

    ### 2026-10-01 — Kurzer Titel (UI-64)

    #### Behoben

    - **Bereich:** was der Nutzer jetzt anders erlebt.

Relative Links schreibt man so, als stuende der Text schon in
``CHANGELOG.md`` (also ``docs/...``, nicht ``../docs/...``) —
``tools/check_doc_links.py`` prueft sie genau so.

Aufruf::

    ./venv/bin/python tools/changelog_sammeln.py --pruefen   # Trockenlauf
    ./venv/bin/python tools/changelog_sammeln.py             # sammeln + Fragmente loeschen
    ./venv/bin/python tools/changelog_sammeln.py --waechter  # direkte Aenderungen melden

Windows entsprechend mit ``venv/Scripts/python``, z. B.::

    venv/Scripts/python tools/changelog_sammeln.py --pruefen

Der Waechter (auch als Test ``tests/test_changelog_fragmente.py`` im Gate)
---------------------------------------------------------------------------
Er vergleicht ``CHANGELOG.md`` im Arbeitsbaum mit dem Stand an der
**Abzweigung von origin/main** (``git merge-base``, also dasselbe wie
``git diff origin/main...``). Erlaubt ist eine Aenderung nur, wenn

* jede hinzugekommene, nicht leere Zeile aus einem Fragment stammt, das es an
  der Abzweigung gab und das jetzt geloescht ist (= ein Sammel-Lauf), und keine
  bestehende Zeile entfernt wurde, **oder**
* ein Commit seit der Abzweigung, der CHANGELOG.md anfasst, eine Betreffzeile
  mit ``changelog:`` beginnt (bewusste Korrektur, z. B. eine umbenannte ID).
  Das gilt auch fuer den **Release-Schritt**: ``## [Unreleased]`` in
  ``## [x.y.z] — Datum`` umbenennen und einen neuen, leeren Unreleased-Kopf
  setzen erzeugt Zeilen ohne Fragment — Betreff ``changelog: release x.y.z``.

★ **Bewusst still bestanden** ohne ``origin/main``, ohne Merge-Basis (flacher
Klon) oder ausserhalb eines Git-Baums. Genau so sieht der CI-Lauf aus:
``actions/checkout`` holt nur den einen PR-Merge-Commit, ``origin/main``
fehlt. Der Waechter ist ein **lokales** Gate fuer den Zweig, den man gerade
baut; im CI wuerde er ohne PR-Kontext nur raten — und ein Waechter, der im
Merge-Commit Fehlalarm schlaegt, wird abgeschaltet. Ueber die Merge-Basis
statt ueber ``origin/main`` direkt gerechnet, damit ein Zweig, der hinter
``main`` liegt, die zwischenzeitlich auf ``main`` gesammelten Eintraege nicht
als eigene Aenderung angelastet bekommt.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRAGMENT_ORDNER = "changelog.d"
CHANGELOG = "CHANGELOG.md"
UNRELEASED = "## [Unreleased]"
MARKER = "changelog:"

# JJJJ-MM-TT-<ID>.md — die README.md im Ordner faellt damit automatisch heraus.
FRAGMENT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([A-Za-z0-9][A-Za-z0-9._-]*)\.md$")


# --------------------------------------------------------------------------- git

def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Nur lesend; UTF-8 fest, sonst stirbt es auf Windows an ★/— (XPLAT-20)."""
    try:
        p = subprocess.run(("git", *args), cwd=str(repo), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return 1, ""
    return p.returncode, p.stdout


# --------------------------------------------------------------------- Fragmente

def ist_fragment_name(name: str) -> bool:
    return FRAGMENT_NAME.match(name) is not None


def pruefe_fragment(name: str, text: str) -> list[str]:
    """Formfehler eines Fragments (leer = in Ordnung)."""
    fehler = []
    if not ist_fragment_name(name):
        fehler.append(f"{name}: Dateiname passt nicht zu JJJJ-MM-TT-<ID>.md")
    rumpf = text.strip()
    if not rumpf:
        fehler.append(f"{name}: Fragment ist leer")
        return fehler
    if not rumpf.startswith("### "):
        fehler.append(f"{name}: muss mit einer '### '-Ueberschrift beginnen "
                      "(Datum — Titel (ID))")
    im_code = False
    for nr, zeile in enumerate(rumpf.splitlines(), 1):
        if zeile.lstrip().startswith(("```", "~~~")):
            im_code = not im_code
            continue
        if not im_code and re.match(r"^#{1,2}\s", zeile):
            fehler.append(f"{name}:{nr}: '#'/'##'-Ueberschriften zerbrechen den "
                          "CHANGELOG-Aufbau — ab '###' abwaerts schreiben")
    return fehler


def _lies_text(pfad: Path) -> str:
    # newline=None vereinheitlicht CRLF (Windows-Checkout) zu \n.
    with open(pfad, "r", encoding="utf-8", newline=None) as f:
        return f.read()


def _hinzugefuegt_um(repo: Path, relpfad: str) -> float:
    """Zeitpunkt, an dem das Fragment in die Historie kam (Merge-Reihenfolge).

    Noch nicht committete Fragmente gelten als neueste; ohne Git zaehlt nur
    der Dateiname."""
    rc, aus = _git(repo, "log", "--diff-filter=A", "--format=%ct", "-1", "--",
                   relpfad)
    if rc != 0:
        return 0.0
    aus = aus.strip()
    return float(aus) if aus else float("inf")


def fragmente(repo: Path = REPO) -> list[Path]:
    """Alle Fragmente, **neueste zuerst** (Datum im Namen, dann Merge-Zeitpunkt)."""
    ordner = repo / FRAGMENT_ORDNER
    if not ordner.is_dir():
        return []
    liste = [p for p in ordner.iterdir() if p.is_file() and ist_fragment_name(p.name)]

    def schluessel(p: Path):
        datum = FRAGMENT_NAME.match(p.name).group(1)
        return (datum, _hinzugefuegt_um(repo, f"{FRAGMENT_ORDNER}/{p.name}"), p.name)

    return sorted(liste, key=schluessel, reverse=True)


def fremde_dateien(repo: Path = REPO) -> list[str]:
    """Dateien in changelog.d/, die weder Fragment noch README sind — Tippfehler
    im Namen (``2026-1-01-X.md``) wuerden sonst still nie gesammelt."""
    ordner = repo / FRAGMENT_ORDNER
    if not ordner.is_dir():
        return []
    return sorted(p.name for p in ordner.iterdir()
                  if p.is_file() and p.name != "README.md"
                  and not ist_fragment_name(p.name))


def baue_changelog(changelog_text: str, fragment_texte: list[str]) -> str:
    """Setzt die Fragmente (schon sortiert) direkt unter ``## [Unreleased]``.

    Ein Abschnitt je Fragment, durch eine Leerzeile getrennt, vor dem bisher
    obersten Eintrag — dieselbe Stelle, an die bisher von Hand geschrieben
    wurde (AGENTS.md Regel 3)."""
    zeilen = changelog_text.split("\n")
    try:
        kopf = next(i for i, z in enumerate(zeilen) if z.strip() == UNRELEASED)
    except StopIteration:
        raise ValueError(f"'{UNRELEASED}' fehlt in {CHANGELOG}") from None
    einfuegen = kopf + 1
    while einfuegen < len(zeilen) and not zeilen[einfuegen].strip():
        einfuegen += 1
    block = []
    for text in fragment_texte:
        block.extend(text.strip("\n").split("\n"))
        block.append("")
    neu = zeilen[:kopf + 1] + [""] + block + zeilen[einfuegen:]
    return "\n".join(neu)


def sammeln(repo: Path = REPO, *, pruefen: bool = False,
            ausgabe=print) -> int:
    """Exit-Code: 0 ok/nichts zu tun, 1 Formfehler (dann wird NICHTS geschrieben)."""
    liste = fragmente(repo)
    fehler = [f"{FRAGMENT_ORDNER}/{n}: kein gueltiger Fragmentname "
              "(JJJJ-MM-TT-<ID>.md)" for n in fremde_dateien(repo)]
    texte = []
    for p in liste:
        t = _lies_text(p)
        fehler.extend(pruefe_fragment(p.name, t))
        texte.append(t)
    if fehler:
        for f in fehler:
            ausgabe(f"[changelog] FEHLER: {f}")
        return 1
    if not liste:
        ausgabe("[changelog] keine Fragmente — nichts zu sammeln.")
        return 0
    pfad = repo / CHANGELOG
    roh = pfad.read_bytes().decode("utf-8")
    crlf = "\r\n" in roh
    neu = baue_changelog(roh.replace("\r\n", "\n"), texte)
    ausgabe(f"[changelog] {len(liste)} Fragment(e), neueste zuerst:")
    for p in liste:
        ausgabe(f"  {FRAGMENT_ORDNER}/{p.name}")
    if pruefen:
        ausgabe("[changelog] --pruefen: nichts geschrieben, nichts geloescht.")
        return 0
    if crlf:
        neu = neu.replace("\n", "\r\n")
    pfad.write_bytes(neu.encode("utf-8"))
    for p in liste:
        p.unlink()
    ausgabe(f"[changelog] {CHANGELOG} geschrieben, Fragmente entfernt. "
            f"Commit z. B. mit Betreff '{MARKER} sammeln'.")
    return 0


# ---------------------------------------------------------------------- Waechter

def _diff_zeilen(diff: str) -> tuple[list[str], list[str]]:
    """Hinzugekommene/entfernte Zeilen eines ``git diff``.

    Uebersprungen werden nur die Datei-Koepfe (``--- a/…``, ``+++ b/…``,
    ``/dev/null``) — und zwar nur VOR dem ersten ``@@`` einer Datei. Ein
    pauschales ``startswith("---")`` haette eine entfernte Markdown-Trennlinie
    (``----`` im Diff) oder eine Inhaltszeile ``-- x`` verschluckt."""
    plus, minus = [], []
    im_hunk = False
    for z in diff.split("\n"):
        if z.startswith("diff --git "):
            im_hunk = False
            continue
        if z.startswith("@@"):
            im_hunk = True
            continue
        if not im_hunk:
            continue   # Kopf: index …, --- a/…, +++ b/…, /dev/null, Modi
        if z.startswith("+"):
            plus.append(z[1:].rstrip("\r"))
        elif z.startswith("-"):
            minus.append(z[1:].rstrip("\r"))
    return plus, minus


def direkte_aenderungen(repo: Path = REPO, basis: str = "origin/main") -> list[str]:
    """Befunde zu CHANGELOG.md-Aenderungen ausserhalb eines Sammel-Laufs.

    Leere Liste = in Ordnung ODER nicht pruefbar (siehe Modul-Doku: still
    bestanden ohne ``origin/main``/Merge-Basis — so laeuft die CI)."""
    rc, _ = _git(repo, "rev-parse", "--verify", "-q", f"{basis}^{{commit}}")
    if rc != 0:
        return []
    rc, mb = _git(repo, "merge-base", basis, "HEAD")
    mb = mb.strip()
    if rc != 0 or not mb:
        return []
    # Gegen den ARBEITSBAUM: auch eine noch nicht committete Hand-Aenderung
    # soll vor dem Commit auffallen, nicht erst im PR.
    rc, diff = _git(repo, "diff", "--no-color", "--no-ext-diff", "-U0", mb,
                    "--", CHANGELOG)
    if rc != 0 or not diff.strip():
        return []
    plus, minus = _diff_zeilen(diff)
    if not any(z.strip() for z in plus + minus):
        return []

    rc, betreffe = _git(repo, "log", "--format=%s", f"{mb}..HEAD", "--", CHANGELOG)
    if rc == 0 and any(b.strip().lower().startswith(MARKER)
                       for b in betreffe.splitlines()):
        return []

    # Fragmente, die es an der Abzweigung gab und die jetzt weg sind = gesammelt.
    erlaubt: set[str] = set()
    rc, namen = _git(repo, "ls-tree", "-r", "--name-only", mb, "--",
                     f"{FRAGMENT_ORDNER}/")
    if rc == 0:
        for rel in namen.splitlines():
            rel = rel.strip()
            if not rel or not ist_fragment_name(rel.rsplit("/", 1)[-1]):
                continue
            if (repo / rel).exists():
                continue
            rc2, inhalt = _git(repo, "show", f"{mb}:{rel}")
            if rc2 == 0:
                erlaubt.update(z.rstrip("\r").rstrip()
                               for z in inhalt.split("\n"))

    befunde = []
    weg = [z for z in minus if z.strip()]
    if weg:
        befunde.append(f"{len(weg)} bestehende Zeile(n) entfernt/geaendert, "
                       f"z. B.: {weg[0][:100]!r}")
    fremd = [z for z in plus if z.strip() and z.rstrip() not in erlaubt]
    if fremd:
        befunde.append(f"{len(fremd)} Zeile(n) direkt eingefuegt statt ueber "
                       f"ein Fragment, z. B.: {fremd[0][:100]!r}")
    return befunde


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pruefen", action="store_true",
                    help="Trockenlauf: nur anzeigen, nichts schreiben/loeschen")
    ap.add_argument("--waechter", action="store_true",
                    help="direkte CHANGELOG.md-Aenderungen seit origin/main melden")
    a = ap.parse_args(argv)
    if a.waechter:
        befunde = direkte_aenderungen(REPO)
        for b in befunde:
            print(f"[changelog] {b}")
        if befunde:
            print(f"[changelog] Bitte ein Fragment unter {FRAGMENT_ORDNER}/ "
                  "anlegen statt CHANGELOG.md direkt zu bearbeiten "
                  f"(bewusste Korrektur: Commit-Betreff mit '{MARKER}').")
            return 1
        print("[changelog] Waechter: keine direkten Aenderungen.")
        return 0
    return sammeln(REPO, pruefen=a.pruefen)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    os.chdir(REPO)
    sys.exit(main())
