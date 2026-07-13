"""Tests für die Show-Validierungs-Ebene (Phase 1, Report-Modus).

- Akzeptanz: eine absichtlich kaputte Show (Fake-Algo + Fake-Widget +
  Fake-param_key) erzeugt genau die erwarteten lauten Findings.
- Eine saubere Minimal-Show erzeugt KEINE Fehler.
- Report-Lauf über alle committeten shows/*.lshow (blockiert NICHT — Phase 1 ist
  Frühwarnung; das harte CI-Gate kommt erst in Phase 5).
"""
from __future__ import annotations

import glob
import os

from src.core.capability.reflect import get_capabilities
from src.core.capability.validate import (
    ERROR, WARNING, validate_show_dict, validate_lshow, assert_show_dict,
    ShowValidationError, format_findings)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHOWS = os.path.join(_ROOT, "shows")


def _codes(findings, severity=None):
    return [f.code for f in findings if severity is None or f.severity == severity]


def test_reflect_smoke():
    """Die SSOT reflektiert die echten Sätze (nicht leer, echte Werte drin)."""
    caps = get_capabilities()
    assert "VCButton" in caps.widget_types
    assert "VCSlider" in caps.widget_types
    assert "Toggle" in caps.button_actions          # ButtonAction.TOGGLE.value
    assert "Level" in caps.slider_modes             # plain-str SliderMode
    assert "Schachbrett" in caps.matrix_algorithms  # RgbAlgorithm.CHECKER.value
    assert "RGB" in caps.matrix_styles
    assert "Circle" in caps.efx_algorithms
    assert "RGBMatrix" in caps.function_types
    assert "speed" in caps.all_param_keys
    assert caps.show_version  # "1.1"


def test_linter_widget_types_match_registry():
    """REGRESSION (2026-07-02): Der Linter muss EXAKT die echte WIDGET_REGISTRY
    kennen. Scheitert der Import in reflect() (except: pass → leeres Set),
    deaktiviert sich die VC-TYPE-Regel still; driftet die Quelle, meldet der
    Linter Falsches. Beides knallt hier laut."""
    from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
    caps = get_capabilities()
    assert caps.widget_types, \
        "Linter kennt KEINE Widget-Typen (Registry-Import in reflect() gescheitert?)"
    assert caps.widget_types == frozenset(WIDGET_REGISTRY), \
        f"Linter/Registry-Drift: {sorted(caps.widget_types ^ set(WIDGET_REGISTRY))}"


def test_validator_catches_broken_show():
    """ACCEPTANCE: Fake-Matrix-Algo + unbekanntes Widget + Fake-param_key →
    drei laute ERROR-Findings mit den richtigen Codes."""
    show = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 1, "type": "RGBMatrix", "name": "Kaputte Matrix",
             "algorithm": "Schachbret",   # Tippfehler von "Schachbrett"
             "style": "RGB", "params": {}},
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCBogus", "caption": "gibt's nicht"},
            {"type": "VCSlider", "caption": "Tempo", "mode": "Level",
             "param_key": "speeed", "function_id": 1},   # Tippfehler von "speed"
        ]},
    }
    findings = validate_show_dict(show)
    errors = [f for f in findings if f.severity == ERROR]
    codes = _codes(findings, ERROR)

    assert "MX-ALGO" in codes, format_findings(findings)
    assert "VC-TYPE" in codes, format_findings(findings)
    assert "VC-PARAMKEY" in codes, format_findings(findings)
    assert len(errors) >= 3, format_findings(findings)

    # Jedes Finding zitiert die echte Schluck-Stelle.
    assert all(f.swallow_site for f in errors), format_findings(errors)

    # assert_* wirft entsprechend.
    try:
        assert_show_dict(show)
    except ShowValidationError:
        pass
    else:
        raise AssertionError("assert_show_dict hätte werfen müssen")


def test_asymmetry_efx_and_style_caught():
    """Die zentrale Asymmetrie: falscher EFX-Algo (hart) und falscher Matrix-Style
    (hart) werden BEIDE gefangen — nicht nur der weiche Matrix-Algo-Fall."""
    show = {
        "functions": {"functions": [
            {"id": 1, "type": "EFX", "name": "Bad EFX", "motion": True,
             "algorithm": "Kreisel"},                       # kein EfxAlgorithm
            {"id": 2, "type": "RGBMatrix", "name": "Bad Style",
             "algorithm": "Plain", "style": "Regenbogen"},  # kein MatrixStyle
        ]},
    }
    codes = _codes(validate_show_dict(show), ERROR)
    assert "EFX-ALGO" in codes
    assert "MX-STYLE" in codes


def test_clean_show_passes():
    """Eine saubere Minimal-Show erzeugt keine Fehler."""
    show = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 1, "type": "RGBMatrix", "name": "OK Matrix",
             "algorithm": "Plain", "style": "RGB", "params": {}},
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCButton", "caption": "Go", "action": "Toggle", "function_id": 1},
            {"type": "VCSlider", "caption": "Speed", "mode": "EffectSpeed",
             "param_key": "speed", "function_id": 1},
        ]},
    }
    findings = validate_show_dict(show)
    errors = [f for f in findings if f.severity == ERROR]
    assert not errors, format_findings(findings)
    assert_show_dict(show)  # darf NICHT werfen


def test_paramkey_bound_to_wrong_function_type_caught():
    """QA-19: ein global gültiger param_key, der an eine Funktion gebunden ist,
    deren Typ ihn NICHT trägt (QA-05-Bugklasse: global gültig, für DIESE Funktion
    inert), wird als VC-PARAMKEY-FN-ERROR gemeldet — statt still durch den
    Union-Check (caps.all_param_keys) zu rutschen.

    'size' ist ein echter EFX-Param (also in der Union), aber KEIN Matrix-Param;
    an eine RGBMatrix gebunden bleibt der Regler wirkungslos."""
    caps = get_capabilities()
    assert "size" in caps.all_param_keys        # global gültig …
    assert "size" not in caps.matrix_all_param_keys  # … aber nicht an einer Matrix
    show = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 7, "type": "RGBMatrix", "name": "Matrix",
             "algorithm": "Plain", "style": "RGB", "params": {}},
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCSlider", "caption": "Size?", "mode": "Level",
             "param_key": "size", "function_id": 7},
        ]},
    }
    findings = validate_show_dict(show)
    codes = _codes(findings, ERROR)
    assert "VC-PARAMKEY-FN" in codes, format_findings(findings)
    # NICHT als bloßer Union-Miss (Tippfehler) gemeldet — der Key IST global gültig.
    assert "VC-PARAMKEY" not in codes, format_findings(findings)
    # das Finding zitiert die echte Schluck-Stelle.
    fn = [f for f in findings if f.code == "VC-PARAMKEY-FN"][0]
    assert fn.swallow_site


def test_paramkey_correct_binding_stays_clean():
    """Gegenprobe zu QA-19: derselbe param_key, korrekt an eine EFX gebunden
    (die 'size' wirklich trägt), erzeugt KEIN VC-PARAMKEY-FN-Finding. Und ein
    universeller Matrix-Param ('speed') an einer Matrix bleibt ebenfalls sauber."""
    show = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 1, "type": "EFX", "name": "Kreis", "motion": True,
             "algorithm": "Circle"},
            {"id": 2, "type": "RGBMatrix", "name": "Matrix",
             "algorithm": "Plain", "style": "RGB", "params": {}},
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCSlider", "caption": "Size", "mode": "Level",
             "param_key": "size", "function_id": 1},     # EFX trägt 'size' -> ok
            {"type": "VCSlider", "caption": "Speed", "mode": "EffectSpeed",
             "param_key": "speed", "function_id": 2},     # Matrix-universell -> ok
        ]},
    }
    findings = validate_show_dict(show)
    assert "VC-PARAMKEY-FN" not in _codes(findings, ERROR), format_findings(findings)


def test_paramkey_bound_to_efx_tagged_non_efxinstance_stays_clean():
    """QA-19-Regression (adversariale Review): ``FunctionType.EFX`` ist mehrdeutig —
    ``Carousel`` (Diskriminator ``pattern``) und ``LayeredEffect`` (``layers``) tragen
    denselben Typ-Tag ``"EFX"`` wie die echte Pan/Tilt-``EfxInstance`` (``motion``/
    ``speed_hz``), exponieren aber KEINE ``list_params``. Der maßgebliche Live-Check
    liefert für sie ``[]`` und flaggt nichts; der statische VC-PARAMKEY-FN-Check darf
    daher NICHT strenger sein und eine sonst gültige Show beim Speichern blocken.

    'offset' ist global gültig (Matrix-Param) aber KEIN EFX-Param — vor dem Fix meldete
    der statische Pfad ihn an einer Carousel/LayeredEffect fälschlich als Fehler."""
    caps = get_capabilities()
    assert "offset" in caps.all_param_keys        # global gültig …
    assert "offset" not in caps.efx_param_keys    # … aber kein EFX-Param
    show = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 1, "type": "EFX", "name": "Wirbel", "pattern": "Pulse"},   # Carousel
            {"id": 2, "type": "EFX", "name": "Schichten", "layers": []},      # LayeredEffect
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCSlider", "caption": "Off1", "mode": "Level",
             "param_key": "offset", "function_id": 1},
            {"type": "VCSlider", "caption": "Off2", "mode": "Level",
             "param_key": "offset", "function_id": 2},
        ]},
    }
    findings = validate_show_dict(show)
    assert "VC-PARAMKEY-FN" not in _codes(findings, ERROR), format_findings(findings)
    assert_show_dict(show)  # die sonst gültige Show darf NICHT am Speichern gehindert werden

    # Gegenprobe, dass der scharfe Check lebt: dieselbe 'offset'-Bindung an eine echte
    # EfxInstance (motion) MUSS weiterhin als VC-PARAMKEY-FN feuern.
    hard = {
        "version": "1.1",
        "functions": {"functions": [
            {"id": 3, "type": "EFX", "name": "Kreis", "motion": True, "algorithm": "Circle"},
        ]},
        "virtual_console": {"widgets": [
            {"type": "VCSlider", "caption": "Off", "mode": "Level",
             "param_key": "offset", "function_id": 3},
        ]},
    }
    assert "VC-PARAMKEY-FN" in _codes(validate_show_dict(hard), ERROR), \
        format_findings(validate_show_dict(hard))


def test_paramkey_unbound_still_only_union_checked():
    """Ohne function_id (keine Bindung auflösbar) bleibt es beim Union-Check:
    ein global gültiger Key ist ok, ein Tippfehler weiterhin VC-PARAMKEY."""
    ok = {"virtual_console": {"widgets": [
        {"type": "VCSlider", "caption": "x", "mode": "Level", "param_key": "size"}]}}
    assert not _codes(validate_show_dict(ok), ERROR), \
        format_findings(validate_show_dict(ok))
    bad = {"virtual_console": {"widgets": [
        {"type": "VCSlider", "caption": "x", "mode": "Level", "param_key": "siize"}]}}
    assert "VC-PARAMKEY" in _codes(validate_show_dict(bad), ERROR)


def test_legacy_matrix_algo_accepted():
    """Ein Legacy-Algorithmus-String (über _LEGACY_ALGO_MAP migriert) ist gültig."""
    show = {"functions": {"functions": [
        {"id": 1, "type": "RGBMatrix", "name": "Legacy",
         "algorithm": "Chase Horizontal", "style": "RGB"},
    ]}}
    assert "MX-ALGO" not in _codes(validate_show_dict(show), ERROR)


def test_ascii_color_target_normalized():
    """Alt-Show mit ASCII-ColorTarget ('…hinzufuegen') wird NICHT als Fehler
    gemeldet — der Loader normalisiert ASCII->Umlaut, der Validator spiegelt das."""
    show = {"virtual_console": {"widgets": [
        {"type": "VCColor", "caption": "x", "target": "Effekt (Farbe hinzufuegen)"},
    ]}}
    codes = _codes(validate_show_dict(show), ERROR)
    assert "VC-COLORTARGET" not in codes
    # ein WIRKLICH falscher Wert wird weiter gemeldet
    bad = {"virtual_console": {"widgets": [
        {"type": "VCColor", "caption": "x", "target": "Gibtsnicht"}]}}
    assert "VC-COLORTARGET" in _codes(validate_show_dict(bad), ERROR)


def test_vccolor_loads_ascii_target():
    """VCColor.apply_dict normalisiert einen ASCII-Alt-Wert auf den heutigen."""
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    from src.ui.virtualconsole.vc_color import VCColor, ColorTarget
    w = VCColor("x")
    w.apply_dict({"target": "Effekt (Farbe hinzufuegen)"})
    assert w.target == ColorTarget.EFFECT_ADD   # '…hinzufügen' (Umlaut)


def test_committed_shows_have_no_errors(capsys):
    """PHASE 5 HARD-GATE: alle LOKALEN shows/*.lshow MÜSSEN frei von
    ERROR-Findings sein (Warnungen erlaubt). Blockiert ab jetzt (Report→Fail).

    Trotz des Namens: gelint wird ALLES, was lokal in shows/ liegt — die
    meisten .lshow sind gitignored (user-spezifisch), committet sind nur die
    demo_*-Ausnahmen. Wird eine per Generator gebaute Show nach einem
    Code-Umbau stale (z. B. entfernter Widget-Typ), den Generator fixen und
    die Show LOKAL neu erzeugen (tools/build_*.py) — nicht den Linter lockern."""
    paths = sorted(glob.glob(os.path.join(_SHOWS, "*.lshow")))
    if not paths:
        return  # keine Shows committet
    total_err = total_warn = 0
    lines = []
    for p in paths:
        try:
            findings = validate_lshow(p)
        except Exception as exc:
            lines.append(f"[FAIL] {os.path.basename(p)}: Lesefehler: {exc}")
            total_err += 1
            continue
        errs = sum(1 for f in findings if f.severity == ERROR)
        warns = sum(1 for f in findings if f.severity == WARNING)
        total_err += errs
        total_warn += warns
        mark = "[FAIL]" if errs else ("[warn]" if warns else "[ ok ]")
        lines.append(f"{mark} {os.path.basename(p)}: {errs} Fehler, {warns} Warnungen")
    report = "\n".join(lines) + \
        f"\n== GATE: {total_err} Fehler, {total_warn} Warnungen ueber {len(paths)} Shows =="
    with capsys.disabled():
        print("\n[show-lint Hard-Gate]\n" + report)
    assert total_err == 0, (
        "Committete Shows enthalten Lint-FEHLER (Phase-5-Hard-Gate). "
        "Mit `python tools/lint_show.py shows/*.lshow` ansehen:\n" + report)
