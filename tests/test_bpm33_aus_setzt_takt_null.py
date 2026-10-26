"""BPM-33: Der Wechsel der BPM-Quelle auf „Aus" setzt den Takt auf 0.

Entscheidung des Projektinhabers (25.10.2026): Eine frische App startet weiter mit
„PC-Audio (Systemstandard)", die sofort einen Takt erkennt. Wird danach auf „Aus"
umgeschaltet, setzt LightOS den Takt auf 0 — Beat-Effekte stehen, und beim Play
zeigt die Auto-Show den BPM-32-Hinweis „Takt aus Titel uebernehmen". Vorher blieb
der alte Takt stehen (gemessen 60 BPM), die Leiste erschien nicht.

Der Test nutzt den echten ``SourceController`` und den echten ``BPMManager``;
nur Capture, OS2L-Server und Detektor sind Fakes.
"""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.audio.music_show import MusicShowDirector

_app = QApplication.instance() or QApplication([])


class _Cap:
    def __init__(self):
        self.running = False

    def set_source_mode(self, mode, device=None):
        pass

    def start(self):
        self.running = True
        return True

    def stop(self):
        self.running = False

    def is_running(self):
        return self.running

    def last_error(self):
        return None

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass


class _Os2l:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def is_running(self):
        return self.running


class _Det:
    def set_tempo_hint(self, bpm):
        pass

    def reset(self):
        pass

    def process_chunk(self, *_a):
        pass

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass


class _Player:
    current_track = None


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture
def mgr():
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    m = get_bpm_manager()
    m.use_audio_source(False)
    m.reset()
    m.set_locked(False)
    m.set_mode(BpmMode.AUTO)
    yield m
    m._bpm_change_callbacks[:] = [
        cb for cb in m._bpm_change_callbacks
        if not isinstance(getattr(cb, "__self__", None), MusicShowDirector)]
    m.use_audio_source(False)
    m.reset()
    m.set_mode(BpmMode.AUTO)


@pytest.fixture
def ctrl(prefs, mgr, monkeypatch):
    import src.ui.bpm_source_controller as sc
    cap, det = _Cap(), _Det()
    # Auch der Manager holt sich Capture/Detektor selbst — nie echtes Audio im Test.
    monkeypatch.setattr("src.core.audio.capture.get_audio_capture", lambda: cap)
    monkeypatch.setattr("src.core.audio.beat_detector.get_beat_detector", lambda: det)
    c = sc.SourceController(mgr=mgr, cap=cap, os2l=_Os2l(), det=det, player=_Player())
    monkeypatch.setattr(sc, "get_source_controller", lambda: c)
    return c


def _pc_audio_mit_takt(ctrl, mgr, bpm=60.0):
    """Wie auf dem Rig: PC-Audio gewaehlt, der Detektor hat einen Takt gesetzt."""
    ctrl.apply("loopback")
    assert mgr.audio_active
    assert mgr.request_bpm(bpm, "audio") is not False
    assert mgr.bpm == bpm


# ── 1. Der Wechsel auf „Aus" ─────────────────────────────────────────────────────

def test_aus_setzt_vorhandenen_takt_auf_null(ctrl, mgr):
    _pc_audio_mit_takt(ctrl, mgr)
    assert ctrl.apply("off") is True
    assert mgr.bpm == 0.0
    assert not mgr.audio_active


def test_aus_laesst_den_modus(ctrl, mgr):
    """``reset`` statt ``turn_off``: der Modus bleibt — sonst fuehrte PC-Audio danach nicht."""
    from src.core.engine.bpm_manager import BpmMode
    _pc_audio_mit_takt(ctrl, mgr)
    ctrl.apply("off")
    assert mgr.mode == BpmMode.AUTO
    ctrl.apply("loopback")
    assert mgr.audio_active
    assert mgr.request_bpm(128.0, "audio") is not False
    assert mgr.bpm == 128.0


def test_von_hand_gesetzter_takt_bleibt(ctrl, mgr):
    """„Manuell + Aus" ist die Arbeitslage fuer Tap/Eingabe: der Takt gehoert
    nicht der Quelle und bleibt (Wahrheitstabelle in test_bpm_view_state_table)."""
    from src.core.engine.bpm_manager import BpmMode
    ctrl.apply("song")
    mgr.set_manual_bpm(140.0)
    ctrl.apply("off")
    assert mgr.bpm == 140.0
    assert mgr.mode == BpmMode.MANUAL


def test_erkannter_takt_nach_manuell_wird_genullt(ctrl, mgr):
    """Auf Manuell gestellt, aber der Takt stammt noch von PC-Audio: „Aus" nullt."""
    from src.core.engine.bpm_manager import BpmMode
    _pc_audio_mit_takt(ctrl, mgr, 60.0)
    mgr.set_mode(BpmMode.MANUAL)
    assert mgr.bpm == 60.0
    ctrl.apply("off")
    assert mgr.bpm == 0.0
    assert mgr.mode == BpmMode.MANUAL


def test_aus_erneut_gewaehlt_ist_idempotent(ctrl, mgr):
    """Steht schon „Aus", nullt ein erneuter Klick einen danach gesetzten Takt nicht."""
    _pc_audio_mit_takt(ctrl, mgr)
    ctrl.apply("off")
    assert mgr.bpm == 0.0
    mgr.request_bpm(100.0, "file")
    assert mgr.bpm == 100.0
    assert ctrl.apply("off") is False
    assert mgr.bpm == 100.0


def test_musik_bpm_taste_aus_nullt(ctrl, mgr):
    """Die VC-Taste „Musik-BPM" schaltet bei „aus" auf die letzte Nicht-Audio-Quelle
    (hier keine → „Aus") — ueber ``apply``, also ebenfalls Takt 0."""
    _pc_audio_mit_takt(ctrl, mgr)
    assert ctrl.toggle_audio() is True
    assert ctrl.kind == "off"
    assert mgr.bpm == 0.0


# ── 2. Play danach: Hinweis sichtbar ────────────────────────────────────────────

def test_play_nach_aus_zeigt_den_hinweis(ctrl, mgr, monkeypatch):
    from src.core.app_state import get_state
    from src.core.engine.function_manager import get_function_manager
    import src.core.audio.music_show as ms
    fm = get_function_manager()
    f = fm.new_scene("BPM33-Global")
    f.set_value(1, 1, 255)
    st = get_state()
    st.music_autoshow = {"enabled": True, "function_ids": [f.id], "bank": 0, "slots": {}}
    track = SimpleNamespace(autoshow_function_ids=[], bpm=124.0, path="a.mp3",
                            title="Beispiel-Titel", bpm_timeline=None)
    player = SimpleNamespace(current_track=track, is_playing=True, couple_bpm=True)
    try:
        _pc_audio_mit_takt(ctrl, mgr)
        ctrl.apply("off")
        d = MusicShowDirector()
        monkeypatch.setattr(ms, "_director", d)
        monkeypatch.setattr("src.core.audio.media_player.get_media_player",
                            lambda: player)
        seen = []
        d.taktHinweisChanged.connect(lambda b: seen.append(b))
        d.start_show()
        assert mgr.bpm == 0.0
        assert d.takt_hinweis() == 124.0
        assert seen == [124.0]
    finally:
        try:
            fm.stop(f.id)
        except Exception:
            pass
        st.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}


# ── 3. Gegenproben ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["song", "os2l", "input"])
def test_andere_quellen_lassen_den_takt(ctrl, mgr, kind):
    _pc_audio_mit_takt(ctrl, mgr, 96.0)
    ctrl.apply(kind)
    assert mgr.bpm == 96.0


def test_vorgabe_frischer_app_bleibt_pc_audio(prefs):
    assert prefs.load_settings()["source"] == "loopback"
    assert prefs.DEFAULTS["source"] == "loopback"
