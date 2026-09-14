"""BPM-09 (S4): Wahrheitstabelle Auto | Manuell x Quelle x Lock -> Manager-Zustand.

Vier Backend-Flags (``mode``, ``current_source``, ``_audio_active``,
``is_locked``) haengen an zwei sichtbaren Schaltern (Auto | Manuell, Quelle)
und einem Toggle in Erweitert (Tempo einfrieren). Die Tabelle haelt fest, was
jede Kombination im Manager ergibt (ui_markt Risiko 2). Echter Manager,
echter Controller; AudioCapture.start ist gestubbt (S2-Lehre), OS2L-Server
gestubbt (kein Socket im Test).

Regeln, die die Tabelle festschreibt:
* Die Quelle schaltet ``_audio_active`` (Audio an / sonst aus), NICHT den Modus.
* Auto | Manuell schaltet ``mode``, NICHT die Quelle; in Manuell bleibt der
  Capture aktiv (Erkennung im Hintergrund sichtbar, Rueckweg sofort).
* Lock aendert weder Modus noch Quelle noch ``_audio_active``.
* ``current_source`` folgt dem letzten, der die BPM gesetzt hat: bei Quelle
  „Lied-Analyse" in Auto ``timeline``; in Manuell aendert ein Quellenwechsel
  die Quelle der BPM nicht (``request_bpm`` greift nur in AUTO).
"""
from __future__ import annotations
import itertools

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


class _FakeOs2l:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def is_running(self):
        return self.running

    def last_bpm(self):
        return 0.0


@pytest.fixture
def backend(monkeypatch):
    """Echter Manager + echter Controller; Capture.start/OS2L gestubbt."""
    import src.core.audio.capture as cap_mod
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    from src.core.audio.media_player import get_media_player, Track
    from src.ui.bpm_source_controller import SourceController
    monkeypatch.setattr(cap_mod.AudioCapture, "start", lambda self: False)
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices", staticmethod(lambda: ["Mic"]))
    os2l = _FakeOs2l()
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.use_audio_source(False)
    mgr.set_locked(False)
    mgr.set_mode(BpmMode.AUTO)
    tl = {"v": 2, "duration_ms": 20000, "engine": "builtin", "beats_per_bar": 4,
          "segments": [[0, 128.0, 0.9]], "beats_ms": [0, 469, 938]}
    mp = get_media_player()
    mp.set_tracks([Track(path="song.mp3", title="Test Song", bpm_timeline=tl)])
    ctrl = SourceController(mgr=mgr, cap=cap_mod.get_audio_capture(), os2l=os2l, player=mp)
    yield mgr, ctrl, os2l
    mgr.use_audio_source(False)
    mgr.set_locked(False)
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)
    mp.set_tracks([])
    cap_mod.get_audio_capture().set_source_mode("loopback")


def _pick(v, data):
    """Nutzer waehlt einen Eintrag: Index + ``activated`` (auch fuer denselben Eintrag)."""
    idx = v._cmb_source.findData(data)
    assert idx >= 0, data
    v._cmb_source.setCurrentIndex(idx)
    v._cmb_source.activated.emit(idx)
    _app.processEvents()


def _make(ctrl):
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView(source_controller=ctrl)
    v.show()
    _app.processEvents()
    return v


SOURCES = ("loopback", "input:Mic", "os2l", "song", "off")


def _expected(auto: bool, source: str, lock: bool):
    """Erwartung je Zeile: (mode, _audio_active, os2l_running, current_source)."""
    from src.core.engine.bpm_manager import BpmMode
    kind = source.split(":")[0]
    mode = BpmMode.AUTO if auto else BpmMode.MANUAL
    audio = kind in ("loopback", "input")
    os2l = kind == "os2l"
    if auto and kind == "song":
        src = "timeline"
    elif not auto:
        src = "manual"                      # in Manuell: Tempo per Eingabe gesetzt
    else:
        src = "off"                         # Auto ohne gesetzte BPM (kein Audio im Test)
    return mode, audio, os2l, src


@pytest.mark.parametrize("auto,source,lock", list(itertools.product((True, False), SOURCES, (False, True))))
def test_wahrheitstabelle(backend, _isolated_prefs, auto, source, lock):
    mgr, ctrl, os2l = backend
    v = _make(ctrl)
    try:
        # Startlage: Auto, unbekannte Quelle, kein Lock, keine BPM
        assert v._btn_auto.isChecked()
        if not auto:
            mgr.set_manual_bpm(100.0)       # ein manuelles Tempo, das gehalten wird
            v._btn_manual.setChecked(True)
        _pick(v, source)
        v._btn_lock.setChecked(lock)
        _app.processEvents()

        mode, audio, os2l_running, src = _expected(auto, source, lock)
        assert mgr.mode == mode
        assert mgr._audio_active is audio
        assert os2l.is_running() is os2l_running
        assert mgr.is_locked is lock
        assert mgr.current_source == src
        # Der Controller kennt den Eintrag; ein zweiter Klick auf denselben
        # Eintrag schaltet nichts (idempotent).
        kind, dev = v._parse_source(source)
        assert ctrl.current == (kind, dev)
        assert ctrl.apply(kind, dev) is False
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_manuell_haelt_tempo_auto_uebernimmt_quelle(backend, _isolated_prefs):
    """Auto -> Manuell -> Auto ueber die Knoepfe: Manuell friert den Modus,
    nicht die Quelle; zurueck in Auto laeuft die Audio-Quelle wieder als Treiber."""
    from src.core.engine.bpm_manager import BpmMode
    mgr, ctrl, os2l = backend
    v = _make(ctrl)
    try:
        _pick(v, "loopback")
        assert mgr._audio_active and mgr.mode == BpmMode.AUTO
        v._btn_manual.setChecked(True)
        _app.processEvents()
        assert mgr.mode == BpmMode.MANUAL and mgr._audio_active      # Capture bleibt
        mgr.use_audio_source(False)                                   # z. B. VC-Widget
        v._btn_auto.setChecked(True)
        _app.processEvents()
        assert mgr.mode == BpmMode.AUTO and mgr._audio_active         # wieder Audio
        # Quelle „Lied-Analyse" in Auto: Player-Track treibt (128 BPM Median)
        _pick(v, "song")
        assert not mgr._audio_active and mgr.current_source == "timeline"
        assert abs(mgr.bpm - 128.0) < 1.0
    finally:
        v.hide(); v.deleteLater(); _app.processEvents()


def test_zustandswort_reine_funktion():
    from types import SimpleNamespace as NS
    from src.ui.views.bpm_manager_view import state_word
    assert state_word(True, "loopback", None)[0] == "MANUELL"
    assert state_word(False, "loopback", None)[0] == "KEIN SIGNAL"
    assert state_word(False, "input", NS(state="no_signal", hold_stage=0, bpm=0))[0] == "KEIN SIGNAL"
    assert state_word(False, "input", NS(state="searching", hold_stage=0, bpm=0))[0] == "SUCHT"
    assert state_word(False, "input", NS(state="locked", hold_stage=0, bpm=128))[0] == "EINGERASTET"
    assert state_word(False, "input", NS(state="locked", hold_stage=2, bpm=128.4))[0] == "PAUSE · hält 128"
    assert state_word(False, "os2l", None, os2l_waiting=True)[0].startswith("OS2L · wartet")
    assert state_word(False, "song", None)[0] == "LIED-ANALYSE"
    assert state_word(False, "off", None)[0] == "AUS"
