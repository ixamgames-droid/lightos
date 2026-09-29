"""VIZ-63: die Koepfe einer Mover-Bar stehen im 3D wie am echten Geraet.

Bis 2026-09-29 nahm ``_build_fixture_payload`` invert/swap nur fuer das
Gesamtgeraet zurueck; das Kopf-Array ``heads`` kam aus den DRAHT-Werten.
Gemessen: Bar mit 2 Koepfen, Programmer pan=100, ``invert_pan`` -> Payload
pan=100 (richtig), heads [155, 155] (Drahtwert, gespiegelt). Das JS nimmt fuer
Bars den Pro-Kopf-Pan.
"""
from types import SimpleNamespace

from src.core.app_state import apply_pan_tilt_orientation
from src.ui.visualizer.visualizer_service import _build_fixture_payload

MODELL = {"intensity": 255, "color_r": 255, "color_r#1": 255,
          "pan": 100, "tilt": 40, "pan#1": 180, "tilt#1": 210}


def _fx(**flags):
    return SimpleNamespace(fid=3, invert_pan=flags.get("ip", False),
                           invert_tilt=flags.get("it", False),
                           swap_pan_tilt=flags.get("sw", False))


def _koepfe(fx, modell):
    """Wie im Betrieb: Modellwerte -> Ausgabestufe (Draht) -> Payload."""
    draht = apply_pan_tilt_orientation(fx, dict(modell))
    return [(h["pan"], h["tilt"]) for h in _build_fixture_payload(fx, draht)["heads"]]


def test_ohne_flag_unveraendert():
    assert _koepfe(_fx(), MODELL) == [(100, 40), (180, 210)]


def test_invert_pan_zeigt_den_modellwert():
    assert _koepfe(_fx(ip=True), MODELL) == [(100, 40), (180, 210)]


def test_invert_tilt_und_swap_und_alles():
    for flags in ({"it": True}, {"sw": True}, {"ip": True, "it": True, "sw": True}):
        assert _koepfe(_fx(**flags), MODELL) == [(100, 40), (180, 210)], flags


def test_feinkanal_je_kopf():
    modell = dict(MODELL, pan_fine=128, **{"pan_fine#1": 64, "tilt_fine#1": 192})
    for flags in ({}, {"ip": True, "it": True}):
        k = _koepfe(_fx(**flags), modell)
        assert k == [(100.5, 40), (180.25, 210.75)], (flags, k)


def test_gesamtgeraet_und_kopf_0_stimmen_ueberein():
    fx = _fx(ip=True, sw=True)
    p = _build_fixture_payload(fx, apply_pan_tilt_orientation(fx, dict(MODELL)))
    assert (p["pan"], p["tilt"]) == (p["heads"][0]["pan"], p["heads"][0]["tilt"])


def test_spider_pan_als_tilt_mit_invert():
    """Spider ohne tilt#1: pan ist Bar-0-Tilt — auch der kommt als Modellwert."""
    modell = {"intensity": 255, "pan": 77, "tilt": 190, "color_r": 10, "color_r#1": 20}
    assert [t for _, t in _koepfe(_fx(), modell)] == [77, 190]
    assert [t for _, t in _koepfe(_fx(ip=True, it=True), modell)] == [77, 190]
