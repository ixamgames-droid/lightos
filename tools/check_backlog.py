"""Kleiner Linter für die kanonische Arbeitswarteschlange in BACKLOG.md."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"todo", "decision", "blocked", "wip", "review", "done", "teils"}


def canonical_items(text: str) -> list[str]:
    start = text.index("### Jetzt ausführbar")
    end = text.index("### Wartet auf Produktentscheidung", start)
    return re.findall(r"^\d+\. \*\*([A-Z]+-?\d*|QA-LIVE)\*\*", text[start:end], re.M)


def lint(path: Path = ROOT / "BACKLOG.md") -> list[str]:
    text = path.read_text(encoding="utf-8")
    items = canonical_items(text)
    errors = []
    if len(items) != len(set(items)):
        errors.append("doppelte ID in der kanonischen Arbeitswarteschlange")
    if not items:
        errors.append("kanonische Arbeitswarteschlange ist leer")
    # Der Statuswortschatz wird bewusst nur für neue, kanonische Tabellenzeilen
    # geprüft; Detailregister enthalten historische, erklärende Statusformen.
    for line in text.splitlines():
        if line.startswith("| QA-") and "|" in line:
            status = line.split("|")[3].strip().split()[0]
            if status not in ALLOWED and not status.startswith(("✅", "⏸")):
                errors.append(f"unbekannter QA-Status: {status}")
    return errors


if __name__ == "__main__":
    raise SystemExit(0 if not lint() else 1)
