"""BPM-21 — WASAPI-Aussetzer werden gezaehlt; der Recorder-Puffer hat Reserve.

Befund (Sitzung B, Windows-Rig 01.10.2026): der WASAPI-Puffer war genauso
gross wie der Lese-Chunk (1024 Frames, 23 ms). Lief er ueber, meldete soundcard
das nur per ``warnings.warn("data discontinuity in recording")`` auf stderr —
der AUSSETZER-Chip sah es nicht, denn der LevelMeter misst nur
Ankunftsabstaende, und die bleiben nach einem Ueberlauf unauffaellig.

Hier festgehalten:

* ``LevelMeter.luecke()`` zaehlt (gesamt + 10-s-Fenster, Wanduhr) und
  veroeffentlicht sofort einen neuen Snapshot; ``reset()`` leert;
* der Warnungs-Hook ordnet die soundcard-Warnung dem Capture des eigenen
  Threads zu und laesst alle anderen Warnungen unveraendert durch;
* ``_run`` oeffnet den Recorder unter Windows mit Puffer-Reserve
  (> Lese-Chunk), unter Linux NICHT (PulseAudio: blocksize = Fragmentgroesse);
* eine Luecke setzt den Chip JITTER (Anzeige „AUSSETZER") und die Statuszeile.
"""
from __future__ import annotations

import threading
import warnings
from types import SimpleNamespace

import numpy as np

from src.core.audio import capture as C
from src.core.audio.level_meter import LUECKEN_FENSTER_S, CaptureSnapshot, LevelMeter
from src.ui.bpm_status_rules import MgrState, chips, status_line


class _Uhr:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class _SoundcardWarnung(RuntimeWarning):
    """Wie soundcard.mediafoundation.SoundcardRuntimeWarning."""


def _warnen():
    warnings.warn("data discontinuity in recording", _SoundcardWarnung)


# ── LevelMeter ───────────────────────────────────────────────────────────────

def test_luecke_zaehlt_sofort_und_im_fenster():
    uhr = _Uhr()
    m = LevelMeter(44100, clock=uhr)
    assert m.snapshot().luecken == 0 and m.snapshot().luecken_10s == 0
    m.luecke()
    uhr.t += 1.0
    m.luecke()
    s = m.snapshot()
    assert (s.luecken, s.luecken_10s) == (2, 2)
    # Ein Chunk spaeter bleiben beide Zahlen stehen ...
    uhr.t += 0.02
    m.on_chunk(np.zeros(1024, dtype=np.float32))
    assert (m.snapshot().luecken, m.snapshot().luecken_10s) == (2, 2)
    # ... nach Ablauf des Fensters faellt nur das Fenster.
    uhr.t += LUECKEN_FENSTER_S + 0.1
    m.on_chunk(np.zeros(1024, dtype=np.float32))
    assert (m.snapshot().luecken, m.snapshot().luecken_10s) == (2, 0)


def test_reset_leert_die_luecken():
    m = LevelMeter(44100, clock=_Uhr())
    m.luecke()
    m.reset()
    assert (m.snapshot().luecken, m.snapshot().luecken_10s) == (0, 0)


# ── Warnungs-Hook ────────────────────────────────────────────────────────────

def test_hook_zaehlt_im_eigenen_thread_und_laesst_fremdes_durch():
    cap = C.AudioCapture()
    fremd = []
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.showwarning = lambda msg, *a, **k: fremd.append(str(msg))
        C._luecken_hook_installieren()
        C._luecken_hook_installieren()   # idempotent: kein doppelter Wrapper

        def capture_thread():
            C._tls.capture = cap
            try:
                _warnen()
                warnings.warn("etwas anderes", RuntimeWarning)
            finally:
                C._tls.capture = None

        t = threading.Thread(target=capture_thread)
        t.start()
        t.join()
        _warnen()   # Hauptthread: kein Capture -> unveraendert weiter
    assert cap.snapshot().luecken == 1
    assert fremd == ["etwas anderes", "data discontinuity in recording"]


# ── _run: Puffer-Reserve + Zuordnung ─────────────────────────────────────────

class _Rec:
    def __init__(self, cap):
        self.cap = cap
        self.n = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def record(self, numframes):
        self.n += 1
        if self.n == 1:
            _warnen()
        else:
            self.cap._running = False
        return np.zeros((numframes, 1), dtype=np.float32)


def test_run_puffer_reserve_und_luecke(monkeypatch):
    cap = C.AudioCapture()
    gesehen = {}

    def recorder(samplerate, channels, blocksize):
        gesehen["blocksize"] = blocksize
        return _Rec(cap)

    mic = SimpleNamespace(recorder=recorder)
    monkeypatch.setattr(C, "sc", SimpleNamespace(get_microphone=lambda *a, **k: mic),
                        raising=False)
    cap.source_mode = "input"
    cap._device_name = "Testgeraet"
    cap._running = True
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        cap._run(epoch=cap._epoch)
    assert cap.snapshot().luecken == 1
    assert getattr(C._tls, "capture", None) is None
    if C.sys.platform == "win32":
        assert gesehen["blocksize"] > C.CHUNK_SIZE
    else:
        assert gesehen["blocksize"] == C.CHUNK_SIZE


# ── Chip + Statuszeile ───────────────────────────────────────────────────────

def _cap(**kw):
    base = dict(rms_dbfs_300ms=-18.0, rms_dbfs_1s=-18.0, peak_dbfs=-6.0, peak_hold_dbfs=-6.0,
                chunk_ms_p95=24.0, chunks=500, running=True)
    base.update(kw)
    return CaptureSnapshot(**base)


def test_luecke_setzt_aussetzer_chip():
    assert chips(_cap(), None) == set()
    assert chips(_cap(luecken_10s=1, luecken=1), None) == {"JITTER"}
    # Alte Luecken (ausserhalb des Fensters) halten den Chip nicht.
    assert chips(_cap(luecken_10s=0, luecken=7), None) == set()


def test_statuszeile_nennt_die_luecken():
    m = MgrState(kind="input", device_label="USB Audio CODEC", bpm=128.0)
    line = status_line(_cap(luecken_10s=3, luecken=3), None, m, None, 0)
    assert line.key == "jitter"
    assert "3 Datenlücken in 10 s" in line.text
    eins = status_line(_cap(luecken_10s=1, luecken=1), None, m, None, 0)
    assert "1 Datenlücke in 10 s" in eins.text
