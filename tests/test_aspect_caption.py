"""Welle 4 (Label-Fix): aspect_caption — erzeugte Widgets tragen eine sprechende
Beschriftung (FX Speed / Helligkeit / Parametername …) statt ueberall des blossen
Effektnamens ('Matrix 1'). Toggle/Flash/Bulk behalten den Effektnamen.
"""
from src.ui.virtualconsole.vc_effect_meta import (
    aspect_caption, ControlOption, ControlKind)


def test_aspect_caption_per_kind():
    assert aspect_caption(ControlOption(ControlKind.INTENSITY, "Helligkeit"), "Matrix 1") == "Helligkeit"
    assert aspect_caption(ControlOption(ControlKind.TEMPO, "Tempo (Geschwindigkeit)"), "Matrix 1") == "FX Speed"
    assert aspect_caption(ControlOption(ControlKind.COLORS, "Farben aendern…"), "Matrix 1") == "Farben"
    assert aspect_caption(ControlOption(ControlKind.MOVEMENT, "Bewegung (XY-Feld)…"), "Matrix 1") == "Bewegung"
    assert aspect_caption(ControlOption(ControlKind.TEMPO_BUS, "Tempo-Bus zuweisen…"), "M") == "Tempo-Bus"
    # PARAM -> der Parametername aus dem Label (ohne 'Parameter: '-Praefix)
    assert aspect_caption(
        ControlOption(ControlKind.PARAM, "Parameter: Läufer-Anzahl", param_key="runner_count"),
        "Matrix 1") == "Läufer-Anzahl"
    # ACTION -> der Aktionsname
    assert aspect_caption(ControlOption(ControlKind.ACTION, "Aktion: Nächste Farbe"), "M") == "Nächste Farbe"
    # Toggle/Flash/Bulk -> Effektname
    assert aspect_caption(ControlOption(ControlKind.TOGGLE, "An/Aus (Toggle)"), "Matrix 1") == "Matrix 1"
    assert aspect_caption(ControlOption(ControlKind.FLASH, "Flash"), "Matrix 1") == "Matrix 1"
    assert aspect_caption(ControlOption(ControlKind.BULK, "Alle…"), "Matrix 1") == "Matrix 1"


def test_result_for_sets_aspect_caption():
    from src.ui.virtualconsole.smart_drop_dialog import SmartDropDialog
    dlg = SmartDropDialog(5)
    r = dlg._result_for(ControlOption(ControlKind.INTENSITY, "Helligkeit"), "VCSlider", "Matrix 1")
    assert r.caption == "Helligkeit"        # nicht 'Matrix 1'
    r2 = dlg._result_for(
        ControlOption(ControlKind.PARAM, "Parameter: Läufer", param_key="runner_count"),
        "VCStepper", "Matrix 1")
    assert r2.caption == "Läufer"
    # Toggle behaelt den Effektnamen
    r3 = dlg._result_for(ControlOption(ControlKind.TOGGLE, "An/Aus (Toggle)"), "VCButton", "Matrix 1")
    assert r3.caption == "Matrix 1"
