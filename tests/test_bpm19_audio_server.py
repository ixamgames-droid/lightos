"""BPM-19: „Paket soundcard oder numpy fehlt" stand auch da, wenn nur der
Audio-Server nicht lief.

``capture.py`` fing beim Import JEDE Ausnahme und setzte nur ``HAS_SOUNDCARD =
False``; die Statuszeile riet dann immer zu ``pip install soundcard numpy``. Das
Paket war aber installiert — PulseAudio/PipeWire (Windows: Audiodienst) lief nur
nicht. Jetzt merkt sich ``capture.AUDIO_FEHLT_GRUND`` die Ursache („paket" bei
``ImportError``, sonst „server"), die View reicht sie als ``MgrState.audio_grund``
weiter und ``_r_audio_fehlt`` meldet je Ursache eine eigene Abhilfe.

Der Frischimport nutzt die Hilfe aus test_audio_capture_import_resilience
(stellt sys.modules UND das Paketattribut wieder her, QA-79) — kein echtes
soundcard, kein Audio-Server wird angefasst.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.ui.bpm_status_rules import MgrState, status_line
from test_audio_capture_import_resilience import _lade_capture_mit_import_fehler
# Gemeinsame Fixtures der View-Tests (Attrappen fuer Capture/Quelle/Recorder).
from test_bpm_view_status import (  # noqa: F401
    _isolated_prefs, _tick, _xplat15_no_leaked_widgets, env,
)

IN = MgrState(kind="input", device_label="USB Audio CODEC", bpm=128.0)


# ── capture.py: Ursache beim Import ─────────────────────────────────────────

@pytest.mark.parametrize("fehler", [
    AssertionError("pulseaudio not ready"),            # realer Linux-Fall
    RuntimeError("Connection refused"),
    OSError("Audiodienst nicht gestartet"),
])
def test_server_fehler_beim_import_heisst_server(fehler):
    modul = _lade_capture_mit_import_fehler(fehler)
    assert modul.HAS_SOUNDCARD is False
    assert modul.AUDIO_FEHLT_GRUND == "server"
    assert type(fehler).__name__ in modul.AUDIO_FEHLT_DETAIL


@pytest.mark.parametrize("fehler", [
    ImportError("No module named 'soundcard'"),
    ModuleNotFoundError("No module named 'cffi'"),
])
def test_fehlendes_paket_heisst_paket(fehler):
    modul = _lade_capture_mit_import_fehler(fehler)
    assert modul.HAS_SOUNDCARD is False
    assert modul.AUDIO_FEHLT_GRUND == "paket"


@pytest.mark.parametrize("fehler", [
    OSError("cannot load library 'pulse': libpulse.so.0: cannot open shared object file"),
    OSError("dlopen() failed to load a library: pulse"),
])
def test_fehlende_bibliothek_heisst_bibliothek(fehler):
    """Review BPM-19: fehlt libpulse0, ist weder pip noch ein Server-Neustart die Abhilfe."""
    modul = _lade_capture_mit_import_fehler(fehler)
    assert modul.AUDIO_FEHLT_GRUND == "bibliothek"


def test_bibliothek_meldung_nennt_libpulse_nicht_pip():
    line = status_line(None, None, replace(IN, audio_available=False, audio_grund="bibliothek"),
                       None, 0)
    text = f"{line.problem} {line.ursache} {line.abhilfe}"
    assert line.key == "audio_bibliothek"
    assert "libpulse0" in text
    assert "pip" not in text


# ── Statuszeile: getrennte Meldung + Abhilfe ────────────────────────────────

def _text(line):
    return f"{line.problem} {line.ursache} {line.abhilfe}"


def test_server_nicht_erreichbar_raet_nicht_zu_pip():
    line = status_line(None, None, replace(IN, audio_available=False, audio_grund="server"), None, 0)
    t = _text(line)
    assert line.key == "audio_server"
    assert "pip" not in t and "soundcard oder numpy" not in t
    assert "Audio-Server" in t
    assert "pactl info" in t and "PipeWire" in t and "Audiodienst" in t


@pytest.mark.parametrize("grund", ["paket", None])
def test_fehlendes_paket_raet_zu_pip(grund):
    line = status_line(None, None, replace(IN, audio_available=False, audio_grund=grund), None, 0)
    assert line.key == "audio_fehlt"
    assert "pip install soundcard numpy" in _text(line)


# ── View: Ursache kommt bis in die sichtbare Zeile ──────────────────────────

def test_view_zeigt_server_meldung(env, monkeypatch):
    import src.core.audio.capture as cap_mod
    make, cap, clock, det = env
    monkeypatch.setattr(cap_mod, "HAS_SOUNDCARD", False)
    monkeypatch.setattr(cap_mod, "AUDIO_FEHLT_GRUND", "server", raising=False)
    v, *_ = make()
    txt = _tick(v, clock, 0.0)
    assert "Audio-Server nicht erreichbar" in txt
    assert "pip install" not in txt


def test_view_zeigt_paket_meldung(env, monkeypatch):
    import src.core.audio.capture as cap_mod
    make, cap, clock, det = env
    monkeypatch.setattr(cap_mod, "HAS_SOUNDCARD", False)
    monkeypatch.setattr(cap_mod, "AUDIO_FEHLT_GRUND", "paket", raising=False)
    v, *_ = make()
    txt = _tick(v, clock, 0.0)
    assert "pip install soundcard numpy" in txt
