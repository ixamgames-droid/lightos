"""Welle 4 (L/N): VCEffectEditor — beweglicher Effekt-Editor-Container.

Smart-Drop mit „Als Box gruppieren" baut alle gewaehlten Widgets in eine
VCEffectEditor-Box (VCFrame-Subklasse) statt lose aufs Canvas. Die Box bindet an
den Effekt (effect_id), bettet eine Live-Vorschau ein, Kinder sind auto-gelabelt,
Snap-out + Teil-Entfernen erbt die Box.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt


def _app():
    return QApplication.instance() or QApplication([])


def _results():
    from src.ui.virtualconsole.smart_drop_dialog import SmartDropResult
    from src.ui.virtualconsole.vc_button import ButtonAction
    return [
        SmartDropResult(widget_type="VCButton", function_id=5, caption="An/Aus",
                        action=ButtonAction.FUNCTION_TOGGLE),
        SmartDropResult(widget_type="VCSlider", function_id=5, caption="Helligkeit"),
    ]


def test_registered():
    _app()
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor
    assert WIDGET_REGISTRY.get("VCEffectEditor") is VCEffectEditor


def test_build_box_groups_children():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_effect_editor import VCEffectEditor
    from src.ui.virtualconsole.vc_widget import VCWidget
    c = VCCanvas()
    created = c.build_from_smart_results(_results(), pos=QPoint(50, 50), box=True)
    frame = created[0]
    assert isinstance(frame, VCEffectEditor)
    assert frame.effect_id == 5
    kids = frame.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kids) == 2                      # Button + Slider IN der Box
    assert sorted(k.caption for k in kids) == ["An/Aus", "Helligkeit"]   # auto-Labels
    # Ohne Box: weiterhin lose (kein VCEffectEditor)
    c2 = VCCanvas()
    loose = c2.build_from_smart_results(_results(), pos=QPoint(50, 50), box=False)
    assert not any(isinstance(w, VCEffectEditor) for w in loose)


def test_box_roundtrip():
    _app()
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_widget import VCWidget
    c = VCCanvas()
    frame = c.build_from_smart_results(_results(), pos=QPoint(0, 0), box=True)[0]
    d = frame.to_dict()
    assert d["type"] == "VCEffectEditor"
    assert d["effect_id"] == 5
    assert len(d["children"]) == 2             # Vorschau NICHT serialisiert (aus effect_id abgeleitet)
    # Reload in eine frische Box
    c2 = VCCanvas()
    f2 = c2._add_widget("VCEffectEditor", QPoint(0, 0))
    f2.apply_dict(d)
    assert f2.effect_id == 5
    kids2 = f2.findChildren(VCWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(kids2) == 2
