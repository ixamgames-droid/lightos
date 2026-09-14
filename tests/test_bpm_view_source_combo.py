"""BPM-09 (S4): Quelle-Combo -> SourceController -> Fake-Capture/-OS2L/-Manager.

Jeder Eintrag der Combo loest genau die Aufrufe aus, die
``src/ui/bpm_source_controller.py`` im Modulkopf tabelliert; ein doppelter
Aufruf desselben Eintrags schaltet nichts ein zweites Mal (S2-Befund: der
Radio-Wechsel feuerte doppelt und startete den Capture zweimal). Bei jedem
Wechsel: ``det.set_tempo_hint(None)`` + ``det.reset()``.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


class _Log:
    def __init__(self):
        self.calls: list = []


class _Cap(_Log):
    def __init__(self):
        super().__init__()
        self.running = False
        self.source_mode = "loopback"

    def set_source_mode(self, mode, device=None):
        self.calls.append(("set_source_mode", mode, device))
        self.source_mode = mode

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

    @staticmethod
    def list_input_devices():
        return ["USB Audio CODEC Analog Stereo", "Scarlett 2i2"]

    @staticmethod
    def list_loopback_sinks():
        return [("alsa_output.pci.analog-stereo", "Built-in Audio Analog Stereo"),
                ("alsa_output.hdmi", "HDMI Audio")]


class _Os2l(_Log):
    def __init__(self):
        super().__init__()
        self.running = False

    def start(self):
        self.calls.append(("start",))
        self.running = True

    def stop(self):
        self.calls.append(("stop",))
        self.running = False

    def is_running(self):
        return self.running

    def last_bpm(self):
        return 0.0


class _Det(_Log):
    def set_tempo_hint(self, bpm):
        self.calls.append(("set_tempo_hint", bpm))

    def reset(self):
        self.calls.append(("reset",))

    def set_octave_preference(self, step):
        self.calls.append(("set_octave_preference", step))


class _Mgr(_Log):
    """Manager-Fake: nur die Aufrufe, die der Controller macht."""

    def __init__(self, cap):
        super().__init__()
        from src.core.engine.bpm_manager import BpmMode
        self._cap = cap
        self.mode = BpmMode.AUTO
        self.audio_active = False
        self.bpm = 0.0

    def use_audio_source(self, on):
        self.calls.append(("use_audio_source", on))
        if on:
            self._cap.start()
            from src.core.engine.bpm_manager import BpmMode
            self.mode = BpmMode.AUTO
        self.audio_active = bool(on)

    def set_mode(self, mode):
        from src.core.engine.bpm_manager import BpmMode
        if isinstance(mode, str):
            mode = BpmMode.AUTO if mode == "auto" else BpmMode.MANUAL
        self.calls.append(("set_mode", mode.name.lower()))
        self.mode = mode

    def request_bpm(self, bpm, source="audio"):
        self.calls.append(("request_bpm", bpm, source))

    def set_manual_bpm(self, bpm):
        self.calls.append(("set_manual_bpm", bpm))
        self.bpm = bpm


class _Player:
    current_track = None


@pytest.fixture
def fakes():
    from src.ui.bpm_source_controller import SourceController
    cap, os2l, det = _Cap(), _Os2l(), _Det()
    mgr = _Mgr(cap)
    ctrl = SourceController(mgr=mgr, cap=cap, os2l=os2l, det=det, player=_Player())
    return ctrl, cap, os2l, det, mgr


def _clear(*logs):
    for l in logs:
        l.calls.clear()


def _make(ctrl, monkeypatch):
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices", staticmethod(_Cap.list_input_devices))
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks", staticmethod(_Cap.list_loopback_sinks))
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView(source_controller=ctrl)
    v.show()
    _app.processEvents()
    return v


def _select(v, data):
    """Nutzer waehlt einen Eintrag: currentIndexChanged (bei Wechsel) + activated
    (immer) — beide Signale, ein Schaltvorgang (Controller idempotent)."""
    idx = v._cmb_source.findData(data)
    assert idx >= 0, data
    v._cmb_source.setCurrentIndex(idx)
    v._cmb_source.activated.emit(idx)
    _app.processEvents()


def test_combo_eintraege(fakes, _isolated_prefs, monkeypatch):
    ctrl = fakes[0]
    v = _make(ctrl, monkeypatch)
    try:
        items = [(v._cmb_source.itemText(i), v._cmb_source.itemData(i)) for i in range(v._cmb_source.count())]
        assert items == [
            ("PC-Audio (Systemstandard)", "loopback"),
            ("PC-Audio: Built-in Audio Analog Stereo", "loopback:alsa_output.pci.analog-stereo"),
            ("PC-Audio: HDMI Audio", "loopback:alsa_output.hdmi"),
            ("Eingang: USB Audio CODEC Analog Stereo", "input:USB Audio CODEC Analog Stereo"),
            ("Eingang: Scarlett 2i2", "input:Scarlett 2i2"),
            ("OS2L (DJ-Software)", "os2l"),
            ("Lied-Analyse (Player)", "song"),
            ("Aus", "off"),
        ]
        assert v._cmb_source.currentData() == "loopback"     # Default-Quelle der Prefs
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_eingang_startet_capture_mit_geraet_und_stoppt_os2l(fakes, _isolated_prefs, monkeypatch):
    ctrl, cap, os2l, det, mgr = fakes
    os2l.running = True
    v = _make(ctrl, monkeypatch)
    try:
        _clear(cap, os2l, det, mgr)
        _select(v, "input:Scarlett 2i2")
        assert det.calls == [("set_tempo_hint", None), ("reset",)]
        assert os2l.calls == [("stop",)]
        assert cap.calls == [("set_source_mode", "input", "Scarlett 2i2"), ("start",)]
        assert mgr.calls == [("use_audio_source", True), ("set_mode", "auto")]
        v.flush_pending_save()
        s = _isolated_prefs.load_settings()
        assert (s["source"], s["device"]) == ("input", "Scarlett 2i2")
        # zweiter Klick auf denselben Eintrag: nichts passiert (idempotent)
        _clear(cap, os2l, det, mgr)
        assert ctrl.apply("input", "Scarlett 2i2") is False
        _select(v, "input:Scarlett 2i2")
        v._on_source_changed()
        assert cap.calls == [] and mgr.calls == [] and det.calls == []
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_pc_audio_ohne_geraet(fakes, _isolated_prefs, monkeypatch):
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        _select(v, "input:Scarlett 2i2")
        _clear(cap, os2l, det, mgr)
        _select(v, "loopback")
        assert cap.calls == [("set_source_mode", "loopback", None), ("start",)]
        assert mgr.calls == [("use_audio_source", True), ("set_mode", "auto")]
        v.flush_pending_save()
        s = _isolated_prefs.load_settings()
        assert (s["source"], s["device"]) == ("loopback", None)
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_pc_audio_je_ausgabegeraet_merkt_sink_id(fakes, _isolated_prefs, monkeypatch):
    """S5: PC-Audio je Sink — die sink_id geht an den Capture und in die
    Einstellungen; nach dem Neustart steht derselbe Eintrag. Ein Mikrofonname als
    Loopback-Geraet wird verworfen (Standard-Ausgabegeraet)."""
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        _clear(cap, os2l, det, mgr)
        _select(v, "loopback:alsa_output.hdmi")
        assert cap.calls == [("set_source_mode", "loopback", "alsa_output.hdmi"), ("start",)]
        v.flush_pending_save()
        s = _isolated_prefs.load_settings()
        assert (s["source"], s["device"]) == ("loopback", "alsa_output.hdmi")
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()
    v2 = _make(ctrl, monkeypatch)                 # „Neustart" der Ansicht
    try:
        assert v2._cmb_source.currentData() == "loopback:alsa_output.hdmi"
    finally:
        v2.hide(); v2.deleteLater(); _app.processEvents()
    _clear(cap, os2l, det, mgr)
    assert ctrl.apply("loopback", "Scarlett 2i2") is True
    assert cap.calls[0] == ("set_source_mode", "loopback", None)


def test_nicht_vorhandener_sink_bleibt_waehlbar(fakes, _isolated_prefs, monkeypatch):
    _isolated_prefs.save_settings({"source": "loopback", "device": "alsa_output.usb"})
    v = _make(fakes[0], monkeypatch)
    try:
        assert v._cmb_source.currentData() == "loopback:alsa_output.usb"
        assert v._cmb_source.currentText() == "PC-Audio: alsa_output.usb (nicht gefunden)"
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_os2l_stoppt_capture_und_startet_server(fakes, _isolated_prefs, monkeypatch):
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        _select(v, "loopback")
        assert cap.is_running()
        _clear(cap, os2l, det, mgr)
        _select(v, "os2l")
        assert det.calls == [("set_tempo_hint", None), ("reset",)]
        assert mgr.calls == [("use_audio_source", False)]
        assert cap.calls == [("stop",)]
        assert os2l.calls == [("start",)]
        _clear(cap, os2l, det, mgr)
        assert ctrl.apply("os2l") is False                    # idempotent
        assert os2l.calls == [] and cap.calls == []
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_song_und_aus_stoppen_alles(fakes, _isolated_prefs, monkeypatch):
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        _select(v, "os2l")
        _clear(cap, os2l, det, mgr)
        _select(v, "song")
        assert mgr.calls == [("use_audio_source", False)]      # kein Track -> kein request_bpm
        assert os2l.calls == [("stop",)] and cap.calls == []   # Capture lief nicht
        _select(v, "loopback")
        _clear(cap, os2l, det, mgr)
        _select(v, "off")
        assert mgr.calls == [("use_audio_source", False)]
        assert cap.calls == [("stop",)] and os2l.calls == []
        assert det.calls == [("set_tempo_hint", None), ("reset",)]
        v.flush_pending_save()
        assert _isolated_prefs.load_settings()["source"] == "off"
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_quellenwechsel_behaelt_manuell(fakes, _isolated_prefs, monkeypatch):
    """Capture haengt an der Quelle, der Modus am Manager (S2-Lehre)."""
    from src.core.engine.bpm_manager import BpmMode
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        mgr.set_mode("manual")
        _clear(cap, os2l, det, mgr)
        _select(v, "input:Scarlett 2i2")
        assert mgr.calls == [("use_audio_source", True), ("set_mode", "manual")]
        assert mgr.mode == BpmMode.MANUAL and mgr.audio_active
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_halb_doppel_je_modus(fakes, _isolated_prefs, monkeypatch):
    from src.core.engine.bpm_manager import BpmMode
    ctrl, cap, os2l, det, mgr = fakes
    v = _make(ctrl, monkeypatch)
    try:
        mgr.mode = BpmMode.AUTO
        v._btn_half.click(); v._btn_double.click()
        assert det.calls[-2:] == [("set_octave_preference", -1), ("set_octave_preference", 1)]
        mgr.mode = BpmMode.MANUAL
        mgr.bpm = 128.0
        _clear(det, mgr)
        v._btn_half.click()
        assert mgr.calls == [("set_manual_bpm", 64.0)]
        v._btn_double.click()
        assert mgr.calls[-1] == ("set_manual_bpm", 128.0)
        assert det.calls == []                                 # in Manuell kein Oktav-Vorzug
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_tap_knopf_ruft_den_helfer(fakes, _isolated_prefs, monkeypatch):
    class _Tap:
        def __init__(self):
            self.n = 0

        def tap(self):
            self.n += 1
            return 0.0
    tap = _Tap()
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices", staticmethod(_Cap.list_input_devices))
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView(source_controller=fakes[0], tap_helper=tap)
    v.show(); _app.processEvents()
    try:
        v._btn_tap.click(); v._btn_tap.click()
        assert tap.n == 2
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_pegelmeter_neben_bpm_zahl_aus_capture_snapshot(fakes, _isolated_prefs, monkeypatch):
    """S5: der 50-ms-Timer speist das Pegelmeter aus ``cap.snapshot()``; bei
    Nicht-Audio-Quellen bleibt es leer. Das Meter sitzt in der Spalte der BPM-Zahl."""
    import src.core.audio.capture as cap_mod
    from src.core.audio.level_meter import CaptureSnapshot
    snap = CaptureSnapshot(rms_dbfs_300ms=-12.0, peak_hold_dbfs=-8.0, chunks=5, running=True)

    class _SnapCap:
        def last_error(self):
            return None

        def snapshot(self):
            return snap
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: _SnapCap())
    ctrl = fakes[0]
    v = _make(ctrl, monkeypatch)
    try:
        assert v._level.parentWidget() is v._lbl_bpm.parentWidget()
        _select(v, "loopback")
        v._refresh_monitor()
        assert v._level._snap is snap and v._level.zone() == "ziel"
        _select(v, "off")
        v._refresh_monitor()
        assert v._level._snap is None and not v._level.active()
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()
