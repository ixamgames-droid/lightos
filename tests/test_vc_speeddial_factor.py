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


def test_tempo_bus_mult_freerun_also_scales_speed():
    # Free-Run-Fallback: haengt der Effekt an KEINEM laufenden Bus (tempo_bus_id leer),
    # muss der Faktor zusaetzlich auf die freie Geschwindigkeit (speed) wirken — sonst
    # waere der Dial ein stiller No-op (tempo_multiplier wird im Free-Run nicht gelesen).
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine import effect_live
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    fm = get_function_manager()
    e = fm.new_efx("FR")
    e.tempo_bus_id = ""                     # frei laufend
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = [e.id]
    d.factor_buttons = [0.25, 0.5, 1.0, 2.0, 4.0]
    d._set_factor(0.5)
    assert abs(effect_live.get_param("speed", e.id) - 0.5) < 1e-6, "Free-Run-Speed nicht gesetzt"
    assert abs(e.tempo_multiplier - 0.5) < 1e-6, "Bus-Multiplikator ebenfalls gesetzt"
    d._set_factor(2.0)
    assert abs(effect_live.get_param("speed", e.id) - 2.0) < 1e-6


def test_tempo_bus_mult_custom_param_keeps_speed():
    # Eigener per-Effekt-Parameter (Phase E): NUR dieser wird gesteuert; die freie
    # Geschwindigkeit (speed) darf der Fallback dann NICHT anfassen.
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine import effect_live
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    fm = get_function_manager()
    e = fm.new_efx("CP")
    e.tempo_bus_id = ""
    speed0 = effect_live.get_param("speed", e.id)
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.function_ids = [e.id]
    d.param_keys_per_id = {e.id: "intensity"}
    d.factor_buttons = [0.25, 0.5, 1.0, 2.0, 4.0]
    d._set_factor(2.0)
    assert abs(effect_live.get_param("speed", e.id) - speed0) < 1e-6, \
        "speed darf bei eigenem Parameter nicht angefasst werden"


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


def test_dialog_target_editor_sets_multiple_effects(monkeypatch):
    # Mehrere Effekte per NAMEN ueber die aufklappbare „Steuert"-Liste auswaehlen ->
    # erstes Ziel landet in function_id, der Rest in function_ids (Multi-Effekt-Dial).
    from PySide6.QtWidgets import QDialog
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    from src.ui.virtualconsole.target_list_editor import TargetListEditor
    fm = get_function_manager()
    a = fm.new_efx("A")
    b = fm.new_efx("B")
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT

    def fake_exec(self):
        ed = self.findChild(TargetListEditor)
        assert ed is not None, "Steuert-Liste fehlt im SpeedDial-Dialog"
        ed.set_targets([a.id, b.id])
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    d._open_properties()
    assert d.function_id == a.id
    assert d.function_ids == [b.id]
    assert set(d._targets()) == {a.id, b.id}


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
