"""XPLAT-43: maschinenlesbare Bilanz eines Segment-Gate-Laufs (summary.json).

Wird von ``tools/verify_segmented.sh`` am Laufende aufgerufen und schreibt
``<Ausgabeverzeichnis>/summary.json``. Das Windows-Gate
(``tools/verify_segmented.ps1``) schreibt dieselbe Datei mit DENSELBEN Feldern
selbst — ohne Python-Aufruf, weil PowerShell 5.1 unter
``$ErrorActionPreference = "Stop"`` jede stderr-Zeile eines nativen Programms
zum Abbruch macht (XPLAT-27). ``tests/test_xplat43_gate_summary.py`` haelt die
Feldnamen beider Seiten deckungsgleich.

WOZU: bisher stand die Bilanz nur als Text im Terminal. Um ueber Wochen zu
sehen, welche Dateien auf welcher Plattform wie oft abstuerzen oder ins
Zeitlimit laufen (Grundlage einer spaeteren Toleranzliste mit Ablaufdaten),
braucht es je Lauf einen Datensatz mit Commit, Plattform und Zaehlung.

★ Der Exit-Code des Runners haengt NICHT an dieser Datei. Scheitert das
Schreiben, meldet der Runner das und endet mit demselben Code wie ohne sie.

Felder: commit, plattform, python, arch, gruen, rot, crash, timeout,
toleriert[], gesamt, dauer_s, zeitstempel (UTC, ISO 8601).

Aufruf (nur durch den Runner)::

    python tools/_gate_summary.py --out DIR --gesamt N --start EPOCH
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

#: Reihenfolge = Reihenfolge in der Datei. Muss mit dem ``[ordered]@{...}`` in
#: ``tools/verify_segmented.ps1`` uebereinstimmen (Paritaetstest).
FELDER = ("commit", "plattform", "python", "arch", "gruen", "rot", "crash",
          "timeout", "toleriert", "gesamt", "dauer_s", "zeitstempel")


def einstufen(rc: int) -> str:
    """Art eines Segments nach seinem Exit-Code — wie die .sh-Ausgabe zeigt.

    ``124`` ist das Zeitlimit von ``timeout``, ``129..192`` ein Signal
    (128+n, z. B. 139 = SIGSEGV) — dieselbe Crash-Familie wie in der .ps1.
    Auf Linux ist jede dieser Arten ROT (verify_segmented.sh zaehlt jeden
    rc != 0); die Einstufung dient nur der Statistik.
    """
    if rc == 0:
        return "gruen"
    if rc == 124:
        return "timeout"
    if 129 <= rc <= 192:
        return "crash"
    return "rot"


def zaehle(results_tsv: str) -> dict[str, int]:
    zahl = {"gruen": 0, "rot": 0, "crash": 0, "timeout": 0}
    try:
        with open(results_tsv, encoding="utf-8", errors="replace") as f:
            for zeile in f:
                rc_text = zeile.split("\t", 1)[0].strip()
                if not rc_text:
                    continue
                try:
                    rc = int(rc_text)
                except ValueError:
                    rc = 1
                zahl[einstufen(rc)] += 1
    except OSError:
        pass
    return zahl


def commit(repo: str) -> str | None:
    try:
        erg = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if erg.returncode != 0:
        return None
    return erg.stdout.strip() or None


def plattform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def zeitstempel() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bilanz(out: str, gesamt: int, start: float | None,
           repo: str) -> dict:
    zahl = zaehle(os.path.join(out, "results.tsv"))
    dauer = round(time.time() - start, 1) if start else None
    daten = {
        "commit": commit(repo),
        "plattform": plattform(),
        "python": platform.python_version(),
        "arch": platform.machine(),
        "gruen": zahl["gruen"],
        "rot": zahl["rot"],
        "crash": zahl["crash"],
        "timeout": zahl["timeout"],
        # verify_segmented.sh toleriert nichts: jeder rc != 0 ist rot. Das ist
        # die bewusste Entscheidung aus XPLAT-27/29 — die Liste bleibt leer.
        "toleriert": [],
        "gesamt": gesamt,
        "dauer_s": dauer,
        "zeitstempel": zeitstempel(),
    }
    assert tuple(daten) == FELDER
    return daten


def _start(text: str) -> float | None:
    # bash 5.0 gibt $EPOCHREALTIME je nach Locale mit Komma aus.
    try:
        return float(text.replace(",", "."))
    except (AttributeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--gesamt", type=int, required=True)
    ap.add_argument("--start", default="")
    ap.add_argument("--repo", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    a = ap.parse_args(argv)
    daten = bilanz(a.out, a.gesamt, _start(a.start), a.repo)
    ziel = os.path.join(a.out, "summary.json")
    with open(ziel, "w", encoding="utf-8", newline="\n") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
