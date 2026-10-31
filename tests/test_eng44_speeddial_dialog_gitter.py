"""ENG-44: Einstellungsdialog des Speed-Dials und Faktor-Gitter.

* Faellt beim Gitterwechsel im Dialog der aktive Faktor heraus, springt der Dial
  auf das Reset-Ziel aus ENG-32 (Gitterstufe naechst 1×), nicht auf factors[0].
* Im Multiplikator-Modus (TEMPO_BUS_MULT) kommt ``_mult`` nur aus dem aktiven
  Faktor — das Multiplikator-Eingabefeld des Dialogs ueberschreibt ihn nicht
  getrennt (sonst zeigt das Gitter einen anderen Faktor als den angewandten).
* Die ENG-32-Skalierung der freien Geschwindigkeit bleibt beim Dialog-OK korrekt.
"""
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


def _dialog_ok(monkeypatch, d, factors_text, mult_value=None):
    """Dialog oeffnen, Faktor-Feld (und optional Multiplikator-Feld) setzen, OK."""
    from PySide6.QtWidgets import QDialog, QLineEdit, QDoubleSpinBox

    from src.ui.virtualconsole.vc_speedial import _fmt_factor
    start = ", ".join(_fmt_factor(f) for f in d.factor_buttons)

    def fake_exec(self):
        edits = [e for e in self.findChildren(QLineEdit) if e.text() == start]
        assert edits, "Faktor-Feld nicht gefunden"
        edits[0].setText(factors_text)
        if mult_value is not None:
            sb = [s for s in self.findChildren(QDoubleSpinBox) if s.suffix() == " ×"]
            assert sb, "Multiplikator-Feld nicht gefunden"
            sb[0].setValue(mult_value)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    d._open_properties()


def _mult_dial(fids, factors, active):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.TEMPO_BUS_MULT
    d.multiplier_mode = True
    d.function_ids = list(fids)
    d.factor_buttons = list(factors)
    d._active_factor = d._mult = float(active)
    return d


def _efx(name, mult, speed_hz):
    from src.core.engine.function_manager import get_function_manager
    e = get_function_manager().new_efx(name)
    e.tempo_bus_id = ""                      # Free-Run
    e.tempo_multiplier = mult
    e.speed_hz = speed_hz
    return e


def test_herausfallender_faktor_springt_auf_reset_ziel(monkeypatch):
    # Aktiv 2×, neues Gitter 1/16·1/8·1/4 ohne 1× -> Reset-Ziel 1/4, nicht 1/16.
    e = _efx("A", 2.0, 5.0)
    d = _mult_dial([e.id], [0.5, 1.0, 2.0], 2.0)
    _dialog_ok(monkeypatch, d, "1/16, 1/8, 1/4")
    assert d.factor_buttons == [1 / 16, 1 / 8, 1 / 4]
    assert abs(d._active_factor - 0.25) < 1e-9, d._active_factor
    assert abs(d._mult - d._active_factor) < 1e-9, "_mult weicht vom aktiven Faktor ab"
    assert abs(e.tempo_multiplier - 0.25) < 1e-9
    # ENG-32: speed im selben Verhaeltnis wie tempo_multiplier (2× -> ¼ = /8).
    assert abs(e.speed_hz - 5.0 / 8) < 1e-6, e.speed_hz


def test_speed_node_sub_herausfallender_faktor_reset_ziel(monkeypatch):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.SPEED_NODE
    d.role = "sub"
    d.factor_buttons = [0.5, 1.0, 2.0]
    d._active_factor = 2.0
    _dialog_ok(monkeypatch, d, "1/16, 1/8, 1/4")
    assert abs(d._active_factor - 0.25) < 1e-9, d._active_factor


def test_mult_kommt_im_gittermodus_nur_vom_faktor(monkeypatch):
    # Gitter unveraendert, aktiver Faktor 2× bleibt; ein abweichender Wert im
    # Multiplikator-Feld darf _mult nicht getrennt vom Gitter setzen.
    e = _efx("B", 2.0, 5.0)
    d = _mult_dial([e.id], [0.5, 1.0, 2.0], 2.0)
    _dialog_ok(monkeypatch, d, "0.5, 1, 2", mult_value=1.5)
    assert abs(d._active_factor - 2.0) < 1e-9
    assert abs(d._mult - 2.0) < 1e-9, d._mult
    assert abs(e.tempo_multiplier - 2.0) < 1e-9
    assert abs(e.speed_hz - 5.0) < 1e-6, "Dialog-OK ohne Faktorwechsel aendert speed"


def test_ohne_gitter_zaehlt_das_multiplikator_feld(monkeypatch):
    # FUNCTION-Modus mit Multiplikator: kein Faktor-Gitter -> Eingabefeld ist Quelle.
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial, SpeedTarget
    d = VCSpeedDial("x")
    d.target_mode = SpeedTarget.FUNCTION
    d.multiplier_mode = True
    _dialog_ok(monkeypatch, d, "0.25, 0.5, 1, 2", mult_value=1.5)
    assert abs(d._mult - 1.5) < 1e-9


def test_unveraendertes_ok_behaelt_gerundeten_faktor(monkeypatch):
    # 1/3 kommt aus dem Faktor-Feld nur gerundet zurueck (0.333333) — ein OK ohne
    # Aenderung darf den aktiven Faktor nicht auf das Reset-Ziel 1× werfen.
    d = _mult_dial([], [1 / 3, 1.0, 3.0], 1 / 3)
    start = ", ".join(__import__("src.ui.virtualconsole.vc_speedial",
                                 fromlist=["_fmt_factor"])._fmt_factor(f)
                      for f in d.factor_buttons)
    _dialog_ok(monkeypatch, d, start)
    assert abs(d._active_factor - 1 / 3) < 1e-5, d._active_factor
    assert d._active_factor in d.factor_buttons, "Faktor nicht auf die Stufe eingerastet"
    assert abs(d._mult - d._active_factor) < 1e-12
