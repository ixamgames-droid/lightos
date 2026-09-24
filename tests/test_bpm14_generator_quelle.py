"""BPM-14: „Im Player laden & als BPM-Quelle nutzen" schaltet ueber den
SourceController — und die Quelle-Liste im Sub-Tab „Erkennung" zieht mit.

Befund (2026-09-16, beim Schreiben der BPM-Anleitung): der Generator-Knopf rief
nur ``get_bpm_manager().use_audio_source(False)``, also an der einen Schaltstelle
aus BPM-09 (``src/ui/bpm_source_controller.py``) vorbei. Die Liste blieb auf
„PC-Audio", der Capture lief weiter, Statuszeile und Zustandswort sprachen von
der alten Quelle.

Abnahme (BACKLOG BPM-14): nach dem Klick zeigt ``_cmb_source`` „Lied-Analyse
(Player)", ``mgr.current_source`` folgt der Timeline, der Capture ist gestoppt
bzw. nicht mehr am Manager; ein doppelter Klick ist EIN Schaltvorgang.

Dazu die Mechanik dahinter: der Controller meldet jeden wirksamen Wechsel an
Abonnenten (``subscribe_change``), die Ansicht spiegelt ihn in die Liste — per
Rueckruf, nicht per Abfrage der Liste im Poll-Timer.
"""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets, destroy_widget  # noqa: E402

_LIED = "bpm14_lied.mp3"          # relativer Name: nie ein echter Nutzerpfad


@pytest.fixture(autouse=True)
def _keine_widget_reste():
    yield
    destroy_all_top_level_widgets(_app)


# ── Fakes (nur die Aufrufe, die Controller und Manager machen) ──────────────────

class _Cap:
    """Capture-Fake: zaehlt Schaltaufrufe; Abonnenten wie der echte Capture."""

    def __init__(self):
        self.calls: list = []
        self.running = False
        self.subscribers: list = []

    def set_source_mode(self, mode, device=None):
        self.calls.append(("set_source_mode", mode, device))

    def subscribe(self, cb):
        if cb not in self.subscribers:
            self.subscribers.append(cb)

    def unsubscribe(self, cb):
        if cb in self.subscribers:
            self.subscribers.remove(cb)

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
    def __init__(self):
        self.calls: list = []
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


class _Det:
    def __init__(self):
        self.calls: list = []

    def set_tempo_hint(self, bpm):
        self.calls.append(("set_tempo_hint", bpm))

    def reset(self):
        self.calls.append(("reset",))


class _Mgr:
    """Manager-Fake: protokolliert, was der Controller am Manager schaltet."""

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
        from src.core.engine.bpm_manager import BpmMode
        if isinstance(mode, str):
            mode = BpmMode.AUTO if mode == "auto" else BpmMode.MANUAL
        self.calls.append(("set_mode", mode.name.lower()))
        self.mode = mode

    def request_bpm(self, bpm, source="audio"):
        self.calls.append(("request_bpm", bpm, source))


class _Player:
    current_track = None


def _clear(*fakes):
    for f in fakes:
        f.calls.clear()


# ── Umgebung ────────────────────────────────────────────────────────────────────

@pytest.fixture
def _prefs(tmp_path, monkeypatch):
    """Einstellungen in tmp: die Ansicht liest und schreibt ``ui_prefs.json``."""
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


@pytest.fixture
def _geraete(monkeypatch):
    """Feste Geraeteliste fuer die Quelle-Liste (unabhaengig vom Rechner)."""
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_input_devices",
                        staticmethod(_Cap.list_input_devices))
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks",
                        staticmethod(_Cap.list_loopback_sinks))


@pytest.fixture
def _player():
    """Echter Player-Singleton (den fuellt der Generator); danach Ausgangszustand."""
    from src.core.audio.media_player import get_media_player
    from src.core.app_state import get_state
    mp = get_media_player()
    vorher = (list(mp.tracks), mp.index, mp.couple_bpm, list(get_state().playlist))
    mp.set_tracks([])
    mp.couple_bpm = True
    yield mp
    tracks, index, couple, playlist = vorher
    mp.set_tracks(tracks)
    mp.index = index
    mp.couple_bpm = couple
    get_state().playlist = playlist


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


def _timeline():
    """Drei Tempo-Abschnitte 120 → 124 → 128 BPM; Median 124."""
    from src.core.audio.offline_timeline import BpmTimeline, BpmSegment
    return BpmTimeline(segments=[BpmSegment(0, 120.0, 0.9), BpmSegment(8000, 124.0, 0.9),
                                 BpmSegment(16000, 128.0, 0.9)],
                       duration_ms=24000, step_ms=8000, window_ms=8000)


def _generator(ctrl, monkeypatch):
    """Generator mit fertiger Analyse; ``get_source_controller()`` liefert ``ctrl``."""
    import src.ui.bpm_source_controller as sc
    monkeypatch.setattr(sc, "_controller", ctrl)
    from src.ui.views.bpm_generator_view import BpmGeneratorView
    g = BpmGeneratorView()
    g._path = _LIED
    g._timeline = _timeline()
    g._btn_use.setEnabled(True)
    return g


def _klick(g):
    g._btn_use.click()
    _app.processEvents()


def _erkennung(ctrl):
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView(source_controller=ctrl)
    v.show()
    _app.processEvents()
    return v


def _waehle(v, data):
    """Nutzer waehlt einen Eintrag der Liste (beide Signale, wie in der echten App)."""
    idx = v._cmb_source.findData(data)
    assert idx >= 0, data
    v._cmb_source.setCurrentIndex(idx)
    v._cmb_source.activated.emit(idx)
    _app.processEvents()


# ── Abnahme ─────────────────────────────────────────────────────────────────────

def test_klick_schaltet_ueber_den_controller_und_die_liste_zieht_mit(
        _prefs, _geraete, _player, _echter_mgr, monkeypatch):
    """Vorher PC-Audio: nach dem Klick steht die Liste auf „Lied-Analyse (Player)",
    der Capture ist gestoppt, das Zustandswort spricht von der Lied-Analyse, die
    Einstellung ist gemerkt. Der zweite Klick schaltet nichts mehr."""
    from src.ui.bpm_source_controller import SourceController
    cap, os2l, det = _Cap(), _Os2l(), _Det()
    mgr = _Mgr(cap)
    ctrl = SourceController(mgr=mgr, cap=cap, os2l=os2l, det=det, player=None)
    v = _erkennung(ctrl)
    g = _generator(ctrl, monkeypatch)
    try:
        _waehle(v, "loopback")
        assert cap.running and mgr.audio_active
        _clear(cap, os2l, det, mgr)

        _klick(g)
        assert v._cmb_source.currentText() == "Lied-Analyse (Player)"
        assert v._cmb_source.currentData() == "song"
        assert ctrl.kind == "song"
        assert cap.calls == [("stop",)] and not cap.running          # Capture gestoppt
        assert [c for c in mgr.calls if c[0] == "use_audio_source"] == [("use_audio_source", False)]
        assert ("request_bpm", 124.0, "timeline") in mgr.calls         # Median des geladenen Lieds
        assert det.calls == [("set_tempo_hint", None), ("reset",)]
        v._refresh_monitor()
        assert v._lbl_state.text() == "LIED-ANALYSE"
        v.flush_pending_save()
        assert _prefs.load_settings()["source"] == "song"

        _clear(cap, os2l, det, mgr)
        _klick(g)                                                       # doppelter Klick
        assert mgr.calls == [] and cap.calls == [] and det.calls == [] and os2l.calls == []
        assert v._cmb_source.currentData() == "song"
    finally:
        destroy_widget(g, _app)
        destroy_widget(v, _app)


def test_current_source_folgt_der_timeline_und_capture_nicht_mehr_am_manager(
        _prefs, _player, _echter_mgr, monkeypatch):
    """Echter Manager, echter Detektor: vorher haengt der Detektor am Capture und
    der Manager am Detektor. Nach dem Klick hoert der Manager nicht mehr zu, der
    Capture steht, und die BPM folgt der Timeline des geladenen Lieds."""
    import src.core.audio.capture as cap_mod
    from src.core.audio.beat_detector import get_beat_detector
    from src.core.audio.music_show import MusicShowDirector
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    mgr, det = _echter_mgr, get_beat_detector()
    ctrl = SourceController(cap=cap, os2l=_Os2l())
    g = _generator(ctrl, monkeypatch)
    try:
        assert ctrl.apply("loopback") is True
        assert mgr.audio_active and cap.running
        assert mgr._on_audio_beat in det._beat_callbacks

        schaltungen = []
        orig_use = mgr.use_audio_source
        monkeypatch.setattr(mgr, "use_audio_source",
                            lambda on: (schaltungen.append(on), orig_use(on))[1])
        orig_reset = det.reset
        monkeypatch.setattr(det, "reset", lambda: (schaltungen.append("reset"), orig_reset())[1])

        _klick(g)
        assert schaltungen == ["reset", False]                   # EIN Schaltvorgang
        assert not mgr.audio_active
        assert mgr._on_audio_beat not in det._beat_callbacks     # nicht mehr am Manager
        assert not cap.running                                   # Capture gestoppt
        assert mgr.current_source == "timeline"
        assert mgr.bpm == pytest.approx(124.0, abs=0.05)         # Median als Start-BPM

        d = MusicShowDirector()
        d._on_position(17000, 24000)
        assert mgr.current_source == "timeline" and mgr.bpm == pytest.approx(128.0, abs=0.05)
        d._on_position(500, 24000)
        assert mgr.current_source == "timeline" and mgr.bpm == pytest.approx(120.0, abs=0.05)

        schaltungen.clear()
        cap.calls.clear()
        _klick(g)                                                 # doppelter Klick
        assert schaltungen == [] and cap.calls == []
        assert mgr.current_source == "timeline" and not mgr.audio_active
    finally:
        destroy_widget(g, _app)


# ── Mechanik: Rueckruf statt Poll ───────────────────────────────────────────────

def test_erkennung_spiegelt_jeden_wechsel_von_aussen(_prefs, _geraete):
    """Nicht nur der Generator: jede Schaltung am Controller, die nicht aus der
    Liste kam, landet in der Liste — ohne dass die Liste selbst erneut schaltet."""
    from src.ui.bpm_source_controller import SourceController
    cap, os2l, det = _Cap(), _Os2l(), _Det()
    ctrl = SourceController(mgr=_Mgr(cap), cap=cap, os2l=os2l, det=det, player=_Player())
    v = _erkennung(ctrl)
    try:
        v._poll.stop()                                   # der Poll darf es nicht sein
        aufrufe = []
        orig = ctrl.apply

        def zaehlend(*a, **k):
            aufrufe.append(a)
            return orig(*a, **k)
        ctrl.apply = zaehlend

        ctrl.apply("os2l")
        assert v._cmb_source.currentData() == "os2l"
        ctrl.apply("input", "Scarlett 2i2")
        assert v._cmb_source.currentText() == "Eingang: Scarlett 2i2"
        ctrl.apply("input", "Weg-Geraet")
        assert v._cmb_source.currentText() == "Eingang: Weg-Geraet (nicht gefunden)"
        ctrl.apply("off")
        assert v._cmb_source.currentData() == "off"
        assert aufrufe == [("os2l",), ("input", "Scarlett 2i2"), ("input", "Weg-Geraet"),
                           ("off",)]                     # die Liste schaltet NICHT nach
        v.flush_pending_save()
        assert _prefs.load_settings()["source"] == "off"
    finally:
        destroy_widget(v, _app)
    assert ctrl._listeners == []                         # abgebaute Ansicht meldet sich ab
    ctrl.apply("song")                                   # und wird nicht mehr gerufen


def test_controller_meldet_jeden_wirksamen_wechsel_genau_einmal(monkeypatch):
    import src.core.audio.capture as cap_mod
    monkeypatch.setattr(cap_mod.AudioCapture, "list_loopback_sinks",
                        staticmethod(_Cap.list_loopback_sinks))
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    ctrl = SourceController(mgr=_Mgr(cap), cap=cap, os2l=_Os2l(), det=_Det(), player=_Player())
    got = []

    def kaputt(_k, _d):
        raise RuntimeError("Abonnent defekt")
    ctrl.subscribe_change(kaputt)                        # blockiert die anderen nicht
    ctrl.subscribe_change(lambda k, d: got.append((k, d)))

    assert ctrl.apply("song") is True
    assert ctrl.apply("song") is False                   # idempotent -> keine Meldung
    assert got == [("song", None)]
    ctrl.apply("loopback")
    assert got[-1] == ("loopback", None)
    # fehlendes Ausgabegeraet: angewandt bleibt der Standard (kein Wechsel), die
    # Liste soll aber den GEWUENSCHTEN Eintrag zeigen -> gemeldet wird ``wanted``
    assert ctrl.apply("loopback", "alsa_output.usb") is False
    assert got[-1] == ("loopback", "alsa_output.usb")
    n = len(got)
    ctrl.reconnect()                                     # erzwungen neu angewandt
    assert len(got) == n + 1 and got[-1] == ("loopback", "alsa_output.usb")

    ctrl.unsubscribe_change(kaputt)
    ctrl.unsubscribe_change(kaputt)                      # doppelt abmelden ist harmlos
    assert len(ctrl._listeners) == 1


# ── Nacharbeit: Audio am Controller vorbei (VC-Aktion „Musik-BPM") ──────────────
#
# Pruefer-Befund zu BPM-14: steht der Controller schon auf „song" und schaltet die
# VC-Aktion AUDIO_BPM (``vc_button``: ``mgr.use_audio_source(not mgr.audio_active)``)
# den Manager am Controller vorbei auf Live-Audio, war ``apply("song")`` idempotent
# und lieferte False — Live-Audio blieb am Manager, ``request_bpm("timeline")`` wurde
# verworfen, und die Statuszeile meldete trotzdem Erfolg. Der alte Knopf
# (``use_audio_source(False)``) deckte das ab. Die Umgehung selbst ist BPM-16.

def test_klick_holt_die_lied_analyse_zurueck_wenn_audio_am_controller_vorbei_lief(
        _prefs, _geraete, _player, _echter_mgr, monkeypatch):
    import src.core.audio.capture as cap_mod
    from src.core.audio.beat_detector import get_beat_detector
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    mgr, det = _echter_mgr, get_beat_detector()
    ctrl = SourceController(cap=cap, os2l=_Os2l())
    v = _erkennung(ctrl)
    g = _generator(ctrl, monkeypatch)
    try:
        assert ctrl.apply("song") is True
        assert v._cmb_source.currentData() == "song"
        mgr.use_audio_source(not mgr.audio_active)        # wie VC-Aktion AUDIO_BPM
        assert mgr.audio_active and cap.running
        assert ctrl.kind == "song"                        # der Controller merkt nichts

        _klick(g)
        assert not mgr.audio_active
        assert mgr._on_audio_beat not in det._beat_callbacks
        assert not cap.running
        assert mgr.current_source == "timeline"
        assert mgr.bpm == pytest.approx(124.0, abs=0.05)
        assert v._cmb_source.currentData() == "song"
        assert g._status.text().startswith("✓")

        schaltungen = []
        orig_use = mgr.use_audio_source
        monkeypatch.setattr(mgr, "use_audio_source",
                            lambda on: (schaltungen.append(on), orig_use(on))[1])
        _klick(g)                                         # danach wieder EIN Vorgang
        assert schaltungen == [] and not mgr.audio_active
    finally:
        destroy_widget(g, _app)
        destroy_widget(v, _app)


@pytest.mark.parametrize("kind", ["song", "os2l", "off"])
def test_nicht_audio_quelle_schaltet_erneut_wenn_der_manager_noch_audio_hoert(kind):
    """Die Idempotenz gilt fuer Nicht-Audio-Quellen nur, solange der Manager
    wirklich kein Live-Audio hoert — sonst ist der Eintrag nicht mehr aktiv."""
    from src.ui.bpm_source_controller import SourceController
    cap, os2l, det = _Cap(), _Os2l(), _Det()
    mgr = _Mgr(cap)
    ctrl = SourceController(mgr=mgr, cap=cap, os2l=os2l, det=det, player=_Player())
    got = []
    ctrl.subscribe_change(lambda k, d: got.append((k, d)))
    assert ctrl.apply(kind) is True
    mgr.use_audio_source(True)                            # am Controller vorbei
    assert cap.running
    _clear(cap, os2l, det, mgr)
    got.clear()

    assert ctrl.apply(kind) is True
    assert [c for c in mgr.calls if c[0] == "use_audio_source"] == [("use_audio_source", False)]
    assert not mgr.audio_active and cap.calls == [("stop",)] and not cap.running
    assert det.calls == [("set_tempo_hint", None), ("reset",)]
    assert got == [(kind, None)]

    _clear(cap, os2l, det, mgr)
    assert ctrl.apply(kind) is False                      # danach wieder idempotent
    assert mgr.calls == [] and cap.calls == [] and det.calls == []


def test_audio_quelle_bleibt_idempotent_auch_wenn_der_manager_kein_audio_hoert():
    """Grenze der Nacharbeit, bewusst: fuer PC-Audio/Eingang bleibt es beim alten
    Verhalten. Ein fehlgeschlagener Capture-Start laesst ``audio_active`` auf False;
    ein erneutes Schalten bei jedem doppelt feuernden Signal waere genau der
    S2-Befund (Capture zweimal gestartet). Zurueck geht es ueber Auto
    (``set_auto`` holt ``use_audio_source(True)`` nach) oder „erneut verbinden"."""
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    mgr = _Mgr(cap)
    ctrl = SourceController(mgr=mgr, cap=cap, os2l=_Os2l(), det=_Det(), player=_Player())
    assert ctrl.apply("loopback") is True
    mgr.use_audio_source(False)                           # am Controller vorbei
    _clear(cap, mgr)
    assert ctrl.apply("loopback") is False
    assert mgr.calls == [] and cap.calls == []


# ── Statuszeile des Generators: ehrlich ─────────────────────────────────────────

class _KaputterController:
    def apply(self, *_a, **_k):
        raise RuntimeError("Quelle-Backend fehlt")


def test_statuszeile_meldet_keinen_erfolg_wenn_das_umschalten_scheitert(
        _prefs, _player, monkeypatch):
    g = _generator(_KaputterController(), monkeypatch)
    try:
        _klick(g)
        text = g._status.text()
        assert not text.startswith("✓"), text
        assert "Quelle-Backend fehlt" in text
        assert "Lied-Analyse (Player)" in text                # sagt, was zu tun ist
        assert _player.current_track is not None and _player.current_track.path == _LIED
    finally:
        destroy_widget(g, _app)


@pytest.mark.parametrize("zustand, erwartet", [("manuell", "Manuell"),
                                                 ("eingefroren", "eingefroren")])
def test_statuszeile_nennt_manuell_und_einfrieren(
        zustand, erwartet, _prefs, _player, _echter_mgr, monkeypatch):
    """In Manuell bzw. bei eingefrorenem Tempo folgt die BPM dem Lied NICHT —
    die Statuszeile darf das nicht behaupten."""
    from src.core.engine.bpm_manager import BpmMode
    from src.ui.bpm_source_controller import SourceController
    cap = _Cap()
    ctrl = SourceController(mgr=_Mgr(cap), cap=cap, os2l=_Os2l(), det=_Det(), player=_Player())
    g = _generator(ctrl, monkeypatch)
    try:
        if zustand == "manuell":
            _echter_mgr.set_mode(BpmMode.MANUAL)
        else:
            _echter_mgr.set_locked(True)
        _klick(g)
        text = g._status.text()
        assert erwartet in text, text
        assert "die BPM folgt dem Lied über die Zeit" not in text
    finally:
        _echter_mgr.set_locked(False)
        destroy_widget(g, _app)
