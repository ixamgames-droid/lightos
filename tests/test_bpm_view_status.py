"""BPM-11 (S6): Statuszeile, Chips und „Eingang 30 s aufnehmen" in der Ansicht „Erkennung".

Fake-Snapshots (Detektor + Capture) und eine gestellte Uhr; der 50-ms-Timer wird
durch direkte ``_refresh_monitor()``-Aufrufe ersetzt. AudioCapture.start ist
No-op (S2-Lehre), der Recorder ist ein Fake — es wird nichts geschrieben.
"""
from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from src.core.audio.level_meter import CaptureSnapshot
from src.core.audio.tempo_tracker import DetectorSnapshot
from src.ui.bpm_source_controller import SourceController

_app = QApplication.instance() or QApplication([])

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(_app)


@pytest.fixture(autouse=True)
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


def _det(**kw):
    base = dict(sample_pos=0, sample_rate=44100, state="locked", hold_stage=0, bpm=128.0,
                bpm_raw=128.0, confidence=0.9, alt_bpm=64.0, alt_score=0.1, tempo_hint=None,
                next_beat_sample=0, beat_latency_ms=0, window_s=6.0, window_filled_s=6.0,
                signal_s=20.0, level_rms_dbfs=-18.0, peak_dbfs=-6.0, clip_1s=0,
                noise_floor_dbfs=-60.0, hum_ratio=0.0, hum_hz=0, dc_offset=0.0, backlog_ms=5.0,
                jitter_ms=2.0, onset_contrast=8.0)
    base.update(kw)
    return DetectorSnapshot(**base)


class FakeCap:
    def __init__(self):
        self.running = True
        self.err = None
        self.snap = CaptureSnapshot(rms_dbfs_300ms=-18.0, rms_dbfs_1s=-18.0, peak_dbfs=-6.0,
                                    peak_hold_dbfs=-6.0, chunk_ms_p95=23.0, dc_offset=0.0012,
                                    chunks=100, running=True)

    def snapshot(self):
        return replace(self.snap, running=self.running)

    def last_error(self):
        return self.err

    def is_running(self):
        return self.running

    def stop(self):
        self.running = False

    def set_source_mode(self, mode, dev=None):
        pass

    @staticmethod
    def list_input_devices():
        return ["USB Audio CODEC"]

    @staticmethod
    def list_loopback_sinks():
        return [("alsa_output.pci", "Built-in Audio")]


class FakeSrc:
    def __init__(self, kind="input", dev="USB Audio CODEC"):
        self._cur = (kind, dev)
        self.calls: list = []
        self.missing_sink = None
        self.octave_result = (True, None)

    @property
    def kind(self):
        return self._cur[0]

    @property
    def current(self):
        return self._cur

    def is_audio(self):
        return self.kind in ("loopback", "input")

    def apply(self, kind, device=None, force=False):
        self.calls.append(("apply", kind, device, force))
        self._cur = (kind, device)
        return True

    def set_auto(self, auto):
        self.calls.append(("set_auto", auto))

    def octave(self, step):
        self.calls.append(("octave", step))
        return self.octave_result

    def octave_target(self, step):
        return 256.0 if step > 0 else 64.0


class FakeRec:
    def __init__(self):
        self.running = False
        self.progress = 0.0
        self.starts: list = []
        self.cancelled = 0
        self.on_finished = None
        self.last_info = None

    def is_running(self):
        return self.running

    def progress_s(self):
        return self.progress

    def start(self, seconds=30):
        if self.running:
            return False
        self.starts.append(seconds)
        self.running = True
        return True

    def cancel(self):
        self.cancelled += 1


@pytest.fixture
def env(monkeypatch):
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "start", lambda self: False)
    cap = FakeCap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    clock = [0.0]
    det = {"snap": _det()}
    made = []

    def make(src=None, rec=None):
        from src.ui.views.bpm_manager_view import BpmManagerView
        src = src if src is not None else FakeSrc()
        rec = rec if rec is not None else FakeRec()
        v = BpmManagerView(source_controller=src, recorder=rec, clock=lambda: clock[0])
        v._snapshot = lambda: det["snap"]
        v.show()
        _app.processEvents()
        v._poll.stop()                     # Uhr ist gestellt: Poll nur von Hand
        made.append(v)
        return v, src, rec

    yield make, cap, clock, det
    for v in made:
        v.hide()
        v.deleteLater()
    _app.processEvents()
    from src.core.engine.bpm_manager import get_bpm_manager
    get_bpm_manager().use_audio_source(False)


def _tick(v, clock, t):
    clock[0] = t
    v._refresh_monitor()
    return v.status_text()


def test_ok_zeile_nie_leer(env):
    make, cap, clock, det = env
    v, *_ = make()
    txt = _tick(v, clock, 0.0)
    assert txt.startswith("Eingerastet — 128 BPM aus Eingang »USB Audio CODEC«")
    assert v.visible_chips() == set()


def test_brumm_statuszeile_und_chip_2s_an_3s_aus(env):
    make, cap, clock, det = env
    v, *_ = make()
    _tick(v, clock, 0.0)
    det["snap"] = _det(state="searching", hum_ratio=0.8, hum_hz=50)
    cap.snap = replace(cap.snap, netz_linie=0.99, netz_hz=50)
    t = 10.0
    while t < 11.95:
        assert _tick(v, clock, t).startswith("Eingerastet")
        assert "BRUMM" not in v.visible_chips()
        t += 0.25
    txt = _tick(v, clock, 12.0)
    assert txt.startswith("Netzbrumm 50 Hz — Brummanteil im Bassband 80 %")
    assert "BRUMM" in v.visible_chips()
    assert 'href="record"' in v._lbl_abhilfe.text()
    assert "#f85149" in v._lbl_problem.styleSheet()          # Problem = rot
    det["snap"] = _det()
    t = 12.25
    while t < 14.95:
        assert _tick(v, clock, t).startswith("Netzbrumm")
        assert "BRUMM" in v.visible_chips()
        t += 0.25
    assert _tick(v, clock, 15.0).startswith("Eingerastet")
    assert "BRUMM" not in v.visible_chips()


def test_clip_chip_neben_meter(env):
    make, cap, clock, det = env
    v, *_ = make()
    cap.snap = replace(cap.snap, clip_chunks_1s=5, clip_samples_1s=40, peak_hold_dbfs=0.0)
    for t in (0.0, 1.0, 2.0):
        _tick(v, clock, t)
    assert v.visible_chips() == {"CLIP"}
    assert v.status_text().startswith("Übersteuert")
    assert v._chips["CLIP"].text() == "CLIP" and v._chips["CLIP"].toolTip()


def test_link_reconnect_ruft_apply_force(env):
    make, cap, clock, det = env
    v, src, _ = make()
    cap.running = False
    _tick(v, clock, 0.0)
    assert v.status_text().startswith("Audio gestoppt")
    assert 'href="reconnect"' in v._lbl_abhilfe.text()
    src.calls.clear()
    v._lbl_abhilfe.linkActivated.emit("reconnect")
    assert src.calls == [("apply", "input", "USB Audio CODEC", True)]


def test_link_record_startet_recorder(env):
    make, cap, clock, det = env
    v, src, rec = make()
    v._lbl_abhilfe.linkActivated.emit("record")
    assert rec.starts == [30]
    assert rec.on_finished is not None


def test_link_record_ohne_quelle_meldet(env):
    make, cap, clock, det = env
    v, src, rec = make(src=FakeSrc("os2l", None))
    v._lbl_abhilfe.linkActivated.emit("record")
    assert rec.starts == []
    assert _tick(v, clock, 0.1).startswith("Aufnahme nicht möglich")


def test_link_range_und_source(env, monkeypatch):
    make, cap, clock, det = env
    v, *_ = make()
    assert not v._advanced.is_expanded()
    v._lbl_abhilfe.linkActivated.emit("range")
    assert v._advanced.is_expanded()
    popups = []
    monkeypatch.setattr(v._cmb_source, "showPopup", lambda: popups.append(1))
    v._lbl_abhilfe.linkActivated.emit("source")
    assert popups == [1]


def test_aufnahme_knopf_fortschritt_und_deaktiviert(env):
    make, cap, clock, det = env
    v, src, rec = make()
    v._advanced.set_expanded(True)
    _tick(v, clock, 0.0)
    assert v._btn_record.isEnabled() and v._btn_record.text() == "Eingang 30 s aufnehmen"
    assert v._btn_record.toolTip()
    v._btn_record.click()
    assert rec.starts == [30]
    rec.progress = 12.4
    _tick(v, clock, 12.0)
    assert v._btn_record.text() == "Aufnahme … 12 s"
    assert v.status_text().startswith("Aufnahme läuft — 12 / 30 s")
    v._btn_record.click()                              # zweiter Klick = abbrechen
    assert rec.cancelled == 1 and rec.starts == [30]
    rec.running = False
    rec.last_info = {"datei": "audio_diag/lightos_eingang_20260914-120000.wav", "dauer_s": 30.0,
                     "abgebrochen": False}
    v._rec_done_sig.emit("/irgendwo/audio_diag/lightos_eingang_20260914-120000.wav")
    _app.processEvents()
    txt = _tick(v, clock, 13.0)
    assert txt == ("Aufnahme gespeichert — audio_diag/lightos_eingang_20260914-120000.wav — "
                   "Datei an Robin/Support schicken")
    assert "/irgendwo" not in txt
    assert v._btn_record.text() == "Eingang 30 s aufnehmen"
    # Capture gestoppt -> Knopf aus
    cap.running = False
    _tick(v, clock, 14.0)
    assert not v._btn_record.isEnabled()


def test_aufnahme_knopf_aus_ohne_audio_quelle(env):
    make, cap, clock, det = env
    v, *_ = make(src=FakeSrc("off", None))
    _tick(v, clock, 0.0)
    assert not v._btn_record.isEnabled()
    assert v.status_text().startswith("Erkennung aus")


class _Mgr:
    def __init__(self, bpm, lo=60.0, hi=200.0):
        from src.core.engine.bpm_manager import BpmMode
        self.mode = BpmMode.AUTO
        self.bpm, self.min_bpm, self.max_bpm = bpm, lo, hi
        self.calls: list = []

    def set_manual_bpm(self, bpm):
        self.calls.append(("set_manual_bpm", bpm))


class _Det:
    def __init__(self):
        self.calls: list = []

    def set_octave_preference(self, step):
        self.calls.append(("set_octave_preference", step))

    def set_tempo_hint(self, bpm):
        pass

    def reset(self):
        pass

    def snapshot(self):
        return _det()


def test_controller_oktave_prueft_tempo_bereich():
    d = _Det()
    ctrl = SourceController(mgr=_Mgr(128.0), det=d)
    ok, grund = ctrl.octave(+1)
    assert ok is False and "200" in grund and d.calls == []
    assert ctrl.octave(-1) == (True, None) and d.calls == [("set_octave_preference", -1)]
    ctrl2 = SourceController(mgr=_Mgr(40.0), det=d)
    d.calls.clear()
    assert ctrl2.octave(-1)[0] is False and d.calls == []
    # Manuell: unveraendert (Manager klemmt selbst)
    from src.core.engine.bpm_manager import BpmMode
    m = _Mgr(128.0)
    m.mode = BpmMode.MANUAL
    assert SourceController(mgr=m, det=d).octave(+1) == (True, None)
    assert m.calls == [("set_manual_bpm", 256.0)]


def test_x2_ausserhalb_bereich_statuszeile_nennt_bereich(env):
    make, cap, clock, det = env
    from src.core.engine.bpm_manager import get_bpm_manager
    real = get_bpm_manager()
    d = _Det()
    ctrl = SourceController(mgr=_Mgr(128.0, real.min_bpm, real.max_bpm), det=d)
    ctrl._current = ("input", "USB Audio CODEC")
    v, *_ = make(src=ctrl)
    clock[0] = 5.0
    v._btn_double.click()
    assert d.calls == []                                       # kein set_octave_preference
    txt = v.status_text()
    assert txt.startswith("×2 nicht möglich")
    assert f"{real.max_bpm:.0f}" in txt and "Tempo-Bereich" in txt
    assert 'href="range"' in v._lbl_abhilfe.text()
    assert _tick(v, clock, 7.9).startswith("×2 nicht möglich")
    assert _tick(v, clock, 8.1).startswith("Eingerastet")      # ~3 s


def test_x2_im_bereich_unveraendert(env):
    make, cap, clock, det = env
    d = _Det()
    ctrl = SourceController(mgr=_Mgr(90.0, 60.0, 200.0), det=d)
    ctrl._current = ("input", "USB Audio CODEC")
    v, *_ = make(src=ctrl)
    v._btn_double.click()
    assert d.calls == [("set_octave_preference", 1)]
    assert not v.status_text().startswith("×2")


def test_fehlender_sink_statuszeile(env, monkeypatch):
    make, cap, clock, det = env
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks", staticmethod(FakeCap.list_loopback_sinks))
    ctrl = SourceController(mgr=_Mgr(128.0), cap=cap, det=_Det())
    ctrl._manager().use_audio_source = lambda on: None
    ctrl._manager().set_mode = lambda m: None
    ctrl._os2l = type("O", (), {"is_running": lambda self: False})()
    assert ctrl.apply("loopback", "alsa_output.usb-weg") is True
    assert ctrl.missing_sink == "alsa_output.usb-weg"
    v, *_ = make(src=ctrl)
    txt = _tick(v, clock, 0.0)
    assert txt.startswith("Ausgabegerät nicht gefunden") and "Standardausgabe" in txt
    assert ctrl.apply("loopback", "alsa_output.pci") is True
    assert ctrl.missing_sink is None


def test_diagnosezeile_zeigt_dc_und_chunk_p95(env):
    make, cap, clock, det = env
    v, *_ = make()
    v._advanced.set_expanded(True)
    _tick(v, clock, 0.0)
    assert "DC (Eingang) +0.0012" in v._lbl_diag.text()
    assert "Chunk p95 23 ms" in v._lbl_diag.text()


def test_systemstandard_eintrag_alte_einstellung_passt(env, _isolated_prefs, monkeypatch):
    make, cap, clock, det = env
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks", staticmethod(FakeCap.list_loopback_sinks))
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices", staticmethod(FakeCap.list_input_devices))
    _isolated_prefs.save_settings({"source": "loopback", "device": None})
    v, *_ = make(src=FakeSrc("loopback", None))
    assert v._cmb_source.currentData() == "loopback"
    assert v._cmb_source.currentText() == "PC-Audio (Systemstandard)"
    texts = [v._cmb_source.itemText(i) for i in range(v._cmb_source.count())]
    assert texts.count("PC-Audio (Systemstandard)") == 1 and "PC-Audio" not in texts
