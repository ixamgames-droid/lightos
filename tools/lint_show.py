"""CLI: prüft eine oder mehrere .lshow (oder show.json) gegen die echten
Bauteil-Sätze von LightOS — macht halluzinierte Widgets/Algos/Params/Styles laut.

    venv/Scripts/python.exe tools/lint_show.py shows/Demo_Show_Full.lshow
    venv/Scripts/python.exe tools/lint_show.py shows/*.lshow
    venv/Scripts/python.exe tools/lint_show.py --strict shows/*.lshow   # Warnungen = Fehler

Exit-Code 1, sobald ein ERROR-Finding existiert (mit --strict auch bei Warnungen).
"""
from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Die VC-Widget-Module sind QWidgets — eine QApplication schadet headless nicht
# und vermeidet jede Überraschung beim Import.
try:
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
except Exception:
    _app = None

from src.core.capability.validate import (  # noqa: E402
    ERROR, WARNING, validate_lshow, format_findings)


def _expand(args: list[str]) -> list[str]:
    out: list[str] = []
    for a in args:
        hits = glob.glob(a)
        out.extend(hits if hits else [a])
    return out


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    paths = _expand([a for a in argv if not a.startswith("-")])
    if not paths:
        print("Verwendung: lint_show.py [--strict] <show.lshow> [...]")
        return 2

    total_err = total_warn = 0
    for path in paths:
        if not os.path.exists(path):
            print(f"\n[FAIL] {path}: Datei nicht gefunden")
            total_err += 1
            continue
        try:
            findings = validate_lshow(path)
        except Exception as exc:  # defekte ZIP / kein show.json
            print(f"\n[FAIL] {path}: konnte nicht gelesen werden: {exc}")
            total_err += 1
            continue
        errs = [f for f in findings if f.severity == ERROR]
        warns = [f for f in findings if f.severity == WARNING]
        total_err += len(errs)
        total_warn += len(warns)
        mark = "[FAIL]" if errs else ("[warn]" if warns else "[ ok ]")
        print(f"\n{mark} {os.path.basename(path)} -- "
              f"{len(errs)} Fehler, {len(warns)} Warnungen")
        if findings:
            print(format_findings(findings))

    print(f"\n== Gesamt: {total_err} Fehler, {total_warn} Warnungen "
          f"ueber {len(paths)} Show(s) ==")
    if total_err or (strict and total_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
