"""Welle 4 (O): Live-Mini-Editor — Long-Press im VC-Live-Modus + DEFERRED APPLY.

Der Editor liest die aktuellen Effekt-Parameter, aendert nur eine lokale Kopie und
sendet sie ERST beim Klick auf „Anwenden" (kein Streaming vorher). Der Long-Press
ist pro Button schaltbar und nur fuer Toggle/Effekt-Aktion mit gebundenem Effekt aktiv.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _matrix():
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm
    fm = get_function_manager()
    m = RgbMatrixInstance(name="M", cols=4, rows=1, fixture_grid=[1, 2, 3, 4],
                          algorithm=RgbAlgorithm.CHASE)
    fm.add(m)
    return fm, m


def test_live_editor_deferred_apply():
    _app()
    fm, m = _matrix()
    from src.ui.virtualconsole.vc_live_editor import VCLiveEditor
    from src.core.engine import effect_live
    ed = VCLiveEditor(m.id)
    assert "speed" in ed.staged_values()           # numerische Params vorhanden
    before = effect_live.get_param("intensity", m.id)
    kind, w = ed._controls["intensity"]            # float 0..1
    w.setValue(0.5)
    # DEFERRED: noch NICHT gesendet -> Effekt unveraendert
    assert effect_live.get_param("intensity", m.id) == before
    assert abs(ed.staged_values()["intensity"] - 0.5) < 1e-6
    # jetzt anwenden
    ed._apply_and_close()
    assert abs(effect_live.get_param("intensity", m.id) - 0.5) < 1e-6


def test_button_long_press_arming_and_serialization():
    _app()
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    b = VCButton()
    assert b.long_press_editor is False             # Default aus (sicher)
    assert b.to_dict()["long_press_editor"] is False

    b.long_press_editor = True
    b.action = ButtonAction.FUNCTION_TOGGLE
    b.function_id = 7
    b._maybe_arm_long_press()
    assert b._lp_timer.isActive()                   # Toggle + gebunden -> Arm
    b._lp_timer.stop()

    b.function_id = None                            # keine Bindung -> kein Arm
    b._maybe_arm_long_press()
    assert not b._lp_timer.isActive()

    b.function_id = 7
    b.action = ButtonAction.FUNCTION_FLASH          # Flash -> kein Arm (Konflikt)
    b._maybe_arm_long_press()
    assert not b._lp_timer.isActive()

    b.action = ButtonAction.FUNCTION_TOGGLE
    d = b.to_dict()
    b2 = VCButton()
    b2.apply_dict(d)
    assert b2.long_press_editor is True
