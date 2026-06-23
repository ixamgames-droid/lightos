"""F2: kanonischer Attribut-Klassifizierer.

Programmer-Attribut-Tabs und der Speichern-Kanal-Dialog teilen sich EINE Quelle
(src/core/attr_groups) -> kein Auseinanderdriften mehr (Bug E bleibt gefixt:
Strobe/Shutter zaehlen als Intensity, nicht als Beam).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.attr_groups import classify_attr, ATTR_GROUPS, ATTR_GROUP_ORDER


def test_core_classification():
    assert classify_attr("strobe") == "Intensity"
    assert classify_attr("shutter") == "Intensity"
    assert classify_attr("dimmer") == "Intensity"
    assert classify_attr("color_r") == "Color"
    assert classify_attr("color_w") == "Color"
    assert classify_attr("pan") == "Position"
    assert classify_attr("prism") == "Beam"
    # Regression: prism_rot ist exakt in Effect und darf NICHT ueber den
    # Beam-Substring "prism" als Beam klassifiziert werden (Zwei-Pass-Reihenfolge).
    assert classify_attr("prism_rot") == "Effect"
    assert classify_attr("gobo_wheel") == "Gobo"
    assert classify_attr("unknown_attr") == "Other"


def test_programmer_and_save_dialog_share_one_classifier():
    from src.ui.views.snap_file_panel import _classify_attr as snap_classify
    from src.ui.views.programmer_view import _classify_attribute as prog_classify
    for attr in ("strobe", "shutter", "dimmer", "intensity", "color_r",
                 "color_wheel", "pan", "prism", "gobo", "macro", "zoom", "foo"):
        assert snap_classify(attr) == prog_classify(attr) == classify_attr(attr), attr
    # exakt dasselbe Funktionsobjekt (eine Quelle, kein Drift moeglich)
    assert snap_classify is prog_classify is classify_attr


def test_order_other_last_and_complete():
    assert ATTR_GROUP_ORDER[-1] == "Other"
    assert set(ATTR_GROUP_ORDER) - {"Other"} == set(ATTR_GROUPS.keys())
