"""Generiert tools/README.md — Index aller Werkzeuge mit Zweck-Zeile.

Zieht je Skript die erste Docstring-Zeile (.py via ast) bzw. die Synopsis-/
Kommentar-Kopfzeile (.ps1) und schreibt eine Tabelle fuer tools/ plus eine
Kurzliste fuer tools/_archiv/. tests/test_tools_index.py prueft, dass der Index
vollstaendig ist — nach dem Anlegen/Umbenennen eines Tools also einmal laufen
lassen:

    venv/Scripts/python.exe tools/gen_tools_index.py

Reines Stdlib-Werkzeug, keine src-Imports.
"""
from __future__ import annotations

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


def main() -> int:
    content = build_readme()
    with open(README, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"geschrieben: {README} ({content.count(chr(10))} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
