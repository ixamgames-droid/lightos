"""Show-Datei-Aufloesung fuer tools/-Skripte: shows/ mit Fallback shows/_archiv/.

Hintergrund: Am 2026-07-19 wurden viele historische Demo-/Testshows aus
``shows/`` in Davids lokales Archiv ``shows/_archiv/`` verschoben (gitignored,
siehe .gitignore ``shows/_archiv/``). Aeltere Capture-/Render-/Diagnose-Skripte
zeigten hart auf ``shows/<Name>.lshow`` und liefen dadurch ins Leere.

``find_show("hochzeit.lshow")`` liefert den ersten existierenden Kandidaten:

  1. ``<repo>/shows/<name>``           (aktive Show — gewinnt immer)
  2. ``<repo>/shows/_archiv/<name>``   (archivierte Show — Lesen ist gefahrlos)

Existiert keiner, bricht das Skript mit einer klaren Meldung ab (SystemExit)
statt spaeter mit FileNotFoundError/leerer Show stumm falsche Ergebnisse zu
produzieren. Reine Lese-Helfer — verschiebt/schreibt nichts.
"""
from __future__ import annotations

import os
from pathlib import Path

# tools/ -> Repo-Root (das innere lightos-main mit shows/ + src/)
_ROOT = Path(__file__).resolve().parents[1]


def find_show(name: str, *, hint: str = "") -> Path:
    """Ersten existierenden Pfad fuer ``name`` liefern (shows/, dann shows/_archiv/).

    ``hint`` wird bei Nichtfund an die Fehlermeldung angehaengt (z. B. "erst
    tools/build_neue_demo_show.py laufen lassen").
    """
    candidates = [
        _ROOT / "shows" / name,
        _ROOT / "shows" / "_archiv" / name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    msg = (
        f"Show '{name}' weder in shows/ noch in shows/_archiv/ gefunden.\n"
        f"  gesucht: " + " | ".join(str(p) for p in candidates)
    )
    if hint:
        msg += f"\n  Hinweis: {hint}"
    raise SystemExit(msg)


def show_db_isolated() -> bool:
    """True, wenn der Prozess NICHT auf der geteilten data/current_show.db arbeitet."""
    return bool(os.environ.get("LIGHTOS_SHOW_DB"))
