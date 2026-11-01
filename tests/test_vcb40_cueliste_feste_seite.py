"""VCB-40: Die VC-Cue-Liste kann optional eine FESTE Executor-Seite steuern.

Frueher steuerte VCCueList immer den Executor der gerade gewaehlten Seite —
ein Seitenwechsel aenderte still das Ziel. Standard bleibt „folgt der
aktuellen Seite" (alte Shows unveraendert); mit fester Seite aendert ein
Seitenwechsel das Ziel nicht. Die Zielseite steht im Widget."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from src.core.engine.executor import PlaybackEngine
from src.ui.virtualconsole.vc_cuelist import VCCueList

_app = QApplication.instance() or QApplication([])


class _Zustand:
    def __init__(self):
        self.playback_engine = PlaybackEngine(self)


@pytest.fixture
def zustand(monkeypatch):
    z = _Zustand()
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_state", lambda: z)
    return z


class _Stapel:
    """Attrappe eines Cuestacks: merkt sich nur die Transport-Aufrufe."""
    cues: list = []
    current_index = -1

    def __init__(self):
        self.calls = []

    def go(self):
        self.calls.append("go")

    def back(self):
        self.calls.append("back")

    def stop(self):
        self.calls.append("stop")


def _liste(**kw):
    w = VCCueList()
    w._refresh_timer.stop()
    for k, v in kw.items():
        setattr(w, k, v)
    return w


def test_standard_folgt_der_aktuellen_seite(zustand):
    pe = zustand.playback_engine
    w = _liste(stack_slot=2)
    assert w._executor() is pe.pages[0][2]
    pe.set_page(4)
    assert w._executor() is pe.pages[4][2]
    w._refresh()
    assert w._target_label.text() == "Ex 3 · Seite 5 (folgt)"


def test_feste_seite_seitenwechsel_aendert_ziel_nicht(zustand):
    pe = zustand.playback_engine
    w = _liste(stack_slot=2)
    w.apply_dict({"caption": "Fest", "stack_slot": 2, "fixed_page": 1})
    assert w._executor() is pe.pages[1][2]
    pe.set_page(6)
    assert w._executor() is pe.pages[1][2]
    w._refresh()
    assert w._target_label.text() == "Ex 3 · Seite 2 (fest)"
    # GO/BACK/STOP treffen die feste Seite, nicht die aktuelle
    fest, aktuell = _Stapel(), _Stapel()
    pe.pages[1][2].stack = fest
    pe.pages[6][2].stack = aktuell
    w._do_go()
    w._do_back()
    w._do_stop()
    assert fest.calls == ["go", "back", "stop"]
    assert aktuell.calls == []


def test_speichern_laden_und_alte_shows():
    w = _liste(stack_slot=1)
    d = w.to_dict()
    assert "fixed_page" not in d  # Standard: Show-Format unveraendert
    w2 = _liste()
    w2.apply_dict(d)
    assert w2.fixed_page is None

    w.fixed_page = 3
    d = w.to_dict()
    assert d["fixed_page"] == 3
    w3 = _liste()
    w3.apply_dict(d)
    assert w3.fixed_page == 3 and w3.stack_slot == 1

    for kaputt in (-1, "2", True, None):
        w4 = _liste()
        w4.apply_dict({"stack_slot": 0, "fixed_page": kaputt})
        assert w4.fixed_page is None


def test_ungueltige_feste_seite_liefert_keinen_executor(zustand):
    w = _liste(stack_slot=0, fixed_page=PlaybackEngine.MAX_PAGES + 3)
    assert w._executor() is None


def test_seitenzahl_passt_zur_engine():
    assert VCCueList.SEITEN == PlaybackEngine.MAX_PAGES


def test_korrupter_stack_slot_bricht_laden_und_anzeige_nicht(zustand):
    """Die Zielzeile darf eine handbearbeitete Show mit kaputtem stack_slot
    nicht zum Absturz bringen (vor VCB-40 lud so eine Show ohne Fehler)."""
    for kaputt in ("2", None, [1]):
        w = _liste()
        w.apply_dict({"caption": "X", "stack_slot": kaputt})
        w._refresh()
        assert "Seite 1 (folgt)" in w._target_label.text()
