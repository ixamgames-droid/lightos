"""BPM-11 (S6): AudioRecorder — 30 s Eingang als WAV PCM16 + Sidecar-JSON.

Fake-Capture speist Chunks schnell ein; geschrieben wird ausschliesslich unter
``tmp_path`` (base_dir bzw. umgebogenes ``app_data_dir``), nie in den echten
Datenordner.
"""
from __future__ import annotations

import json
import os
import threading
import time
import wave

import numpy as np
import pytest

from src.core.audio import audio_recorder as ar
from src.core.audio.audio_recorder import AudioRecorder
from src.core.audio.level_meter import CaptureSnapshot

CHUNK = 1024
PFLICHT = ("version", "zeit_utc", "dauer_s", "sample_rate", "quelle", "geraet", "rms_dbfs",
           "peak_dbfs", "clip_samples", "abgebrochen", "datei")


class FakeCap:
    def __init__(self, sr=44100):
        self.sr = sr
        self.subs: list = []
        self.running = True
        self.source_mode = "input"

    def subscribe(self, cb):
        if cb not in self.subs:
            self.subs.append(cb)

    def unsubscribe(self, cb):
        if cb in self.subs:
            self.subs.remove(cb)

    def is_running(self):
        return self.running

    def snapshot(self):
        return CaptureSnapshot(sample_rate=self.sr, running=self.running, device="USB Audio CODEC",
                               source_mode=self.source_mode, chunk_ms_p95=23.0)

    def feed(self, seconds, amp=0.25):
        n = int(seconds * self.sr / CHUNK) + 1
        t = np.arange(CHUNK) / self.sr
        x = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        for _ in range(n):
            for cb in list(self.subs):
                cb(x)


class FakeDet:
    def snapshot(self):
        class S:
            hum_ratio, hum_hz, state, bpm, confidence, backlog_ms = 0.12, 50, "locked", 128.0, 0.8, 4.0
        return S()


def _rec(tmp_path, cap, **kw):
    done = threading.Event()
    got: list = []

    def fin(p):
        got.append(p)
        done.set()
    r = AudioRecorder(capture=cap, detector=FakeDet(), base_dir=str(tmp_path), on_finished=fin, **kw)
    return r, done, got


def _dateien(tmp_path):
    d = tmp_path / "audio_diag"
    return sorted(os.listdir(d)) if d.exists() else []


def test_30s_wav_und_json(tmp_path):
    cap = FakeCap()
    r, done, got = _rec(tmp_path, cap)
    assert r.start(30) is True
    cap.feed(31.0)
    assert done.wait(10.0)
    assert not r.is_running()
    wav_path = got[0]
    assert os.path.dirname(wav_path) == str(tmp_path / "audio_diag")
    assert os.path.basename(wav_path).startswith("lightos_eingang_")
    with wave.open(wav_path, "rb") as wf:
        assert wf.getframerate() == 44100
        assert wf.getsampwidth() == 2
        assert wf.getnchannels() == 1
        dauer = wf.getnframes() / wf.getframerate()
    assert abs(dauer - 30.0) <= 0.1
    files = _dateien(tmp_path)
    assert len([f for f in files if f.endswith(".wav")]) == 1
    assert len([f for f in files if f.endswith(".json")]) == 1
    info = json.loads(open(os.path.splitext(wav_path)[0] + ".json", encoding="utf-8").read())
    for k in PFLICHT:
        assert k in info, k
    assert info["abgebrochen"] is False
    assert info["sample_rate"] == 44100
    assert abs(info["dauer_s"] - 30.0) <= 0.1
    assert info["hum_ratio"] == 0.12
    assert -16.0 < info["rms_dbfs"] < -14.0          # Sinus 0,25 -> −15,05 dBFS
    assert info["datei"] == "audio_diag/" + os.path.basename(wav_path)
    assert "T" in info["zeit_utc"] and info["zeit_utc"].endswith("+00:00")
    text = json.dumps(info)
    assert str(tmp_path) not in text and os.path.expanduser("~") not in text
    assert r.progress_s() == pytest.approx(30.0, abs=0.1)
    assert cap.subs == []                              # abgemeldet


def test_zweiter_start_waehrend_lauf_false(tmp_path):
    cap = FakeCap()
    r, done, _ = _rec(tmp_path, cap)
    assert r.start(30) is True
    assert r.start(30) is False
    assert len(cap.subs) == 1
    r.cancel()
    assert done.wait(5.0)


def test_cancel_kuerzere_datei_und_abgebrochen(tmp_path):
    cap = FakeCap()
    r, done, got = _rec(tmp_path, cap)
    r.start(30)
    cap.feed(5.0)
    t0 = time.monotonic()
    while r.progress_s() < 4.9 and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    r.cancel()
    assert done.wait(5.0)
    with wave.open(got[0], "rb") as wf:
        dauer = wf.getnframes() / wf.getframerate()
    assert 4.9 <= dauer < 30.0
    info = json.loads(open(os.path.splitext(got[0])[0] + ".json", encoding="utf-8").read())
    assert info["abgebrochen"] is True
    assert info["dauer_s"] == pytest.approx(dauer, abs=0.01)
    assert len(_dateien(tmp_path)) == 2


def test_capture_stop_beendet_sauber(tmp_path):
    cap = FakeCap()
    r, done, got = _rec(tmp_path, cap)
    r.start(30)
    cap.feed(2.0)
    cap.running = False
    assert done.wait(5.0)
    info = json.loads(open(os.path.splitext(got[0])[0] + ".json", encoding="utf-8").read())
    assert info["abgebrochen"] is True and info["grund"] == "capture_gestoppt"
    with wave.open(got[0], "rb") as wf:
        assert wf.getnframes() > 0


def test_48000_hz_uebernommen(tmp_path):
    cap = FakeCap(sr=48000)
    r, done, got = _rec(tmp_path, cap)
    r.start(2)
    cap.feed(2.5)
    assert done.wait(5.0)
    with wave.open(got[0], "rb") as wf:
        assert wf.getframerate() == 48000
        assert abs(wf.getnframes() / 48000 - 2.0) <= 0.01
    assert r.last_info["sample_rate"] == 48000


def test_callback_kostet_unter_0_05_ms(tmp_path):
    cap = FakeCap()
    r, done, _ = _rec(tmp_path, cap)
    r.start(30)
    x = np.zeros(CHUNK, np.float32)
    n = 400
    kosten = []
    for _ in range(n):
        t0 = time.perf_counter()
        r._on_chunk(x)
        kosten.append((time.perf_counter() - t0) * 1000.0)
    r.cancel()
    assert done.wait(5.0)
    med = float(np.median(kosten))
    print(f"Callback-Kosten Median {med:.4f} ms, p95 {np.percentile(kosten, 95):.4f} ms")
    assert med < 0.05


def test_pfad_unter_app_data_dir(tmp_path, monkeypatch):
    import src.core.paths as paths
    monkeypatch.setattr(paths, "app_data_dir", lambda: str(tmp_path / "LightOS"))
    cap = FakeCap()
    done = threading.Event()
    got: list = []
    r = AudioRecorder(capture=cap, detector=FakeDet(), on_finished=lambda p: (got.append(p), done.set()))
    r.start(1)
    cap.feed(1.5)
    assert done.wait(5.0)
    assert got[0].startswith(str(tmp_path / "LightOS" / "audio_diag") + os.sep)


def test_zwei_aufnahmen_gleiche_sekunde_zwei_paare(tmp_path):
    cap = FakeCap()
    for _ in range(2):
        r, done, _ = _rec(tmp_path, cap)
        r.start(0.5)
        cap.feed(0.6)
        assert done.wait(5.0)
    files = _dateien(tmp_path)
    assert len(files) == 4 and len({os.path.splitext(f)[0] for f in files}) == 2


def test_version_ermittelbar():
    assert ar._lightos_version()


def _offen(pfad: str) -> int:
    """Wie viele Datei-Handles dieses Prozesses zeigen auf ``pfad`` (Linux /proc; sonst 0)."""
    fd_dir = "/proc/self/fd"
    if not os.path.isdir(fd_dir):
        return 0
    ziel, n = os.path.realpath(pfad), 0
    for fd in os.listdir(fd_dir):
        try:
            n += os.readlink(os.path.join(fd_dir, fd)) == ziel
        except OSError:
            pass
    return n


@pytest.mark.parametrize("ende", ["cancel", "capture_stop"])
def test_wav_ist_beim_callback_schon_geschlossen_und_gueltig(tmp_path, ende):
    """on_finished meldet eine FERTIGE Datei: Header mit Frame-Zahl, Groesse passt —
    auch bei Abbruch (die View zeigt „Aufnahme abgebrochen — Datei …" sofort an)."""
    cap = FakeCap()
    beim_callback: list = []
    done = threading.Event()

    def fin(p):
        offen = _offen(p)                     # vor dem eigenen Lesen zaehlen
        with wave.open(p, "rb") as wf:
            beim_callback.append((wf.getnframes(), os.path.getsize(p), offen))
        done.set()
    r = AudioRecorder(capture=cap, detector=FakeDet(), base_dir=str(tmp_path), on_finished=fin)
    r.start(30)
    cap.feed(2.0)
    t0 = time.monotonic()
    while r.progress_s() < 1.9 and time.monotonic() - t0 < 5:
        time.sleep(0.01)
    if ende == "cancel":
        r.cancel()
    else:
        cap.running = False
    assert done.wait(5.0)
    frames, groesse, offen = beim_callback[0]
    assert frames >= int(1.9 * cap.sr)
    assert groesse == 44 + 2 * frames
    assert offen == 0, "WAV-Datei noch offen (Handle nicht geschlossen)"
