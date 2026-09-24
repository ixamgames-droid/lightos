"""BPM-16: die VC-Aktion „Musik-BPM" (``ButtonAction.AUDIO_BPM``) schaltet ueber
den SourceController — Quelle-Liste, Capture und OS2L laufen nicht mehr auseinander.

Befund (Nebenbefund zu BPM-14, 2026-09-24): ``vc_button`` rief
``mgr.use_audio_source(not mgr.audio_active)`` direkt am Manager, also an der
einen Schaltstelle aus BPM-09 (``src/ui/bpm_source_controller.py``) vorbei. Die
Liste im Sub-Tab „Erkennung" zeigte weiter die alte Quelle, ein laufender
OS2L-Server blieb an, beim Ausschalten lief der Capture weiter, und der
Controller hielt seinen gemerkten Eintrag fuer aktiv.

Abnahme (BACKLOG BPM-16): Taste an/aus -> ``_cmb_source`` und ``ctrl.kind``
folgen, Capture/OS2L passend, je Druck genau ein Schaltvorgang; das LED-Feedback
(``apc_mk2_feedback``) bleibt richtig. Regel: an = die zuletzt gewaehlte
Audio-Quelle (sonst die gespeicherte, sonst PC-Audio Systemstandard) und Auto
wie bisher; aus = die zuletzt gewaehlte andere Quelle (sonst die gespeicherte,
sonst Aus). Mitgeprueft: „BPM = 0/aus" (``BPMManager.turn_off``).
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
    """Manager-Fake: protokolliert, was Controller und Taste am Manager schalten."""

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


def _schaltungen(mgr) -> list:
    return [c for c in mgr.calls if c[0] == "use_audio_source"]


# ── Umgebung ────────────────────────────────────────────────────────────────────

@pytest.fixture
def _prefs(tmp_path, monkeypatch):
    """Einstellungen in tmp: Ansicht und Controller lesen/schreiben ``ui_prefs.json``."""
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


def _controller(monkeypatch, **backends):
    """Controller mit den gegebenen Backends; ``get_source_controller()`` liefert ihn."""
    import src.ui.bpm_source_controller as sc
    ctrl = sc.SourceController(**backends)
    monkeypatch.setattr(sc, "_controller", ctrl)
    return ctrl


def _fake_controller(monkeypatch):
    cap, os2l, det = _Cap(), _Os2l(), _Det()
    mgr = _Mgr(cap)
    ctrl = _controller(monkeypatch, mgr=mgr, cap=cap, os2l=os2l, det=det, player=_Player())
    return ctrl, mgr, cap, os2l, det


def _taste():
    from src.ui.virtualconsole.vc_button import VCButton, ButtonAction
    b = VCButton("Musik-BPM")
    b.action = ButtonAction.AUDIO_BPM
    return b


def _druck(b):
    """Ein Druck wie in der echten App (Druck + Loslassen)."""
    b._trigger_primary(True)
    b._trigger_primary(False)
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

def test_taste_an_aus_liste_und_controller_folgen(_prefs, _geraete, monkeypatch):
    """Liste auf „Aus": die Taste schaltet PC-Audio ein — die Liste springt mit,
    der Capture laeuft, die Wahl ist gemerkt. Der zweite Druck fuehrt zurueck auf
    „Aus" und stoppt den Capture (vorher lief er weiter). Je Druck EIN Vorgang."""
    ctrl, mgr, cap, os2l, det = _fake_controller(monkeypatch)
    v = _erkennung(ctrl)
    b = _taste()
    try:
        _waehle(v, "off")
        _clear(cap, os2l, det, mgr)

        _druck(b)
        assert v._cmb_source.currentData() == "loopback"
        assert v._cmb_source.currentText() == "PC-Audio (Systemstandard)"
        assert ctrl.kind == "loopback"
        assert _schaltungen(mgr) == [("use_audio_source", True)]
        assert cap.calls == [("set_source_mode", "loopback", None), ("start",)] and cap.running
        assert det.calls == [("set_tempo_hint", None), ("reset",)]      # EIN Wechsel
        assert os2l.calls == []
        v.flush_pending_save()
        assert _prefs.load_settings()["source"] == "loopback"

        _clear(cap, os2l, det, mgr)
        _druck(b)
        assert v._cmb_source.currentData() == "off"
        assert ctrl.kind == "off"
        assert _schaltungen(mgr) == [("use_audio_source", False)]
        assert cap.calls == [("stop",)] and not cap.running             # Capture gestoppt
        assert det.calls == [("set_tempo_hint", None), ("reset",)]
        assert os2l.calls == []
        v.flush_pending_save()
        assert _prefs.load_settings()["source"] == "off"
    finally:
        destroy_widget(b, _app)
        destroy_widget(v, _app)


@pytest.mark.parametrize("vorher", ["os2l", "song"])
def test_taste_kehrt_zur_vorher_gewaehlten_quelle_zurueck(vorher, _prefs, _geraete, monkeypatch):
    """„aus" heisst: zurueck zur zuletzt gewaehlten Nicht-Audio-Quelle. Bei OS2L
    geht der Server beim Einschalten aus und beim Ausschalten wieder an."""
    ctrl, mgr, cap, os2l, det = _fake_controller(monkeypatch)
    v = _erkennung(ctrl)
    b = _taste()
    try:
        _waehle(v, vorher)
        assert os2l.running is (vorher == "os2l")
        _clear(cap, os2l, det, mgr)

        _druck(b)
        assert v._cmb_source.currentData() == "loopback" and ctrl.kind == "loopback"
        assert not os2l.running                                          # OS2L aus
        assert os2l.calls == ([("stop",)] if vorher == "os2l" else [])
        assert cap.running and mgr.audio_active

        _clear(cap, os2l, det, mgr)
        _druck(b)
        assert v._cmb_source.currentData() == vorher and ctrl.kind == vorher
        assert os2l.running is (vorher == "os2l")                        # OS2L wieder an
        assert os2l.calls == ([("start",)] if vorher == "os2l" else [])
        assert not cap.running and not mgr.audio_active
        assert _schaltungen(mgr) == [("use_audio_source", False)]
    finally:
        destroy_widget(b, _app)
        destroy_widget(v, _app)


def test_taste_nimmt_das_zuletzt_gewaehlte_audiogeraet(_prefs, _geraete, monkeypatch):
    """„an" heisst: die zuletzt gewaehlte Audio-Quelle samt Geraet — nicht immer
    PC-Audio. Wer vorher den Eingang hatte, bekommt ihn zurueck."""
    ctrl, mgr, cap, os2l, det = _fake_controller(monkeypatch)
    v = _erkennung(ctrl)
    b = _taste()
    try:
        _waehle(v, "input:Scarlett 2i2")
        _waehle(v, "off")
        _clear(cap, os2l, det, mgr)

        _druck(b)
        assert v._cmb_source.currentText() == "Eingang: Scarlett 2i2"
        assert ctrl.kind == "input" and ctrl.current == ("input", "Scarlett 2i2")
        assert cap.calls[0] == ("set_source_mode", "input", "Scarlett 2i2")
        assert _schaltungen(mgr) == [("use_audio_source", True)]
    finally:
        destroy_widget(b, _app)
        destroy_widget(v, _app)


@pytest.mark.parametrize("gespeichert, erwartet_an, erwartet_aus", [
    ({"source": "song", "device": None}, ("loopback", None), ("song", None)),
    ({"source": "input", "device": "Scarlett 2i2"}, ("input", "Scarlett 2i2"), ("off", None)),
])
def test_ohne_vorgeschichte_gilt_die_gespeicherte_quelle(
        gespeichert, erwartet_an, erwartet_aus, _prefs, monkeypatch):
    """Frischer Start, noch nichts geschaltet (bei „Lied-Analyse"/„Aus" startet der
    Auto-Start nichts): die gespeicherte Quelle zaehlt als zuletzt gewaehlte."""
    _prefs.save_settings({**_prefs.DEFAULTS, **gespeichert})
    ctrl, mgr, cap, os2l, det = _fake_controller(monkeypatch)
    b = _taste()
    try:
        _druck(b)
        assert ctrl.current == erwartet_an and mgr.audio_active
        _druck(b)
        assert ctrl.current == erwartet_aus and not mgr.audio_active
        assert not cap.running
    finally:
        destroy_widget(b, _app)


def test_echter_manager_ein_schaltvorgang_je_druck_und_auto_wie_bisher(
        _prefs, _echter_mgr, monkeypatch):
    """Echter Manager, echter Detektor: „an" haengt den Manager an den Detektor und
    stellt wie bisher auf Auto (sonst folgte die BPM der Musik nicht); „aus" nimmt
    ihn ab UND stoppt den Capture. Je Druck genau ein Umschalten am Manager."""
    import src.core.audio.capture as cap_mod
    from src.core.audio.beat_detector import get_beat_detector
    from src.core.engine.bpm_manager import BpmMode
    cap = _Cap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    mgr, det = _echter_mgr, get_beat_detector()
    ctrl = _controller(monkeypatch, cap=cap, os2l=_Os2l())
    b = _taste()
    try:
        assert ctrl.apply("off") is True
        mgr.set_mode(BpmMode.MANUAL)
        schaltungen = []
        orig_use = mgr.use_audio_source
        monkeypatch.setattr(mgr, "use_audio_source",
                            lambda on: (schaltungen.append(on), orig_use(on))[1])

        _druck(b)
        assert schaltungen == [True]
        assert mgr.audio_active and mgr.mode == BpmMode.AUTO
        assert mgr._on_audio_beat in det._beat_callbacks
        assert cap.running and ctrl.kind == "loopback"

        schaltungen.clear()
        _druck(b)
        assert schaltungen == [False]
        assert not mgr.audio_active
        assert mgr._on_audio_beat not in det._beat_callbacks
        assert not cap.running and ctrl.kind == "off"
    finally:
        destroy_widget(b, _app)


# ── Mitgeprueft: „BPM = 0/aus" (turn_off) ───────────────────────────────────────

def test_bpm_aus_laesst_die_quelle_stehen_und_die_taste_holt_audio_zurueck(
        _prefs, _echter_mgr, monkeypatch):
    """``turn_off`` ist ein Modus-Wechsel (Manuell + BPM 0), kein Quellenwechsel:
    die Quelle bleibt gewaehlt, der Capture laeuft wie in Manuell weiter. Der
    Rueckweg geht ueber den Controller — die Taste schaltet PC-Audio mit EINEM
    Vorgang wieder zu, obwohl derselbe Eintrag schon angewandt ist."""
    import src.core.audio.capture as cap_mod
    from src.core.engine.bpm_manager import BpmMode
    cap = _Cap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    mgr = _echter_mgr
    ctrl = _controller(monkeypatch, cap=cap, os2l=_Os2l())
    b = _taste()
    try:
        assert ctrl.apply("loopback") is True
        mgr.turn_off()
        assert not mgr.audio_active and mgr.mode == BpmMode.MANUAL
        assert ctrl.kind == "loopback" and cap.running                  # Quelle bleibt

        schaltungen = []
        orig_use = mgr.use_audio_source
        monkeypatch.setattr(mgr, "use_audio_source",
                            lambda on: (schaltungen.append(on), orig_use(on))[1])
        _druck(b)
        assert schaltungen == [True]
        assert mgr.audio_active and mgr.mode == BpmMode.AUTO
        assert ctrl.kind == "loopback"
    finally:
        destroy_widget(b, _app)


# ── LED-Feedback (APC mini mk2) ─────────────────────────────────────────────────

class _Canvas:
    def __init__(self, buttons):
        self._buttons = buttons

    def findChildren(self, cls):
        return [w for w in self._buttons if isinstance(w, cls)]


def test_apc_led_folgt_der_taste(_prefs, _echter_mgr, monkeypatch):
    """Das Pad leuchtet hell, solange die Taste Audio eingeschaltet hat, und
    gedimmt danach — unveraendert, nur jetzt ueber den Controller geschaltet."""
    import src.core.audio.capture as cap_mod
    from src.core.midi import apc_mk2_feedback as fbm
    cap = _Cap()
    monkeypatch.setattr(cap_mod, "get_audio_capture", lambda: cap)
    monkeypatch.setattr(fbm.ApcMk2Feedback, "_open", lambda self: False)
    _controller(monkeypatch, cap=cap, os2l=_Os2l())
    b = _taste()
    b.midi_data1 = 20
    b.midi_type = "note_on"
    fb = fbm.ApcMk2Feedback(_Canvas([b]))
    fb._bm = _echter_mgr
    fb._last_beat_time = -100.0                                          # kein Beat-Blitz
    try:
        assert fb._collect_desired(0.0)[20] == (fbm.DIM, fbm.AZURE)
        _druck(b)
        assert fb._collect_desired(0.0)[20] == (fbm.FULL, fbm.AZURE)
        _druck(b)
        assert fb._collect_desired(0.0)[20] == (fbm.DIM, fbm.AZURE)
    finally:
        destroy_widget(b, _app)
