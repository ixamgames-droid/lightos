"""Stufe 5 — VC-Live-Kopplung: Effekte taktgleich an Tempo-Busse/Dials koppeln.

Deckt ab:
- effect_live.set_param("tempo_bus_id", …) re-ankert einen LAUFENDEN Effekt sofort
  (taktgleich beim Live-Umhaengen; erzeugt feste Buses A-D bei Bedarf).
- VCBusSelector haengt MEHRERE gekoppelte Effekte mit einem Chip-Klick taktgleich
  auf den Bus; ohne Effekt-Bindung bleibt das globale Arm-Verhalten.
- VCSpeedDial Multiplier-Anzeige (_mult_base_bus/_live_bpm_probe) folgt dem Bus der
  gekoppelten Effekte statt immer dem Default-Bus.
- VCSpeedDial _apply_mult_bus_coupling weist die gekoppelten Effekte dem Dial-Bus zu.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt, QPointF, QEvent
import pytest

_app = QApplication.instance() or QApplication([])

from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
from src.core.engine import effect_live


@pytest.fixture(autouse=True)
def _clean():
    reset_tempo_bus_manager()
    get_function_manager().from_dict({"functions": []})
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    get_tempo_bus_manager().set_auto_sync(True)
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    mgr = get_bpm_manager(); mgr.set_locked(False); mgr.reset()
    get_tempo_bus_manager().set_auto_sync(False)


def _matrix(name, bus_id="Global"):
    fm = get_function_manager()
    m = RgbMatrixInstance(name=name, cols=4, rows=1, algorithm=RgbAlgorithm.CHASE,
                          fixture_grid=[1, 2, 3, 4])
    m.tempo_bus_id = bus_id
    fm.add(m)
    return m


# ── effect_live: Live-Bus-Wechsel re-ankert ─────────────────────────────────────
def test_set_param_tempo_bus_reanchors_running_effect():
    tbm = get_tempo_bus_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)
    m = _matrix("M", "Global"); m.start()
    tbm.get("default").advance_frame(1.3)        # Default laeuft weiter
    m._beat_anchor = 999.0                        # kuenstlich verstellter Alt-Anker
    ok = effect_live.set_param("tempo_bus_id", "A", m.id)
    assert ok
    assert m.tempo_bus_id == "A"
    busA = tbm.get("A")
    assert busA is not None, "fester Bus A muss beim Live-Wechsel erzeugt werden"
    assert m._beat_anchor != 999.0, "Live-Bus-Wechsel hat NICHT re-ankert (Phasensprung-Bug)"
    assert abs(m._beat_anchor - busA.position()) < 1e-6


# ── VCBusSelector: mehrere Effekte taktgleich umhaengen ─────────────────────────
def _click_chip(widget, idx, n_chips=4, w=220):
    widget.resize(w, 84)
    x = int(w / n_chips * idx) + 10
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(x, 40),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)


def test_bus_selector_moves_multiple_effects():
    from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
    tbm = get_tempo_bus_manager()
    a = _matrix("A", "Global"); b = _matrix("B", "Global")
    tbm.armed_bus_id = "A"
    w = VCBusSelector()
    w.function_id = a.id
    w.function_ids = [b.id]
    _click_chip(w, 2)                             # Chip-Index 2 = "C"
    assert a.tempo_bus_id == "C"
    assert b.tempo_bus_id == "C", "zweiter gekoppelter Effekt nicht mit umgehaengt"
    assert tbm.armed_bus_id == "A", "globaler Arm-Bus darf bei Effekt-Bindung unberuehrt bleiben"


def test_bus_selector_global_arm_without_binding():
    from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
    tbm = get_tempo_bus_manager()
    w = VCBusSelector()                           # keine Effekt-Bindung
    _click_chip(w, 1)                             # "B"
    assert tbm.armed_bus_id == "B"


def test_bus_selector_roundtrip_multi():
    from src.ui.virtualconsole.vc_bus_selector import VCBusSelector
    w = VCBusSelector()
    w.buses = ["A", "B", "C", "D"]
    w.function_id = 7
    w.function_ids = [8, 9]
    d = w.to_dict()
    w2 = VCBusSelector()
    w2.apply_dict(d)
    assert w2.function_id == 7
    assert w2.function_ids == [8, 9]


# ── VCSpeedDial Multiplier: Anzeige + Bus-Kopplung ──────────────────────────────
def test_speeddial_mult_readout_follows_effect_bus():
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    tbm = get_tempo_bus_manager(); mgr = get_bpm_manager()
    mgr.set_manual_bpm(120.0)                     # Default/Haupt-BPM = 120
    busA = tbm.ensure_bus("A"); busA.set_bpm(140.0)
    m = _matrix("M", "A")                         # Effekt liegt auf Bus A (140)
    dial = VCSpeedDial()
    dial.target_mode = SpeedTarget.TEMPO_BUS_MULT
    dial.function_id = m.id
    dial._set_factor(2.0)                         # ×2
    probe = dial._live_bpm_probe()
    assert probe is not None
    assert abs(probe - 280.0) < 1.0, f"Anzeige folgt nicht Bus A (140×2), probe={probe}"


def test_speeddial_mult_couples_effects_to_chosen_bus():
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    m = _matrix("M", "Global")
    dial = VCSpeedDial()
    dial.target_mode = SpeedTarget.TEMPO_BUS_MULT
    dial.function_id = m.id
    dial.tempo_bus_id = "B"
    dial._apply_mult_bus_coupling()
    assert m.tempo_bus_id == "B", "Multiplier-Dial koppelt Effekt nicht an den gewaehlten Bus"
