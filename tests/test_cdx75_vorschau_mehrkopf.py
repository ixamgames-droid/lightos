"""CDX-75 (1): 3D-Vorschau im Fixture-Editor — Mehrkopf-Geraete leuchten mit
allen Koepfen.

Der Renderer (``updateParBarDmx``/``updateMoverBarDmx``/``updateMatrixPanelDmx``
in ``builders.js``) faerbt Kopf i aus ``heads[i]``; ohne Kopf-Daten leuchtet
nur Kopf 0. Die Vorschau schickte nie ein ``heads``-Array — eine 4er-PAR-Bar
zeigte deshalb nur den ersten PAR.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from _qt_lifecycle import destroy_all_top_level_widgets, destroy_widget

_app = QApplication.instance() or QApplication([])

from src.ui.widgets import fixture_vorschau_3d as V   # noqa: E402


@pytest.fixture(autouse=True)
def _keine_uebrigen_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


_PARBAR = ["dimmer"] + ["color_r", "color_g", "color_b"] * 4


def test_licht_payload_mit_vier_koepfen_traegt_vier_gleiche_koepfe():
    p = V.licht_payload((255, 0, 128), n_heads=4)
    assert len(p["heads"]) == 4
    for h in p["heads"]:
        assert (h["r"], h["g"], h["b"]) == (255, 0, 128)
        # Spider liest die Rohkanaele cr/cg/cb
        assert (h["cr"], h["cg"], h["cb"]) == (255, 0, 128)


def test_einzelkopf_ohne_heads():
    assert "heads" not in V.licht_payload((255, 255, 255))
    assert "heads" not in V.licht_payload((255, 255, 255), n_heads=1)


def test_weissband_nur_bei_weiss_kanal():
    ohne = V.licht_payload((255, 255, 255), n_heads=2)
    assert all(h["cw"] == 0 for h in ohne["heads"])
    mit = V.licht_payload((255, 255, 255), n_heads=2, mit_weiss=True)
    assert all(h["cw"] == 255 for h in mit["heads"])
    rot = V.licht_payload((255, 0, 0), n_heads=2, mit_weiss=True)
    assert all(h["cw"] == 0 for h in rot["heads"])


def test_vorschau_schickt_heads_fuer_eine_par_bar():
    d = V.VorschauDaten(typ="led_bar", viz_model="par_bar", attribute=_PARBAR)
    vs = V.FixtureVorschau3D(lambda: d)
    try:
        vs._licht_senden()
        p = vs.letzter_licht_payload
        assert len(p.get("heads", [])) == 4
        farbe = (p["r"], p["g"], p["b"])
        assert all((h["r"], h["g"], h["b"]) == farbe for h in p["heads"])
    finally:
        destroy_widget(vs, _app)


def test_vorschau_einzelkopf_bleibt_ohne_heads():
    d = V.VorschauDaten(typ="par", attribute=["dimmer", "color_r", "color_g",
                                              "color_b"])
    vs = V.FixtureVorschau3D(lambda: d)
    try:
        vs._licht_senden()
        assert "heads" not in vs.letzter_licht_payload
    finally:
        destroy_widget(vs, _app)
