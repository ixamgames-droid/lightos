"""BPM-18: der Menuepunkt „OS2L-Server (Port 1234)" stellt die BPM-Quelle um.

Befund (Nebenbefund zu BPM-14/BPM-16, 2026-09-24, mit Fakes gemessen):
``MainWindow._toggle_os2l_server`` rief ``get_os2l_server().start()``/``stop()``
direkt — dieselbe Fehlerklasse wie BPM-14/BPM-16. (1) Liste auf **OS2L**, Menue
aus → Server steht, ``ctrl.kind`` bleibt ``os2l``, die Liste zeigt weiter OS2L,
und erneutes Waehlen von OS2L war idempotent — der Server blieb aus. (2) Liste
auf **PC-Audio**, Menue an → OS2L-Server und Capture liefen gleichzeitig.

**Entscheidung des Betreibers (2026-09-28):** der Menuepunkt ist die QUELLE, kein
Diagnose-Schalter. an = Quelle OS2L, aus = zurueck zur Quelle davor.

Abnahme (BACKLOG BPM-18): Menue an/aus bei Liste PC-Audio und bei Liste OS2L →
``_cmb_source``, ``ctrl.kind``, Server und Capture passend, je Klick ein
Schaltvorgang; erneutes Waehlen von OS2L startet einen gestoppten Server.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets, destroy_widget  # noqa: E402


@pytest.fixture(autouse=True)
def _keine_widget_reste():
    yield
    destroy_all_top_level_widgets(_app)


# ── Fakes ───────────────────────────────────────────────────────────────────────

class _Cap:
    def __init__(self):
        self.calls: list = []
        self.running = False

    def set_source_mode(self, mode, device=None):
        self.calls.append(("set_source_mode", mode, device))

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def start(self):
        self.calls.append(("start",))
        self.running = True
        return True

    def stop(self):
        self.calls.append(("stop",))
        self.running = False

    def is_running(self):
        return self.running

    def last_error(self):
        return None

    def snapshot(self):
        return None

    @staticmethod
    def list_input_devices():
        return ["Scarlett 2i2"]

    @staticmethod
    def list_loopback_sinks():
        return [("alsa_output.hdmi", "HDMI Audio")]


class _Os2l:
    def __init__(self, startet=True):
        self.calls: list = []
        self.running = False
        self._startet = startet

    def start(self):
        self.calls.append(("start",))
        self.running = self._startet

    def stop(self):
        self.calls.append(("stop",))
        self.running = False

    def is_running(self):
        return self.running

    def last_bpm(self):
        return 0.0


class _Det:
    def set_tempo_hint(self, bpm):
        pass

    def reset(self):
        pass


class _Mgr:
    def __init__(self, cap):
        from src.core.engine.bpm_manager import BpmMode
        self.calls: list = []
        self._cap = cap
        self.mode = BpmMode.AUTO
        self.audio_active = False
        self.bpm = 0.0

    def use_audio_source(self, on):
        self.calls.append(("use_audio_source", on))
        if on:
            self._cap.start()
        self.audio_active = bool(on)

    def set_mode(self, mode):
        self.mode = mode

    def request_bpm(self, bpm, source="audio"):
        pass


# ── Umgebung ────────────────────────────────────────────────────────────────────

@pytest.fixture
def _prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture
def _geraete(monkeypatch):
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices",
                        staticmethod(_Cap.list_input_devices))
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks",
                        staticmethod(_Cap.list_loopback_sinks))


def _ctrl(os2l=None):
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    srv = os2l or _Os2l()
    ctrl = SourceController(mgr=_Mgr(cap), cap=cap, os2l=srv, det=_Det())
    return ctrl, cap, srv


# ── Controller ──────────────────────────────────────────────────────────────────

def test_menue_an_bei_pc_audio_schaltet_auf_os2l(_prefs, _geraete):
    """Befund (2): vorher liefen Server und Capture gleichzeitig."""
    ctrl, cap, srv = _ctrl()
    ctrl.apply("loopback", "alsa_output.hdmi")
    assert cap.running
    srv.calls.clear()
    assert ctrl.toggle_os2l(True) == (True, None)
    assert ctrl.kind == "os2l"
    assert srv.running and srv.calls == [("start",)]          # ein Schaltvorgang
    assert not cap.running                                    # Capture gestoppt
    assert ctrl._manager().audio_active is False


def test_menue_aus_kehrt_zur_quelle_davor_zurueck(_prefs, _geraete):
    """Befund (1): vorher blieb die Quelle auf OS2L stehen, nur der Server ging aus."""
    ctrl, cap, srv = _ctrl()
    ctrl.apply("loopback", "alsa_output.hdmi")
    ctrl.toggle_os2l(True)
    assert ctrl.toggle_os2l(False) == (True, None)
    assert ctrl.wanted == ("loopback", "alsa_output.hdmi")    # samt Geraet
    assert not srv.running
    assert cap.running


def test_menue_aus_ohne_vorgeschichte_nimmt_die_voreinstellung(_prefs, _geraete):
    """Nichts geschaltet, nichts gespeichert: die Voreinstellung (PC-Audio) gilt als
    die Quelle davor — dieselbe Voreinstellung, die BPM-17 fuer „wer fuehrt" nimmt."""
    ctrl, cap, srv = _ctrl()
    ctrl.toggle_os2l(True)
    ctrl.toggle_os2l(False)
    assert ctrl.kind == "loopback" and not srv.running and cap.running


def test_gespeichertes_aus_bleibt_aus(_prefs, _geraete):
    _prefs.save_settings({"source": "off"})
    ctrl, cap, srv = _ctrl()
    ctrl.toggle_os2l(True)
    ctrl.toggle_os2l(False)
    assert ctrl.kind == "off" and not srv.running and not cap.running


def test_gespeicherte_lied_analyse_gilt_als_quelle_davor(_prefs, _geraete):
    """Fuer „Lied-Analyse" schaltet der Auto-Start nichts — trotzdem soll „aus"
    dorthin zurueck und nicht auf „Aus" fallen."""
    _prefs.save_settings({"source": "song"})
    ctrl, cap, srv = _ctrl()
    ctrl.toggle_os2l(True)
    ctrl.toggle_os2l(False)
    assert ctrl.kind == "song"


def test_erneutes_waehlen_startet_gestoppten_server(_prefs, _geraete):
    """DoD: OS2L gewaehlt, Server am Controller vorbei gestoppt → dieselbe Wahl
    startet ihn wieder (vorher idempotent: ``apply`` → False, Server blieb aus)."""
    ctrl, cap, srv = _ctrl()
    ctrl.apply("os2l")
    srv.stop()
    srv.calls.clear()
    assert ctrl.apply("os2l") is True
    assert srv.running and srv.calls == [("start",)]
    assert ctrl.apply("os2l") is False                        # laeuft er, bleibt es idempotent


def test_server_startet_nicht_das_menue_meldet_es(_prefs, _geraete):
    ctrl, cap, srv = _ctrl(os2l=_Os2l(startet=False))
    ok, grund = ctrl.toggle_os2l(True)
    assert ok is False and "1234" in grund


def test_fremd_gestarteter_server_menue_aus_laesst_die_quelle_stehen(_prefs, _geraete):
    """Laeuft der Server, obwohl PC-Audio gewaehlt ist, stoppt „aus" nur ihn."""
    ctrl, cap, srv = _ctrl()
    ctrl.apply("loopback", "alsa_output.hdmi")
    srv.start()
    ctrl.toggle_os2l(False)
    assert not srv.running
    assert ctrl.kind == "loopback" and cap.running


# ── Liste in „Erkennung" und Menue ──────────────────────────────────────────────

def test_liste_in_erkennung_folgt_dem_menue(_prefs, _geraete, monkeypatch):
    import src.ui.bpm_source_controller as sc
    from src.ui.views.bpm_manager_view import BpmManagerView
    ctrl, cap, srv = _ctrl()
    monkeypatch.setattr(sc, "_controller", ctrl)
    ctrl.apply("loopback", "alsa_output.hdmi")
    v = BpmManagerView(source_controller=ctrl)
    v.show()
    _app.processEvents()
    try:
        ctrl.toggle_os2l(True)
        _app.processEvents()
        assert v._cmb_source.currentData() == "os2l"
        ctrl.toggle_os2l(False)
        _app.processEvents()
        assert v._cmb_source.currentData() == "loopback:alsa_output.hdmi"
    finally:
        destroy_widget(v, _app)


class _Aktion:
    def __init__(self):
        self.checked = None

    def setChecked(self, on):
        self.checked = bool(on)


class _Statusleiste:
    def __init__(self):
        self.texte: list = []

    def showMessage(self, text, ms=0):
        self.texte.append(text)


class _Fenster:
    """Nur was ``_toggle_os2l_server`` anfasst — ohne das ganze Hauptfenster."""

    def __init__(self, srv):
        self._act_os2l = _Aktion()
        self._leiste = _Statusleiste()
        self._srv = srv

    def statusBar(self):
        return self._leiste

    def _sync_os2l_action(self):
        self._act_os2l.setChecked(self._srv.is_running())


def test_menuepunkt_schaltet_ueber_den_controller(_prefs, _geraete, monkeypatch):
    import src.ui.bpm_source_controller as sc
    from src.ui.main_window import MainWindow
    ctrl, cap, srv = _ctrl()
    monkeypatch.setattr(sc, "_controller", ctrl)
    ctrl.apply("loopback", "alsa_output.hdmi")
    f = _Fenster(srv)
    MainWindow._toggle_os2l_server(f, True)
    assert ctrl.kind == "os2l" and srv.running and not cap.running
    assert f._act_os2l.checked is True
    MainWindow._toggle_os2l_server(f, False)
    assert ctrl.kind == "loopback" and not srv.running and cap.running
    assert f._act_os2l.checked is False


def test_menuepunkt_zeigt_startfehler(_prefs, _geraete, monkeypatch):
    import src.ui.bpm_source_controller as sc
    import src.ui.main_window as mw
    ctrl, cap, srv = _ctrl(os2l=_Os2l(startet=False))
    monkeypatch.setattr(sc, "_controller", ctrl)
    warnungen = []
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warnungen.append(a[-1])))
    f = _Fenster(srv)
    mw.MainWindow._toggle_os2l_server(f, True)
    assert warnungen and "1234" in warnungen[0]
    assert f._act_os2l.checked is False
