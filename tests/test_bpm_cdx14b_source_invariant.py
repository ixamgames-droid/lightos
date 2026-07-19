"""CDX-14b: quellen­lose ``set_bpm(bpm>0)``-Aufrufer schliessen die Invariante
``_bpm>0  ⇒  _source != "off"``.

CDX-14 machte ``set_bpm(bpm, source=...)`` atomar, aber drei Aufrufer setzten aus
dem Off-Zustand weiter einen positiven Wert OHNE Quelle → ``_bpm>0`` bei
``_source=='off'`` (der Beat-Timer laeuft, obwohl die UI „aus" zeigt). Sie geben
die Quelle jetzt mit:

  - **chaser** (`_on_start`, audio_triggered-Default-Takt) → ``"manual"`` (fester
    Default, kein gemessener Beat; Modus bleibt AUTO, Audio darf uebernehmen).
  - **os2l** (`_push_bpm_to_manager`-Fallback ohne ``request_bpm``) → ``"os2l"``.
  - **tempo_bus** (Freeze/Unfreeze) sichert die Quelle beim Einfrieren und
    restauriert sie beim Auftauen treu.

Ansatz bewusst OHNE ``request_bpm``/``set_manual_bpm``-Routing — deren
Praezedenz-Guards (MANUAL/Lock/Audio) wuerden das Laufzeitverhalten der Aufrufer
aendern (z. B. koennte der Chaser-Default ploetzlich MANUAL erzwingen, der
OS2L-Fallback von einem Audio-Lock geschluckt werden). ``set_bpm`` mit expliziter
Quelle haelt die Praezedenz identisch. Ergaenzt CDX-14 / A3D-17.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
from src.core.engine.tempo_bus import get_tempo_bus_manager
from src.core.engine.chaser import Chaser


def _fresh_mgr():
    mgr = get_bpm_manager()
    mgr.reset()
    mgr.set_locked(False)
    mgr._audio_active = False
    mgr.set_bounds(60, 200)
    mgr.set_mode(BpmMode.AUTO)
    return mgr


def _invariant_ok(mgr):
    # Kern-Invariante: nie ein positiver Wert bei ausgeschalteter Quelle.
    return not (mgr.bpm > 0 and mgr.current_source == "off")


def test_chaser_audio_default_seed_sets_source():
    mgr = _fresh_mgr()
    assert mgr.bpm == 0.0 and mgr.current_source == "off"    # Off-Zustand
    ch = Chaser("cdx14b")
    ch.audio_triggered = True
    ch.tempo_bus_id = ""            # Bus-Anker-Block ueberspringen -> isoliert
    ch._on_start()                  # enthaelt den 120-BPM-Default-Seed
    assert mgr.bpm == 120.0                       # Default-Takt geseedet
    assert mgr.current_source != "off"            # CDX-14b: Quelle gesetzt
    assert _invariant_ok(mgr), (mgr.bpm, mgr.current_source)
    mgr.reset()


def test_tempo_bus_freeze_unfreeze_preserves_source():
    mgr = _fresh_mgr()
    mgr._audio_active = True
    mgr._apply_detected_bpm(140.0)
    assert mgr.bpm == 140.0 and mgr.current_source == "audio"

    tbm = get_tempo_bus_manager()
    if tbm.is_frozen():             # evtl. Rest-State aus anderem Test aufloesen
        tbm.toggle_freeze()

    assert tbm.toggle_freeze() is True            # einfrieren
    assert mgr.bpm == 0.0 and mgr.current_source == "off"   # konsistent aus
    assert _invariant_ok(mgr)

    assert tbm.toggle_freeze() is False           # auftauen
    assert mgr.bpm == 140.0                        # Wert restauriert
    assert mgr.current_source == "audio"           # CDX-14b: Quelle treu restauriert
    assert _invariant_ok(mgr), (mgr.bpm, mgr.current_source)
    mgr.reset()


def test_os2l_fallback_passes_source(monkeypatch):
    # Der Fallback-Zweig (Manager OHNE request_bpm) muss die Quelle mitgeben.
    import src.core.engine.bpm_manager as bm_mod
    from src.core.audio.os2l import OS2LServer

    class _FakeMgrNoRequest:        # bewusst KEIN request_bpm -> Fallback greift
        def __init__(self):
            self.calls = []

        def set_bpm(self, bpm, source=None):
            self.calls.append((bpm, source))

    fake = _FakeMgrNoRequest()
    # os2l importiert get_bpm_manager im Methodenrumpf aus diesem Modul -> patchbar.
    monkeypatch.setattr(bm_mod, "get_bpm_manager", lambda: fake)
    # _push_bpm_to_manager nutzt self nicht fuer die Manager-Logik.
    OS2LServer._push_bpm_to_manager(object(), 128.0)
    assert fake.calls == [(128.0, "os2l")]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
