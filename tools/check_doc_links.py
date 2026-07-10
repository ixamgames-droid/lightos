"""Prüft relative Markdown-Links in den Projektdokumenten."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LINK = re.compile(r"\]\(([^)]+)\)")


def markdown_files(root: Path = ROOT) -> list[Path]:
    # Historische Notizen referenzieren bewusst entfernte Planstände; sie sind
    # kein aktiver Dokumentationsvertrag und werden deshalb explizit ausgenommen.
    files = [path for path in (root / "docs").rglob("*.md")
             if "_archiv" not in path.relative_to(root).parts]
    files.extend(root / name for name in ("BACKLOG.md", "ROADMAP.md", "CHANGELOG.md"))
    return [path for path in files if path.exists()]


def broken_links(root: Path = ROOT) -> list[str]:
    broken: list[str] = []
    for source in markdown_files(root):
        for target in _LINK.findall(source.read_text(encoding="utf-8")):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "/")):
                continue
            if not target.lower().endswith(".md"):
                continue
            if not (source.parent / target).resolve().is_file():
                broken.append(f"{source.relative_to(root).as_posix()} -> {target}")
    return broken


def main() -> int:
    broken = broken_links()
    if broken:
        print("Tote Markdown-Links:", *broken, sep="\n")
        return 1
    print(f"OK: {len(markdown_files())} Markdown-Dateien geprüft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
