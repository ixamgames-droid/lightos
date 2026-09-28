"""BPM-17: die gewaehlte Quelle sperrt die Lied-Analyse.

Befund (Pruefer zu BPM-14, 2026-09-24, mit echtem Manager, Player und
``MusicShowDirector`` nachgemessen): bei Quelle **Aus** bzw. **OS2L** setzte in
Auto ein laufendes analysiertes Lied trotzdem die BPM (128,0 bei Position 17 s,
``current_source`` = ``timeline``), ein Lied ohne Analyse ueber „BPM koppeln"
seine Nominal-BPM (``file``). ``MusicShowDirector._on_position`` prueft nur
``mgr.audio_active``, nicht die gewaehlte Quelle — sein Docstring behauptete
dagegen, die Analyse fuehre nur bei gewaehlter Lied-Analyse. Folge: bei **Aus**
sprachen Statuszeile und Zustandswort von „Erkennung aus", waehrend die BPM dem
Lied folgte; bei **OS2L** schrieben DJ-Programm und Lied-Kurve beide ins Tempo.

**Entscheidung des Betreibers (2026-09-28):** die Quelle-Liste **sperrt** — ein
analysiertes Lied fuehrt nur bei gewaehlter „Lied-Analyse (Player)".

Abnahme (BACKLOG BPM-17): Test mit echtem Director je Quelle-Eintrag
(Aus/OS2L/Lied-Analyse/PC-Audio) gegen die gewaehlte Regel.
"""
from __future__ import annotations

import pytest


# ── Fakes ───────────────────────────────────────────────────────────────────────

class _FakeCtrl:
    """Controller-Fake: liefert genau die gewaehlte Art."""

    def __init__(self, kind):
        self._kind = kind

    def chosen_kind(self):
        return self._kind


class _Cap:
    """Capture-Fake — ohne ihn fasst ``apply`` das echte Audiosystem an (gemessen:
    ``pa_mutex_lock``-Abbruch beim Prozessende, Exit 134 trotz gruener Tests)."""

    running = False

    @staticmethod
    def list_loopback_sinks():
        return [("alsa_output.echt", "Lautsprecher")]

    @staticmethod
    def list_input_devices():
        return ["Mikrofon"]

    def set_source_mode(self, mode, device=None):
        pass

    def subscribe(self, cb):
        pass

    def unsubscribe(self, cb):
        pass

    def start(self):
        self.running = True
        return True

    def stop(self):
        self.running = False

    def is_running(self):
        return self.running


class _Mgr:
    """Manager-Fake: sonst schaltet ``apply`` den ECHTEN Manager, und der holt sich
    sein eigenes Capture — der Grund fuer den ``pa_mutex_lock``-Abbruch."""

    def __init__(self):
        from src.core.engine.bpm_manager import BpmMode
        self.mode = BpmMode.AUTO
        self.audio_active = False
        self.bpm = 0.0

    def use_audio_source(self, on):
        self.audio_active = bool(on)

    def set_mode(self, mode):
        self.mode = mode

    def request_bpm(self, bpm, source="audio"):
        pass


class _Det:
    def set_tempo_hint(self, hint):
        pass

    def reset(self):
        pass


class _Os2l:
    def is_running(self):
        return False

    def start(self):
        pass

    def stop(self):
        pass


class _Track:
    def __init__(self, path="/tmp/lied.mp3", bpm=0.0, timeline=None):
        self.path = path
        self.bpm = bpm
        self.bpm_timeline = timeline


class _Player:
    """Player-Fake fuer den Director (nur was ``_on_position`` anfasst)."""

    def __init__(self, track, couple_bpm=True):
        self.current_track = track
        self.couple_bpm = couple_bpm
        self.is_playing = False


def _timeline_dict():
    """Drei Tempo-Abschnitte 120 → 124 → 128 BPM (wie in test_bpm14_*)."""
    from src.core.audio.offline_timeline import BpmTimeline, BpmSegment
    tl = BpmTimeline(segments=[BpmSegment(0, 120.0, 0.9), BpmSegment(8000, 124.0, 0.9),
                               BpmSegment(16000, 128.0, 0.9)],
                     duration_ms=24000, step_ms=8000, window_ms=8000)
    return tl.to_dict()


# ── Umgebung ────────────────────────────────────────────────────────────────────

@pytest.fixture
def _prefs(tmp_path, monkeypatch):
    """Einstellungen in tmp — ``_seed_memory`` liest sie."""
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture
def _geraete(monkeypatch):
    """Feste Sink-Liste — ``_known_sink`` fragt sonst das echte PulseAudio."""
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks",
                        staticmethod(_Cap.list_loopback_sinks))
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices",
                        staticmethod(_Cap.list_input_devices))


def _controller():
    """Controller mit Attrappen statt echtem Capture/OS2L."""
    from src.ui.bpm_source_controller import SourceController
    return SourceController(mgr=_Mgr(), cap=_Cap(), os2l=_Os2l(), det=_Det())


@pytest.fixture
def _echter_mgr():
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    mgr = get_bpm_manager()
    mgr.use_audio_source(False)
    mgr.reset()
    mgr.set_locked(False)
    mgr.set_mode(BpmMode.AUTO)
    yield mgr
    mgr.use_audio_source(False)
    mgr.reset()
    mgr.set_mode(BpmMode.AUTO)


def _quelle(monkeypatch, kind):
    """``song_may_lead`` soll diese Quelle sehen."""
    import src.ui.bpm_source_controller as sc
    monkeypatch.setattr(sc, "get_source_controller", lambda: _FakeCtrl(kind))


# ── 1. Die Entscheidung selbst: song_may_lead ───────────────────────────────────

def test_lied_fuehrt_nur_bei_gewaehlter_lied_analyse(monkeypatch):
    from src.ui.bpm_source_controller import song_may_lead
    _quelle(monkeypatch, "song")
    assert song_may_lead() is True


@pytest.mark.parametrize("kind", ["off", "os2l", "loopback", "input"])
def test_jede_andere_quelle_sperrt(monkeypatch, kind):
    """Auch ``loopback``/``input``: steht die Liste auf PC-Audio, fuehrt das Lied
    NICHT — selbst wenn der Capture gar nicht laeuft (``audio_active`` False nach
    gescheitertem Start). Genau diese Luecke liess die alte Pruefung offen."""
    from src.ui.bpm_source_controller import song_may_lead
    _quelle(monkeypatch, kind)
    assert song_may_lead() is False


def test_unbekannte_quelle_fuehrt_weiter(monkeypatch):
    """Fail-open: ist gar nichts zu ermitteln, bleibt es beim Verhalten von frueher.
    Die Sperre ist eine Praezisierung, kein Schutzmechanismus — sie darf die
    BPM-Kopplung nicht stumm abschalten, wenn die Abfrage nichts weiss."""
    from src.ui.bpm_source_controller import song_may_lead
    _quelle(monkeypatch, None)
    assert song_may_lead() is True


def test_kaputte_abfrage_fuehrt_weiter(monkeypatch):
    """Dasselbe, wenn der Controller selbst wirft."""
    import src.ui.bpm_source_controller as sc
    from src.ui.bpm_source_controller import song_may_lead

    def _kaputt():
        raise RuntimeError("kein Controller")

    monkeypatch.setattr(sc, "get_source_controller", _kaputt)
    assert song_may_lead() is True


# ── 2. Woher die gewaehlte Quelle kommt: chosen_kind ────────────────────────────

def test_gespeicherte_quelle_zaehlt_wenn_noch_nichts_geschaltet_ist(_prefs):
    """★ Der Fall, der die Sperre sonst zur Regression machen wuerde: fuer
    „Lied-Analyse" und „Aus" schaltet der Auto-Start beim Hochfahren NICHTS. Ohne
    den Rueckgriff auf die gespeicherte Quelle stuende der Controller nach jedem
    Neustart auf „unbekannt" — und die Lied-Analyse wuerde trotz Auswahl fuehren
    oder nicht fuehren, je nach Fail-Richtung."""
    _prefs.save_settings({"source": "song"})
    ctrl = _controller()
    assert ctrl.current is None and ctrl.wanted is None      # noch nichts geschaltet
    assert ctrl.chosen_kind() == "song"


def test_gespeichertes_aus_sperrt_ohne_schaltvorgang(_prefs):
    _prefs.save_settings({"source": "off"})
    ctrl = _controller()
    assert ctrl.chosen_kind() == "off"


def test_geschaltete_quelle_schlaegt_die_gespeicherte(_prefs):
    _prefs.save_settings({"source": "song"})
    ctrl = _controller()
    assert ctrl.apply("off") is True
    assert ctrl.chosen_kind() == "off"


def test_gewuenschte_quelle_schlaegt_die_aufgeloeste(_prefs, _geraete):
    """Massstab ist der WUNSCH: ein gespeichertes, gerade fehlendes Ausgabegeraet
    faellt intern auf den Standard zurueck („(nicht gefunden)", BPM-13) — die
    gewaehlte ART bleibt trotzdem PC-Audio und sperrt."""
    ctrl = _controller()
    ctrl.apply("loopback", "gibt-es-nicht")
    assert ctrl.wanted == ("loopback", "gibt-es-nicht")
    assert ctrl.chosen_kind() == "loopback"


# ── 3. Der echte Director je Quelle-Eintrag (Abnahme) ───────────────────────────

def _director_bei(monkeypatch, kind, mgr):
    """Echter ``MusicShowDirector`` mit analysiertem Lied bei Quelle ``kind``."""
    import src.core.audio.media_player as mp_mod
    from src.core.audio.music_show import MusicShowDirector
    _quelle(monkeypatch, kind)
    track = _Track(timeline=_timeline_dict())
    monkeypatch.setattr(mp_mod, "get_media_player", lambda: _Player(track))
    d = MusicShowDirector()
    d._on_position(17000, 24000)
    return mgr


def test_bei_lied_analyse_fuehrt_das_lied(monkeypatch, _echter_mgr):
    mgr = _director_bei(monkeypatch, "song", _echter_mgr)
    assert mgr.current_source == "timeline"
    assert mgr.bpm == pytest.approx(128.0, abs=0.05)


@pytest.mark.parametrize("kind", ["off", "os2l", "loopback", "input"])
def test_bei_jeder_anderen_quelle_fuehrt_das_lied_nicht(monkeypatch, _echter_mgr, kind):
    """Der gemessene Befund: heute stuende hier 128,0 und ``timeline``."""
    vorher_bpm, vorher_quelle = _echter_mgr.bpm, _echter_mgr.current_source
    mgr = _director_bei(monkeypatch, kind, _echter_mgr)
    assert mgr.current_source == vorher_quelle
    assert mgr.bpm == pytest.approx(vorher_bpm, abs=0.001)


def test_director_fuehrt_weiter_wenn_die_abfrage_kaputt_ist(monkeypatch, _echter_mgr):
    """Fail-open auch hier — und das ist hier besonders wichtig: der ganze Rumpf von
    ``_on_position`` haengt in einem ``except: pass``, ein Importfehler wuerde die
    Kopplung sonst STILL und dauerhaft abschalten."""
    import src.core.audio.media_player as mp_mod
    import src.ui.bpm_source_controller as sc
    from src.core.audio.music_show import MusicShowDirector

    def _kaputt():
        raise RuntimeError("kein Controller")

    monkeypatch.setattr(sc, "get_source_controller", _kaputt)
    track = _Track(timeline=_timeline_dict())
    monkeypatch.setattr(mp_mod, "get_media_player", lambda: _Player(track))
    MusicShowDirector()._on_position(17000, 24000)
    assert _echter_mgr.current_source == "timeline"
    assert _echter_mgr.bpm == pytest.approx(128.0, abs=0.05)


# ── 4. Nominal-BPM ueber „BPM koppeln" (derselbe Vorrang) ───────────────────────

def test_nominal_bpm_nur_bei_lied_analyse(monkeypatch, _echter_mgr):
    """``MediaPlayer._apply_track_bpm`` (Haken „BPM koppeln") folgt derselben Regel —
    sonst fuehrt ein Lied OHNE Analyse bei Quelle „Aus" weiter das Tempo."""
    from src.core.audio.media_player import MediaPlayer

    class _Stub:                                   # die echte Methode, ohne Qt-Aufbau
        couple_bpm = True
        current_track = _Track(bpm=132.0)

    mp = _Stub()

    _quelle(monkeypatch, "off")
    MediaPlayer._apply_track_bpm(mp)
    assert _echter_mgr.current_source != "file"

    _quelle(monkeypatch, "song")
    MediaPlayer._apply_track_bpm(mp)
    assert _echter_mgr.current_source == "file"
    assert _echter_mgr.bpm == pytest.approx(132.0, abs=0.05)
