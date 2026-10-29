"""ENG-32: Speed-Dial im Multiplikator-Modus (TEMPO_BUS_MULT) passt zum Faktor-Gitter.

* Reset „X" springt auf 1× nur, wenn das Gitter 1× anbietet — sonst auf den
  Gitterwert, der 1× am naechsten liegt (bei den ENG-31-Dials der Baufaktor).
* Ein Faktor-Klick behaelt die gebaute Free-Run-Geschwindigkeit (speed_hz =
  150/60 × Faktor aus ENG-31) im Verhaeltnis, statt den Rohfaktor als speed zu
  schreiben.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])

SEED_BPM = 150.0


@pytest.fixture(autouse=True)
def _clean():
    yield
    from src.core.show.show_file import reset_show
    reset_show()


def _dial(fids, factors, active):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = list(fids)
    d.factor_buttons = list(factors)
    d._active_factor = d._mult = float(active)
    return d


def _efx_like_eng31(name, mult):
    from src.core.engine.function_manager import get_function_manager
    e = get_function_manager().new_efx(name)
    e.tempo_bus_id = ""                      # Free-Run
    e.tempo_multiplier = mult
    e.speed_hz = round(SEED_BPM / 60.0 * mult, 4)
    return e


@pytest.mark.parametrize("factors,erwartet", [
    ([1 / 8, 1 / 4], 1 / 4),                 # MH-Dial (ENG-31)
    ([1 / 16, 1 / 8], 1 / 8),                # Spider-Dial (ENG-31)
    ([2.0, 4.0], 2.0),
    ([0.25, 0.5, 1.0, 2.0, 4.0], 1.0),       # Standardgitter: wie bisher 1×
])
def test_reset_bleibt_im_gitter(factors, erwartet):
    e = _efx_like_eng31("R", factors[0])
    d = _dial([e.id], factors, factors[0])
    d._reset_factor()
    assert abs(d._active_factor - erwartet) < 1e-9
    assert any(abs(d._active_factor - f) < 1e-9 for f in factors), \
        "Reset landet ausserhalb des Faktor-Gitters"
    assert abs(e.tempo_multiplier - erwartet) < 1e-9


def test_faktor_klick_behaelt_free_run_speed():
    e = _efx_like_eng31("MH", 0.25)          # speed_hz 0.625 bei ¼
    d = _dial([e.id], [1 / 8, 1 / 4], 0.25)
    d._set_factor(0.25)                      # gleicher Faktor: speed unveraendert
    assert abs(e.speed_hz - 0.625) < 1e-6, f"Free-Run verloren: {e.speed_hz}"
    d._set_factor(1 / 8)                     # halbes Tempo -> halbe Free-Run-Rate
    assert abs(e.tempo_multiplier - 0.125) < 1e-9
    assert abs(e.speed_hz - 0.3125) < 1e-6, f"Free-Run nicht skaliert: {e.speed_hz}"
    d._reset_factor()                        # zurueck auf den Baufaktor
    assert abs(e.speed_hz - 0.625) < 1e-6
