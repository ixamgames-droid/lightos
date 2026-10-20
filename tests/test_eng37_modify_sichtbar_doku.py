"""ENG-37 „Modify sichtbar machen" — Doku-Waechter: die Anleitungen nennen das
Zeichen auf der Taste, den Hinweis im Chaser-Editor (Wortlaut wie im Code) und
den geplanten echten Laeufer ENG-42; die neuen Backlog-Items ENG-42/43 stehen."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_anleitungen_nennen_zeichen_hinweis_und_eng42():
    from pathlib import Path
    from src.ui.views.chaser_editor import MODIFY_SCHRITT_HINWEIS
    repo = Path(__file__).resolve().parents[1]
    dm = (repo / "docs/anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md").read_text(encoding="utf-8")
    abschnitt = dm.split("## 5. Modify-Effekt", 1)[1]
    for wort in ("unten links das Zeichen der Betriebsart", "**◐**", "**Chaser-Editor**",
                 " ".join(MODIFY_SCHRITT_HINWEIS.split())):
        assert wort in " ".join(abschnitt.split()), wort
    pr = (repo / "docs/anleitung_prioritaeten/ANLEITUNG.md").read_text(encoding="utf-8")
    kein = pr.split("**Kein „Untergrund“:**", 1)[1].split("\n- ", 1)[0]
    assert "Modify-Effekt" in kein and "ENG-42" in kein
    assert "anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md" in kein
    for fid in ("ENG-42", "ENG-43"):
        text = (repo / "backlog.d" / f"{fid}.md").read_text(encoding="utf-8")
        assert text.startswith(f"ID: {fid}\n") and "Fertig, wenn:" in text
