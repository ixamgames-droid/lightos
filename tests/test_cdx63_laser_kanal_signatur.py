"""CDX-63 (Codex zu #1205, LAS-43) — „Einzelne Kanäle“ beim Laserwechsel.

Befund: Die Rebuild-Signatur des Laser-Reiters kannte je doppeltem Attribut
nur den ERSTEN Kanal (``_template_channels``) und den Attributnamen
(``_getrennt``). Wechselte die Auswahl auf einen Laser mit gleichem ersten
Kanal, aber einem weiteren Vorkommen (oder anders benanntem zweiten Kanal),
blieb die alte Reglerliste stehen — der neue Kanal bekam keinen Regler.

Jetzt traegt die Signatur Nummer, Name und Bereiche jedes Vorkommens.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_las43_laser_kanaele_getrennt as T43  # noqa: E402
import test_laser_view as LV  # noqa: E402


def _zeilen(view):
    return {k: r for k, r in view._rows.items()
            if k.split("#", 1)[0] == "macro"}


def _titel(row) -> str:
    from PySide6.QtWidgets import QLabel
    return " ".join(lb.text() for lb in row.findChildren(QLabel))


def test_drittes_vorkommen_bekommt_nach_wechsel_einen_regler(monkeypatch):
    LV._app()
    zwei = LV._FX(1, T43._el230ish())
    drei_ch = T43._el230ish()
    drei_ch.append(T43._Ch("macro", 6, [], "Effekt"))
    drei = LV._FX(2, drei_ch)

    view, state = LV._make_view(monkeypatch, [zwei])
    view.refresh_from_selection()
    assert set(_zeilen(view)) == {"macro", "macro#1"}

    state._fixtures = [drei]                     # Auswahl wechselt
    view.refresh_from_selection()
    zeilen = _zeilen(view)
    assert set(zeilen) == {"macro", "macro#1", "macro#2"}, list(zeilen)
    assert "Kanal 6" in _titel(zeilen["macro#2"])

    state._fixtures = [zwei]                     # und zurueck
    view.refresh_from_selection()
    assert set(_zeilen(view)) == {"macro", "macro#1"}


def test_anderer_zweiter_kanal_wird_neu_beschriftet(monkeypatch):
    LV._app()
    a = LV._FX(1, T43._el230ish())
    b_ch = T43._el230ish()
    b_ch[1].name = "Effekt"
    b_ch[1].ranges = []
    b = LV._FX(2, b_ch)

    view, state = LV._make_view(monkeypatch, [a])
    view.refresh_from_selection()
    assert "Pattern" in _titel(_zeilen(view)["macro#1"])

    state._fixtures = [b]
    view.refresh_from_selection()
    titel = _titel(_zeilen(view)["macro#1"])
    assert "Effekt" in titel and "Pattern" not in titel, titel
