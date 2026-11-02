"""CDX-63 (Codex zu #1186, VIZ-95) — grosse Lasermuster werden ausgeduennt.

Befund: ``_muster_geometrie`` liess jeden Linienzug weg, der das Segment-
Budget des Kegelmantels (``LASER_MUSTER_MAX_KONTUR`` = 192) ueberschritt.
Gueltige Profilangaben (``anzahl`` bis ``ANZAHL_MAX`` = 64) wie eine Spirale
mit 7 Windungen oder eine Welle mit 9 Perioden kamen dadurch LEER und
„unbekannt“ an — der Viewer zeigte einen geraden Strahl statt des Musters;
acht Kreise verloren zwei.

Jetzt werden die Linienzuege gleichmaessig auf das Budget ausgeduennt: jeder
Zug bleibt erhalten, Anfang und Ende bleiben, geschlossene bleiben zu.
"""
import pytest

from src.core.laser.musterformen import form_polylinien
from src.core.laser.profilangaben import ANZAHL_MAX, Muster
from src.ui.visualizer.visualizer_service import (
    LASER_MUSTER_MAX_KONTUR, _muster_geometrie,
)


def _m(form, anzahl):
    return Muster(von=0, bis=9, name=form, form=form, anzahl=anzahl)


def _segmente(kontur):
    return sum(len(z) // 2 - 1 for z in kontur)


@pytest.mark.parametrize("form,anzahl", [
    ("spirale", 7), ("welle", 9), ("mehrere_kreise", 8),
    ("mehrere_kreise", ANZAHL_MAX), ("spirale", ANZAHL_MAX),
    ("welle", ANZAHL_MAX), ("stern", ANZAHL_MAX)])
def test_jeder_linienzug_bleibt_im_budget(form, anzahl):
    m = _m(form, anzahl)
    linien = [l for l in form_polylinien(m) if l.art != "punkte"]
    g = _muster_geometrie(m)
    assert "unbekannt" not in g, f"{form} x{anzahl} kam leer an"
    assert len(g["kontur"]) == len(linien), (
        f"{form} x{anzahl}: {len(linien)} Zuege, {len(g['kontur'])} angekommen")
    assert 0 < _segmente(g["kontur"]) <= LASER_MUSTER_MAX_KONTUR
    for l, z in zip(linien, g["kontur"]):
        # Anfang bleibt; geschlossene enden mit ihrem ersten Punkt, offene
        # mit ihrem letzten.
        assert z[:2] == [round(c, 3) for c in l.punkte[0]]
        ende = l.punkte[0] if l.geschlossen else l.punkte[-1]
        assert z[-2:] == [round(c, 3) for c in ende]
        if l.geschlossen:
            assert len(z) // 2 - 1 >= 3, "geschlossener Zug zu Strich verkuemmert"


def test_kleine_muster_bleiben_unveraendert():
    m = _m("mehrere_kreise", 3)
    linien = form_polylinien(m)
    g = _muster_geometrie(m)
    assert [len(z) // 2 for z in g["kontur"]] == [len(l.punkte) + 1 for l in linien]


def test_kurze_zuege_behalten_ihre_ecken():
    """Review: in einer eigenen Form neben einem langen Zug darf ein Quadrat
    nicht anteilig zum Dreieck ausgeduennt werden — kurze Zuege behalten alle
    Punkte, gekuerzt wird nur, was ueber dem fairen Anteil liegt."""
    from src.core.laser.profilangaben import EIGENE_FORM
    quadrat = {"punkte": [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]],
               "geschlossen": True}
    lang = {"punkte": [[-1 + 2 * i / 249, 0.0] for i in range(250)]}
    m = Muster(von=0, bis=9, name="eigen", form=EIGENE_FORM,
               linien=(quadrat, lang))
    g = _muster_geometrie(m)
    assert len(g["kontur"]) == 2
    assert len(g["kontur"][0]) // 2 == 5, "Quadrat hat Ecken verloren"
    assert _segmente(g["kontur"]) <= LASER_MUSTER_MAX_KONTUR
    assert len(g["kontur"][1]) // 2 - 1 >= LASER_MUSTER_MAX_KONTUR - 4 - 1
