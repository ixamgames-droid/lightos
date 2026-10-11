"""Generiert tools/README.md — Index aller Werkzeuge mit Zweck-Zeile.

Zieht je Skript die erste Docstring-Zeile (.py via ast) bzw. die Synopsis-/
Kommentar-Kopfzeile (.ps1) und schreibt eine Tabelle fuer tools/ plus eine
Kurzliste fuer tools/_archiv/. tests/test_tools_index.py prueft, dass der Index
vollstaendig ist — nach dem Anlegen/Umbenennen eines Tools also einmal laufen
lassen:

    venv/Scripts/python.exe tools/gen_tools_index.py
    (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)

Nur nachsehen, ob der Index noch stimmt (schreibt nichts, Exit 1 = veraltet):

    venv/Scripts/python.exe tools/gen_tools_index.py --pruefen

Reines Stdlib-Werkzeug, keine src-Imports.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ARCHIV = os.path.join(TOOLS, "_archiv")
README = os.path.join(TOOLS, "README.md")
SKIP = {"__init__.py"}


def py_purpose(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            doc = ast.get_docstring(ast.parse(f.read()))
    except SyntaxError:
        return "(Docstring nicht lesbar)"
    if not doc:
        return "(kein Docstring)"
    return doc.strip().splitlines()[0].strip()


def ps1_purpose(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.strip().upper() == ".SYNOPSIS" and i + 1 < len(lines):
            return lines[i + 1].strip()
        if line.startswith("#"):
            return line.lstrip("# ").strip()
    return "(kein Kommentar-Kopf)"


def sh_purpose(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                return s.lstrip("# ").strip()
    return "(kein Kommentar-Kopf)"


def _entries(folder: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in sorted(os.listdir(folder), key=str.lower):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or name in SKIP:
            continue
        if name.endswith(".py"):
            out.append((name, py_purpose(path)))
        elif name.endswith(".ps1"):
            out.append((name, ps1_purpose(path)))
        elif name.endswith(".sh"):
            out.append((name, sh_purpose(path)))
    return out


def _md_escape(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|")


def build_readme() -> str:
    lines = [
        "# tools/ — Werkzeug-Index",
        "",
        "> **Generiert** von `tools/gen_tools_index.py` — nicht von Hand pflegen;",
        "> nach neuem/umbenanntem Tool den Generator laufen lassen",
        "> (`tests/test_tools_index.py` erinnert daran). Zweck-Zeile = erste",
        "> Docstring-/Synopsis-Zeile des Skripts.",
        "",
        "| Werkzeug | Zweck |",
        "|---|---|",
    ]
    for name, purpose in _entries(TOOLS):
        lines.append(f"| `{name}` | {_md_escape(purpose)} |")
    lines += [
        "",
        "## _archiv/ — ausgemustert",
        "",
        "Begruendungen: [tools/_archiv/README.md](_archiv/README.md).",
        "",
    ]
    if os.path.isdir(ARCHIV):
        for name, _purpose in _entries(ARCHIV):
            lines.append(f"- `_archiv/{name}`")
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="gen_tools_index.py",
        description="Schreibt tools/README.md neu: Index aller Werkzeuge in "
                    "tools/ mit Zweck-Zeile, dazu die Kurzliste fuer "
                    "tools/_archiv/.")
    ap.add_argument(
        "--pruefen", action="store_true",
        help="nichts schreiben; Exit 1, wenn tools/README.md fehlt oder nicht "
             "dem entspricht, was der Generator jetzt schreiben wuerde")
    return ap


def _vorhandene_readme() -> str | None:
    """Inhalt der README, ``None`` wenn sie fehlt.

    Gelesen wird mit vereinheitlichten Zeilenenden: Git checkt die Datei unter
    Windows je nach ``core.autocrlf`` mit CRLF aus — das ist keine Abweichung.
    """
    try:
        with open(README, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def main(argv: list[str] | None = None) -> int:
    # TOOL-14: bis hierhin las main() die Kommandozeile gar nicht — JEDER
    # Aufruf schrieb die README neu, auch ``--help`` und ein Tippfehler in
    # einer Option. argparse beendet beides, bevor etwas geschrieben ist.
    args = _parser().parse_args(argv)
    content = build_readme()
    if args.pruefen:
        vorhanden = _vorhandene_readme()
        if vorhanden == content:
            print(f"aktuell: {README}")
            return 0
        grund = "fehlt" if vorhanden is None else "ist veraltet"
        print(f"{README} {grund} -> tools/gen_tools_index.py ohne --pruefen "
              f"laufen lassen", file=sys.stderr)
        return 1
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"geschrieben: {README} ({content.count(chr(10))} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
