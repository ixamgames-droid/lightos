#!/usr/bin/env python3
"""pseudonymisieren.py — Klarnamen im OEFFENTLICHEN Repo durch ein Pseudonym ersetzen.

Das Repo ist oeffentlich und zugleich das gemeinsame Gedaechtnis mehrerer
Sitzungen. Befunde zurueckzuhalten waere kein Datenschutz, sondern
Arbeitsverweigerung — deshalb gilt: **Inhalt vollstaendig, Person pseudonym**
(s. ``COORDINATION.md``).

Der Name des Rig-Betreibers steht heute an ueber 300 Stellen in rund 180
Dateien: Kommentare, Docstrings, Testnamen, Anleitungen, Backlog. Deshalb ein
Werkzeug statt Handarbeit — und deshalb **zwei getrennte Schritte**:

    python tools/pseudonymisieren.py --pruefen      # nur zaehlen, nichts aendern
    python tools/pseudonymisieren.py --anwenden     # ersetzen
    python tools/pseudonymisieren.py --anwenden --nur BACKLOG.md backlog.d
                                                    # nur diese Pfade (PRIV-06)

★ **Der richtige Zeitpunkt ist wichtiger als das Werkzeug.** Die Ersetzung
beruehrt fast jede Datei des Repos. Laeuft dabei eine zweite Sitzung mit
offenen Branches, konfliktet praktisch jeder davon. Also: erst ``list`` in
``session_claim.py`` pruefen, dann ansagen, dann anwenden — am besten, wenn
keine offenen PRs stehen.

**Was das Werkzeug NICHT kann und auch nicht vorgibt zu koennen:**

* Die **Git-Historie** bleibt unveraendert. Alte Commits tragen den Namen
  weiter. Ihn dort zu entfernen hiesse die Historie umzuschreiben — ein
  Eingriff, den nur ein Mensch entscheidet, nicht eine Sitzung.
* **Bezeichner** (Variablen, Funktionen, Dateinamen) werden bewusst nicht
  angefasst: dort waere eine Textersetzung keine Umbenennung, sondern ein
  stiller Bruch. Sie werden gemeldet, nicht geaendert.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Der Klarname steht bewusst NICHT als Vorgabe im Quelltext — sonst waere er
# genau hier wieder eingecheckt. Er wird uebergeben oder aus der Umgebung
# gelesen (lokal, nie im Repo).
UMGEBUNG = "LIGHTOS_KLARNAME"

# Nur Text-Formate, in denen ein Name Prosa ist. Binaerdateien und Shows sind
# ausgeschlossen; `.json` ebenso — dort waere ein Name ein Datenwert.
ENDUNGEN = (".md", ".py", ".js", ".sh", ".ps1", ".txt", ".html", ".css")

# Diese Dateien sind Protokolle: sie beschreiben, was WANN geschah. Sie
# nachtraeglich umzuschreiben ist so oder so eine Entscheidung fuer sich.
PROTOKOLLE = ("CHANGELOG.md", "BACKLOG_ARCHIVE.md")


def _repo() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dateien(repo: str) -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=repo,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return []
    return [p for p in r.stdout.split("\0")
            if p and p.endswith(ENDUNGEN)]


def _norm(pfad: str) -> str:
    return pfad.replace("\\", "/").strip("/")


def _im_bereich(rel: str, nur: list[str] | None) -> bool:
    """PRIV-06: ``--nur`` schraenkt auf Dateien bzw. Ordner ein (Praefix je
    Pfadsegment — ``backlog.d`` trifft ``backlog.d/X.md``, nicht
    ``backlog.dx/``)."""
    if not nur:
        return True
    return any(rel == n or rel.startswith(n + "/") for n in map(_norm, nur))


def _ist_protokoll_ausgenommen(rel: str, protokolle: bool,
                               nur: list[str] | None) -> bool:
    """Protokolle bleiben draussen — es sei denn ``--protokolle``, oder die
    Datei ist in ``--nur`` AUSDRUECKLICH genannt (ein Ordner reicht dafuer
    nicht: wer eine Protokolldatei umschreibt, soll sie beim Namen nennen)."""
    if protokolle or os.path.basename(rel) not in PROTOKOLLE:
        return False
    return not (nur and rel in map(_norm, nur))


# PRIV-06: Wortgrenze OHNE den Unterstrich. ``\\b`` sieht ``_`` als
# Wortzeichen — damit rutschte Markdown-Kursiv (``_Name-Auftrag …_``) durch.
_VOR = r"(?<![^\W_])"
_NACH = r"(?![^\W_])"


def _muster(name: str) -> re.Pattern:
    """Wortgenau, mit deutschem Genitiv-s, ohne Ruecksicht auf Gross/klein.

    ``\\b`` allein reicht nicht: „Davids" soll mitgehen, „Davidson" nicht.
    """
    return re.compile(rf"{_VOR}({re.escape(name)})(s)?{_NACH}", re.IGNORECASE)


def _ersatz(gefunden: str, pseudo: str) -> str:
    """Schreibweise mitnehmen: GROSS bleibt GROSS, klein bleibt klein."""
    if gefunden.isupper() and len(gefunden) > 1:
        return pseudo.upper()
    if gefunden.islower():
        return pseudo.lower()
    return pseudo


def _ist_bezeichner(zeile: str, name: str) -> bool:
    """Steht der Name in etwas, das Code ANSPRICHT statt beschreibt?"""
    return bool(re.search(
        rf"(def |class |import |from )\w*{re.escape(name)}\w*|"
        rf"\w*{re.escape(name.lower())}\w*\s*=|"
        rf"[\"'][^\"']*{re.escape(name)}[^\"']*[\"']\s*[:=]",
        zeile))


def lauf(repo: str, klar: str, pseudo: str, anwenden: bool,
         protokolle: bool, nur: list[str] | None = None) -> int:
    muster = _muster(klar)
    gesamt = 0
    betroffen = 0
    bezeichner: list[str] = []
    uebersprungen: list[str] = []

    for rel in _dateien(repo):
        if not _im_bereich(rel, nur):
            continue
        if _ist_protokoll_ausgenommen(rel, protokolle, nur):
            uebersprungen.append(rel)
            continue
        pfad = os.path.join(repo, rel)
        try:
            with open(pfad, encoding="utf-8") as f:
                zeilen = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue

        treffer = 0
        neu = []
        for nr, zeile in enumerate(zeilen, 1):
            if muster.search(zeile):
                if _ist_bezeichner(zeile, klar):
                    bezeichner.append(f"{rel}:{nr}")
                    neu.append(zeile)
                    continue
                treffer += len(muster.findall(zeile))
                neu.append(muster.sub(
                    lambda m: _ersatz(m.group(1), pseudo) + (m.group(2) or ""),
                    zeile))
            else:
                neu.append(zeile)

        if treffer:
            gesamt += treffer
            betroffen += 1
            if anwenden:
                with open(pfad, "w", encoding="utf-8") as f:
                    f.writelines(neu)
            else:
                print(f"  {rel}: {treffer}")

    kopf = "ERSETZT" if anwenden else "GEFUNDEN (nichts geaendert)"
    print(f"\n{kopf}: {gesamt} Stellen in {betroffen} Dateien "
          f"({klar!r} -> {pseudo!r})")
    if uebersprungen:
        print(f"  Protokolle uebersprungen: {', '.join(uebersprungen)} "
              f"(--protokolle oder --nur <datei> nimmt sie mit)")
    if bezeichner:
        print(f"\n⚠️  {len(bezeichner)} Stellen sehen nach Bezeichnern/Datenwerten "
              f"aus und wurden NICHT angefasst — bitte einzeln ansehen:")
        for b in bezeichner[:20]:
            print(f"     {b}")
        if len(bezeichner) > 20:
            print(f"     … und {len(bezeichner) - 20} weitere")
    if anwenden:
        print("\nNaechster Schritt: Gate fahren (./tools/verify_loop.sh), dann "
              "EIN Commit — ein so breiter Diff will nicht mit anderer Arbeit "
              "vermischt werden.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--klarname", default=os.environ.get(UMGEBUNG),
                   help=f"zu ersetzender Name (sonst ${UMGEBUNG})")
    p.add_argument("--pseudonym", default="Robin")
    p.add_argument("--anwenden", action="store_true",
                   help="wirklich schreiben (ohne: nur zaehlen)")
    p.add_argument("--pruefen", action="store_true", help="nur zaehlen (Default)")
    p.add_argument("--protokolle", action="store_true",
                   help="CHANGELOG/BACKLOG_ARCHIVE mitnehmen")
    p.add_argument("--nur", nargs="+", metavar="PFAD",
                   help="nur diese Dateien/Ordner (relativ zum Repo); eine "
                        "Protokolldatei zaehlt nur, wenn sie hier beim Namen steht")
    args = p.parse_args(argv)

    if not args.klarname:
        print(f"Kein Klarname angegeben. --klarname <name> oder ${UMGEBUNG} "
              f"setzen.\nEr steht bewusst nicht im Quelltext — sonst waere er "
              f"genau hier wieder eingecheckt.", file=sys.stderr)
        return 2
    if args.klarname == args.pseudonym:
        print("Klarname und Pseudonym sind gleich.", file=sys.stderr)
        return 2
    return lauf(_repo(), args.klarname, args.pseudonym,
                args.anwenden and not args.pruefen, args.protokolle, args.nur)


if __name__ == "__main__":
    # XPLAT-20: Windows-Konsolen und -Pipes laufen ohne PYTHONUTF8 auf cp1252.
    # Die Statuszeichen dieses Werkzeugs (✓ ⚠ ★ ⏳) haben dort keine Abbildung,
    # der Bericht stirbt also mitten in der Ausgabe an einem UnicodeEncodeError.
    # Bewusst HIER und nicht auf Modulebene: beim Import (Tests laden die
    # Werkzeuge per exec_module) bleibt der Datenstrom des Aufrufers unberuehrt.
    for _strom in (sys.stdout, sys.stderr):
        if hasattr(_strom, "reconfigure"):
            _strom.reconfigure(encoding="utf-8")
    raise SystemExit(main())
