"""VCSpeedDial: TEMPO_BUS_MULT zeigt jetzt das Faktor-Gitter (¼ ½ 1 2 3 4) und der
Faktor-Klick schreibt den Pro-Effekt-tempo_multiplier (unbegrenzt viele unabhaengige
Multiplikatoren am selben Master). SPEED_NODE-Sub bleibt unveraendert."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _clean():
    yield
    from src.core.show.show_file import reset_show
    reset_show()


def test_tempo_bus_mult_uses_factor_grid():
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    assert d._factor_grid_mode() is True


def test_tempo_bus_mult_factor_click_sets_multiplier():
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    fm = get_function_manager()
    e = fm.new_efx("T")
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = [e.id]
    d.factor_buttons = [0.25, 0.5, 1.0, 2.0, 3.0, 4.0]
    d._set_factor(3.0)
    assert abs(e.tempo_multiplier - 3.0) < 1e-6, "Faktor x3 nicht geschrieben"
    d._set_factor(0.5)
    assert abs(e.tempo_multiplier - 0.5) < 1e-6, "Faktor x0.5 nicht geschrieben"


def test_speed_node_master_keeps_dial():
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.SPEED_NODE
    d.role = "sub"
    assert d._factor_grid_mode() is True
    d.role = "master"
    assert d._factor_grid_mode() is False


def test_multiplier_grid_shown_even_if_show_factors_off():
    # Im Multiplikator-Modus muss das Faktor-Gitter IMMER gezeichnet/klickbar sein,
    # auch wenn show_factors aus ist (sonst leeres Widget). Ohne show_factors zu mutieren.
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.show_factors = False
    assert d._show_factor_grid() is True
    # show_factors bleibt unveraendert (keine versteckte Mutation/Persistenz)
    assert d.show_factors is False


def test_speed_node_sub_respects_show_factors():
    # SPEED_NODE-Sub respektiert weiterhin die Anzeigeoption.
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.SPEED_NODE
    d.role = "sub"
    d.show_factors = False
    assert d._show_factor_grid() is False
    d.show_factors = True
    assert d._show_factor_grid() is True


def test_live_probe_tracks_master_in_multiplier_mode():
    # Im Multiplikator-Modus liefert die Live-Probe die Master-BPM × Faktor;
    # in nicht-Tempo-Modi None (kein unnoetiger Poll-Repaint).
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d._active_factor = 2.0
    probe = d._live_bpm_probe()
    assert isinstance(probe, float)         # haengt an der Master-BPM
    d.target_mode = SpeedTarget.EXECUTOR
    assert d._live_bpm_probe() is None       # keine externe BPM -> kein Poll noetig


def _drive_func_pick(monkeypatch, start_mode):
    """Oeffnet den Dialog, waehlt im Namens-Dropdown eine Funktion und gibt den
    danach im Ziel-Dropdown stehenden Modus zurueck (Dialog wird verworfen)."""
    from PySide6.QtWidgets import QDialog, QComboBox
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    e = fm.new_efx("PickTest")
    d = VCSpeedDial("x")
    d.target_mode = start_mode
    captured = {}

    def fake_exec(self):
        combos = self.findChildren(QComboBox)
        mode_cb = next(c for c in combos
                       if any(c.itemData(i) == SpeedTarget.TEMPO_BUS_MULT
                              for i in range(c.count())))
        func_combo = next(c for c in combos
                          if any(c.itemData(i) == e.id for i in range(c.count())))
        idx = next(i for i in range(func_combo.count())
                   if func_combo.itemData(i) == e.id)
        func_combo.setCurrentIndex(idx)             # Ziel-Effekt per Name waehlen
        captured["mode"] = mode_cb.currentData()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    d._open_properties()
    return captured["mode"]


def test_func_pick_keeps_multiplier_mode(monkeypatch):
    # Ziel-Effekt waehlen darf den bereits gewaehlten Multiplikator-Modus NICHT kippen.
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    assert _drive_func_pick(monkeypatch, SpeedTarget.TEMPO_BUS_MULT) == SpeedTarget.TEMPO_BUS_MULT


def test_func_pick_switches_from_executor(monkeypatch):
    # Aus dem Default (Executor) heraus schaltet das Waehlen einer Funktion bequem
    # auf „Funktion/Effekt" (alte Komfort-Funktion bleibt erhalten).
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    assert _drive_func_pick(monkeypatch, SpeedTarget.EXECUTOR) == SpeedTarget.FUNCTION


def test_poll_live_repaints_only_on_change(monkeypatch):
    # ~10-Hz-Poll zeichnet NUR neu, wenn sich der angezeigte Wert geaendert hat.
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    monkeypatch.setattr(d, "isVisible", lambda: True)
    vals = iter([100.0, 100.0, 120.0])
    monkeypatch.setattr(d, "_live_bpm_probe", lambda: next(vals))
    calls = []
    monkeypatch.setattr(d, "update", lambda *a, **k: calls.append(1))
    d._poll_live()   # 100 -> neu
    d._poll_live()   # 100 -> unveraendert, kein Repaint
    d._poll_live()   # 120 -> neu
    assert len(calls) == 2
