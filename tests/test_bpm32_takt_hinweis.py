"""BPM-32: Die Auto-Show setzt bei BPM-Quelle „Aus"/„OS2L" keinen Titel-Takt mehr.

Entscheidung des Projektinhabers (25.10.2026): Die Wahl der Quelle gilt auch fuer
``MusicShowDirector._ensure_bpm`` (Play, globale Liste, Lied-Look, Trackwechsel).
Statt still die Nominal-BPM des Titels zu setzen, meldet der Director einen
sichtbaren Hinweis mit dem Ein-Klick „Takt aus Titel uebernehmen" (Quelle →
Lied-Analyse, Nominal-BPM als „file"). Bei Lied-Analyse und PC-Audio bleibt der
Fallback unveraendert.
"""
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.audio.music_show import MusicShowDirector

_app = QApplication.instance() or QApplication([])

_REPO = Path(__file__).resolve().parents[1]
_ANLEITUNG = _REPO / "docs" / "anleitung_musik_sync" / "ANLEITUNG_MUSIK_SYNC.md"


# ── Fakes ───────────────────────────────────────────────────────────────────────

class _FakeCtrl:
    """Controller-Fake: gewaehlte Art, ``apply`` merkt sich den Wechsel."""

    def __init__(self, kind):
        self.kind = kind
        self.applied = []
        self._listeners = []

    def chosen_kind(self):
        return self.kind

    def apply(self, kind, device=None, force=False):
        self.applied.append(kind)
        self.kind = kind
        for cb in list(self._listeners):
            cb(kind, device)
        return True

    def subscribe_change(self, cb):
        self._listeners.append(cb)

    def unsubscribe_change(self, cb):
        if cb in self._listeners:
            self._listeners.remove(cb)


def _player(bpm=124.0, ids=(), playing=True):
    track = SimpleNamespace(autoshow_function_ids=list(ids), bpm=bpm, path="a.mp3",
                            title="Beispiel-Titel", bpm_timeline=None)
    return SimpleNamespace(current_track=track, is_playing=playing, couple_bpm=True)


@pytest.fixture
def mgr():
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    m = get_bpm_manager()
    m.use_audio_source(False)
    m.reset()
    m.set_locked(False)
    m.set_mode(BpmMode.AUTO)
    yield m
    # Hinweis-Abos der Wegwerf-Directors wieder abhaengen
    m._bpm_change_callbacks[:] = [
        cb for cb in m._bpm_change_callbacks
        if not isinstance(getattr(cb, "__self__", None), MusicShowDirector)]
    m.use_audio_source(False)
    m.reset()
    m.set_mode(BpmMode.AUTO)


@pytest.fixture
def show(monkeypatch):
    """Eingeschaltete Auto-Show mit einer globalen Funktion."""
    from src.core.app_state import get_state
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    f = fm.new_scene("BPM32-Global")
    f.set_value(1, 1, 255)
    st = get_state()
    st.music_autoshow = {"enabled": True, "function_ids": [f.id], "bank": 0, "slots": {}}
    yield f
    try:
        fm.stop(f.id)
    except Exception:
        pass
    st.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}


def _quelle(monkeypatch, kind):
    import src.ui.bpm_source_controller as sc
    ctrl = _FakeCtrl(kind)
    monkeypatch.setattr(sc, "get_source_controller", lambda: ctrl)
    return ctrl


def _director(monkeypatch, player):
    import src.core.audio.music_show as ms
    d = MusicShowDirector()
    monkeypatch.setattr(ms, "_director", d)
    monkeypatch.setattr("src.core.audio.media_player.get_media_player", lambda: player)
    seen = []
    d.taktHinweisChanged.connect(lambda b: seen.append(b))
    return d, seen


# ── 1. Die Sperre selbst ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,gesperrt", [
    ("off", True), ("os2l", True), ("song", False), ("loopback", False),
    ("input", False), (None, False)])
def test_nominal_fallback_blocked(monkeypatch, kind, gesperrt):
    from src.ui.bpm_source_controller import nominal_fallback_blocked
    _quelle(monkeypatch, kind)
    assert nominal_fallback_blocked() is gesperrt


def test_kaputte_abfrage_sperrt_nicht(monkeypatch):
    import src.ui.bpm_source_controller as sc

    def _kaputt():
        raise RuntimeError("kein Controller")
    monkeypatch.setattr(sc, "get_source_controller", _kaputt)
    assert sc.nominal_fallback_blocked() is False


# ── 2. Play bei Aus/OS2L: kein Takt, Hinweis sichtbar ───────────────────────────

@pytest.mark.parametrize("kind", ["off", "os2l"])
def test_aus_und_os2l_setzen_keinen_takt(monkeypatch, mgr, show, kind):
    _quelle(monkeypatch, kind)
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    assert mgr.bpm == 0.0, "die Auto-Show darf bei dieser Quelle keinen Takt setzen"
    assert d.takt_hinweis() == 124.0
    assert seen == [124.0]
    # die Show selbst startet trotzdem
    from src.core.engine.function_manager import get_function_manager
    assert get_function_manager().is_running(show.id)


def test_lied_look_allein_bei_aus(monkeypatch, mgr):
    """Der BPM-31-Weg (nur Lied-Look) ist ebenso gesperrt."""
    from src.core.app_state import get_state
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    look = fm.new_scene("BPM32-Look")
    look.set_value(1, 3, 255)
    get_state().music_autoshow = {"enabled": True, "function_ids": [], "bank": 0, "slots": {}}
    try:
        _quelle(monkeypatch, "off")
        d, _seen = _director(monkeypatch, _player(118.0, ids=[look.id]))
        d.start_show()
        assert fm.is_running(look.id)
        assert mgr.bpm == 0.0
        assert d.takt_hinweis() == 118.0
    finally:
        fm.stop(look.id)
        get_state().music_autoshow = {"enabled": False, "function_ids": [], "bank": 0,
                                      "slots": {}}


def test_ohne_titel_bpm_bietet_120(monkeypatch, mgr, show):
    _quelle(monkeypatch, "off")
    d, _seen = _director(monkeypatch, _player(0.0))
    d.start_show()
    assert mgr.bpm == 0.0
    assert d.takt_hinweis() == 120.0


# ── 3. Gegenproben: Lied-Analyse / PC-Audio unveraendert ─────────────────────────

@pytest.mark.parametrize("kind", ["song", "loopback", "input"])
def test_andere_quellen_setzen_den_titel_takt(monkeypatch, mgr, show, kind):
    _quelle(monkeypatch, kind)
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    assert mgr.bpm == 124.0
    assert d.takt_hinweis() == 0.0
    assert seen == []


def test_vorhandener_takt_bleibt_und_kein_hinweis(monkeypatch, mgr, show):
    _quelle(monkeypatch, "off")
    mgr.request_bpm(128.0, "os2l")
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    assert mgr.bpm == 128.0
    assert d.takt_hinweis() == 0.0
    assert seen == []


# ── 4. Ein-Klick „Takt aus Titel uebernehmen" ────────────────────────────────────

@pytest.mark.parametrize("kind", ["off", "os2l"])
def test_klick_stellt_quelle_um_und_setzt_bpm(monkeypatch, mgr, show, kind):
    ctrl = _quelle(monkeypatch, kind)
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    assert d.takt_hinweis() == 124.0
    bpm = d.uebernehme_titel_takt()
    assert ctrl.applied == ["song"]
    assert bpm == 124.0 and mgr.bpm == 124.0
    assert mgr._source == "file"
    assert d.takt_hinweis() == 0.0
    assert seen == [124.0, 0.0]


def test_klick_mit_echtem_controller(monkeypatch, mgr, show, tmp_path):
    """Integration: der echte SourceController (Attrappen fuer Capture/OS2L/
    Detektor) steht danach auf „Lied-Analyse"."""
    import src.core.audio.bpm_settings as bs
    import src.ui.bpm_source_controller as sc
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    cap = SimpleNamespace(is_running=lambda: False, stop=lambda: None,
                          set_source_mode=lambda *a, **k: None)
    srv = SimpleNamespace(is_running=lambda: False, start=lambda: None, stop=lambda: None)
    det = SimpleNamespace(set_tempo_hint=lambda h: None, reset=lambda: None)
    player = _player(124.0)
    ctrl = sc.SourceController(mgr=mgr, cap=cap, os2l=srv, det=det, player=player)
    ctrl.apply("off")
    monkeypatch.setattr(sc, "get_source_controller", lambda: ctrl)
    d, _seen = _director(monkeypatch, player)
    d.start_show()
    assert mgr.bpm == 0.0 and d.takt_hinweis() == 124.0
    d.uebernehme_titel_takt()
    assert ctrl.chosen_kind() == "song"
    assert mgr.bpm == 124.0
    assert d.takt_hinweis() == 0.0


# ── 5. Hinweis verschwindet: Takt kommt / Quelle wechselt / Show stoppt ──────────

def test_hinweis_weg_sobald_takt_da(monkeypatch, mgr, show):
    _quelle(monkeypatch, "os2l")
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    d._abo_hinweis()
    mgr.request_bpm(126.0, "os2l")          # DJ-Programm liefert jetzt
    _app.processEvents()
    assert d.takt_hinweis() == 0.0
    assert mgr.bpm == 126.0
    assert seen == [124.0, 0.0]


def test_hinweis_weg_bei_quellenwechsel_und_fallback_greift(monkeypatch, mgr, show):
    ctrl = _quelle(monkeypatch, "off")
    d, _seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    d._abo_hinweis()
    ctrl.apply("song")                      # Wechsel in der Liste „Erkennung"
    _app.processEvents()
    assert d.takt_hinweis() == 0.0
    assert mgr.bpm == 124.0


def test_wechsel_zwischen_gesperrten_quellen_haelt_hinweis(monkeypatch, mgr, show):
    ctrl = _quelle(monkeypatch, "off")
    d, _seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    d._abo_hinweis()
    ctrl.apply("os2l")
    _app.processEvents()
    assert d.takt_hinweis() == 124.0
    assert mgr.bpm == 0.0


def test_stop_nimmt_hinweis_weg(monkeypatch, mgr, show):
    _quelle(monkeypatch, "off")
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    d.stop_show()
    assert d.takt_hinweis() == 0.0
    assert seen == [124.0, 0.0]


def test_bpm_aus_fremdem_thread_landet_im_gui_thread(monkeypatch, mgr, show):
    """OS2L/Audio melden BPM aus eigenen Threads: der Hinweis wird erst im
    GUI-Thread (Ereignisschleife) weggenommen, nie direkt im fremden Thread."""
    _quelle(monkeypatch, "os2l")
    d, seen = _director(monkeypatch, _player(124.0))
    d.start_show()
    d._abo_hinweis()
    threads = []
    d.taktHinweisChanged.connect(lambda _b: threads.append(threading.current_thread()))
    t = threading.Thread(target=lambda: mgr.request_bpm(127.0, "os2l"))
    t.start()
    t.join()
    assert d.takt_hinweis() == 124.0, "noch nicht im GUI-Thread verarbeitet"
    _app.processEvents()
    assert d.takt_hinweis() == 0.0
    assert threads == [threading.main_thread()]


# ── 6. Trackwechsel ──────────────────────────────────────────────────────────────

def test_trackwechsel_bei_aus_setzt_nichts_und_zeigt_neue_bpm(monkeypatch, mgr, show):
    _quelle(monkeypatch, "off")
    player = _player(124.0)
    d, seen = _director(monkeypatch, player)
    d.start_show()
    player.current_track = SimpleNamespace(autoshow_function_ids=[], bpm=132.0,
                                           path="b.mp3", title="B", bpm_timeline=None)
    d._on_track_changed(1)
    assert mgr.bpm == 0.0
    assert d.takt_hinweis() == 132.0
    assert seen == [124.0, 132.0]


def test_trackwechsel_gegenprobe_lied_analyse(monkeypatch, mgr, show):
    _quelle(monkeypatch, "song")
    player = _player(124.0)
    d, _seen = _director(monkeypatch, player)
    mgr.reset()
    player.current_track = SimpleNamespace(autoshow_function_ids=[], bpm=132.0,
                                           path="b.mp3", title="B", bpm_timeline=None)
    d._on_track_changed(1)
    assert mgr.bpm == 132.0
    assert d.takt_hinweis() == 0.0


# ── 7. Sichtbar: Musik-Tab und VC-Musik-Anzeige ─────────────────────────────────

@pytest.fixture
def echter_player():
    """Der echte MediaPlayer mit einem Platzhalter-Titel (spielt nie)."""
    from src.core.audio.media_player import get_media_player, Track
    mp = get_media_player()
    alt = list(mp.tracks)
    mp.set_tracks([Track(path="Musik/Beispiel-Titel.mp3", title="Beispiel-Titel",
                         bpm=124.0)])
    mp.index = 0
    yield mp
    mp.set_tracks(alt)


def _director_echt(monkeypatch):
    import src.core.audio.music_show as ms
    d = MusicShowDirector()
    monkeypatch.setattr(ms, "_director", d)
    return d

def test_musik_tab_zeigt_hinweis_und_klick(monkeypatch, mgr, show, echter_player):
    ctrl = _quelle(monkeypatch, "off")
    d = _director_echt(monkeypatch)
    from src.ui.views.music_view import MusicView
    view = MusicView()
    try:
        assert view._takt_hinweis.isHidden()
        d.start_show()
        assert not view._takt_hinweis.isHidden()
        assert "„Aus“" in view._lbl_takt_hinweis.text()
        assert "Kein Takt" in view._lbl_takt_hinweis.text()
        assert view._btn_takt_titel.text() == "Takt aus Titel übernehmen (124 BPM)"
        view._btn_takt_titel.click()
        assert ctrl.kind == "song"
        assert mgr.bpm == 124.0
        assert view._takt_hinweis.isHidden()
    finally:
        view.deleteLater()


def test_musik_tab_os2l_text_und_gegenprobe(monkeypatch, mgr, show, echter_player):
    from src.ui.views.music_view import MusicView
    assert "OS2L" in MusicView.takt_hinweis_text("os2l")
    assert "„Aus“" in MusicView.takt_hinweis_text("off")
    _quelle(monkeypatch, "song")
    d = _director_echt(monkeypatch)
    view = MusicView()
    try:
        d.start_show()
        assert view._takt_hinweis.isHidden()
    finally:
        view.deleteLater()


def test_musik_tab_zeigt_bestehenden_hinweis_beim_aufbau(monkeypatch, mgr, show,
                                                         echter_player):
    _quelle(monkeypatch, "off")
    d = _director_echt(monkeypatch)
    d.start_show()
    from src.ui.views.music_view import MusicView
    view = MusicView()
    try:
        assert not view._takt_hinweis.isHidden()
    finally:
        view.deleteLater()


def test_vc_musik_anzeige_kennt_hinweis(monkeypatch, mgr, show, echter_player):
    _quelle(monkeypatch, "off")
    d = _director_echt(monkeypatch)
    from src.ui.virtualconsole.vc_song_info import VCSongInfo
    w = VCSongInfo()
    try:
        assert w.takt_hinweis() == 0.0
        d.start_show()
        assert w.takt_hinweis() == 124.0
        w.grab()                             # paintEvent mit Hinweiszeile laeuft
        d.stop_show()
        assert w.takt_hinweis() == 0.0
    finally:
        w.deleteLater()


# ── 8. Doku ──────────────────────────────────────────────────────────────────────

def test_anleitung_erklaert_den_hinweis():
    text = _ANLEITUNG.read_text(encoding="utf-8")
    assert "Takt aus Titel übernehmen" in text
    assert "OS2L" in text
