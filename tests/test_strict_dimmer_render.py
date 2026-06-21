"""Strikte Trennung Farbe/Dimmer am ECHTEN Render-Pfad (_render_frame) der Show.

Beweist: ein reiner Farb-Effekt (Seite 1) setzt RGB, aber NICHT die Intensitaet
(Lampe bleibt dunkel). Erst ein Dimmer-Effekt (Seite 2 „Dimmer Voll") gibt
Helligkeit. So sind Farbe und Dimmer komplett getrennt.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.app_state import get_state, get_channels_for_patched
from src.core.dmx.universe import Universe
from src.core.show.show_file import load_show, reset_show
from src.core.engine.function_manager import get_function_manager
from src.core.engine import effect_live

SHOW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "shows", "Farb_FX_VC_Show.lshow")


@pytest.fixture()
def loaded():
    if not os.path.exists(SHOW):
        pytest.skip("Show fehlt — zuerst tools/build_farb_fx_vc_show.py laufen lassen")
    ok, msg = load_show(SHOW)
    assert ok, msg
    st = get_state()
    st.universes = {1: Universe(1)}     # COM3 nicht verfuegbar -> Universe manuell
    st._rebuild_render_plan()
    yield st, get_function_manager()
    reset_show()


def _addr(st, fid, attr):
    fx = next(f for f in st.get_patched_fixtures() if f.fid == fid)
    ch = {c.attribute: c.channel_number for c in get_channels_for_patched(fx)}
    return fx.address + ch[attr] - 1


def _fid(fm, name):
    return next(f for f in fm.all() if f.name == name).id


def test_color_only_dark_then_dimmer_lights(loaded):
    st, fm = loaded
    inten = _addr(st, 1, "intensity")
    blue = _addr(st, 1, "color_b")

    # 1) reiner Farb-Effekt (blau) -> Farbe gesetzt, Dimmer bleibt 0 (dunkel)
    sid = _fid(fm, "PAR Solid")
    fm.start(sid)
    effect_live.set_param("color1", (0, 0, 255), sid)
    st._render_frame(0.05)
    assert st.universes[1].get_channel(inten) == 0, "Farb-Effekt treibt den Dimmer (nicht strikt!)"
    assert st.universes[1].get_channel(blue) == 255, "Farbe nicht gesetzt"

    # 2) + Dimmer Voll -> Intensitaet voll, Farbe bleibt -> leuchtet blau
    vid = _fid(fm, "PAR Dimmer Voll")
    fm.start(vid)
    st._render_frame(0.05)
    assert st.universes[1].get_channel(inten) == 255, "Dimmer Voll hebt die Helligkeit nicht"
    assert st.universes[1].get_channel(blue) == 255

    # 3) Dimmer wieder aus -> wieder dunkel (Farbe bleibt gesetzt)
    fm.stop(vid)
    st._render_frame(0.05)
    assert st.universes[1].get_channel(inten) == 0, "Dimmer bleibt haengen"
    fm.stop(sid)
