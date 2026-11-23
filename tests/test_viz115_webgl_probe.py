"""VIZ-115: 3D-Ansicht ohne WebGL darf die App nicht mehr abstuerzen lassen.

Live-Klicktest 23.11.2026: in einem Fenster-Server ohne GPU riss das Oeffnen
der 3D-Ansicht die ganze App mit (Segfault im nativen Teil). Seither prueft ein
Kindprozess vorab, ob WebGL geht; sonst Software-Rendering, sonst Meldung.

Hier nur die Entscheidungslogik und die Verdrahtung — ohne echtes GL, ohne
echten Kindprozess (der Lauf wird durch eine Attrappe ersetzt).
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from src.ui.visualizer import webgl_probe as W


@pytest.fixture(autouse=True)
def _frisch(monkeypatch):
    W._zuruecksetzen_fuer_test()
    monkeypatch.delenv("LIGHTOS_3D_ERZWINGEN", raising=False)
    yield
    W._zuruecksetzen_fuer_test()


def _attrappe(antworten, aufrufe=None):
    """Ersetzt subprocess.run: je Aufruf (rc, stdout) aus ``antworten``."""
    it = iter(antworten)

    def run(cmd, **kw):
        if aufrufe is not None:
            aufrufe.append(kw["env"]["QTWEBENGINE_CHROMIUM_FLAGS"])
        assert kw.get("encoding") == "utf-8" and kw.get("errors") == "replace"
        rc, out = next(it)
        return SimpleNamespace(returncode=rc, stdout=out)
    return run


# ── bewerte ────────────────────────────────────────────────────────────────
def test_bewerte_ok_nogl_absturz_zeit():
    assert W.bewerte(0, "x\nLIGHTOS_WEBGL=ok\n") == "ok"
    assert W.bewerte(0, "LIGHTOS_WEBGL=nogl") == "nogl"
    assert W.bewerte(-signal.SIGSEGV, "") == "absturz"
    # Absturz NACH der ok-Zeile ist trotzdem ein Absturz
    assert W.bewerte(-signal.SIGSEGV, "LIGHTOS_WEBGL=ok") == "absturz"
    assert W.bewerte(None, "", True) == "zeit"
    assert W.bewerte(0, "") == "fehler"
    assert W.bewerte(3, "") == "absturz"


# ── entscheide ─────────────────────────────────────────────────────────────
def test_entscheide_normal_software_aus():
    assert W.entscheide("ok", None, {}).modus == "normal"
    e = W.entscheide("nogl", "ok", {})
    assert e.modus == "software" and e.erlaubt and "Software" in e.meldung
    aus = W.entscheide("nogl", "nogl", {})
    assert aus.modus == "aus" and not aus.erlaubt
    assert "2D" in aus.meldung and "WebGL" in aus.meldung
    assert W.entscheide("absturz", "absturz", {}).modus == "aus"
    assert W.entscheide("zeit", "zeit", {}).modus == "aus"


def test_erzwingen_laedt_trotzdem():
    assert W.entscheide("nogl", "nogl", {"LIGHTOS_3D_ERZWINGEN": "1"}).modus == "normal"


def test_probe_noetig_schalter():
    assert W.probe_noetig({}, "linux") is True
    assert W.probe_noetig({"QT_QPA_PLATFORM": "offscreen"}, "linux") is False
    assert W.probe_noetig({}, "win32") is False
    assert W.probe_noetig({"LIGHTOS_3D_PROBE": "0"}, "linux") is False
    assert W.probe_noetig({"LIGHTOS_3D_PROBE": "1", "QT_QPA_PLATFORM": "offscreen"},
                          "win32") is True


# ── pruefen: zwei Stufen ───────────────────────────────────────────────────
def test_pruefen_erst_basis_dann_software():
    flags = []
    run = _attrappe([(0, "LIGHTOS_WEBGL=nogl"), (0, "LIGHTOS_WEBGL=ok")], flags)
    e = W.pruefen(run, {"QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox"})
    assert e.modus == "software"
    assert flags[0] == "--no-sandbox"
    assert flags[1].startswith("--no-sandbox") and W.SOFTWARE_FLAGS in flags[1]


def test_pruefen_basis_ok_kein_zweiter_lauf():
    flags = []
    e = W.pruefen(_attrappe([(0, "LIGHTOS_WEBGL=ok")], flags), {})
    assert e.modus == "normal" and len(flags) == 1


def test_kindprozess_segfault_sperrt_3d():
    run = _attrappe([(-signal.SIGSEGV, ""), (-signal.SIGSEGV, "")])
    e = W.pruefen(run, {})
    assert e.modus == "aus" and "abgestürzt" in e.meldung


# ── vor_3d_start: Flags setzen / sperren ───────────────────────────────────
def test_vor_3d_start_setzt_software_flags_einmal(monkeypatch):
    monkeypatch.setenv("LIGHTOS_3D_PROBE", "1")
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    monkeypatch.setattr(W, "pruefen", lambda *a, **k: W.entscheide("nogl", "ok", {}))
    assert W.vor_3d_start().modus == "software"
    assert W.vor_3d_start().modus == "software"
    f = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"]
    assert f.count("--use-angle=swiftshader") == 1 and f.startswith("--no-sandbox")


def test_vor_3d_start_ohne_probe_normal(monkeypatch):
    monkeypatch.setenv("LIGHTOS_3D_PROBE", "0")
    monkeypatch.setattr(W, "pruefen", lambda *a, **k: pytest.fail("keine Probe"))
    assert W.vor_3d_start().modus == "normal"


# ── Verdrahtung in der Live-View ───────────────────────────────────────────
def test_live_view_bleibt_bei_gesperrtem_3d_in_2d(monkeypatch):
    from src.ui.views.live_view import LiveView
    import src.ui.visualizer.visualizer_view as vv

    monkeypatch.setattr(W, "vor_3d_start",
                        lambda *a, **k: W.entscheide("nogl", "nogl", {}))

    def _nie(*a, **k):
        raise AssertionError("3D-View darf ohne WebGL nicht gebaut werden")
    monkeypatch.setattr(vv, "Visualizer3DView", _nie)

    class _Btn:
        def __init__(self):
            self.c, self.tip = False, ""

        def setChecked(self, v):
            self.c = bool(v)

        def isChecked(self):
            return self.c

        def setToolTip(self, t):
            self.tip = t

    class _Stack:
        current = None

        def setCurrentWidget(self, w):
            self.current = w

    class _Stub:
        _set_view_3d = LiveView._set_view_3d
        _melde_3d_gesperrt = LiveView._melde_3d_gesperrt

        def __init__(self):
            self._btn_view2d, self._btn_view3d = _Btn(), _Btn()
            self._viz3d = None
            self._viz_popout = None
            self._page2d = object()
            self._view_stack = _Stack()
            self._minimap = SimpleNamespace(setVisible=lambda v: None)
            self._btn_minimap = _Btn()
            self._canvas = SimpleNamespace(_reload_positions_safe=lambda: None)
            self.status = []

        def _set_status(self, msg, sticky_sec=4.0):
            self.status.append(msg)

    s = _Stub()
    s._set_view_3d(True)
    assert s._viz3d is None
    assert s._view_stack.current is s._page2d
    assert s._btn_view2d.isChecked() and not s._btn_view3d.isChecked()
    assert any("3D-Ansicht kann" in m for m in s.status)
    assert "WebGL" in s._btn_view3d.tip
