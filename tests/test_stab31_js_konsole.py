"""STAB-31: Restpunkte des Diagnose-Logs aus STAB-30.

(2) Die JS-Konsole des Visualizers landet im Log — mit Stufe, Quelle und Zeile,
    gedrosselt, Info nur im Debug. Qts Standard reichte nur Warnungen/Fehler als
    nackte Qt-Meldung durch (ohne Ort, ungedrosselt), ``console.log`` gar nicht.
(3) Bisher stille Stellen schreiben eine ``[still:…]``-Zeile; ihr Verhalten
    (weiterlaufen, Eintrag ueberspringen) bleibt gleich.
"""
from __future__ import annotations

import os
import re
import time
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core import debug_log, diagnose_log   # noqa: E402
from src.ui.visualizer import js_konsole as JK   # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _frisch():
    diagnose_log._still_reset()
    vorher = debug_log.is_enabled()
    debug_log.set_debug(False)
    yield
    debug_log.set_debug(vorher)
    diagnose_log._still_reset()


class _Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _drossel(**kw):
    zeilen: list[str] = []
    uhr = _Uhr()
    w = JK.JsKonsolenWeiterleitung(uhr=uhr, ausgabe=zeilen.append, **kw)
    return w, zeilen, uhr


# ── (2) echte Seite ──────────────────────────────────────────────────────────
def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _warte(app, bedingung, sek=15.0):
    ende = time.monotonic() + sek
    while time.monotonic() < ende and not bedingung():
        app.processEvents()
        time.sleep(0.01)
    return bedingung()


def _weg(obj):
    from PySide6.QtCore import QCoreApplication, QEvent
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _seite_mit(weiterleitung):
    from PySide6.QtCore import QEventLoop, QTimer
    app = _qapp()
    page = JK.KonsolenPage(herkunft="test", weiterleitung=weiterleitung)
    loop = QEventLoop()
    page.loadFinished.connect(lambda _ok: loop.quit())
    page.setHtml("<html><body>probe</body></html>")
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    return app, page


def test_js_fehler_landet_mit_stufe_und_ort_im_log():
    w, zeilen, _ = _drossel()
    app, page = _seite_mit(w)
    try:
        page.runJavaScript("console.error('STAB31-kaputt'); console.warn('STAB31-warn');"
                           " console.log('STAB31-info');")
        assert _warte(app, lambda: len(zeilen) >= 2), zeilen
        _warte(app, lambda: False, 0.3)      # Info haette jetzt auch da sein koennen
        fehler = [z for z in zeilen if "STAB31-kaputt" in z]
        assert fehler and fehler[0].startswith("[viz-js:test] FEHLER "), zeilen
        assert re.search(r"FEHLER \S*:\d+ — STAB31-kaputt", fehler[0]), fehler[0]
        assert any(z.startswith("[viz-js:test] WARNUNG ") and "STAB31-warn" in z
                   for z in zeilen), zeilen
        assert not any("STAB31-info" in z for z in zeilen), "Info nur im Debug"
    finally:
        _weg(page)


def test_js_info_kommt_im_debug():
    debug_log.set_debug(True)
    w, zeilen, _ = _drossel()
    app, page = _seite_mit(w)
    try:
        page.runJavaScript("console.log('STAB31-info-debug');")
        assert _warte(app, lambda: any("STAB31-info-debug" in z for z in zeilen)), zeilen
        assert any(z.startswith("[viz-js:test] INFO ") for z in zeilen)
    finally:
        _weg(page)


def test_js_fehler_im_takt_wird_gedrosselt_auf_echter_seite():
    w, zeilen, _ = _drossel()
    app, page = _seite_mit(w)
    try:
        page.runJavaScript("for (let i = 0; i < 200; i++) console.error('STAB31-flut');"
                           " console.error('STAB31-ende');")
        assert _warte(app, lambda: any("STAB31-ende" in z for z in zeilen)), zeilen
        assert sum("STAB31-flut" in z for z in zeilen) == JK.MAX_GLEICH
    finally:
        _weg(page)


# ── (2) Drossel ──────────────────────────────────────────────────────────────
def test_gleiche_meldung_hoechstens_n_je_fenster_dann_zaehler():
    w, zeilen, uhr = _drossel(max_gleich=3, fenster_s=60)
    for _ in range(10):
        w.melde("FEHLER", "boom", 7, "file:///x/y/bridge.js?v=1")
    assert len(zeilen) == 3
    assert zeilen[0] == "[viz-js:viz] FEHLER bridge.js:7 — boom"
    uhr.t += 61
    w.melde("FEHLER", "boom", 7, "file:///x/y/bridge.js?v=1")
    assert len(zeilen) == 4 and zeilen[-1].endswith("(+7 gleiche unterdrueckt)"), zeilen


def test_andere_meldungen_bleiben_sichtbar_und_gesamtdeckel_greift():
    w, zeilen, uhr = _drossel(max_gleich=2, max_gesamt=5)
    w.melde("FEHLER", "a", 1, "s.js")
    w.melde("FEHLER", "a", 1, "s.js")
    w.melde("FEHLER", "a", 1, "s.js")            # gedrosselt
    w.melde("WARNUNG", "b", 2, "s.js")           # andere Meldung: durch
    assert [z.split(" — ")[1] for z in zeilen] == ["a", "a", "b"]
    for i in range(20):
        w.melde("FEHLER", f"neu{i}", i, "s.js")
    meldungen = [z for z in zeilen if z.startswith("[viz-js:viz]")]
    assert len(meldungen) == 5
    assert sum("zu viele JS-Meldungen" in z for z in zeilen) == 1
    uhr.t += 61
    w.melde("FEHLER", "danach", 1, "s.js")
    assert any("weitere JS-Meldungen im letzten Fenster unterdrueckt" in z for z in zeilen)
    assert zeilen[-1].endswith("— danach")


def test_gpu_zeile_erreicht_systeminfo_auch_gedrosselt(monkeypatch):
    gesehen = []
    monkeypatch.setattr(diagnose_log, "merke_viz_gpu", lambda m: gesehen.append(m) or True)
    w, zeilen, _ = _drossel(max_gleich=1)
    for _ in range(3):
        w.melde("WARNUNG", "[viz] GPU-Tier: high (grund=x, renderer=R, maxTextures=16)", 1, "r.js")
    assert len(gesehen) == 3 and len(zeilen) == 1


def test_lokale_pfade_werden_gekuerzt():
    w, zeilen, _ = _drossel()
    home = os.path.expanduser("~")
    w.melde("FEHLER", f"kann {home}/geheim/x.png nicht laden", 3,
            f"file://{home}/irgendwo/stage_scene.html")
    assert "stage_scene.html:3" in zeilen[0]
    assert "irgendwo" not in zeilen[0]
    if len(home) > 1:
        assert home not in zeilen[0]


def test_beide_visualizer_seiten_bekommen_die_konsolen_seite():
    """Fenster und eingebettete View: die Seite wird direkt nach dem Erzeugen der
    QWebEngineView ersetzt — vor jedem ``.page()``-Zugriff (Profil, WebChannel,
    Absturz-Waechter haengen sonst an der verworfenen Standard-Seite)."""
    for datei, herkunft in (("src/ui/visualizer/visualizer_window.py", "fenster"),
                            ("src/ui/visualizer/visualizer_view.py", "eingebettet")):
        with open(os.path.join(_REPO, datei), encoding="utf-8") as f:
            text = f.read()
        erzeugt = [m.start() for m in re.finditer(r"self\._view = QWebEngineView\(\)", text)]
        assert len(erzeugt) == 1, datei
        aufruf = text.find(f'installiere_js_konsole(self._view, "{herkunft}")')
        assert aufruf > erzeugt[0], datei
        assert ".page()" not in text[erzeugt[0]:aufruf], datei


def test_installieren_ersetzt_die_seite():
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _qapp()
    v = QWebEngineView()
    try:
        page = JK.installiere_js_konsole(v, "test")
        assert isinstance(v.page(), JK.KonsolenPage) and v.page() is page
    finally:
        _weg(v)


# ── (3) stille Stellen ──────────────────────────────────────────────────────
def _lshow(tmp_path, text):
    p = tmp_path / "s31.lshow"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("show.json", text)
    return str(p)


def test_show_laden_meldet_verworfene_eintraege(tmp_path, capsys):
    from src.core.show import show_file
    text = ('{"version": "%s",'
            ' "programmer": {"x": {"dimmer": 1}, "4": [1], "5": {"dimmer": "hell"}},'
            ' "base_levels": {"y": {"dimmer": 1}, "6": 3, "7": {"dimmer": null}},'
            ' "visualizer": {"docks": {"z": "el1"}},'
            ' "live_view": {"positions": {"8": [1]}}}' % show_file.SHOW_VERSION)
    ok, msg = show_file.load_show(_lshow(tmp_path, text))
    assert ok, msg
    out = capsys.readouterr().out
    for erwartet in ("[still:show.programmer] Geraet 'x'",
                     "[still:show.programmer] Geraet 4: kein Objekt",
                     "[still:show.programmer] Geraet 5 dimmer",
                     "[still:show.base_levels] Geraet 'y'",
                     "[still:show.base_levels] Geraet 6: kein Objekt",
                     "[still:show.base_levels] Geraet 7 dimmer",
                     "[still:show.viz_dock] Geraet z",
                     "[still:show.live_position] Geraet 8"):
        assert erwartet in out, (erwartet, out)


def _kaputt(*_a):
    raise RuntimeError("abonnent kaputt")


def test_gm_und_blackout_abonnenten_fehler_werden_gemeldet(capsys):
    from src.core.dmx.output_manager import OutputManager
    om = OutputManager()
    om._gm_callbacks.append(_kaputt)
    om.set_grand_master(0.5)
    assert om.grand_master == 0.5
    om._blackout_callbacks.append(_kaputt)
    om._blackout_melden(vorher=False, erzwingen=True)
    out = capsys.readouterr().out
    assert "[still:dmx.gm_callback] RuntimeError: abonnent kaputt" in out
    assert "[still:dmx.blackout_callback] RuntimeError: abonnent kaputt" in out


def test_ausgangs_nic_unlesbare_einstellungen_werden_gemeldet(monkeypatch, capsys):
    from src.core.dmx import output_iface
    from src.ui.views import programmer_view
    monkeypatch.delenv("LIGHTOS_OUTPUT_IFACE", raising=False)
    monkeypatch.setattr(programmer_view, "_load_prefs", _kaputt)
    assert output_iface.output_interface_ip() is None
    assert "[still:dmx.iface_prefs] Einstellungen unlesbar — RuntimeError" in \
        capsys.readouterr().out


def test_reload_callback_fehler_wird_gemeldet(capsys):
    from src.ui.visualizer.visualizer_service import VisualizerService
    fake = SimpleNamespace(_targets=[], force_full_resync=MagicMock())
    VisualizerService.reload_all_targets(fake, SimpleNamespace(on_reload=_kaputt, active=True))
    fake.force_full_resync.assert_called_once()
    assert "[still:viz.reload_callback] RuntimeError: abonnent kaputt" in capsys.readouterr().out


def test_eingebettete_view_activate_und_push_settings_werden_gemeldet(capsys):
    import src.ui.visualizer.visualizer_view as VV
    import src.ui.visualizer.visualizer_window as VW
    bridge = MagicMock()
    bridge._activate.side_effect = RuntimeError("aktivieren kaputt")
    bridge.push_settings.side_effect = RuntimeError("settings kaputt")
    f = SimpleNamespace(_bridge=bridge, _service=None, _target=None, _view=None,
                        _loaded=True, _btn_labels=None,
                        _state=SimpleNamespace(show_fixture_labels=True),
                        _collect_settings=MagicMock(return_value={}))
    VV.Visualizer3DView.on_shown(f)
    bridge.requestFixtures.assert_called_once_with()      # lief trotzdem weiter
    f._edit_mode = "view"
    VV.Visualizer3DView._on_labels_toggled(f, True)
    out = capsys.readouterr().out
    assert "[still:viz.view_activate] RuntimeError: aktivieren kaputt" in out
    assert "[still:viz.view_push_settings] RuntimeError: settings kaputt" in out
    assert VW is not None
