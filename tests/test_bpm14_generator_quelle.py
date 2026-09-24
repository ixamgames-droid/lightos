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


def _erkennung(ctrl):
    from src.ui.views.bpm_manager_view import BpmManagerView
    v = BpmManagerView(source_controller=ctrl)
    v.show()
    _app.processEvents()
    return v


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
