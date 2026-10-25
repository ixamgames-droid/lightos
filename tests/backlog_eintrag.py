"""Einen Backlog-Eintrag lesen — egal, ob er noch als Fragment liegt oder schon
eingesammelt ist.

Warum es das gibt
-----------------
Ein Feature-PR legt seinen Backlog-Eintrag als Fragment ``backlog.d/<ID>.md``
ab (PROC-20). ``tools/backlog_sammeln.py`` schreibt die Fragmente spaeter in
``BACKLOG.md`` und LOESCHT sie. Ein Test, der ``backlog.d/<ID>.md`` direkt
oeffnet, wird nach jedem Sammel-Lauf rot — obwohl der Eintrag noch da ist,
nur an anderer Stelle. Genau das passierte am 20.10.2026 mit
``test_eng39_doku.py`` und ``test_imp2_mitschnitt_anleitung.py``.

Deshalb lesen Tests einen Eintrag nur ueber :func:`eintrag` bzw.
:func:`status`. Der Waechter ``tests/test_backlog_fragment_zugriff.py`` sorgt
dafuer, dass das so bleibt.

Reihenfolge der Suche
---------------------
1. Fragment ``backlog.d/<ID>.md`` (ganzer Text),
2. Tabellenzeile ``| <ID> | …`` in ``BACKLOG.md``,
3. Tabellenzeile ``| <ID> | …`` in ``BACKLOG_ARCHIVE.md``,
4. sonst ``AssertionError`` mit klarer Meldung.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["eintrag", "status", "fundort"]

_DATEIEN = ("BACKLOG.md", "BACKLOG_ARCHIVE.md")


def _zeile(text: str, item_id: str) -> str | None:
    muster = re.compile(r"^\|\s*" + re.escape(item_id) + r"\s*\|.*$", re.M)
    treffer = muster.search(text)
    return treffer.group(0) if treffer else None


def fundort(repo_root, item_id: str) -> tuple[str, str]:
    """``(quelle, text)`` — quelle ist ``backlog.d/<ID>.md``, ``BACKLOG.md``
    oder ``BACKLOG_ARCHIVE.md``; text der Fragment-Text bzw. die Zeile."""
    root = Path(repo_root)
    fragment = root / "backlog.d" / f"{item_id}.md"
    if fragment.is_file():
        return f"backlog.d/{item_id}.md", fragment.read_text(encoding="utf-8")
    for name in _DATEIEN:
        datei = root / name
        if not datei.is_file():
            continue
        zeile = _zeile(datei.read_text(encoding="utf-8"), item_id)
        if zeile is not None:
            return name, zeile
    raise AssertionError(
        f"Backlog-Eintrag {item_id} nicht gefunden: weder backlog.d/{item_id}.md "
        f"noch eine Zeile '| {item_id} |' in BACKLOG.md oder BACKLOG_ARCHIVE.md "
        f"(unter {root}).")


def eintrag(repo_root, item_id: str) -> str:
    """Fragment-Text, sonst die Tabellenzeile aus BACKLOG.md, sonst aus
    BACKLOG_ARCHIVE.md. Fehlt der Eintrag ganz: ``AssertionError``."""
    return fundort(repo_root, item_id)[1]


def status(repo_root, item_id: str) -> str:
    """Der Status des Eintrags: Kopfzeile ``Status:`` (samt ``Status-Notiz``
    nicht) im Fragment, sonst die dritte Spalte der Tabellenzeile."""
    quelle, text = fundort(repo_root, item_id)
    if quelle.startswith("backlog.d/"):
        treffer = re.search(r"^Status:\s*(.*?)\s*$", text, re.M)
        if not treffer:
            raise AssertionError(f"{quelle} hat keine Kopfzeile 'Status:'")
        return treffer.group(1)
    spalten = [s.strip() for s in text.strip().strip("|").split("|")]
    if len(spalten) < 3:
        raise AssertionError(f"Zeile fuer {item_id} in {quelle} hat keine Statusspalte")
    return spalten[2]
